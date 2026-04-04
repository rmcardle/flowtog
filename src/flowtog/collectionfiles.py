import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Generator, Iterable, Self

from flowtog.collectiondirectories import CollectionDirectories
from flowtog.collectionfile import CollectionFile
from flowtog.collectionfilenameparser import CollectionFilenameParser
from flowtog.config import CollectionConfig
from flowtog.filegroup import FileGroup
from flowtog.filetype import FileType, get_file_type
from flowtog.path_utils import get_filename


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionFiles:
    collection: CollectionConfig
    _directories: CollectionDirectories
    _filename_parser: CollectionFilenameParser

    _group_names: set[str] = field(init=False)
    _groups_by_name: dict[str, FileGroup] = field(init=False)
    _xmp_files: list[CollectionFile] = field(init=False)

    @classmethod
    def from_collection(cls, collection: CollectionConfig) -> Self:
        return cls(
            collection=collection,
            _directories=CollectionDirectories.from_collection(collection),
            _filename_parser=CollectionFilenameParser.from_collection(collection),
        )

    def __post_init__(self) -> None:
        self._init_files_from_collection()

    def _init_files_from_collection(self) -> None:
        group_names: set[str] = set()
        files_by_group_name: dict[str, list[CollectionFile]] = defaultdict(list)
        xmp_files: list[CollectionFile] = []

        # CollectionDirectories.get_directory_type() assumes that all paths are absolute
        # That will only be true if os.scandir() is called with absolute paths
        # CollectionDirectories.valid_directories were already made absolute in Config.load()
        for directory_entry in _get_directory_entries(self._directories.valid_directories):
            if (directory_entry.is_file()
                    and (group_name := self._filename_parser.get_group_name(directory_entry))):
                group_names.add(group_name)
                file = self._create_collection_file(directory_entry)
                files_by_group_name[group_name].append(file)
                if file.file_type == FileType.XMP:
                    xmp_files.append(file)

        groups_by_name: dict[str, FileGroup] = {}
        for group_name in group_names:
            if not (group_num := self._filename_parser.get_file_num(group_name)):
                logging.error(f"{group_name}: Could not determine file number")
                continue
            group = FileGroup.from_files(group_name, group_num, files_by_group_name[group_name])
            groups_by_name[group_name] = group

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_group_names", sorted(group_names))
        object.__setattr__(self, "_groups_by_name", groups_by_name)
        object.__setattr__(self, "_xmp_files", xmp_files)

    def _create_collection_file(self,
                                direntry: os.DirEntry[str]) -> CollectionFile:
        file_type = get_file_type(direntry)
        edit_num_str = self._filename_parser.get_edit_num(direntry)
        directory_type = self._directories.get_directory_type(direntry)
        return CollectionFile(
            direntry=direntry,
            path=direntry.path,
            filename=get_filename(direntry),
            file_type=file_type,
            directory_type=directory_type,
            is_edit=bool(edit_num_str),
            edit_num=int(edit_num_str) if edit_num_str else 0,
        )

    @property
    def group_names(self) -> Iterable[str]:
        return self._group_names

    def get_group_num(self, group_name: str) -> int | None:
        return self._filename_parser.get_file_num(group_name)

    def get_group(self, group_name: str) -> FileGroup:
        return self._groups_by_name[group_name]


def _get_directory_entries(directory: str | Iterable[str]) -> Generator[os.DirEntry]:
    # We can't check if directory is an Iterable because str is also Iterable
    if not isinstance(directory, str):
        for d in directory:
            yield from _get_directory_entries(d)
        return

    with os.scandir(directory) as iterator:
        yield from iterator
