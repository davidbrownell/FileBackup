# ----------------------------------------------------------------------
# |
# |  Snapshot.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-11 08:38:24
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the Snapshot object"""

import functools
import itertools
import json

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast, Generator, Optional

from dbrownell_Common import ExecuteTasks  # type: ignore[import-untyped]
from dbrownell_Common.InflectEx import inflect  # type: ignore[import-untyped]
from dbrownell_Common import PathEx  # type: ignore[import-untyped]
from dbrownell_Common.Streams.Capabilities import Capabilities  # type: ignore[import-untyped]
from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]
from rich.progress import Progress, TimeElapsedColumn

from FileBackup.DataStore.Interfaces.FileBasedDataStore import FileBasedDataStore
from FileBackup.Impl.Common import (
    CalculateHash,
    DiffOperation,
    DiffResult,
    DirHashPlaceholder,
    EXECUTE_TASKS_REFRESH_PER_SECOND,
    ItemType,
)


# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Snapshot:
    """Collection of files and hashes"""

    # ----------------------------------------------------------------------
    # |
    # |  Public Types
    # |
    # ----------------------------------------------------------------------
    @dataclass
    class Node:
        """Corresponds to a file or directory"""

        # ----------------------------------------------------------------------
        name: Optional[str]
        parent: Optional["Snapshot.Node"] = field(compare=False)

        hash_value: str | DirHashPlaceholder
        file_size: Optional[int]

        children: dict[str, "Snapshot.Node"] = field(init=False, default_factory=dict)

        # ----------------------------------------------------------------------
        @property
        def is_dir(self) -> bool:
            return isinstance(self.hash_value, DirHashPlaceholder)

        @property
        def is_file(self) -> bool:
            return isinstance(self.hash_value, str)

        @functools.cached_property
        def fullpath(self) -> Path:
            names: list[str] = []

            node: Snapshot.Node | None = self
            while True:
                assert node is not None

                if node.name is None:
                    break

                names.append(node.name)
                node = node.parent

            return Path(*reversed(names))

        # ----------------------------------------------------------------------
        def __post_init__(self):
            assert (self.name is None and self.parent is None) or (
                self.name is not None and self.name and self.parent is not None
            )

            assert (isinstance(self.hash_value, DirHashPlaceholder) and self.file_size is None) or (
                isinstance(self.hash_value, str) and self.file_size is not None and self.file_size >= 0
            ), (self.hash_value, self.file_size)

            assert not self.children or self.is_dir

        # ----------------------------------------------------------------------
        @classmethod
        def Create(
            cls,
            values: dict[Path, Optional[tuple[str, int]]],
        ) -> "Snapshot.Node":
            root = cls(None, None, DirHashPlaceholder(explicitly_added=False), None)

            for path, path_values in values.items():
                if path_values is None:
                    root.AddDir(path)
                else:
                    hash_value, file_size = path_values
                    root.AddFile(path, hash_value, file_size)

            return root

        # ----------------------------------------------------------------------
        def AddFile(
            self,
            path: Path,
            hash_value: str,
            file_size: int,
            *,
            force: bool = False,
        ) -> "Snapshot.Node":
            return self._AddImpl(path, hash_value, file_size, force=force)

        # ----------------------------------------------------------------------
        def AddDir(
            self,
            path: Path,
            *,
            force: bool = False,
        ) -> "Snapshot.Node":
            return self._AddImpl(path, DirHashPlaceholder(explicitly_added=True), None, force=force)

        # ----------------------------------------------------------------------
        def ToJson(self) -> dict[str, Any]:
            result: dict[str, Any] = {}

            if self.is_file:
                assert self.file_size is not None
                assert not self.children

                result["hash_value"] = self.hash_value
                result["file_size"] = self.file_size

            elif self.is_dir:
                assert self.file_size is None

                result["hash_value"] = None
                result["children"] = {k: v.ToJson() for k, v in self.children.items()}

            else:
                assert False, self  # pragma: no cover

            return result

        # ----------------------------------------------------------------------
        @classmethod
        def FromJson(
            cls,
            name: Optional[str],
            parent: Optional["Snapshot.Node"],
            value: dict[str, Any],
        ) -> "Snapshot.Node":
            hash_value = value["hash_value"]

            if isinstance(hash_value, str):
                file_size = value["file_size"]
            else:
                hash_value = DirHashPlaceholder(explicitly_added=not value["children"])
                file_size = None

            result = cls(name, parent, hash_value, file_size)

            if result.is_dir:
                result.children = {k: cls.FromJson(k, result, v) for k, v in value["children"].items()}

            return result

        # ----------------------------------------------------------------------
        def CreateDiffs(
            self,
            other: Optional["Snapshot.Node"],
            file_compare_func: Callable[["Snapshot.Node", "Snapshot.Node"], bool],
        ) -> tuple[list[DiffResult], Optional[DiffOperation]]:
            diffs: list[DiffResult] = []

            if other is None:
                if self.is_dir and self.children:
                    for value in self.children.values():
                        diffs += value.CreateDiffs(None, file_compare_func)[0]

                else:
                    diffs.append(
                        DiffResult(
                            DiffOperation.add,
                            self.fullpath,
                            self.hash_value,
                            self.file_size,
                            None,
                            None,
                        ),
                    )

                return diffs, DiffOperation.add

            if self.is_file or other.is_file:
                if self.is_file and other.is_file:
                    if file_compare_func(self, other):
                        return [], None

                    diffs.append(
                        DiffResult(
                            DiffOperation.modify,
                            self.fullpath,
                            self.hash_value,
                            self.file_size,
                            other.hash_value,
                            other.file_size,
                        ),
                    )
                else:
                    # The type has changed
                    diffs.append(
                        DiffResult(
                            DiffOperation.remove,
                            other.fullpath,
                            None,
                            None,
                            other.hash_value,
                            other.file_size,
                        ),
                    )

                    diffs += self.CreateDiffs(None, file_compare_func)[0]

                assert diffs
                return diffs, DiffOperation.modify

            # We are looking at directories
            atomic_result: Optional[DiffOperation] = None

            # ----------------------------------------------------------------------
            def UpdateAtomicResult(
                result: Optional[DiffOperation],
            ) -> None:
                nonlocal atomic_result

                if atomic_result is None:
                    atomic_result = result
                elif result != atomic_result:
                    atomic_result = DiffOperation.modify

            # ----------------------------------------------------------------------

            for child_name, other_child in other.children.items():
                if child_name in self.children:
                    continue

                diffs.append(
                    DiffResult(
                        DiffOperation.remove,
                        other.fullpath / child_name,
                        None,
                        None,
                        other_child.hash_value,
                        other_child.file_size,
                    ),
                )

                UpdateAtomicResult(DiffOperation.remove)

            for child_name, this_child in self.children.items():
                child_diffs, child_result = this_child.CreateDiffs(
                    other.children.get(child_name, None),
                    file_compare_func,
                )

                diffs += child_diffs
                UpdateAtomicResult(child_result)

            # If all of the results are consistent, we can replace the diffs with a diff at this
            # level (unless this item has been explicitly added, in which case we should keep it
            # around).
            if atomic_result == DiffOperation.remove:
                assert isinstance(self.hash_value, DirHashPlaceholder)
                assert isinstance(other.hash_value, DirHashPlaceholder)

                if self.hash_value.explicitly_added or other.hash_value.explicitly_added:
                    # We don't want to remove the dir because it has been explicitly added.
                    # Keep the existing diffs and show that the node has been modified.
                    atomic_result = DiffOperation.modify
                else:
                    # Replace the existing diffs with a single diff to remove this dir.
                    diffs = [
                        DiffResult(
                            DiffOperation.remove,
                            other.fullpath,
                            None,
                            None,
                            other.hash_value,
                            other.file_size,
                        ),
                    ]

            assert (atomic_result is None and not diffs) or (atomic_result is not None and diffs), (
                atomic_result,
                diffs,
            )

            return diffs, atomic_result

        # ----------------------------------------------------------------------
        def Enum(self) -> Generator["Snapshot.Node", None, None]:
            if self.name is not None:
                yield self

            for child in self.children.values():
                yield from child.Enum()

        # ----------------------------------------------------------------------
        # ----------------------------------------------------------------------
        # ----------------------------------------------------------------------
        def _AddImpl(
            self,
            path: Path,
            hash_value: str | DirHashPlaceholder,
            file_size: Optional[int],
            *,
            force: bool,
        ) -> "Snapshot.Node":
            node = self

            for part in path.parent.parts:
                new_node = node.children.get(part, None)

                if new_node is None:
                    new_node = self.__class__(part, node, DirHashPlaceholder(explicitly_added=False), None)
                    node.children[part] = new_node

                node = new_node

            assert force or path.name not in node.children, path
            node.children[path.name] = self.__class__(path.name, node, hash_value, file_size)

            return self

    # ----------------------------------------------------------------------
    PERSISTED_FILE_NAME = "BackupSnapshot.json"

    # ----------------------------------------------------------------------
    # |
    # |  Public Data
    # |
    # ----------------------------------------------------------------------
    node: Node

    # ----------------------------------------------------------------------
    # |
    # |  Public Methods
    # |
    # ----------------------------------------------------------------------
    @classmethod
    def Calculate(
        cls,
        dm: DoneManager,
        inputs: list[Path],
        data_store: FileBasedDataStore,
        *,
        run_in_parallel: bool,
        quiet: bool = False,
        filter_filename_func: Optional[Callable[[Path], bool]] = None,
        calculate_hashes: bool = True,
    ) -> "Snapshot":
        # Validate that the inputs do not overlap
        assert inputs

        for input_item in inputs:
            item_type = data_store.GetItemType(input_item)

            if item_type != ItemType.File and item_type != ItemType.Dir:
                raise Exception(f"'{input_item}' is not a file or directory.")

        sorted_inputs = list(inputs)
        sorted_inputs.sort(key=lambda value: len(value.parts))

        for input_index in range(1, len(sorted_inputs)):
            input_item = sorted_inputs[input_index]

            for query_index in range(0, input_index):
                query_item = sorted_inputs[query_index]

                if PathEx.IsDescendant(input_item, query_item):
                    raise Exception(f"The input '{input_item}' overlaps with '{query_item}'.")

        # Continue with the calculation
        filter_filename_func = filter_filename_func or (lambda value: True)

        # ----------------------------------------------------------------------
        @dataclass(frozen=True)
        class InputInfo:
            # pylint: disable=missing-class-docstring

            # ----------------------------------------------------------------------
            filenames: list[Path]
            empty_dirs: list[Path]

            # ----------------------------------------------------------------------
            def __bool__(self) -> bool:
                return bool(self.filenames) or bool(self.empty_dirs)

        # ----------------------------------------------------------------------

        all_input_infos: dict[Path, InputInfo] = {}

        # ----------------------------------------------------------------------
        def OnNestedExit():
            # We need to do some extra work because inflect doesn't work when we need a word between
            # the number and plural where the singular form of the plural ends in 'y'.
            num_empty_dirs = sum(len(input_info.empty_dirs) for input_info in all_input_infos.values())

            return "{} found, {} empty {} found".format(
                inflect.no(
                    "file",
                    sum(len(input_info.filenames) for input_info in all_input_infos.values()),
                ),
                num_empty_dirs,
                inflect.plural("directory", num_empty_dirs),
            )

        # ----------------------------------------------------------------------

        with dm.Nested("Discovering files...", OnNestedExit) as calculating_dm:
            # ----------------------------------------------------------------------
            def TransformTask(
                context: Any,
                status: ExecuteTasks.Status,
            ) -> ExecuteTasks.TransformResultComplete:
                input_item = cast(Path, context)
                del context

                filenames: list[Path] = []
                empty_dirs: list[Path] = []

                input_item_type = data_store.GetItemType(input_item)

                if input_item_type == ItemType.File:
                    filenames.append(input_item)

                elif input_item_type == ItemType.Dir:
                    for this_root, these_directories, these_filenames in data_store.Walk(input_item):
                        if not these_directories and not these_filenames:
                            empty_dirs.append(this_root)
                            continue

                        for this_filename in these_filenames:
                            fullpath = this_root / this_filename

                            if data_store.GetItemType(fullpath) != ItemType.File:
                                status.OnInfo(f"The file '{fullpath}' is not a supported item type.")
                                continue

                            if not filter_filename_func(fullpath):
                                status.OnInfo(
                                    f"The file '{fullpath}' has been excluded by the filter function.",
                                    verbose=True,
                                )

                                continue

                            filenames.append(fullpath)

                else:
                    # By default, FileSystemDataStore and SFTPDataStore will not get here, as
                    # the will not traverse directory symlinks.
                    raise Exception(f"'{input_item}' is not a supported item type.")  # pragma: no cover

                short_desc = "{} found".format(inflect.no("file", len(filenames)))

                status.OnInfo(
                    f"{short_desc} in '{input_item}'",
                    verbose=True,
                )

                return ExecuteTasks.TransformResultComplete(
                    InputInfo(filenames, empty_dirs),
                    0,
                    short_desc,
                )

            # ----------------------------------------------------------------------

            complete_input_infos = ExecuteTasks.TransformTasks(
                calculating_dm,
                "Processing",
                [ExecuteTasks.TaskData(str(input_item), input_item) for input_item in inputs],
                TransformTask,
                quiet=quiet,
                max_num_threads=None if run_in_parallel else 1,
                refresh_per_second=EXECUTE_TASKS_REFRESH_PER_SECOND,
            )

            if calculating_dm.result != 0:
                raise Exception("Errors were encountered while calculating files.")

            for this_root, input_info in zip(inputs, complete_input_infos):
                assert isinstance(input_info, InputInfo), input_info
                all_input_infos[this_root] = input_info

        if not any(input_info for input_info in all_input_infos.values()):
            return cls(Snapshot.Node(None, None, DirHashPlaceholder(explicitly_added=False), None))

        with dm.Nested(
            "\n" + ("Calculating hashes..." if calculate_hashes else "Retrieving file information..."),
        ) as hashes_dm:
            # ----------------------------------------------------------------------
            def PrepareTask(
                context: Any,
                on_simple_status_func: Callable[[str], None],  # pylint: disable=unused-argument
            ) -> tuple[int, ExecuteTasks.TransformTasksExTypes.TransformFuncType]:
                input_item = cast(Path, context)
                del context

                # ----------------------------------------------------------------------
                def Execute(
                    status: ExecuteTasks.Status,
                ) -> Optional[tuple[str, int]]:
                    if data_store.GetItemType(input_item) is None:
                        status.OnInfo(f"'{item_type}' no longer exists.")
                        return None

                    if not calculate_hashes:
                        hash_value = "not calculated"
                    else:
                        hash_value = CalculateHash(
                            data_store,
                            input_item,
                            lambda bytes_hashed: cast(None, status.OnProgress(bytes_hashed, None)),
                        )

                    return hash_value, data_store.GetFileSize(input_item)

                # ----------------------------------------------------------------------

                if data_store.GetItemType(input_item) is None:
                    file_size = 1
                else:
                    file_size = data_store.GetFileSize(input_item)

                return file_size, Execute

            # ----------------------------------------------------------------------

            file_infos: list[Optional[tuple[str, int]]] = []

            tasks: list[ExecuteTasks.TaskData] = [
                ExecuteTasks.TaskData(str(filename), filename)
                for filename in itertools.chain(
                    *(input_info.filenames for input_info in all_input_infos.values())
                )
            ]

            if tasks:
                file_infos += cast(
                    list[Optional[tuple[str, int]]],
                    ExecuteTasks.TransformTasksEx(
                        hashes_dm,
                        "Processing",
                        tasks,
                        PrepareTask,
                        quiet=quiet,
                        max_num_threads=None if run_in_parallel else 1,
                        refresh_per_second=EXECUTE_TASKS_REFRESH_PER_SECOND,
                    ),
                )

                if hashes_dm.result != 0:
                    raise Exception("Errors were encountered while hashing files.")

        with dm.Nested("\nOrganizing results..."):
            root = Snapshot.Node(None, None, DirHashPlaceholder(explicitly_added=False), None)

            file_info_offset = 0

            for input_info in all_input_infos.values():
                for filename in input_info.filenames:
                    file_info = file_infos[file_info_offset]
                    file_info_offset += 1

                    if file_info is None:
                        continue

                    hash_value, file_size = file_info

                    root.AddFile(filename, hash_value, file_size)

                for directory in input_info.empty_dirs:
                    root.AddDir(directory)

        return cls(root)

    # ----------------------------------------------------------------------
    @classmethod
    def IsPersisted(
        cls,
        data_store: FileBasedDataStore,
        *,
        snapshot_filename: Optional[Path] = None,
    ) -> bool:
        snapshot_filename = snapshot_filename or Path(cls.PERSISTED_FILE_NAME)

        return data_store.GetItemType(snapshot_filename) == ItemType.File

    # ----------------------------------------------------------------------
    @classmethod
    def LoadPersisted(
        cls,
        dm: DoneManager,
        data_store: FileBasedDataStore,
        *,
        snapshot_filename: Optional[Path] = None,
    ) -> "Snapshot":
        snapshot_filename = snapshot_filename or Path(cls.PERSISTED_FILE_NAME)

        with dm.Nested(f"Reading '{snapshot_filename}'...") as reading_dm:
            content = bytes()

            with reading_dm.YieldStdout() as stdout_context:
                stdout_context.persist_content = False

                with Progress(
                    *Progress.get_default_columns(),
                    TimeElapsedColumn(),
                    "{task.fields[status]}",
                    console=Capabilities.Get(stdout_context.stream).CreateRichConsole(stdout_context.stream),
                    transient=True,
                ) as progress_bar:
                    total_progress_id = progress_bar.add_task(
                        f"{stdout_context.line_prefix}Total Progress",
                        total=data_store.GetFileSize(snapshot_filename),
                        status="",
                        visible=True,
                    )

                    with data_store.Open(snapshot_filename, "rb") as source:
                        while True:
                            chunk = source.read(16384)
                            if not chunk:
                                break

                            content += chunk

                            progress_bar.update(total_progress_id, advance=len(chunk))

            try:
                return Snapshot(Snapshot.Node.FromJson(None, None, json.loads(content.decode("UTF-8"))))
            except KeyError as ex:
                raise Exception(f"The content at '{snapshot_filename}' is not valid.") from ex

    # ----------------------------------------------------------------------
    def Persist(
        self,
        dm: DoneManager,
        data_store: FileBasedDataStore,
        *,
        snapshot_filename: Optional[Path] = None,
    ) -> None:
        snapshot_filename = snapshot_filename or Path(self.__class__.PERSISTED_FILE_NAME)

        with dm.Nested(f"Writing '{snapshot_filename}'..."):
            with data_store.Open(snapshot_filename, "w") as f:
                json.dump(self.node.ToJson(), f)

    # ----------------------------------------------------------------------
    def Diff(
        self,
        other: "Snapshot",
        *,
        compare_hashes: bool = True,
    ) -> Generator[DiffResult, None, None]:
        """Enumerates the differences between two Snapshots"""

        if compare_hashes:

            def CompareFunc(a, b) -> bool:
                return a.hash_value == b.hash_value
        else:

            def CompareFunc(a, b) -> bool:
                return a.file_size == b.file_size

        yield from self.node.CreateDiffs(other.node, CompareFunc)[0]
