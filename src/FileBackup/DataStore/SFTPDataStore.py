# ----------------------------------------------------------------------
# |
# |  SFTPDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 14:01:24
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the SFTPDataStore object"""

import stat
import textwrap
import traceback

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterator, Optional

import paramiko  # type: ignore[import-untyped]

from dbrownell_Common.ContextlibEx import ExitStack  # type: ignore[import-untyped]
from dbrownell_Common.Streams.DoneManager import DoneManager, DoneManagerException  # type: ignore[import-untyped]
from dbrownell_Common import TextwrapEx  # type: ignore[import-untyped]
from dbrownell_Common.Types import override  # type: ignore[import-untyped]
from paramiko.config import SSH_PORT  # type: ignore[import-untyped]

from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore, ItemType


# ----------------------------------------------------------------------
class SFTPDataStore(FileBasedDataStore):
    """DataStore accessible via SFTP server"""

    # ----------------------------------------------------------------------
    @classmethod
    @contextmanager
    def Create(
        cls,
        dm: DoneManager,
        host: str,
        username: str,
        private_key_or_password: Path | str,
        working_dir: Optional[Path] = None,
        *,
        port: int = SSH_PORT,
    ) -> Iterator["SFTPDataStore"]:
        log_filename = Path("paramiko.log").resolve()

        paramiko.util.log_to_file(str(log_filename))  # type: ignore

        ssh = paramiko.SSHClient()

        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.RejectPolicy())

        if isinstance(private_key_or_password, Path):
            password = None
            private_key_file = paramiko.RSAKey.from_private_key_file(str(private_key_or_password))
        else:
            password = private_key_or_password
            private_key_file = None

        # Connect
        try:
            ssh.connect(
                host,
                port=port,
                username=username,
                password=password,
                pkey=private_key_file,
            )
        except Exception as ex:
            if dm.is_debug:
                error = traceback.format_exc()
            else:
                error = str(ex)

            raise DoneManagerException(
                textwrap.dedent(
                    """\
                    Unable to connect.

                        Host:           {host}
                        Port:           {port}
                        Username:       {username}

                        Error:
                            {error}

                        Additional information is available at {log_filename}.
                    """,
                ).format(
                    host=host,
                    port=port,
                    username=username,
                    error=TextwrapEx.Indent(error, 8, skip_first_line=True),
                    log_filename=(
                        log_filename
                        if dm.capabilities.is_headless
                        else TextwrapEx.CreateAnsiHyperLink(
                            f"file://{log_filename.as_posix()}",
                            str(log_filename),
                        )
                    ),
                ),
            ) from ex

        with ExitStack(ssh.close):
            try:
                sftp = ssh.open_sftp()

                sftp.chdir(str(working_dir))

                yield cls(sftp)

            except Exception as ex:
                if dm.is_debug:
                    error = traceback.format_exc()
                else:
                    error = str(ex)

                raise DoneManagerException(
                    textwrap.dedent(
                        """\
                        Unable to open the STFP client.

                            Host:           {host}
                            Port:           {port}
                            Username:       {username}
                            Working Dir:    {working_dir}

                            Error:
                                {error}

                            Additional information is available at {log_filename}.
                        """,
                    ).format(
                        host=host,
                        port=port,
                        username=username,
                        error=TextwrapEx.Indent(error, 8, skip_first_line=True),
                        log_filename=(
                            log_filename
                            if dm.capabilities.is_headless
                            else TextwrapEx.CreateAnsiHyperLink(
                                f"file://{log_filename.as_posix()}",
                                str(log_filename),
                            )
                        ),
                    ),
                ) from ex

    # ----------------------------------------------------------------------
    def __init__(
        self,
        sftp_client: paramiko.SFTPClient,
    ) -> None:
        super(SFTPDataStore, self).__init__()

        self._client = sftp_client

    # ----------------------------------------------------------------------
    @override
    def ExecuteInParallel(self) -> bool:
        return False

    # ----------------------------------------------------------------------
    @override
    def ValidateBackupInputs(
        self,
        input_filename_or_dirs: list[Path],  # pylint: disable=unused-argument
    ) -> None:
        # Nothing to do here
        pass

    # ----------------------------------------------------------------------
    @override
    def SnapshotFilenameToDestinationName(
        self,
        path: Path,
    ) -> Path:
        if path.parts[0]:
            # Probably on Windows
            path = Path(path.parts[0].replace(":", "_").rstrip("\\")) / Path(*path.parts[1:])
        elif not path.parts[0]:
            path = Path(*path.parts[1:])

        return path

    # ----------------------------------------------------------------------
    @override
    def GetBytesAvailable(self) -> Optional[int]:
        # We don't have APIs to implement this functionality
        return None

    # ----------------------------------------------------------------------
    @override
    def GetWorkingDir(self) -> Path:
        return Path(self._client.getcwd() or "")

    # ----------------------------------------------------------------------
    @override
    def SetWorkingDir(
        self,
        path: Path,
    ) -> None:
        self._client.chdir(path.as_posix())

    # ----------------------------------------------------------------------
    @override
    def GetItemType(
        self,
        path: Path,
    ) -> Optional[ItemType]:
        try:
            result = self._client.stat(path.as_posix())
            assert result.st_mode is not None

            if stat.S_IFMT(result.st_mode) == stat.S_IFDIR:
                return ItemType.Dir

            return ItemType.File

        except FileNotFoundError:
            return None

    # ----------------------------------------------------------------------
    @override
    def GetFileSize(
        self,
        path: Path,
    ) -> int:
        result = self._client.stat(path.as_posix()).st_size
        assert result is not None

        return result

    # ----------------------------------------------------------------------
    @override
    def RemoveDir(
        self,
        path: Path,
    ) -> None:
        try:
            # The client can only remove empty directories, so make it empty
            dirs_to_remove: list[Path] = []

            for root, _, filenames in self.Walk(path):
                for filename in filenames:
                    self.RemoveFile(root / filename)

                dirs_to_remove.append(root)

            for dir_to_remove in reversed(dirs_to_remove):
                self._client.rmdir(dir_to_remove.as_posix())

        except FileNotFoundError:
            # There is no harm in attempting to remove the dir if it does not exist
            pass

    # ----------------------------------------------------------------------
    @override
    def RemoveFile(
        self,
        path: Path,
    ) -> None:
        try:
            self._client.unlink(path.as_posix())
        except FileNotFoundError:
            # There is no harm in attempting to remove the file if it does not exist
            pass

    # ----------------------------------------------------------------------
    @override
    def MakeDirs(
        self,
        path: Path,
    ) -> None:
        try:
            self._client.mkdir(path.as_posix())
        except OSError as ex:
            if "exists" not in str(ex):
                raise

    # ----------------------------------------------------------------------
    @override
    @contextmanager
    def Open(
        self,
        filename: Path,
        *args,
        **kwargs,
    ):
        with self._client.open(filename.as_posix(), *args, **kwargs) as f:
            yield f

    # ----------------------------------------------------------------------
    @override
    def Rename(
        self,
        old_path: Path,
        new_path: Path,
    ) -> None:
        item_type = self.GetItemType(new_path)

        if item_type == ItemType.Dir:
            self.RemoveDir(new_path)
        elif item_type in [ItemType.File, ItemType.SymLink]:
            self.RemoveFile(new_path)

        self._client.rename(old_path.as_posix(), new_path.as_posix())

    # ----------------------------------------------------------------------
    @override
    def Walk(
        self,
        path: Path = Path(),
    ) -> Generator[
        tuple[
            Path,  # root
            list[str],  # directories
            list[str],  # filenames
        ],
        None,
        None,
    ]:
        to_search: list[Path] = [Path(path)]

        while to_search:
            search_dir = to_search.pop()

            if self.GetItemType(search_dir) != ItemType.Dir:
                continue

            directories: list[str] = []
            filenames: list[str] = []

            for item in self._client.listdir_attr(search_dir.as_posix()):
                assert item.st_mode is not None

                is_dir = stat.S_IFMT(item.st_mode) == stat.S_IFDIR

                if is_dir:
                    directories.append(item.filename)
                else:
                    filenames.append(item.filename)

            yield search_dir, directories, filenames

            to_search += [search_dir / directory for directory in directories]
