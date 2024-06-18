# ----------------------------------------------------------------------
# |
# |  FileBasedDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 13:36:43
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the FileBasedDataStore object"""

from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from FileBackup.DataStore.Interfaces.DataStore import DataStore, ItemType


# ----------------------------------------------------------------------
class FileBasedDataStore(DataStore):
    """Abstraction for systems that are able to store and retrieve data as files"""

    # ----------------------------------------------------------------------
    def __init__(
        self,
        *,
        is_local_filesystem: bool = False,
    ) -> None:
        self.is_local_filesystem = is_local_filesystem

    # ----------------------------------------------------------------------
    @abstractmethod
    def ValidateBackupInputs(
        self,
        input_filename_or_dirs: list[Path],
    ) -> None:
        """Ensure that the inputs are valid given the state of the instance"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def SnapshotFilenameToDestinationName(
        self,
        path: Path,
    ) -> Path:
        """Convert from the actual root used when persisting the file (e.g. "C:\\") to the corresponding value on this system"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def GetBytesAvailable(self) -> Optional[int]:
        """Returns the number of bytes available on the storage medium, or None if it is not possible to calculate such a value."""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def GetWorkingDir(self) -> Path:
        """Returns the current working directory"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def SetWorkingDir(
        self,
        path: Path,
    ) -> None:
        """Sets the working directory"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def GetItemType(
        self,
        path: Path,
    ) -> Optional[ItemType]:
        """Get the type for the specific item, or None if the item does not exist"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def GetFileSize(
        self,
        path: Path,
    ) -> int:
        """Returns the file item's size"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def RemoveDir(
        self,
        path: Path,
    ) -> None:
        """Removes the specified directory"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def RemoveFile(
        self,
        path: Path,
    ) -> None:
        """Removes the specified file"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def MakeDirs(
        self,
        path: Path,
    ) -> None:
        """Makes a directory"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    @contextmanager
    def Open(
        self,
        filename: Path,
        *args,
        **kwargs,
    ):
        """Python-like open method"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
    def Rename(
        self,
        old_path: Path,
        new_path: Path,
    ) -> None:
        """Renames the destination item"""
        raise Exception("Abstract method")  # pragma: no cover

    # ----------------------------------------------------------------------
    @abstractmethod
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
        """Walks items on the destination"""
        raise Exception("Abstract method")  # pragma: no cover
