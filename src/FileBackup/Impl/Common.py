# ----------------------------------------------------------------------
# |
# |  Common.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 14:54:07
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Implements functionality used by both Mirror and Offsite"""

import hashlib
import os
import re
import textwrap

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import auto, Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    cast,
    Iterable,
    Iterator,
    Optional,
    Pattern,
    TYPE_CHECKING,
)
from urllib import parse as urlparse

from dbrownell_Common import ExecuteTasks  # type: ignore[import-untyped]
from dbrownell_Common.InflectEx import inflect  # type: ignore[import-untyped]
from dbrownell_Common import PathEx  # type: ignore[import-untyped]
from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]
from dbrownell_Common import TextwrapEx  # type: ignore[import-untyped]

from FileBackup.DataStore.FastGlacierDataStore import FastGlacierDataStore
from FileBackup.DataStore.FileSystemDataStore import FileSystemDataStore
from FileBackup.DataStore.Interfaces.DataStore import DataStore, ItemType
from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore
from FileBackup.DataStore.S3BrowserDataStore import S3BrowserDataStore
from FileBackup.DataStore.SFTPDataStore import SFTPDataStore, SSH_PORT

if TYPE_CHECKING:
    from FileBackup.Snapshot import Snapshot  # type: ignore[import-untyped]  # pragma: no cover


# ----------------------------------------------------------------------
# |
# |  Public Types
# |
# ----------------------------------------------------------------------
SFTP_TEMPLATE_REGEX = re.compile(
    r"""(?#
    Start                                   )^(?#
    Prefix                                  )ftp:\/\/(?#
    Username                                )(?P<username>[^\s:]+)(?#
    [sep]                                   ):(?#
    Posix Private Key Path                  )(?P<password_or_private_key_path>[^@]+)(?#
    [sep]                                   )@(?#
    Host                                    )(?P<host>[^:\/]+)(?#
    Port Group Begin                        )(?:(?#
        [sep]                               ):(?#
        Port                                )(?P<port>\d+)(?#
    Port Group End                          ))?(?#
    Working Group Begin                     )(?:(?#
        [sep]                               )\/(?#
        Posix Working Dir                   )(?P<working_dir>.+)(?#
    Working Group End                       ))?(?#
    End                                     )$(?#
    )""",
)


FAST_GLACIER_TEMPLATE_REGEX = re.compile(
    r"""(?#
    Start                                   )^(?#
    Prefix                                  )fast_glacier:\/\/(?#
    Account Name                            )(?P<account_name>[^@]+)(?#
    [sep]                                   )@(?#
    Region Name                             )(?P<aws_region>[^\/]+)(?#
    Working Dir Begin                       )(?:(?#
        [sep]                               )\/(?#
        Posix Working Dir                   )(?P<working_dir>.+)(?#
    Working Dir End                         ))?(?#
    End                                     )$(?#
    )""",
)


S3_BROWSER_TEMPLATE_REGEX = re.compile(
    r"""(?#
    Start                                   )^(?#
    Prefix                                  )s3_browser:\/\/(?#
    Account Name                            )(?P<account_name>[^@]+)(?#
    [sep]                                   )@(?#
    Bucket Name                             )(?P<bucket_name>[^\/]+)(?#
    Working Dir Begin                       )(?:(?#
        Posix Working Dir                   )(?P<working_dir>.+)(?#
    Working Dir End                         ))?(?#
    End                                     )$(?#
    )""",
)


# ----------------------------------------------------------------------
class DiffOperation(Enum):
    """Defines the cause of a difference in files"""

    add = auto()
    remove = auto()
    modify = auto()


# ----------------------------------------------------------------------
@dataclass(frozen=True)
class DirHashPlaceholder(object):
    """Object that signals the absence of a hash value because the associated item is a directory"""

    # ----------------------------------------------------------------------
    explicitly_added: bool = field(kw_only=True)

    # ----------------------------------------------------------------------
    def __eq__(self, other) -> bool:
        return isinstance(other, self.__class__)

    # ----------------------------------------------------------------------
    def __ne__(self, other) -> bool:
        return not self == other


# ----------------------------------------------------------------------
@dataclass(frozen=True)
class DiffResult:
    """Represents a difference between a file at a source and destination"""

    # ----------------------------------------------------------------------
    operation: DiffOperation
    path: Path

    # Used when operation is [add, modify]
    this_hash: None | str | DirHashPlaceholder
    this_file_size: None | int

    # Used when operation is [remove, modify]
    other_hash: None | str | DirHashPlaceholder
    other_file_size: None | int

    # ----------------------------------------------------------------------
    def __post_init__(self):
        assert (
            (self.operation == DiffOperation.add and self.this_hash is not None and self.other_hash is None)
            or (
                self.operation == DiffOperation.modify
                and self.this_hash is not None
                and self.other_hash is not None
            )
            or (
                self.operation == DiffOperation.remove
                and self.this_hash is None
                and self.other_hash is not None
            )
        ), "Instance is in an inconsistent state"

        assert (self.this_hash is None and self.this_file_size is None) or (
            self.this_hash is not None
            and (
                (isinstance(self.this_hash, DirHashPlaceholder) and self.this_file_size is None)
                or (isinstance(self.this_hash, str) and self.this_file_size is not None)
            )
        ), "'this' values are in an inconsistent state"

        assert (self.other_hash is None and self.other_file_size is None) or (
            self.other_hash is not None
            and (
                (isinstance(self.other_hash, DirHashPlaceholder) and self.other_file_size is None)
                or (isinstance(self.other_hash, str) and self.other_file_size is not None)
            )
        ), "'other' values are in an inconsistent state"

        assert self.operation != DiffOperation.modify or (
            isinstance(self.this_hash, str)
            and isinstance(self.other_hash, str)
            and self.this_hash != self.other_hash
        ), "modify values are in an inconsistent state"

    # ----------------------------------------------------------------------
    def ToJson(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "operation": self.operation.name,
            "path": self.path.as_posix(),
        }

        if isinstance(self.this_hash, str):
            assert self.this_file_size is not None

            result["this_hash"] = self.this_hash
            result["this_file_size"] = self.this_file_size

        if isinstance(self.other_hash, str):
            assert self.other_file_size is not None

            result["other_hash"] = self.other_hash
            result["other_file_size"] = self.other_file_size

        return result

    # ----------------------------------------------------------------------
    @classmethod
    def FromJson(
        cls,
        values: dict[str, Any],
    ) -> "DiffResult":
        if values["operation"] == "add":
            operation = DiffOperation.add

            this_hash = values.get("this_hash", DirHashPlaceholder(explicitly_added=False))
            this_file_size = values.get("this_file_size", None)

            other_hash = None
            other_file_size = None

        elif values["operation"] == "modify":
            operation = DiffOperation.modify

            this_hash = values["this_hash"]
            this_file_size = values["this_file_size"]

            other_hash = values["other_hash"]
            other_file_size = values["other_file_size"]

        elif values["operation"] == "remove":
            operation = DiffOperation.remove

            this_hash = None
            this_file_size = None

            other_hash = values.get("other_hash", DirHashPlaceholder(explicitly_added=False))
            other_file_size = values.get("other_file_size", None)

        else:
            assert False, values["operation"]  # pragma: no cover

        return cls(
            operation,
            Path(values["path"]),
            this_hash,
            this_file_size,
            other_hash,
            other_file_size,
        )


# ----------------------------------------------------------------------
EXECUTE_TASKS_REFRESH_PER_SECOND = 2


# ----------------------------------------------------------------------
PENDING_COMMIT_EXTENSION = ".__pending_commit__"
PENDING_DELETE_EXTENSION = ".__pending_delete__"


# ----------------------------------------------------------------------
# |
# |  Public Functions
# |
# ----------------------------------------------------------------------
def GetDestinationHelp() -> str:
    return textwrap.dedent(
        """\
        Data Store Destinations
        =======================
        The value provided on the command line for 'destination' can be any of these formats...

        File System
        -----------
        Writes content to the local file system.

            Examples:
                /home/mirrored_content
                C:\\MirroredContent

        SFTP
        ----
        Writes content to a SFTP server.

            Format:
                ftp://<username>:<password or posix path to private key>@<host>[:<port>][/<working_dir>]

            Examples:
                ftp://my_username:my_password@my_server.com
                ftp://my_username:my_password@my_server.com/A/Working/Dir
                ftp://my_username:/path/to/private/key@my_server.com
                ftp://my_username:/path/to/private/key@my_server.com/A/Working/Dir

        Fast Glacier
        ------------
        Write content using the Fast Glacier application (https://fastglacier.com/).

            Format:
                fast_glacier://<fast_glacier_account_name>@<aws_region>[/<glacier_dir>]

            Examples:
                fast_glacier://MyFastGlacierAccount@us-west-2
                fast_glacier://MyFastGlacierAccount@us-west-2/Glacier/Dir

        S3 Browser
        ----------
        Write content using the S3 Browser application (https://s3browser.com/).

            Format:
                s3_browser://<s3_browser_account_name>@<bucket_name>[/<working_dir>]

            Examples:
                s3_browser://MyS3BrowserAccount@MyBucket
                s3_browser://MyS3BrowserAccount@MyBucket/A/Working/Dir

        """,
    ).replace("\n", "\n\n")


# ----------------------------------------------------------------------
@contextmanager
def YieldDataStore(
    dm: DoneManager,
    destination: str | Path,
    *,
    ssd: bool,
) -> Iterator[DataStore]:
    if isinstance(destination, str):
        # SFTP
        sftp_match = SFTP_TEMPLATE_REGEX.match(destination)
        if sftp_match:
            private_key_or_password = sftp_match.group("password_or_private_key_path")

            private_key_filename = Path(private_key_or_password)
            if private_key_filename.is_file():
                private_key_or_password = private_key_filename.read_text()

            working_dir = sftp_match.group("working_dir")
            if working_dir:
                working_dir = Path(urlparse.unquote(working_dir))
            else:
                working_dir = None

            with SFTPDataStore.Create(
                dm,
                sftp_match.group("host"),
                sftp_match.group("username"),
                private_key_or_password,
                working_dir,
                port=int(sftp_match.group("port") or SSH_PORT),
            ) as data_store:
                yield data_store
                return

        # Fast Glacier
        fast_glacier_match = FAST_GLACIER_TEMPLATE_REGEX.match(destination)
        if fast_glacier_match:
            yield FastGlacierDataStore(
                fast_glacier_match.group("account_name"),
                fast_glacier_match.group("aws_region"),
                Path(fast_glacier_match.group("working_dir") or ""),
            )
            return

        # S3 Browser
        s3_browser_match = S3_BROWSER_TEMPLATE_REGEX.match(destination)
        if s3_browser_match:
            yield S3BrowserDataStore(
                s3_browser_match.group("account_name"),
                s3_browser_match.group("bucket_name"),
                Path(s3_browser_match.group("working_dir") or ""),
            )
            return

    # Create a FileSystemDataStore instance
    is_local_filesystem_override_value_for_testing: Optional[bool] = None

    # '[nonlocal]' should only be used while testing
    if isinstance(destination, str) and destination.startswith("[nonlocal]"):
        original_destination = destination
        destination = destination[len("[nonlocal]") :]

        dm.WriteInfo(
            textwrap.dedent(
                f"""\
                The destination string used to create a 'FileSystemDataStore' instance has been explicitly declared as nonlocal;
                this should only be used in testing scenarios.

                    Connection:     {original_destination}
                    Filename:       {destination}

                """,
            ),
        )

        is_local_filesystem_override_value_for_testing = False

    yield FileSystemDataStore(
        Path(destination),
        ssd=ssd,
        is_local_filesystem_override_value_for_testing=is_local_filesystem_override_value_for_testing,
    )


# ----------------------------------------------------------------------
def CreateFilterFunc(
    file_includes: Optional[list[Pattern]],
    file_excludes: Optional[list[Pattern]],
) -> Optional[Callable[[Path], bool]]:
    if not file_includes and not file_excludes:
        return None

    # ----------------------------------------------------------------------
    def SnapshotFilter(
        filename: Path,
    ) -> bool:
        filename_str = filename.as_posix()

        if file_excludes is not None and any(exclude.search(filename_str) for exclude in file_excludes):
            return False

        if file_includes is not None and not any(include.search(filename_str) for include in file_includes):
            return False

        return True

    # ----------------------------------------------------------------------

    return SnapshotFilter


# ----------------------------------------------------------------------
def CalculateDiffs(
    dm: DoneManager,
    source_snapshot: "Snapshot",
    dest_snapshot: "Snapshot",
) -> dict[DiffOperation, list[DiffResult]]:
    diffs: dict[DiffOperation, list[DiffResult]] = {
        # This order is important, as removes must happen before adds
        DiffOperation.remove: [],
        DiffOperation.add: [],
        DiffOperation.modify: [],
    }

    with dm.Nested(
        "\nCalculating differences...",
        lambda: "{} found".format(
            inflect.no("difference", sum(len(diff_items) for diff_items in diffs.values()))
        ),
        suffix="\n",
    ) as diff_dm:
        for diff in source_snapshot.Diff(dest_snapshot):
            assert diff.operation in diffs, diff.operation
            diffs[diff.operation].append(diff)

        if dm.is_verbose:
            with diff_dm.YieldVerboseStream() as stream:
                wrote_content = False

                for desc, operation in [
                    ("Adding", DiffOperation.add),
                    ("Modifying", DiffOperation.modify),
                    ("Removing", DiffOperation.remove),
                ]:
                    these_diffs = diffs[operation]
                    if not these_diffs:
                        continue

                    stream.write(
                        textwrap.dedent(
                            """\
                            {}{}
                            """,
                        ).format(
                            "\n" if wrote_content else "",
                            desc,
                        ),
                    )

                    for diff_index, diff in enumerate(these_diffs):
                        stream.write(
                            "  {}) [{}] {}\n".format(
                                diff_index + 1,
                                ("FILE" if diff.path.is_file() else "DIR " if diff.path.is_dir() else "????"),
                                (
                                    diff.path
                                    if dm.capabilities.is_headless
                                    else TextwrapEx.CreateAnsiHyperLink(
                                        f"file:///{diff.path.as_posix()}",
                                        str(diff.path),
                                    )
                                ),
                            ),
                        )

                    wrote_content = True

    return diffs


# ----------------------------------------------------------------------
def ValidateSizeRequirements(
    dm: DoneManager,
    local_data_store: FileBasedDataStore,
    destination_data_store: FileBasedDataStore,
    add_and_modify_diffs: Iterable[DiffResult],
    *,
    header: str = "Validating size requirements...",
) -> None:
    bytes_available = destination_data_store.GetBytesAvailable()

    if bytes_available is None:
        return

    bytes_required = 0

    with dm.Nested(
        header,
        [
            lambda: "{} required".format(PathEx.GetSizeDisplay(bytes_required)),
            lambda: "{} available".format(PathEx.GetSizeDisplay(cast(int, bytes_available))),
        ],
    ) as validate_dm:
        for diff in add_and_modify_diffs:
            item_type = local_data_store.GetItemType(diff.path)

            if item_type == ItemType.Dir:
                continue

            if item_type is None:
                validate_dm.WriteInfo(f"The local file '{diff.path}' is no longer available.\n")
                continue

            assert item_type == ItemType.File, item_type

            bytes_required += local_data_store.GetFileSize(diff.path)

        if (bytes_available * 0.85) <= bytes_required:
            validate_dm.WriteError("There is not enough disk space to process this request.\n")


# ----------------------------------------------------------------------
def WriteFile(
    data_store: FileBasedDataStore,
    source_filename: Path,
    dest_filename: Path,
    status_func: Callable[[int], None],
) -> None:
    temp_dest_filename = dest_filename.parent / f"{dest_filename.stem}.__temp__{dest_filename.suffix}"

    with source_filename.open("rb") as source:
        data_store.MakeDirs(temp_dest_filename.parent)

        with data_store.Open(temp_dest_filename, "wb") as dest:
            bytes_written = 0

            while True:
                chunk = source.read(16384)
                if not chunk:
                    break

                dest.write(chunk)

                bytes_written += len(chunk)
                status_func(bytes_written)

    data_store.Rename(temp_dest_filename, dest_filename)


# ----------------------------------------------------------------------
def CreateDestinationPathFuncFactory() -> Callable[[Path, str], Path]:
    if os.name == "nt":
        # ----------------------------------------------------------------------
        def CreateDestinationPathWindows(
            path: Path,
            extension: str,
        ) -> Path:
            assert ":" in path.parts[0], path.parts

            return (
                Path(path.parts[0].replace(":", "_").rstrip("\\"))
                / Path(*path.parts[1:-1])
                / (path.name + extension)
            )

        # ----------------------------------------------------------------------

        return CreateDestinationPathWindows

    # ----------------------------------------------------------------------
    def CreateDestinationPathNotWindows(
        path: Path,
        extension: str,
    ) -> Path:
        assert path.parts[0] == "/", path.parts

        return Path(*path.parts[1:-1]) / (path.name + extension)

    # ----------------------------------------------------------------------

    return CreateDestinationPathNotWindows


# ----------------------------------------------------------------------
def CopyLocalContent(
    dm: DoneManager,
    destination_data_store: FileBasedDataStore,
    diffs: Iterable[DiffResult],
    create_destination_path_func: Callable[[Path, str], Path],
    *,
    ssd: bool,
    quiet: bool,
) -> list[Optional[Path]]:
    # ----------------------------------------------------------------------
    def PrepareTask(
        context: Any,
        on_simple_status_func: Callable[[str], None],  # pylint: disable=unused-argument
    ) -> tuple[int, ExecuteTasks.TransformTasksExTypes.TransformFuncType]:
        diff = cast(DiffResult, context)
        del context

        dest_filename = create_destination_path_func(diff.path, PENDING_COMMIT_EXTENSION)

        content_size = None

        if diff.path.is_file():
            assert diff.this_file_size is not None
            content_size = diff.this_file_size
        elif diff.path.is_dir():
            content_size = 1
        else:
            assert False, diff.path  # pragma: no cover

        # ----------------------------------------------------------------------
        def Execute(
            status: ExecuteTasks.Status,
        ) -> Optional[Path]:
            if not diff.path.exists():
                return None

            if diff.path.is_dir():
                destination_data_store.MakeDirs(dest_filename)
            elif diff.path.is_file():
                WriteFile(
                    destination_data_store,
                    diff.path,
                    dest_filename,
                    lambda bytes_transferred: cast(None, status.OnProgress(bytes_transferred, None)),
                )
            else:
                assert False, diff.path  # pragma: no cover

            return dest_filename

        # ----------------------------------------------------------------------

        return content_size, Execute

    # ----------------------------------------------------------------------

    return cast(
        list[Optional[Path]],
        ExecuteTasks.TransformTasksEx(
            dm,
            "Processing",
            [ExecuteTasks.TaskData(str(diff.path), diff) for diff in diffs],
            PrepareTask,
            quiet=quiet,
            max_num_threads=None if ssd and destination_data_store.ExecuteInParallel() else 1,
            refresh_per_second=EXECUTE_TASKS_REFRESH_PER_SECOND,
        ),
    )


# ----------------------------------------------------------------------
def CalculateHash(
    data_store: FileBasedDataStore,
    input_item: Path,
    status: Callable[[int], None],
) -> str:
    hasher = hashlib.sha512()

    bytes_hashed = 0

    with data_store.Open(input_item, "rb") as f:
        while True:
            chunk = f.read(16384)
            if not chunk:
                break

            hasher.update(chunk)

            bytes_hashed += len(chunk)
            status(bytes_hashed)

    return hasher.hexdigest()
