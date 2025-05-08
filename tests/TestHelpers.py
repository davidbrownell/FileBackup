# ----------------------------------------------------------------------
# |
# |  TestHelpers.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-12 08:22:46
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains helpers used by multiple tests"""

import os

from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Generator, Optional

from dbrownell_Common import PathEx

from FileBackup import Mirror
from FileBackup.Snapshot import Snapshot


# ----------------------------------------------------------------------
# |
# |  Public Types
# |
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class FileInfo:
    """Information about a file"""

    path: Path
    file_size: Optional[int]  # None if the instance corresponds to an empty dir


# ----------------------------------------------------------------------
# |
# |  Public Functions
# |
# ----------------------------------------------------------------------
def GetOutputPath(
    destination_content_dir: Path,
    working_dir: Path,
) -> Path:
    if os.name == "nt":
        result = (
            destination_content_dir / working_dir.parts[0].replace(":", "_") / Path(*working_dir.parts[1:])
        )
    else:
        assert working_dir.parts[0] == "/", working_dir.parts
        result = destination_content_dir / Path(*working_dir.parts[1:])

    return PathEx.EnsureDir(result)


# ----------------------------------------------------------------------
def Enumerate(
    value: Path,
) -> Generator[FileInfo, None, None]:
    if value.is_file():
        yield FileInfo(value, value.stat().st_size)
        return

    for root_str, directories, filenames in os.walk(value):
        root = Path(root_str)

        if not directories and not filenames:
            yield FileInfo(root, None)
            continue

        for filename in filenames:
            fullpath = root / filename

            yield FileInfo(fullpath, fullpath.stat().st_size)


# ----------------------------------------------------------------------
def SetComparison(
    this_values: list[FileInfo],
    this_root: Path,
    that_values: list[FileInfo],
    that_root: Path,
) -> Generator[
    tuple[
        Optional[FileInfo],  # Will be None if the file is in that but not this
        Optional[FileInfo],  # Will be None if the file is in this but not that
    ],
    None,
    None,
]:
    that_lookup: dict[PurePath, FileInfo] = {
        PathEx.CreateRelativePath(that_root, that_value.path): that_value for that_value in that_values
    }

    for this_value in this_values:
        relative_path = PathEx.CreateRelativePath(this_root, this_value.path)

        yield this_value, that_lookup.pop(relative_path, None)

    for that_value in that_lookup.values():
        yield None, that_value


# ----------------------------------------------------------------------
def ValueComparison(
    this_values: list[FileInfo],
    this_root: Path,
    that_values: list[FileInfo],
    that_root: Path,
    *,
    compare_file_contents: bool,
) -> Generator[
    tuple[
        Optional[FileInfo],  # Will be None if the file is in that but not this
        Optional[FileInfo],  # Will be None if the file is in this but not that
    ],
    None,
    None,
]:
    for this_value, that_value in SetComparison(this_values, this_root, that_values, that_root):
        if this_value is None or that_value is None:
            yield this_value, that_value
            continue

        if this_value.file_size is None or that_value.file_size is None:
            if this_value.file_size != that_value.file_size:
                yield this_value, that_value

            continue

        # If here, compare the files
        assert this_value.file_size is not None
        assert that_value.file_size is not None

        if this_value.file_size != that_value.file_size:
            yield this_value, that_value
            continue

        if compare_file_contents:
            with this_value.path.open("rb") as f:
                this_contents = f.read()

            with that_value.path.open("rb") as f:
                that_contents = f.read()

            if this_contents != that_contents:
                yield this_value, that_value


# ----------------------------------------------------------------------
def CompareFileSystemSourceAndDestination(
    source_or_sources: Path | list[Path],
    destination: Path,
    expected_num_items: Optional[int] = None,
    *,
    compare_file_contents: bool = False,
    is_mirror: bool = True,
) -> None:
    if isinstance(source_or_sources, list):
        sources = source_or_sources
    else:
        sources = [source_or_sources]

    del source_or_sources

    common_source_path = PathEx.GetCommonPath(*sources)
    assert common_source_path is not None

    if is_mirror:
        content_dir = destination / Mirror.CONTENT_DIR_NAME
        content_prefix_dir = GetOutputPath(content_dir, common_source_path)
    else:
        content_dir = destination
        content_prefix_dir = destination

    PathEx.EnsureDir(content_dir)

    source_files: list[FileInfo] = []

    for source in sources:
        source_files += Enumerate(source)

    content_files = list(Enumerate(content_dir))

    assert source_files
    assert content_files

    if expected_num_items is not None:
        assert len(content_files) == expected_num_items, (len(content_files), expected_num_items)

    mismatches = list(
        ValueComparison(
            source_files,
            common_source_path,
            content_files,
            content_prefix_dir,
            compare_file_contents=compare_file_contents,
        ),
    )

    assert not mismatches, mismatches
