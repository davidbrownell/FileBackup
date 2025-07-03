# ----------------------------------------------------------------------
# |
# |  Offsite.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-07-04 11:06:08
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""\
Copies content to an offsite location: a snapshot is saved after the initial backup and
deltas are applied to that snapshot for subsequent backups.
"""

import datetime
import itertools
import json
import os
import re
import shutil
import sys
import textwrap
import threading
import uuid

from contextlib import contextmanager
from dataclasses import dataclass
from enum import auto, Enum
from io import StringIO
from pathlib import Path
from typing import Any, Callable, cast, Iterator, Pattern

from dbrownell_Common.ContextlibEx import ExitStack
from dbrownell_Common import ExecuteTasks
from dbrownell_Common.InflectEx import inflect
from dbrownell_Common import PathEx
from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags
from dbrownell_Common import SubprocessEx
from dbrownell_Common import TextwrapEx

from FileBackup.DataStore.FileSystemDataStore import FileSystemDataStore
from FileBackup.DataStore.Interfaces.BulkStorageDataStore import BulkStorageDataStore
from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore
from FileBackup.Impl import Common
from FileBackup.Snapshot import Snapshot


# ----------------------------------------------------------------------
# |
# |  Public Types
# |
# ----------------------------------------------------------------------
DEFAULT_ARCHIVE_VOLUME_SIZE = 250 * 1024 * 1024  # 250MB

INDEX_FILENAME = "index.json"
INDEX_HASH_FILENAME = f"{INDEX_FILENAME}.hash"

ARCHIVE_FILENAME = "data.7z"
DELTA_SUFFIX = ".delta"


# ----------------------------------------------------------------------
@dataclass(frozen=True)
class SnapshotFilenames:
    """Filenames used to store snapshot information."""

    backup_name: str
    standard: Path
    pending: Path

    # ----------------------------------------------------------------------
    @classmethod
    def Create(
        cls,
        backup_name: str,
    ) -> "SnapshotFilenames":
        snapshot_filename = PathEx.GetUserDirectory() / f"OffsiteFileBackup.{backup_name}.json"

        return cls(
            backup_name,
            snapshot_filename,
            snapshot_filename.parent / f"{snapshot_filename.stem}.__pending__{snapshot_filename.suffix}",
        )


# ----------------------------------------------------------------------
# |
# |  Public Functions
# |
# ----------------------------------------------------------------------
def Backup(
    dm: DoneManager,
    backup_name: str,
    destination: str | None,
    input_filenames_or_dirs: list[Path],
    encryption_password: str | None,
    working_dir: Path,
    *,
    ssd: bool,
    force: bool,
    quiet: bool,
    file_includes: list[Pattern] | None,
    file_excludes: list[Pattern] | None,
    compress: bool,
    archive_volume_size: int = DEFAULT_ARCHIVE_VOLUME_SIZE,
    ignore_pending_snapshot: bool = False,
    commit_pending_snapshot: bool = True,
) -> None:
    # Process the inputs
    for input_filename_or_dir in input_filenames_or_dirs:
        if not input_filename_or_dir.exists():
            raise Exception(f"'{input_filename_or_dir}' is not a valid filename or directory.")

    if compress or encryption_password:
        zip_binary = _GetZipBinary()
    else:
        zip_binary = None

    snapshot_filenames = SnapshotFilenames.Create(backup_name)

    if snapshot_filenames.pending.is_file():
        if not ignore_pending_snapshot:
            dm.WriteError(
                textwrap.dedent(
                    f"""\

                    A pending snapshot exists for the backup '{backup_name}'; this snapshot should be committed before creating updates
                    to the backup.

                    To commit the pending snapshot, run this script with the 'commit' command.

                    To ignore this error and delete the pending snapshot, run this script with the '--ignore-pending-snapshot'
                    argument.


                    """,
                ),
            )

            return

        snapshot_filenames.pending.unlink()

    elif ignore_pending_snapshot:
        dm.WriteError(
            f"A pending snapshot for '{snapshot_filenames.backup_name}' was not found.\n",
        )
        return

    # Create the local snapshot
    with dm.Nested("Creating the local snapshot...") as local_dm:
        local_snapshot = Snapshot.Calculate(
            local_dm,
            input_filenames_or_dirs,
            FileSystemDataStore(),
            run_in_parallel=ssd,
            quiet=quiet,
            filter_filename_func=Common.CreateFilterFunc(file_includes, file_excludes),
        )

        if local_dm.result != 0:
            return

    if force or not snapshot_filenames.standard.is_file():
        force = True

        offsite_snapshot = Snapshot(
            Snapshot.Node(
                None,
                None,
                Common.DirHashPlaceholder(explicitly_added=False),
                None,
            ),
        )
    else:
        with dm.Nested("\nReading the most recent offsite snapshot...") as destination_dm:
            offsite_snapshot = Snapshot.LoadPersisted(
                destination_dm,
                FileSystemDataStore(),
                snapshot_filename=snapshot_filenames.standard,
            )

            if destination_dm.result != 0:
                return

    # Calculate the differences
    diffs: dict[Common.DiffOperation, list[Common.DiffResult]] = Common.CalculateDiffs(
        dm,
        local_snapshot,
        offsite_snapshot,
    )

    if not any(diff_items for diff_items in diffs.values()):
        return

    # Capture all of the changes in a temp directory
    now = datetime.datetime.now()

    file_content_root = (
        working_dir
        / f"{now.year:04}.{now.month:02}.{now.day:02}.{now.hour:02}.{now.minute:02}.{now.second:02}-{now.microsecond:06}{DELTA_SUFFIX if not force else ''}"
    )

    file_content_root.mkdir(parents=True)
    file_content_data_store = FileSystemDataStore(file_content_root)

    # ----------------------------------------------------------------------
    def OnExit():
        if destination is None:
            template = textwrap.dedent(
                f"""\


                Content has been written to '{{}}',
                however the changes have not been committed yet.

                After the generated content is transferred to an offsite location, run this script
                again with the 'commit' command using the backup name '{backup_name}' to ensure that
                these changes are not processed when this offsite backup is run again.


                """,
            )

        elif dm.result == 0:
            shutil.rmtree(file_content_root)
            return

        else:
            if dm.result < 0:
                type_desc = "errors"
            elif dm.result > 0:
                type_desc = "warnings"
            else:
                assert False, dm.result  # pragma: no cover

            template = f"The temporary directory '{{}}' was preserved due to {type_desc}."

        dm.WriteInfo(
            "\n"
            + template.format(
                (
                    file_content_root
                    if dm.capabilities.is_headless
                    else TextwrapEx.CreateAnsiHyperLink(
                        f"file:///{working_dir.as_posix()}",
                        str(working_dir),
                    )
                ),
            ),
        )

    # ----------------------------------------------------------------------

    with ExitStack(OnExit):
        with dm.Nested(
            "Preparing file content...",
            suffix="\n",
        ) as prepare_dm:
            if diffs[Common.DiffOperation.add] or diffs[Common.DiffOperation.modify]:
                # Create a lookup for the hash values of all existing files at the offsite.
                # We will use this information to only copy those files that do not already
                # exist at the offsite.
                offsite_file_lookup: set[str] = set()

                for node in offsite_snapshot.node.Enum():
                    if not node.is_file:
                        continue

                    assert isinstance(node.hash_value, str), node.hash_value
                    offsite_file_lookup.add(node.hash_value)

                # Gather all the diffs associated with the files that need to be transferred
                diffs_to_process: list[Common.DiffResult] = []

                for diff in itertools.chain(
                    diffs[Common.DiffOperation.add],
                    diffs[Common.DiffOperation.modify],
                ):
                    if not diff.path.is_file():
                        continue

                    assert isinstance(diff.this_hash, str), diff.this_hash
                    if diff.this_hash in offsite_file_lookup:
                        continue

                    diffs_to_process.append(diff)
                    offsite_file_lookup.add(diff.this_hash)

                if diffs_to_process:
                    # Calculate the size requirements
                    Common.ValidateSizeRequirements(
                        prepare_dm,
                        file_content_data_store,
                        file_content_data_store,
                        diffs_to_process,
                    )

                    if prepare_dm.result != 0:
                        return

                    # Preserve the files
                    with prepare_dm.Nested("\nPreserving files...") as preserve_dm:
                        # ----------------------------------------------------------------------
                        def PrepareTask(
                            context: Any,
                            on_simple_status_func: Callable[  # pylint: disable=unused-argument
                                [str], None
                            ],
                        ) -> tuple[int, ExecuteTasks.TransformTasksExTypes.TransformFuncType]:
                            diff = cast(Common.DiffResult, context)
                            del context

                            # ----------------------------------------------------------------------
                            def TransformTask(
                                status: ExecuteTasks.Status,
                            ) -> Path:
                                if not diff.path.is_file():
                                    raise Exception(f"The file '{diff.path}' was not found.")

                                assert isinstance(diff.this_hash, str), diff.this_hash
                                dest_filename = (
                                    Path(diff.this_hash[:2]) / diff.this_hash[2:4] / diff.this_hash
                                )

                                Common.WriteFile(
                                    file_content_data_store,
                                    diff.path,
                                    dest_filename,
                                    lambda bytes_written: cast(None, status.OnProgress(bytes_written, None)),
                                )

                                return dest_filename

                            # ----------------------------------------------------------------------

                            content_size = 0
                            if diff.path.is_file():
                                content_size = diff.path.stat().st_size

                            return content_size, TransformTask

                        # ----------------------------------------------------------------------

                        ExecuteTasks.TransformTasksEx(
                            preserve_dm,
                            "Processing",
                            [ExecuteTasks.TaskData(str(diff.path), diff) for diff in diffs_to_process],
                            PrepareTask,
                            quiet=quiet,
                            max_num_threads=(None if file_content_data_store.ExecuteInParallel() else 1),
                            refresh_per_second=Common.EXECUTE_TASKS_REFRESH_PER_SECOND,
                        )

                        if preserve_dm.result != 0:
                            return

            with prepare_dm.Nested(
                "\nPreserving index...",
                suffix="\n",
            ):
                index_filename_path = Path(INDEX_FILENAME)

                with file_content_data_store.Open(index_filename_path, "w") as f:
                    json_diffs: list[dict[str, Any]] = []

                    for these_diffs in diffs.values():
                        these_diffs.sort(key=lambda value: str(value.path))

                        for diff in these_diffs:
                            json_diffs.append(diff.ToJson())

                    json.dump(json_diffs, f)

                with file_content_data_store.Open(Path(INDEX_HASH_FILENAME), "w") as f:
                    f.write(
                        Common.CalculateHash(
                            file_content_data_store,
                            index_filename_path,
                            lambda _: None,
                        ),
                    )

            if encryption_password and compress:
                heading = "Compressing and encrypting..."
                encryption_arg = f' "-p{encryption_password}"'
                compression_level = 9
            elif encryption_password:
                heading = "Encrypting..."
                encryption_arg = f' "-p{encryption_password}"'
                compression_level = 0
            elif compress:
                heading = "Compressing..."
                encryption_arg = ""
                compression_level = 9
            else:
                heading = None
                encryption_arg = None
                compression_level = None

            if heading:
                with prepare_dm.Nested(
                    heading,
                    suffix="\n",
                ) as zip_dm:
                    assert zip_binary is not None

                    command_line = f'{zip_binary} a -t7z -mx{compression_level} -ms=on -mhe=on -sccUTF-8 -scsUTF-8 -ssw -v{archive_volume_size} "{ARCHIVE_FILENAME}" {encryption_arg}'

                    zip_dm.WriteVerbose(f"Command Line: {_ScrubZipCommandLine(command_line)}\n\n")

                    with zip_dm.YieldStream() as stream:
                        zip_dm.result = SubprocessEx.Stream(
                            command_line,
                            stream,
                            cwd=file_content_root,
                        )

                        if zip_dm.result != 0:
                            return

                with prepare_dm.Nested(
                    "Validating archive...",
                    suffix="\n",
                ) as validate_dm:
                    assert zip_binary is not None

                    command_line = (
                        f'{zip_binary} t "{file_content_root / ARCHIVE_FILENAME}.001"{encryption_arg}'
                    )

                    validate_dm.WriteVerbose(f"Command Line: {_ScrubZipCommandLine(command_line)}\n\n")

                    with validate_dm.YieldStream() as stream:
                        validate_dm.result = SubprocessEx.Stream(command_line, stream)

                        if validate_dm.result != 0:
                            return

                with prepare_dm.Nested("Cleaning content...") as clean_dm:
                    for item in file_content_root.iterdir():
                        if item.name.startswith(ARCHIVE_FILENAME):
                            continue

                        with clean_dm.VerboseNested(f"Removing '{item}'..."):
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                            else:
                                assert False, item  # pragma: no cover

        if not destination:
            with dm.Nested("Preserving the pending snapshot...") as pending_dm:
                local_snapshot.Persist(
                    pending_dm,
                    FileSystemDataStore(snapshot_filenames.pending),
                    snapshot_filename=snapshot_filenames.pending,
                )

                if pending_dm.result != 0:
                    return

            return

        with Common.YieldDataStore(
            dm,
            destination,
            ssd=ssd,
        ) as destination_data_store:
            if isinstance(destination_data_store, BulkStorageDataStore):
                _CommitBulkStorageDataStore(
                    dm,
                    file_content_data_store,
                    destination_data_store,
                )
            elif isinstance(destination_data_store, FileBasedDataStore):
                _CommitFileBasedDataStore(
                    dm,
                    snapshot_filenames,
                    file_content_data_store,
                    destination_data_store,
                    quiet=quiet,
                    ssd=ssd,
                )
            else:
                assert False, destination_data_store  # pragma: no cover

            if dm.result != 0:
                return

            if commit_pending_snapshot:
                with dm.Nested("Committing snapshot locally...") as commit_dm:
                    local_snapshot.Persist(
                        commit_dm,
                        FileSystemDataStore(snapshot_filenames.standard.parent),
                        snapshot_filename=snapshot_filenames.standard,
                    )


# ----------------------------------------------------------------------
def Commit(
    dm: DoneManager,
    backup_name: str,
) -> None:
    snapshot_filenames = SnapshotFilenames.Create(backup_name)

    if not snapshot_filenames.pending.is_file():
        dm.WriteError(f"A pending snapshot for the backup '{backup_name}' was not found.\n")
        return

    with dm.Nested(f"Committing the pending snapshot for the backup '{backup_name}'..."):
        snapshot_filenames.standard.unlink(missing_ok=True)
        shutil.move(snapshot_filenames.pending, snapshot_filenames.standard)


# ----------------------------------------------------------------------
def Restore(
    dm: DoneManager,
    backup_name: str,
    data_store_connection_string: str,
    encryption_password: str | None,
    working_dir: Path,
    dir_substitutions: dict[str, str],
    *,
    ssd: bool,
    quiet: bool,
    dry_run: bool,
    overwrite: bool,
    continue_on_errors: bool = False,
) -> None:
    with Common.YieldDataStore(
        dm,
        data_store_connection_string,
        ssd=ssd,
    ) as data_store:
        if not isinstance(data_store, FileBasedDataStore):
            dm.WriteError(
                textwrap.dedent(
                    f"""\
                    '{data_store_connection_string}' does not resolve to a file-based data store, which is required when restoring content.

                    Most often, this error is encountered when attempting to restore an offsite backup that was
                    originally transferred to a cloud-based data store.

                    To restore these types of offsite backups, copy the content from the original data store
                    to your local file system and run this script again while pointing to that
                    location on your file system. This local directory should contain the primary directory
                    created during the initial backup and all directories created as a part of subsequent backups.

                    """,
                ),
            )
            return

        with _YieldTempDirectory(working_dir / "staging", "staging content") as staging_directory:
            # ----------------------------------------------------------------------
            @dataclass(frozen=True)
            class Instruction:
                # ----------------------------------------------------------------------
                operation: Common.DiffOperation
                file_content_path: Path | None
                original_filename: str
                local_filename: Path

                # ----------------------------------------------------------------------
                def __post_init__(self):
                    assert self.file_content_path is None or self.operation in [
                        Common.DiffOperation.add,
                        Common.DiffOperation.modify,
                    ]

            # ----------------------------------------------------------------------

            instructions: dict[str, list[Instruction]] = {}

            # ----------------------------------------------------------------------
            def CountInstructions() -> int:
                total = 0

                for these_instructions in instructions.values():
                    total += len(these_instructions)

                return total

            # ----------------------------------------------------------------------

            with dm.Nested(
                "Processing file content...",
                lambda: "{} found".format(inflect.no("instruction", CountInstructions())),
            ) as preprocess_dm:
                backup_name_path = Path(backup_name)

                if data_store.GetItemType(backup_name_path) == Common.ItemType.Dir:
                    data_store.SetWorkingDir(backup_name_path)

                # We should have a bunch of dirs organized by datetime
                offsite_directories: dict[str, list[tuple[str, bool]]] = {}

                for _, directories, filenames in data_store.Walk():
                    if filenames:
                        preprocess_dm.WriteError(
                            textwrap.dedent(
                                """\
                                Files were not expected:

                                {}

                                """,
                            ).format("\n".join(f"    - {filename}" for filename in filenames)),
                        )
                        return

                    dir_regex = re.compile(
                        textwrap.dedent(
                            r"""(?#
                            Year                )(?P<year>\d{{4}})(?#
                            Month               )\.(?P<month>\d{{2}})(?#
                            Day                 )\.(?P<day>\d{{2}})(?#
                            Hour                )\.(?P<hour>\d{{2}})(?#
                            Minute              )\.(?P<minute>\d{{2}})(?#
                            Second              )\.(?P<second>\d{{2}})(?#
                            Index               )-(?P<index>\d+)(?#
                            Suffix              )(?P<suffix>{})?(?#
                            )""",
                        ).format(re.escape(DELTA_SUFFIX)),
                    )

                    for directory in directories:
                        match = dir_regex.match(directory)
                        if not match:
                            preprocess_dm.WriteError(f"'{directory}' is not a recognized directory name.\n")
                            return

                        offsite_directories.setdefault(directory, []).append(
                            (
                                directory,
                                not match.group("suffix"),
                            ),
                        )

                    # Only process top-level items
                    break

                if not offsite_directories:
                    preprocess_dm.WriteError("No directories were found.\n")
                    return

                # Sort the directories
                keys = list(offsite_directories.keys())
                keys.sort()

                all_directories: list[tuple[str, bool]] = []

                for key in keys:
                    all_directories += offsite_directories[key]

                # Ensure that we start processing at the latest primary directory
                primary_indexes: list[int] = []

                for index, (directory, is_primary) in enumerate(all_directories):
                    if is_primary:
                        primary_indexes.append(index)

                if not primary_indexes:
                    preprocess_dm.WriteError("No primary directories were found.\n")
                    return

                if len(primary_indexes) > 1:
                    preprocess_dm.WriteError(
                        textwrap.dedent(
                            """\
                            Multiple primary directories were found.

                            {}

                            """,
                        ).format(
                            "\n".join(
                                f"    - {all_directories[primary_index][0]}"
                                for primary_index in primary_indexes
                            ),
                        ),
                    )
                    return

                directories = [data[0] for data in all_directories[primary_indexes[-1] :]]

                # Process each directory

                # ----------------------------------------------------------------------
                class ProcessDirectoryState(Enum):
                    Transferring = 0
                    Extracting = auto()
                    Verifying = auto()
                    Moving = auto()

                # ----------------------------------------------------------------------
                def PrepareTask(
                    context: Any,
                    on_simple_status_func: Callable[[str], None],  # pylint: disable=unused-argument
                ) -> tuple[int, ExecuteTasks.TransformTasksExTypes.TransformFuncType]:
                    directory = cast(str, context)
                    del context

                    # ----------------------------------------------------------------------
                    def ExecuteTask(
                        status: ExecuteTasks.Status,
                    ) -> ExecuteTasks.TransformResultComplete:
                        # This function will create the following directory structure:
                        #
                        #  <working_dir>
                        #    └── <directory>
                        #      └── transferred          (temporary)
                        #      └── decompressed         (temporary)
                        #      └── final

                        sink = StringIO()

                        with DoneManager.Create(
                            sink,
                            "",
                            line_prefix="",
                            flags=DoneManagerFlags.Create(verbose=dm.is_verbose, debug=dm.is_debug),
                        ) as dm_sink:
                            assert working_dir is not None
                            this_working_dir = working_dir / directory
                            final_dir = this_working_dir / "final"

                            if final_dir.is_dir():
                                # The destination already exists, no need to process it further
                                return ExecuteTasks.TransformResultComplete(final_dir, 0)

                            with _YieldTransferredArchive(
                                data_store,  # type: ignore
                                directory,
                                this_working_dir / "transferred",
                                lambda bytes_transferred: cast(
                                    None,
                                    status.OnProgress(
                                        ProcessDirectoryState.Transferring.value + 1,
                                        bytes_transferred,
                                    ),
                                ),
                            ) as (transferred_dir, transferred_dir_is_temporary):
                                with _YieldDecompressedFiles(
                                    dm_sink,
                                    transferred_dir,
                                    this_working_dir / "decompressed",
                                    directory,
                                    encryption_password,
                                    lambda message: cast(
                                        None,
                                        status.OnProgress(
                                            ProcessDirectoryState.Extracting.value + 1,
                                            message,
                                        ),
                                    ),
                                    continue_on_errors=continue_on_errors,
                                ) as (decompressed_dir, decompressed_dir_is_temporary):
                                    # Validate the contents
                                    _VerifyFiles(
                                        dm_sink,
                                        directory,
                                        decompressed_dir,
                                        lambda message: cast(
                                            None,
                                            status.OnProgress(
                                                ProcessDirectoryState.Verifying.value + 1,
                                                message,
                                            ),
                                        ),
                                        continue_on_errors=continue_on_errors,
                                    )

                                    # Move/Copy the content. Note that the code assumes a flat
                                    # directory structure and doesn't do anything to account for
                                    # nested dirs. This assumption matches the current archive
                                    # format.
                                    if transferred_dir_is_temporary or decompressed_dir_is_temporary:
                                        func = cast(Callable[[Path, Path], None], shutil.move)
                                    else:
                                        # ----------------------------------------------------------------------
                                        def CreateSymLink(
                                            source: Path,
                                            dest: Path,
                                        ) -> None:
                                            dest /= source.name
                                            os.symlink(source, dest, target_is_directory=source.is_dir())

                                        # ----------------------------------------------------------------------

                                        func = CreateSymLink

                                    temp_dest_dir = final_dir.parent / (final_dir.name + "__temp__")

                                    shutil.rmtree(temp_dest_dir, ignore_errors=True)
                                    temp_dest_dir.mkdir(parents=True)

                                    items = [
                                        item
                                        for item in decompressed_dir.iterdir()
                                        if item.name != INDEX_HASH_FILENAME
                                    ]

                                    for item_index, item in enumerate(items):
                                        status.OnProgress(
                                            ProcessDirectoryState.Moving.value + 1,
                                            f"Moving {item_index + 1} of {len(items)}...",
                                        )

                                        if item.exists():
                                            func(item, temp_dest_dir)

                                    shutil.move(temp_dest_dir, final_dir)

                        if dm_sink.result != 0:
                            status.Log(sink.getvalue())

                        return ExecuteTasks.TransformResultComplete(final_dir, dm_sink.result)

                    # ----------------------------------------------------------------------

                    return len(ProcessDirectoryState), ExecuteTask

                # ----------------------------------------------------------------------

                directory_working_dirs: list[object | None | Exception] = ExecuteTasks.TransformTasksEx(
                    preprocess_dm,
                    "Processing",
                    [ExecuteTasks.TaskData(str(directory), directory) for directory in directories],
                    PrepareTask,
                    quiet=quiet,
                    max_num_threads=None if ssd and data_store.ExecuteInParallel() else 1,
                    refresh_per_second=Common.EXECUTE_TASKS_REFRESH_PER_SECOND,
                )

                # Allow the process to continue if warnings were encountered
                if preprocess_dm.result < 0:
                    return

                assert all(isinstance(working_dir, Path) for working_dir in directory_working_dirs), (
                    directory_working_dirs
                )

                with preprocess_dm.Nested("Staging working content...") as stage_dm:
                    # ----------------------------------------------------------------------
                    def HashToFilename(
                        hash_value: str,
                    ) -> Path:
                        return staging_directory / hash_value[:2] / hash_value[2:4] / hash_value

                    # ----------------------------------------------------------------------
                    def PathToFilename(
                        path: str,
                    ) -> Path:
                        for source_text, dest_text in dir_substitutions.items():
                            path = path.replace(source_text, dest_text)

                        return Path(path)

                    # ----------------------------------------------------------------------

                    file_hashes: set[str] = set()

                    for index, (directory, directory_working_dir) in enumerate(
                        zip(directories, directory_working_dirs)
                    ):
                        assert isinstance(directory_working_dir, Path), directory_working_dir

                        these_instructions: list[Instruction] = []

                        with stage_dm.Nested(
                            f"Processing '{directory}' ({index + 1} of {len(directories)})...",
                            lambda: "{} added".format(inflect.no("instruction", len(these_instructions))),
                        ):
                            # link the content
                            for root_str, _, filenames in os.walk(
                                directory_working_dir,
                                followlinks=True,
                            ):
                                root = Path(root_str)

                                if root == directory_working_dir:
                                    continue

                                for filename in filenames:
                                    fullpath = root / filename

                                    dest_filename = staging_directory / fullpath.relative_to(
                                        directory_working_dir
                                    )

                                    if not dest_filename.is_file():
                                        dest_filename.parent.mkdir(parents=True, exist_ok=True)
                                        os.symlink(fullpath, dest_filename)

                            # Read the instructions
                            with (directory_working_dir / INDEX_FILENAME).open() as f:
                                json_content = json.load(f)

                            # TODO: Validate json against a schema

                            for item_index, item in enumerate(json_content):
                                try:
                                    assert "operation" in item, item

                                    if item["operation"] == "add":
                                        hash_value = item.get("this_hash", None)

                                        if hash_value is None:
                                            # We need to create a directory
                                            hash_filename = None
                                        else:
                                            hash_filename = HashToFilename(hash_value)
                                            file_hashes.add(hash_value)

                                        these_instructions.append(
                                            Instruction(
                                                Common.DiffOperation.add,
                                                hash_filename,
                                                item["path"],
                                                PathToFilename(item["path"]),
                                            ),
                                        )

                                    elif item["operation"] == "modify":
                                        if item["other_hash"] not in file_hashes:
                                            raise Exception(
                                                "The original file does not exist in the staged content."
                                            )

                                        new_hash_filename = HashToFilename(item["this_hash"])
                                        file_hashes.add(item["this_hash"])

                                        these_instructions.append(
                                            Instruction(
                                                Common.DiffOperation.modify,
                                                new_hash_filename,
                                                item["path"],
                                                PathToFilename(item["path"]),
                                            ),
                                        )

                                    elif item["operation"] == "remove":
                                        hash_value = item.get("other_hash", None)

                                        if hash_value is not None:
                                            if item["other_hash"] not in file_hashes:
                                                raise Exception(
                                                    "The referenced file does not exist in the staged content."
                                                )

                                        these_instructions.append(
                                            Instruction(
                                                Common.DiffOperation.remove,
                                                None,
                                                item["path"],
                                                PathToFilename(item["path"]),
                                            ),
                                        )

                                    else:
                                        assert False, item["operation"]  # pragma: no cover

                                except Exception as ex:
                                    raise Exception(
                                        textwrap.dedent(
                                            """\
                                            An error was encountered while processing '{}' [Index: {}].

                                                Original Filename:  {}
                                                Error:              {}

                                            """,
                                        ).format(
                                            directory,
                                            item_index,
                                            item["path"],
                                            str(ex),
                                        ),
                                    ) from ex

                        assert these_instructions
                        instructions[directory] = these_instructions

            with dm.Nested("\nProcessing instructions...") as all_instructions_dm:
                all_instructions_dm.WriteLine("")

                temp_directory = working_dir / "instructions"
                temp_directory.mkdir(parents=True, exist_ok=True)

                with ExitStack(lambda: shutil.rmtree(temp_directory)):
                    commit_actions: list[Callable[[], None]] = []

                    # ----------------------------------------------------------------------
                    def WriteImpl(
                        dm: DoneManager,
                        action: str,
                        local_filename: Path,
                        content_filename: Path | None,
                    ) -> None:
                        if content_filename is None:
                            # ----------------------------------------------------------------------
                            def CommitDir() -> None:
                                if local_filename.is_dir():
                                    shutil.rmtree(local_filename)
                                else:
                                    local_filename.unlink(missing_ok=True)

                                local_filename.mkdir(parents=True)

                            # ----------------------------------------------------------------------

                            commit_actions.append(CommitDir)
                            return

                        content_filename = content_filename.resolve()
                        temp_filename = temp_directory / str(uuid.uuid4())

                        if not content_filename.is_file():
                            dm.WriteError(f"The file could not be {action} as its archive data is missing.\n")
                        else:
                            with content_filename.open("rb") as source:
                                with temp_filename.open("wb") as dest:
                                    dest.write(source.read())

                            # ----------------------------------------------------------------------
                            def CommitFile() -> None:
                                if local_filename.is_dir():
                                    shutil.rmtree(local_filename)
                                elif local_filename.is_file():
                                    local_filename.unlink()

                                local_filename.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(temp_filename, local_filename)

                            # ----------------------------------------------------------------------

                            commit_actions.append(CommitFile)

                    # ----------------------------------------------------------------------
                    def OnAddInstruction(
                        dm: DoneManager,
                        instruction: Instruction,
                    ) -> None:
                        if instruction.local_filename.exists() and not overwrite:
                            dm.WriteError(
                                f"The local item '{instruction.local_filename}' exists and will not be overwritten.\n",
                            )
                            return

                        WriteImpl(dm, "restored", instruction.local_filename, instruction.file_content_path)

                    # ----------------------------------------------------------------------
                    def OnModifyInstruction(
                        dm: DoneManager,  # pylint: disable=unused-argument
                        instruction: Instruction,
                    ) -> None:
                        assert instruction.file_content_path is not None
                        WriteImpl(dm, "modified", instruction.local_filename, instruction.file_content_path)

                    # ----------------------------------------------------------------------
                    def OnRemoveInstruction(
                        dm: DoneManager,  # pylint: disable=unused-argument
                        instruction: Instruction,
                    ) -> None:
                        # ----------------------------------------------------------------------
                        def RemoveItem():
                            if instruction.local_filename.is_file():
                                instruction.local_filename.unlink()
                            elif instruction.local_filename.is_dir():
                                shutil.rmtree(instruction.local_filename)

                        # ----------------------------------------------------------------------

                        commit_actions.append(RemoveItem)

                    # ----------------------------------------------------------------------

                    operation_map: dict[
                        Common.DiffOperation,
                        tuple[
                            str,  # Heading prefix
                            Callable[[DoneManager, Instruction], None],
                        ],
                    ] = {
                        Common.DiffOperation.add: ("Restoring", OnAddInstruction),
                        Common.DiffOperation.modify: ("Updating", OnModifyInstruction),
                        Common.DiffOperation.remove: ("Removing", OnRemoveInstruction),
                    }

                    for directory_index, (directory, these_instructions) in enumerate(instructions.items()):
                        with all_instructions_dm.Nested(
                            f"Processing '{directory}' ({directory_index + 1} of {len(instructions)})...",
                            suffix="\n",
                        ) as instructions_dm:
                            with instructions_dm.YieldStream() as stream:
                                stream.write(
                                    textwrap.dedent(
                                        """\

                                        {}
                                        """,
                                    ).format(
                                        TextwrapEx.CreateTable(
                                            [
                                                "Operation",
                                                "Local Location",
                                                "Original Location",
                                            ],
                                            [
                                                [
                                                    f"[{instruction.operation.name.upper()}]",
                                                    str(instruction.local_filename),
                                                    instruction.original_filename,
                                                ]
                                                for instruction in these_instructions
                                            ],
                                            [
                                                TextwrapEx.Justify.Center,
                                                TextwrapEx.Justify.Left,
                                                TextwrapEx.Justify.Left,
                                            ],
                                        ),
                                    ),
                                )

                            if not dry_run:
                                for instruction_index, instruction in enumerate(these_instructions):
                                    prefix, on_instruction_func = operation_map[instruction.operation]

                                    with instructions_dm.Nested(
                                        f"{prefix} the {'file' if instruction.file_content_path is not None else 'directory'} '{instruction.local_filename}' ({instruction_index + 1} of {len(these_instructions)})...",
                                    ) as execute_dm:
                                        on_instruction_func(execute_dm, instruction)

                                        if execute_dm.result != 0 and not continue_on_errors:
                                            break

                                instructions_dm.WriteLine("")

                            if instructions_dm.result != 0:
                                break

                    # Commit
                    with all_instructions_dm.Nested("Committing content..."):
                        for commit_action in commit_actions:
                            commit_action()


# ----------------------------------------------------------------------
# |
# |  Private Functions
# |
# ----------------------------------------------------------------------
# Not using functools.cache here, as we want the function to generate exceptions each time it is
# invoked, but only calculate the results once.
_get_zip_binary_result: str | Exception | None = None
_get_zip_binary_result_lock = threading.Lock()


def _GetZipBinary() -> str:
    global _get_zip_binary_result  # pylint: disable=global-statement

    with _get_zip_binary_result_lock:
        if _get_zip_binary_result is None:
            for binary_name in ["7z", "7zz"]:
                result = SubprocessEx.Run(binary_name)
                if result.returncode != 0:
                    continue

                _get_zip_binary_result = binary_name
                break

            if _get_zip_binary_result is None:
                _get_zip_binary_result = Exception(
                    "7zip is not available for compression and/or encryption; please add it to the path before invoking this script."
                )

    if isinstance(_get_zip_binary_result, Exception):
        raise _get_zip_binary_result

    return _get_zip_binary_result


# ----------------------------------------------------------------------
def _ScrubZipCommandLine(
    command_line: str,
) -> str:
    """Produces a string suitable for display within a log file"""

    return re.sub(
        r'"-p(?P<password>\\\"|[^\"])+\"',
        '"-p*****"',
        command_line,
    )


# ----------------------------------------------------------------------
def _CommitBulkStorageDataStore(
    dm: DoneManager,
    file_content_data_store: FileSystemDataStore,
    destination_data_store: BulkStorageDataStore,
) -> None:
    # We want to include the data-based directory in the upload, so upload the file
    # content root parent rather than the file content root itself.
    destination_data_store.Upload(dm, file_content_data_store.GetWorkingDir().parent)


# ----------------------------------------------------------------------
def _CommitFileBasedDataStore(
    dm: DoneManager,
    snapshot_filenames: SnapshotFilenames,
    file_content_data_store: FileSystemDataStore,
    destination_data_store: FileBasedDataStore,
    *,
    quiet: bool,
    ssd: bool,
) -> None:
    destination_data_store.SetWorkingDir(Path(snapshot_filenames.backup_name))

    # Get the files
    transfer_diffs: list[Common.DiffResult] = []

    for root, _, filenames in file_content_data_store.Walk():
        transfer_diffs += [
            Common.DiffResult(
                Common.DiffOperation.add,
                filename,
                "ignore",
                filename.stat().st_size,
                None,
                None,
            )
            for filename in [root / filename for filename in filenames]
        ]

    Common.ValidateSizeRequirements(
        dm,
        file_content_data_store,
        destination_data_store,
        transfer_diffs,
        header="Validating destination size requirements...",
    )

    if dm.result != 0:
        return

    dm.WriteLine("")

    with dm.Nested(
        "Transferring content to the destination...",
        suffix="\n",
    ) as transfer_dm:
        file_content_root = file_content_data_store.GetWorkingDir()

        # ----------------------------------------------------------------------
        def StripPath(
            path: Path,
            extension: str,
        ) -> Path:
            return (
                Path(file_content_root.name)
                / path.parent.relative_to(file_content_root)
                / (path.name + extension)
            )

        # ----------------------------------------------------------------------

        pending_items = Common.CopyLocalContent(
            transfer_dm,
            destination_data_store,
            transfer_diffs,
            StripPath,
            quiet=quiet,
            ssd=ssd,
        )

        if transfer_dm.result != 0:
            return

        if not any(pending_item for pending_item in pending_items):
            transfer_dm.WriteError("No content was transferred.\n")
            return

    with dm.Nested(
        "Committing content on the destination...",
        suffix="\n",
    ) as commit_dm:
        # ----------------------------------------------------------------------
        def CommitContext(
            context: Any,
            status: ExecuteTasks.Status,  # pylint: disable=unused-argument
        ) -> None:
            fullpath = cast(Path, context)
            del context

            destination_data_store.Rename(fullpath, fullpath.with_suffix(""))

        # ----------------------------------------------------------------------

        ExecuteTasks.TransformTasks(
            commit_dm,
            "Processing",
            [
                ExecuteTasks.TaskData(str(pending_item), pending_item)
                for pending_item in pending_items
                if pending_item
            ],
            CommitContext,
            quiet=quiet,
            max_num_threads=None if destination_data_store.ExecuteInParallel() else 1,
            refresh_per_second=Common.EXECUTE_TASKS_REFRESH_PER_SECOND,
        )

        if commit_dm.result != 0:
            return


# ----------------------------------------------------------------------
@contextmanager
def _YieldTempDirectory(
    temp_directory: Path,
    desc: str,
) -> Iterator[Path]:
    should_delete = True

    try:
        yield temp_directory
    except:
        should_delete = False
        raise
    finally:
        if should_delete:
            if temp_directory.is_dir():
                shutil.rmtree(temp_directory)
        else:
            sys.stderr.write(
                f"**** The temporary directory '{temp_directory}' was preserved due to errors while {desc}.\n",
            )


# ----------------------------------------------------------------------
@contextmanager
def _YieldTransferredArchive(
    data_store: FileBasedDataStore,
    directory: str,
    working_dir: Path,
    status_func: Callable[[str], None],
) -> Iterator[
    tuple[
        Path,
        bool,  # is temporary directory
    ],
]:
    """Transfer content from the data store to the local filesystem."""

    if data_store.is_local_filesystem:
        working_dir = data_store.GetWorkingDir() / directory
        assert working_dir.is_dir(), working_dir

        yield working_dir, False
        return

    status_func("Calculating files to transfer...")

    with _YieldTempDirectory(working_dir, "transferring archive files") as working_dir:
        # Map the remote filenames to local filenames
        filename_map: dict[Path, Path] = {}

        # Don't change the data store's working dir, as multiple threads might be accessing it at
        # the same time. That does make this code a bit more complicated.
        data_store_dir = data_store.GetWorkingDir() / directory

        for root, _, filenames in data_store.Walk(Path(directory)):
            relative_root = root.relative_to(data_store_dir)

            for filename in filenames:
                filename_map[root / filename] = working_dir / relative_root / filename

        if not filename_map:
            raise Exception(f"The directory '{directory}' does not contain any files.")

        # Transfer the files
        for filename_index, (source_filename, dest_filename) in enumerate(filename_map.items()):
            file_size = data_store.GetFileSize(source_filename) or 1

            status_template = f"Transferring '{source_filename}' ({filename_index + 1} of {len(filename_map)}) [{PathEx.GetSizeDisplay(file_size)}] {{:.02f}}%..."

            Common.WriteFile(
                data_store,
                source_filename,
                dest_filename,
                lambda bytes_transferred: status_func(
                    status_template.format((bytes_transferred / file_size) * 100)
                ),
            )

        yield working_dir, True


# ----------------------------------------------------------------------
@contextmanager
def _YieldDecompressedFiles(
    dm: DoneManager,
    transferred_dir: Path,
    decompressed_dir: Path,
    directory_name: str,
    encryption_password: str | None,
    status_func: Callable[[str], None],
    *,
    continue_on_errors: bool,
) -> Iterator[
    tuple[
        Path,
        bool,  # is temporary directory
    ],
]:
    """Decompress the archive if necessary"""

    if (transferred_dir / INDEX_FILENAME).is_file():
        yield transferred_dir, False
        return

    # By default, 7zip will prompt for a password with archives that were created
    # with a password but no password was provided. This is not what we want, as
    # it will block indefinitely. Instead, employ this workaround suggested at
    # https://sourceforge.net/p/sevenzip/discussion/45798/thread/2b98fd92/.
    #
    #   1) Attempt to extract with a bogus password; this will work for archives
    #      created without a password.
    #
    #   2) If extraction fails, issue an error.
    #
    password = encryption_password or str(uuid.uuid4())

    archive_filename = transferred_dir / (ARCHIVE_FILENAME + ".001")

    if not archive_filename.is_file():
        raise Exception(f"The archive file '{archive_filename.name}' was not found.")

    # Validate
    status_func("Validating archive...")
    with dm.Nested("Validating archive...") as validate_dm:
        result = SubprocessEx.Run(f'{_GetZipBinary()} t "{archive_filename}" "-p{password}"')
        if result.returncode != 0:
            message = textwrap.dedent(
                """\
                Archive validation failed for the directory '{}' ({}).


                    {}

                """,
            ).format(
                directory_name,
                result.returncode,
                TextwrapEx.Indent(
                    result.output.strip(),
                    4,
                    skip_first_line=True,
                ),
            )

            if continue_on_errors:
                validate_dm.WriteWarning(message)
            else:
                raise Exception(message)

    # Extract
    with _YieldTempDirectory(decompressed_dir, "extracting the archive") as decompressed_dir:
        status_func("Extracting archive...")
        with dm.Nested("Extracting archive...") as extract_dm:
            decompressed_dir.mkdir(parents=True, exist_ok=True)

            result = SubprocessEx.Run(
                f'{_GetZipBinary()} x "{archive_filename}" "-p{password}"',
                cwd=decompressed_dir,
            )

            if result.returncode != 0:
                message = textwrap.dedent(
                    """\
                        Archive extraction failed for the directory '{}' ({}).

                            {}

                        """,
                ).format(
                    directory_name,
                    result.returncode,
                    TextwrapEx.Indent(
                        result.output.strip(),
                        4,
                        skip_first_line=True,
                    ),
                )

                if continue_on_errors:
                    extract_dm.WriteWarning(message)
                else:
                    raise Exception(message)

        yield decompressed_dir, True


# ----------------------------------------------------------------------
def _VerifyFiles(
    dm: DoneManager,
    directory_name: str,
    contents_dir: Path,
    status_func: Callable[[str], None],
    *,
    continue_on_errors: bool,
) -> None:
    # Ensure that the index is present
    for index_filename in [INDEX_FILENAME, INDEX_HASH_FILENAME]:
        if not (contents_dir / index_filename).is_file():
            raise Exception(f"The index file '{index_filename}' does not exist.")

    with dm.Nested("Verifying files...") as verify_dm:
        # Ensure that the content is valid
        all_filenames: list[Path] = []

        for root_str, _, filenames in os.walk(contents_dir):
            root = Path(root_str)

            all_filenames += [root / filename for filename in filenames if filename != INDEX_HASH_FILENAME]

        data_store = FileSystemDataStore()

        errors: list[str] = []

        for filename_index, filename in enumerate(all_filenames):
            if filename.name == INDEX_FILENAME:
                expected_hash_value = (contents_dir / INDEX_HASH_FILENAME).read_text().strip()
            else:
                expected_hash_value = filename.name

            file_size = filename.stat().st_size or 1

            status_template = f"Validating file {filename_index + 1} of {len(all_filenames)} [{PathEx.GetSizeDisplay(file_size)}] {{:.02f}}%..."

            actual_hash_value = Common.CalculateHash(
                data_store,
                filename,
                lambda bytes_transferred: status_func(
                    status_template.format((bytes_transferred / file_size) * 100)
                ),
            )

            if actual_hash_value != expected_hash_value:
                errors.append(
                    textwrap.dedent(
                        f"""\
                        Filename:  {filename.relative_to(contents_dir)}
                        Expected:  {expected_hash_value}
                        Actual:    {actual_hash_value}
                        """,
                    ),
                )

        if errors:
            message = textwrap.dedent(
                """\
                Corrupt files were encountered in the directory '{}'.

                    {}

                """,
            ).format(
                directory_name,
                TextwrapEx.Indent(
                    "\n".join(errors),
                    4,
                    skip_first_line=True,
                ),
            )

            if continue_on_errors:
                verify_dm.WriteWarning(message)
            else:
                raise Exception(message)
