import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self

from flowtog.collectiondirectories import CollectionDirectories, DirectoryType
from flowtog.collectionfile import CollectionFile
from flowtog.collectionfilenameparser import CollectionFilenameParser
from flowtog.filegroup import FileGroup
from flowtog.filetype import FileType

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# We only need to keep track of XMP files in these directories for CollectionFiles.get_directory_files_by_type()
_XMP_FILE_DIRECTORY_TYPES = [
    DirectoryType.UNSORTED,
    DirectoryType.PHOTOS,
]


@dataclass(frozen=True)
class _ScanCollectionFilesResult:
    group_names: list[str]
    group_name_to_files: dict[str, list[CollectionFile]]
    directory_type_to_xmp_files: dict[DirectoryType, list[CollectionFile]]


@dataclass(frozen=True)
class _BuildGroupsResult:
    last_group_num: int
    group_name_to_group: dict[str, FileGroup]
    groups_in_unsorted_dir: list[FileGroup]
    selected_groups_with_edits: list[FileGroup]


@dataclass(frozen=True)
class CollectionFiles:
    collection: CollectionConfig
    directories: CollectionDirectories
    _filename_parser: CollectionFilenameParser

    _group_names: list[str] = field(init=False)
    last_group_num: int = field(init=False)
    _group_name_to_group: dict[str, FileGroup] = field(init=False)
    groups_in_unsorted_dir: list[FileGroup] = field(init=False)
    _directory_type_to_xmp_files: dict[DirectoryType, list[CollectionFile]] = field(init=False)
    selected_groups_with_edits: list[FileGroup] = field(init=False)

    @classmethod
    def from_collection(cls, collection: CollectionConfig) -> Self:
        return cls(
            collection=collection,
            directories=CollectionDirectories.from_collection(collection),
            _filename_parser=CollectionFilenameParser.from_collection(collection),
        )

    def __post_init__(self) -> None:
        self._init_files_from_collection()

    def _init_files_from_collection(self) -> None:
        scan_collection_files_result = self._scan_collection_files()
        build_groups_result = self._build_groups(scan_collection_files_result.group_names,
                                                 scan_collection_files_result.group_name_to_files)

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_group_names", scan_collection_files_result.group_names)
        object.__setattr__(self, "last_group_num", build_groups_result.last_group_num)
        object.__setattr__(self, "_group_name_to_group", build_groups_result.group_name_to_group)
        object.__setattr__(self, "groups_in_unsorted_dir", build_groups_result.groups_in_unsorted_dir)
        object.__setattr__(self,
                           "_directory_type_to_xmp_files",
                           scan_collection_files_result.directory_type_to_xmp_files)
        object.__setattr__(self,
                           "selected_groups_with_edits",
                           build_groups_result.selected_groups_with_edits)

    def _scan_collection_files(self) -> _ScanCollectionFilesResult:
        group_names: set[str] = set()
        group_name_to_files: dict[str, list[CollectionFile]] = defaultdict(list)
        directory_type_to_xmp_files: dict[DirectoryType, list[CollectionFile]] = defaultdict(list)

        for directory_entry in _get_directory_entries(self.directories.valid_directories):
            if not (directory_entry.is_file()
                    and (group_name := self._filename_parser.get_group_name(directory_entry))):
                continue

            group_names.add(group_name)
            file = self._create_collection_file(directory_entry)
            group_name_to_files[group_name].append(file)

            if (file.file_type == FileType.XMP
                    and file.directory_type in _XMP_FILE_DIRECTORY_TYPES):
                directory_type_to_xmp_files[file.directory_type].append(file)

        return _ScanCollectionFilesResult(
            group_names=sorted(group_names),
            group_name_to_files=group_name_to_files,
            directory_type_to_xmp_files=directory_type_to_xmp_files,
        )

    def _build_groups(self,
                      group_names: list[str],
                      group_name_to_files: dict[str, list[CollectionFile]]) -> _BuildGroupsResult:
        last_group_num = self.collection.start_num - 1
        group_name_to_group: dict[str, FileGroup] = {}
        groups_in_unsorted_dir: list[FileGroup] = []
        selected_groups_with_edits: list[FileGroup] = []

        for group_name in group_names:
            if not (group_num := self._filename_parser.get_file_num(group_name)):
                _LOG.error(f"{group_name}: Could not determine file number")
                continue

            last_group_num = max(last_group_num, group_num)
            group_files = group_name_to_files[group_name]
            group = FileGroup.from_files(group_name, group_num, group_files)
            group_name_to_group[group_name] = group

            if all(file.directory_type == DirectoryType.UNSORTED for file in group_files):
                groups_in_unsorted_dir.append(group)

            # We'll consider a group selected if it has no files in the unsorted or rejected directories
            if (any(file.is_edit for file in group_files)
                and not any(file.directory_type in (DirectoryType.UNSORTED, DirectoryType.REJECTED)
                            for file in group_files)):
                selected_groups_with_edits.append(group)

        return _BuildGroupsResult(
            last_group_num=last_group_num,
            group_name_to_group=group_name_to_group,
            groups_in_unsorted_dir=groups_in_unsorted_dir,
            selected_groups_with_edits=selected_groups_with_edits,
        )

    def _create_collection_file(self,
                                direntry: os.DirEntry[str]) -> CollectionFile:
        directory = Path(direntry.path).parent
        directory_type = self.directories.get_directory_type(directory)
        edit_num_str = self._filename_parser.get_edit_num(direntry)
        return CollectionFile.from_directory_entry(
            direntry,
            directory_type=directory_type,
            is_edit=bool(edit_num_str),
            edit_num=int(edit_num_str) if edit_num_str else 0,
        )

    @property
    def group_count(self) -> int:
        return len(self._group_names)

    @property
    def group_names(self) -> Iterable[str]:
        return self._group_names

    @property
    def last_group(self) -> FileGroup | None:
        return self.get_group_by_num(self.last_group_num)

    def get_group_num(self, group_name: str) -> int | None:
        return self._filename_parser.get_file_num(group_name)

    def get_group_by_name(self, group_name: str) -> FileGroup | None:
        return self._group_name_to_group.get(group_name)

    def get_group_by_num(self, group_num: int) -> FileGroup | None:
        return self.get_group_by_name(self.collection.filename_format.format(file_num=group_num))

    def get_directory_files_by_type(self,
                                    directory_type: DirectoryType,
                                    file_type: FileType) -> Iterator[CollectionFile]:
        if (file_type == FileType.XMP
                and directory_type in _XMP_FILE_DIRECTORY_TYPES):
            yield from self._directory_type_to_xmp_files[directory_type]
            return
        raise NotImplementedError


def _get_directory_entries(directory: Path | Iterable[Path]) -> Iterator[os.DirEntry[str]]:
    if isinstance(directory, Path):
        with os.scandir(directory) as iterator:
            yield from iterator
        return

    for d in directory:
        yield from _get_directory_entries(d)
