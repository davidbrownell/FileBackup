# ----------------------------------------------------------------------
# |
# |  BulkStorageDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 13:33:45
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the BulkStorageDataStore object"""

from abc import abstractmethod
from pathlib import Path

from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]

from FileBackup.DataStore.Interfaces.DataStore import DataStore  # type: ignore[import-untyped]


# ----------------------------------------------------------------------
class BulkStorageDataStore(DataStore):
    """Abstraction for data stores that can upload content in bulk but not easily retrieve it (such as cloud storage)"""

    # ----------------------------------------------------------------------
    @abstractmethod
    def Upload(
        self,
        dm: DoneManager,
        local_path: Path,
    ) -> None:
        """Uploads all content in the provided path and its children"""
        raise Exception("Abstract method")  # pragma: no cover
