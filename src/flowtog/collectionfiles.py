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
    from collections.abc import Generator, Iterable

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# We only need to keep track of groups in these directories for CollectionFiles.get_groups_by_directory()
_GROUP_DIRECTORY_TYPES = [
    DirectoryType.UNSORTED,
]

# We only need to keep track of XMP files in these directories for CollectionFiles.get_directory_files_by_type()
_XMP_FILE_DIRECTORY_TYPES = [
    DirectoryType.UNSORTED,
    DirectoryType.PHOTOS,
]


@dataclass(frozen=True)
class CollectionFiles:
    collection: CollectionConfig
    directories: CollectionDirectories
    _filename_parser: CollectionFilenameParser

    _group_names: list[str] = field(init=False)
    last_group_num: int = field(init=False)
    _group_name_to_group: dict[str, FileGroup] = field(init=False)
    _directory_type_to_groups: dict[DirectoryType, list[FileGroup]] = field(init=False)
    _directory_type_to_xmp_files: dict[DirectoryType, list[CollectionFile]] = field(init=False)

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

        sorted_group_names = sorted(group_names)
        last_group_num = self.collection.start_num - 1
        group_name_to_group: dict[str, FileGroup] = {}
        directory_type_to_groups: dict[DirectoryType, list[FileGroup]] = defaultdict(list)

        for group_name in sorted_group_names:
            if not (group_num := self._filename_parser.get_file_num(group_name)):
                _LOG.error(f"{group_name}: Could not determine file number")
                continue

            last_group_num = max(last_group_num, group_num)
            group_files = group_name_to_files[group_name]
            group = FileGroup.from_files(group_name, group_num, group_files)
            group_name_to_group[group_name] = group

            directory_type = group_files[0].directory_type
            if all(file.directory_type == directory_type for file in group_files):
                directory_type_to_groups[directory_type].append(group)

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_group_names", sorted_group_names)
        object.__setattr__(self, "last_group_num", last_group_num)
        object.__setattr__(self, "_group_name_to_group", group_name_to_group)
        object.__setattr__(self, "_directory_type_to_groups", directory_type_to_groups)
        object.__setattr__(self, "_directory_type_to_xmp_files", directory_type_to_xmp_files)

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

    def get_groups_by_directory(self, directory_type: DirectoryType) -> list[FileGroup]:
        if directory_type in _GROUP_DIRECTORY_TYPES:
            return self._directory_type_to_groups[directory_type]
        raise NotImplementedError

    def get_directory_files_by_type(self,
                                    directory_type: DirectoryType,
                                    file_type: FileType) -> list[CollectionFile]:
        if (file_type == FileType.XMP
                and directory_type in _XMP_FILE_DIRECTORY_TYPES):
            return self._directory_type_to_xmp_files[directory_type]
        raise NotImplementedError


def _get_directory_entries(directory: Path | Iterable[Path]) -> Generator[os.DirEntry[str]]:
    if isinstance(directory, Path):
        with os.scandir(directory) as iterator:
            yield from iterator
        return

    for d in directory:
        yield from _get_directory_entries(d)
