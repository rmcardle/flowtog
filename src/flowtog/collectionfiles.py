import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Self

from flowtog.collectiondirectories import CollectionDirectories, DirectoryType
from flowtog.collectionfile import CollectionFile
from flowtog.collectionfilenameparser import CollectionFilenameParser
from flowtog.filegroup import FileGroup
from flowtog.filetype import FileType, get_file_type
from flowtog.path_utils import get_filename, get_filename_stem

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionFiles:
    collection: CollectionConfig
    directories: CollectionDirectories
    _filename_parser: CollectionFilenameParser

    _group_names: list[str] = field(init=False)
    last_group_num: int = field(init=False)
    _groups_by_name: dict[str, FileGroup] = field(init=False)
    _xmp_files: list[CollectionFile] = field(init=False)
    _xmp_files_in_photos_dir: list[CollectionFile] = field(init=False)

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
        files_by_group_name: dict[str, list[CollectionFile]] = defaultdict(list)
        xmp_files: list[CollectionFile] = []
        xmp_files_in_photos_dir: list[CollectionFile] = []

        # CollectionDirectories.get_directory_type() assumes that all paths are absolute
        # That will only be true if os.scandir() is called with absolute paths
        # CollectionDirectories.valid_directories were already made absolute in Config.load()
        for directory_entry in _get_directory_entries(self.directories.valid_directories):
            if (directory_entry.is_file()
                    and (group_name := self._filename_parser.get_group_name(directory_entry))):
                group_names.add(group_name)
                file = self._create_collection_file(directory_entry)
                files_by_group_name[group_name].append(file)
                if file.file_type == FileType.XMP:
                    if file.directory_type in [DirectoryType.UNSORTED, DirectoryType.REJECTED]:
                        xmp_files.append(file)
                    if file.directory_type == DirectoryType.PHOTOS:
                        xmp_files_in_photos_dir.append(file)

        groups_by_name: dict[str, FileGroup] = {}
        last_group_num = self.collection.start_num - 1
        for group_name in group_names:
            if not (group_num := self._filename_parser.get_file_num(group_name)):
                _LOG.error(f"{group_name}: Could not determine file number")
                continue
            group = FileGroup.from_files(group_name, group_num, files_by_group_name[group_name])
            groups_by_name[group_name] = group
            last_group_num = max(last_group_num, group_num)

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_group_names", sorted(group_names))
        object.__setattr__(self, "last_group_num", last_group_num)
        object.__setattr__(self, "_groups_by_name", groups_by_name)
        object.__setattr__(self, "_xmp_files", xmp_files)
        object.__setattr__(self, "_xmp_files_in_photos_dir", xmp_files_in_photos_dir)

    def _create_collection_file(self,
                                direntry: os.DirEntry[str]) -> CollectionFile:
        file_type = get_file_type(direntry)
        edit_num_str = self._filename_parser.get_edit_num(direntry)
        directory_type = self.directories.get_directory_type(direntry)
        return CollectionFile(
            direntry=direntry,
            path=direntry.path,
            filename=get_filename(direntry),
            filename_stem=get_filename_stem(direntry),
            file_type=file_type,
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
        return self._groups_by_name.get(group_name)

    def get_group_by_num(self, group_num: int) -> FileGroup | None:
        return self.get_group_by_name(self.collection.filename_format.format(file_num=group_num))

    def get_files_by_type(self, file_type: FileType) -> list[CollectionFile]:
        assert file_type == FileType.XMP
        return self._xmp_files

    def get_files_by_directory_and_type(self,
                                        directory_type: DirectoryType,
                                        file_type: FileType) -> list[CollectionFile]:
        assert directory_type == DirectoryType.PHOTOS
        assert file_type == FileType.XMP
        return self._xmp_files_in_photos_dir


def _get_directory_entries(directory: str | Iterable[str]) -> Generator[os.DirEntry[str]]:
    # We can't check if directory is an Iterable because str is also Iterable
    if not isinstance(directory, str):
        for d in directory:
            yield from _get_directory_entries(d)
        return

    with os.scandir(directory) as iterator:
        yield from iterator
