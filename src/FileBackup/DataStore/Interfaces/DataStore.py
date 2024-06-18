# ----------------------------------------------------------------------
# |
# |  DataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 13:31:26
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the DataStore object"""

from abc import ABC, abstractmethod
from enum import auto, Enum


# ----------------------------------------------------------------------
class ItemType(Enum):
    """type of file-system-like item"""

    File = auto()
    Dir = auto()
    SymLink = auto()


# ----------------------------------------------------------------------
class DataStore(ABC):
    """Abstraction for systems that are able to store data"""

    # ----------------------------------------------------------------------
    @abstractmethod
    def ExecuteInParallel(self) -> bool:
        """Return True if processing should be executed in parallel."""
        raise Exception("Abstract method")  # pragma: no cover
