# ----------------------------------------------------------------------
# |
# |  FileSystemDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 13:42:04
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the FileSystemDataStore object"""

import itertools
import os
import shutil

from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from dbrownell_Common import PathEx  # type: ignore[import-untyped]
from dbrownell_Common.Types import override  # type: ignore[import-untyped]

from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore, ItemType


# ----------------------------------------------------------------------
class FileSystemDataStore(FileBasedDataStore):
    """DataStore associated with a standard, local file system"""

    # ----------------------------------------------------------------------
    def __init__(
        self,
        root: Path = Path.cwd(),
        *,
        ssd: bool = False,
        is_local_filesystem_override_value_for_testing: Optional[bool] = None,
    ) -> None:
        assert not root.exists() or root.is_dir(), root

        super(FileSystemDataStore, self).__init__(
            is_local_filesystem=(
                is_local_filesystem_override_value_for_testing
                if is_local_filesystem_override_value_for_testing is not None
                else root.root == Path.cwd().root
            ),
        )

        self._working_dir: Path = root
        self._ssd = ssd

    # ----------------------------------------------------------------------
    @override
    def ExecuteInParallel(self) -> bool:
        return self._ssd

    # ----------------------------------------------------------------------
    @override
    def ValidateBackupInputs(
        self,
        input_filename_or_dirs: list[Path],
    ) -> None:
        for input_filename_or_dir in input_filename_or_dirs:
            if input_filename_or_dir.is_file():
                input_dir = input_filename_or_dir.parent
            elif input_filename_or_dir.is_dir():
                input_dir = input_filename_or_dir
            else:
                raise Exception(f"'{input_filename_or_dir}' is not a supported item type.")

            if PathEx.IsDescendant(self._working_dir, input_dir):
                raise Exception(
                    f"The directory '{input_filename_or_dir}' overlaps with the destination path '{self._working_dir}'."
                )

    # ----------------------------------------------------------------------
    @override
    def SnapshotFilenameToDestinationName(
        self,
        path: Path,
    ) -> Path:
        if path.parts[0] == "/":
            path = Path(*path.parts[1:])
        elif path.parts[0]:
            # Probably on Windows
            path = Path(path.parts[0].replace(":", "_").rstrip("\\")) / Path(*path.parts[1:])

        return self.GetWorkingDir() / path

    # ----------------------------------------------------------------------
    @override
    def GetBytesAvailable(self) -> Optional[int]:
        # Find a directory that exists
        for potential_dir in itertools.chain(
            [self._working_dir],
            self._working_dir.parents,
            [Path.cwd()],
        ):
            if potential_dir.is_dir():
                return shutil.disk_usage(potential_dir).free

        assert False, self._working_dir

    # ----------------------------------------------------------------------
    @override
    def GetWorkingDir(self) -> Path:
        return self._working_dir

    # ----------------------------------------------------------------------
    @override
    def SetWorkingDir(
        self,
        path: Path,
    ) -> None:
        self._working_dir /= path

    # ----------------------------------------------------------------------
    @override
    def GetItemType(
        self,
        path: Path,
    ) -> Optional[ItemType]:
        path = self._working_dir / path

        if not path.exists():
            return None

        if path.is_symlink():
            return ItemType.SymLink

        if path.is_file():
            return ItemType.File

        if path.is_dir():
            return ItemType.Dir

        raise Exception(f"'{path}' is not a known type.")

    # ----------------------------------------------------------------------
    @override
    def GetFileSize(
        self,
        path: Path,
    ) -> int:
        return (self._working_dir / path).stat().st_size

    # ----------------------------------------------------------------------
    @override
    def RemoveDir(
        self,
        path: Path,
    ) -> None:
        shutil.rmtree(self._working_dir / path)

    # ----------------------------------------------------------------------
    @override
    def RemoveFile(
        self,
        path: Path,
    ) -> None:
        (self._working_dir / path).unlink()

    # ----------------------------------------------------------------------
    @override
    def MakeDirs(
        self,
        path: Path,
    ) -> None:
        (self._working_dir / path).mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------
    @override
    @contextmanager
    def Open(
        self,
        filename: Path,
        *args,
        **kwargs,
    ):
        with (self._working_dir / filename).open(*args, **kwargs) as f:
            yield f

    # ----------------------------------------------------------------------
    @override
    def Rename(
        self,
        old_path: Path,
        new_path: Path,
    ) -> None:
        old_path = self._working_dir / old_path
        new_path = self._working_dir / new_path

        if new_path.is_file():
            new_path.unlink()
        elif new_path.is_dir():
            shutil.rmtree(new_path)

        shutil.move(old_path, new_path)

    # ----------------------------------------------------------------------
    @override
    def Walk(
        self,
        path: Path = Path(),
    ) -> Generator[
        tuple[
            Path,  # root
            list[str],  # directories
            list[str],  # files
        ],
        None,
        None,
    ]:
        for root, directories, filenames in os.walk(self._working_dir / path):
            yield Path(root), directories, filenames
