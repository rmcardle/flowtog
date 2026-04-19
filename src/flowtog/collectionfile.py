import os
from dataclasses import dataclass
from datetime import UTC, datetime
from os import fspath
from typing import TYPE_CHECKING, Self

from flowtog.filetype import get_file_type
from flowtog.path_utils import get_directory, get_filename, get_filename_stem

if TYPE_CHECKING:
    from flowtog.collectiondirectories import DirectoryType
    from flowtog.filetype import FileType


@dataclass
class CollectionFile(os.PathLike[str]):
    path: str
    filename: str
    filename_stem: str
    file_type: FileType
    directory: str
    directory_type: DirectoryType
    is_edit: bool
    edit_num: int
    size: int
    modified_time: datetime
    _fspath: str

    @classmethod
    def from_directory_entry(cls,
                             direntry: os.DirEntry[str],
                             *,
                             directory_type: DirectoryType,
                             is_edit: bool,
                             edit_num: int) -> Self:
        stat = direntry.stat()
        return cls(
            path=direntry.path,
            filename=get_filename(direntry),
            filename_stem=get_filename_stem(direntry),
            file_type=get_file_type(direntry),
            directory=get_directory(direntry),
            directory_type=directory_type,
            is_edit=is_edit,
            edit_num=edit_num,
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            _fspath=fspath(direntry),
        )

    # Implement os.PathLike[str]
    def __fspath__(self) -> str:
        return self._fspath
