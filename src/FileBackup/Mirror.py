# ----------------------------------------------------------------------
# |
# |  Mirror.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 13:29:08
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""\
Mirrors backup content: files created locally will be added to the backup data store; files deleted
locally will be removed from the backup data store; files modified locally will be modified at the
backup data store.
"""

import itertools
import shutil
import textwrap

from enum import Enum
from pathlib import Path
from typing import Any, cast, Optional, Pattern

from dbrownell_Common.ContextlibEx import ExitStack  # type: ignore[import-untyped]
from dbrownell_Common import ExecuteTasks  # type: ignore[import-untyped]
from dbrownell_Common.InflectEx import inflect  # type: ignore[import-untyped]
from dbrownell_Common import PathEx  # type: ignore[import-untyped]
from dbrownell_Common.Streams.Capabilities import Capabilities  # type: ignore[import-untyped]
from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]
from dbrownell_Common import TextwrapEx  # type: ignore[import-untyped]
from rich.progress import Progress, TimeElapsedColumn

from FileBackup.DataStore.FileSystemDataStore import FileSystemDataStore
from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore
from FileBackup.Impl import Common
from FileBackup.Snapshot import Snapshot


# ----------------------------------------------------------------------
# |
# |  Public Types
# |
# ----------------------------------------------------------------------
CONTENT_DIR_NAME = "Content"


# ----------------------------------------------------------------------
class ValidateType(str, Enum):
    """Controls how validation is performed"""

    standard = "standard"  # File names and sizes are validated
    complete = "complete"  # File names, sizes, and hash values are validated


# ----------------------------------------------------------------------
# |
# |  Public Functions
# |
# ----------------------------------------------------------------------
def Backup(
    dm: DoneManager,
    destination: str | Path,
    input_filenames_or_dirs: list[Path],
    *,
    ssd: bool,
    force: bool,
    quiet: bool,
    file_includes: Optional[list[Pattern]],
    file_excludes: Optional[list[Pattern]],
) -> None:
    # Process the inputs
    for input_filename_or_dir in input_filenames_or_dirs:
        if not input_filename_or_dir.exists():
            raise Exception(f"'{input_filename_or_dir}' is not a valid filename or directory.")

    local_data_store = FileSystemDataStore()

    with Common.YieldDataStore(
        dm,
        destination,
        ssd=ssd,
    ) as destination_data_store:
        if not isinstance(destination_data_store, FileBasedDataStore):
            dm.WriteError(
                f"'{destination}' does not resolve to a file-based data store (which is required when mirroring content).\n"
            )
            return

        destination_data_store.ValidateBackupInputs(input_filenames_or_dirs)

        # Create the local snapshot
        with dm.Nested("Creating the local snapshot...") as local_dm:
            local_snapshot = Snapshot.Calculate(
                local_dm,
                input_filenames_or_dirs,
                local_data_store,
                run_in_parallel=ssd,
                filter_filename_func=Common.CreateFilterFunc(file_includes, file_excludes),
                quiet=quiet,
            )

            if local_dm.result != 0:
                return

        # Create the remote snapshot (if necessary)
        if force or not Snapshot.IsPersisted(destination_data_store):
            destination_snapshot = Snapshot(
                Snapshot.Node(
                    None,
                    None,
                    Common.DirHashPlaceholder(explicitly_added=False),
                    None,
                ),
            )
        else:
            with dm.Nested("\nReading the destination snapshot...") as destination_dm:
                destination_snapshot = Snapshot.LoadPersisted(destination_dm, destination_data_store)

                if destination_dm.result != 0:
                    return

        # Calculate the differences
        diffs: dict[Common.DiffOperation, list[Common.DiffResult]] = Common.CalculateDiffs(
            dm,
            local_snapshot,
            destination_snapshot,
        )

        # Calculate the size requirements
        Common.ValidateSizeRequirements(
            dm,
            local_data_store,
            destination_data_store,
            itertools.chain(diffs[Common.DiffOperation.add], diffs[Common.DiffOperation.modify]),
        )

        if dm.result != 0:
            return

        # Cleanup previous content
        _CleanupImpl(dm, destination_data_store)
        if dm.result != 0:
            return

        # Persist all content
        with dm.Nested("\nPersisting content...") as persist_dm:
            # Transfer the snapshot
            pending_snapshot_filename = Path(Snapshot.PERSISTED_FILE_NAME + Common.PENDING_COMMIT_EXTENSION)

            temp_directory = PathEx.CreateTempDirectory()

            with ExitStack(lambda: shutil.rmtree(temp_directory)):
                with persist_dm.Nested("Creating snapshot data...") as snapshot_dm:
                    local_snapshot.Persist(snapshot_dm, FileSystemDataStore(temp_directory))
                    if snapshot_dm.result != 0:
                        return

                with persist_dm.Nested("Transferring snapshot data...") as snapshot_dm:
                    source_filename = temp_directory / Snapshot.PERSISTED_FILE_NAME

                    with snapshot_dm.YieldStdout() as stdout_context:
                        stdout_context.persist_content = False

                        with Progress(
                            *Progress.get_default_columns(),
                            TimeElapsedColumn(),
                            "{task.fields[status]}",
                            console=Capabilities.Get(stdout_context.stream).CreateRichConsole(
                                stdout_context.stream
                            ),
                            transient=True,
                        ) as progress_bar:
                            total_progress_id = progress_bar.add_task(
                                f"{stdout_context.line_prefix}Total Progress",
                                total=source_filename.stat().st_size,
                                status="",
                                visible=True,
                            )

                            Common.WriteFile(
                                destination_data_store,
                                source_filename,
                                pending_snapshot_filename,
                                lambda bytes_transferred: progress_bar.update(
                                    total_progress_id, completed=bytes_transferred
                                ),
                            )

                    if snapshot_dm.result != 0:
                        return

            # Transfer the content
            prev_working_dir = destination_data_store.GetWorkingDir()
            with ExitStack(lambda: destination_data_store.SetWorkingDir(prev_working_dir)):
                destination_data_store.MakeDirs(Path(CONTENT_DIR_NAME))
                destination_data_store.SetWorkingDir(Path(CONTENT_DIR_NAME))

                create_destination_path_func = Common.CreateDestinationPathFuncFactory()

                pending_delete_items: list[Optional[Path]] = []
                pending_commit_items: list[Optional[Path]] = []

                # If force, mark the original content items for deletion
                if force:
                    for root, directories, filenames in destination_data_store.Walk():
                        for item in itertools.chain(directories, filenames):
                            fullpath = root / item

                            delete_filename = fullpath.parent / (
                                fullpath.name + Common.PENDING_DELETE_EXTENSION
                            )

                            destination_data_store.Rename(fullpath, delete_filename)
                            pending_delete_items.append(delete_filename)

                persist_dm.WriteLine("")

                # Rename removed and modified files to their to-be-deleted variations
                if diffs[Common.DiffOperation.modify] or diffs[Common.DiffOperation.remove]:
                    with persist_dm.Nested(
                        "Marking content to be removed...",
                        suffix="\n",
                    ) as this_dm:
                        # ----------------------------------------------------------------------
                        def Remove(
                            context: Any,
                            status: ExecuteTasks.Status,
                        ) -> Optional[Path]:
                            pending_dest_filename = create_destination_path_func(
                                cast(Path, context),
                                Common.PENDING_DELETE_EXTENSION,
                            )

                            original_dest_filename = pending_dest_filename.with_suffix("")

                            if not destination_data_store.GetItemType(original_dest_filename):
                                status.OnInfo(f"'{original_dest_filename}' no longer exists.\n")
                                return None

                            destination_data_store.Rename(
                                original_dest_filename,
                                pending_dest_filename,
                            )

                            return pending_dest_filename

                        # ----------------------------------------------------------------------

                        pending_delete_items += cast(
                            list[Optional[Path]],
                            ExecuteTasks.TransformTasks(
                                this_dm,
                                "Processing",
                                [
                                    ExecuteTasks.TaskData(str(diff.path), diff.path)
                                    for diff in itertools.chain(
                                        diffs[Common.DiffOperation.modify],
                                        diffs[Common.DiffOperation.remove],
                                    )
                                ],
                                Remove,
                                quiet=quiet,
                                max_num_threads=(None if destination_data_store.ExecuteInParallel() else 1),
                                refresh_per_second=Common.EXECUTE_TASKS_REFRESH_PER_SECOND,
                            ),
                        )

                        if this_dm.result != 0:
                            return

                # Move added and modified files to their pending variations
                if diffs[Common.DiffOperation.add] or diffs[Common.DiffOperation.modify]:
                    with persist_dm.Nested(
                        "Transferring added and modified content...",
                        suffix="\n",
                    ) as this_dm:
                        pending_commit_items += Common.CopyLocalContent(
                            this_dm,
                            destination_data_store,
                            itertools.chain(
                                diffs[Common.DiffOperation.add],
                                diffs[Common.DiffOperation.modify],
                            ),
                            create_destination_path_func,
                            quiet=quiet,
                            ssd=ssd,
                        )

                        if this_dm.result != 0:
                            return

                if pending_commit_items or pending_delete_items:
                    for desc, items, func in [
                        (
                            "Committing added content...",
                            pending_commit_items,
                            lambda fullpath, item_type: cast(
                                FileBasedDataStore, destination_data_store
                            ).Rename(fullpath, fullpath.with_suffix("")),
                        ),
                        (
                            "Committing removed content...",
                            pending_delete_items,
                            lambda fullpath, item_type: (
                                cast(FileBasedDataStore, destination_data_store).RemoveDir(fullpath)
                                if item_type == Common.ItemType.Dir
                                else cast(FileBasedDataStore, destination_data_store).RemoveFile(fullpath)
                            ),
                        ),
                    ]:
                        if not any(item for item in items):
                            continue

                        with persist_dm.Nested(desc, suffix="\n") as this_dm:
                            # ----------------------------------------------------------------------
                            def Commit(
                                context: Any,
                                status: ExecuteTasks.Status,  # pylint: disable=unused-argument
                            ) -> None:
                                fullpath = cast(Path, context)
                                del context

                                item_type = destination_data_store.GetItemType(fullpath)

                                if item_type is not None:
                                    func(fullpath, item_type)

                            # ----------------------------------------------------------------------

                            ExecuteTasks.TransformTasks(
                                this_dm,
                                "Processing",
                                [
                                    ExecuteTasks.TaskData(str(fullpath), fullpath)
                                    for fullpath in items
                                    if fullpath
                                ],
                                Commit,
                                quiet=quiet,
                                max_num_threads=(None if destination_data_store.ExecuteInParallel() else 1),
                                refresh_per_second=Common.EXECUTE_TASKS_REFRESH_PER_SECOND,
                            )

                            if this_dm.result != 0:
                                return

            with persist_dm.Nested("Committing snapshot data..."):
                destination_data_store.Rename(
                    pending_snapshot_filename,
                    pending_snapshot_filename.with_suffix(""),
                )


# ----------------------------------------------------------------------
def Cleanup(
    dm: DoneManager,
    destination: str | Path,
) -> None:
    with Common.YieldDataStore(
        dm,
        destination,
        ssd=False,
    ) as destination_data_store:
        if not isinstance(destination_data_store, FileBasedDataStore):
            dm.WriteError(
                f"'{destination}' does not resolve to a file-based data store (which is required when mirroring content).\n"
            )
            return

        return _CleanupImpl(dm, destination_data_store)


# ----------------------------------------------------------------------
def Validate(
    dm: DoneManager,
    destination: str | Path,
    validate_type: ValidateType,
    *,
    ssd: bool,
    quiet: bool,
) -> None:
    with Common.YieldDataStore(
        dm,
        destination,
        ssd=ssd,
    ) as destination_data_store:
        if not isinstance(destination_data_store, FileBasedDataStore):
            dm.WriteError(
                f"'{destination}' does not resolve to a file-based data store (which is required when mirroring content).\n"
            )
            return

        if not Snapshot.IsPersisted(destination_data_store):
            dm.WriteError("No snapshot was found.\n")
            return

        mirrored_snapshot = Snapshot.LoadPersisted(dm, destination_data_store)

        _CleanupImpl(dm, destination_data_store)

        prev_working_dir = destination_data_store.GetWorkingDir()
        with ExitStack(lambda: destination_data_store.SetWorkingDir(prev_working_dir)):
            content_dir = destination_data_store.GetWorkingDir() / CONTENT_DIR_NAME
            destination_data_store.SetWorkingDir(content_dir)

            with dm.Nested("\nExtracting files...", suffix="\n") as extract_dm:
                current_snapshot = Snapshot.Calculate(
                    extract_dm,
                    [Path()],
                    destination_data_store,
                    run_in_parallel=destination_data_store.ExecuteInParallel(),
                    quiet=quiet,
                    calculate_hashes=validate_type == ValidateType.complete,
                )

            # The values in the mirrored snapshot are based on the original values provided during
            # the backup with the values of the current snapshot are based on what is on the file
            # system. Convert the data in the mirror snapshot so it matches the values in the
            # current snapshot before we compare the contents of each.
            new_root = Snapshot.Node(None, None, Common.DirHashPlaceholder(explicitly_added=False), None)

            for node in mirrored_snapshot.node.Enum():
                destination_path = destination_data_store.SnapshotFilenameToDestinationName(node.fullpath)

                if node.is_dir:
                    if not node.children:
                        new_root.AddDir(destination_path, force=True)
                elif node.is_file:
                    new_root.AddFile(
                        destination_path,
                        cast(str, node.hash_value),
                        cast(int, node.file_size),
                    )
                else:
                    assert False, node  # pragma: no cover

        with dm.Nested(
            "Validating content...",
            suffix="\n" if dm.is_verbose else "",
        ) as validate_dm:
            # Windows and Linux have different sorting orders, so capture and sort the list before
            # displaying the contents.
            diffs = list(
                current_snapshot.Diff(
                    Snapshot(new_root),
                    compare_hashes=validate_type == ValidateType.complete,
                )
            )

            if not diffs:
                validate_dm.WriteInfo("No differences were found.\n")
                return

            diffs.sort(key=lambda diff: diff.path)

            for diff in diffs:
                if diff.operation == Common.DiffOperation.add:
                    validate_dm.WriteError(f"'{diff.path}' has been added.\n")
                elif diff.operation == Common.DiffOperation.remove:
                    validate_dm.WriteError(f"'{diff.path}' has been removed.\n")
                elif diff.operation == Common.DiffOperation.modify:
                    assert diff.this_file_size is not None
                    assert diff.other_file_size is not None

                    validate_dm.WriteWarning(
                        textwrap.dedent(
                            """\
                            '{}' has been modified.

                                Expected file size:     {}
                                Actual file size:       {}
                            {}
                            """,
                        ).format(
                            diff.path,
                            diff.other_file_size,
                            diff.this_file_size,
                            (
                                ""
                                if diff.this_hash == "not calculated"
                                else TextwrapEx.Indent(
                                    textwrap.dedent(
                                        f"""\
                                    Expected hash value:    {diff.other_hash}
                                    Actual hash value:      {diff.this_hash}
                                    """,
                                    ),
                                    4,
                                )
                            ),
                        ),
                    )
                else:
                    assert False, diff.operation  # pragma: no cover


# ----------------------------------------------------------------------
# |
# |  Private Functions
# |
# ----------------------------------------------------------------------
def _CleanupImpl(
    dm: DoneManager,
    data_store: FileBasedDataStore,
) -> None:
    items_reverted = 0

    with dm.Nested(
        "Reverting partially committed content at the destination...",
        lambda: "{} reverted".format(inflect.no("item", items_reverted)),
    ) as clean_dm:
        item_type = data_store.GetItemType(Path(CONTENT_DIR_NAME))

        if item_type is None:
            clean_dm.WriteInfo("Content does not exist.\n")
            return

        if item_type == Common.ItemType.File:
            with clean_dm.Nested(f"Removing the file '{CONTENT_DIR_NAME}'..."):
                data_store.RemoveFile(Path(CONTENT_DIR_NAME))
                return

        if item_type != Common.ItemType.Dir:
            raise Exception(f"'{CONTENT_DIR_NAME}' is not a valid directory.")

        for root, directories, filenames in data_store.Walk():
            if clean_dm.capabilities.is_interactive:
                clean_dm.WriteStatus(f"Processing '{root}'...")

            for items, remove_func in [
                (directories, data_store.RemoveDir),
                (filenames, data_store.RemoveFile),
            ]:
                for item in items:
                    fullpath = root / item

                    if fullpath.suffix == Common.PENDING_COMMIT_EXTENSION:
                        with clean_dm.Nested(f"Removing '{fullpath}'..."):
                            remove_func(fullpath)
                            items_reverted += 1

                    elif fullpath.suffix == Common.PENDING_DELETE_EXTENSION:
                        original_filename = fullpath.with_suffix("")

                        with clean_dm.Nested(f"Restoring '{original_filename}'..."):
                            data_store.Rename(fullpath, original_filename)
                            items_reverted += 1
