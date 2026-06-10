import os
from dataclasses import dataclass
from datetime import UTC, datetime
from os import fspath
from pathlib import Path
from typing import TYPE_CHECKING, Self

from flowtog.filetype import get_file_type

if TYPE_CHECKING:
    from flowtog.collectiondirectories import DirectoryType
    from flowtog.filetype import FileType


@dataclass
class CollectionFile(os.PathLike[str]):
    path: Path
    filename: str
    filename_stem: str
    file_type: FileType
    directory: Path
    directory_type: DirectoryType
    is_edit: bool
    edit_num: int
    size: int
    modified_time: datetime

    @classmethod
    def from_directory_entry(cls,
                             direntry: os.DirEntry[str],
                             *,
                             directory_type: DirectoryType,
                             is_edit: bool,
                             edit_num: int) -> Self:
        path = _get_normalized_path(direntry)
        stat = direntry.stat()  # Use the cached stat_result in direntry so we don't need to make another system call
        return cls(
            path=path,
            filename=path.name,
            filename_stem=path.stem,
            file_type=get_file_type(path),
            directory=path.parent,
            directory_type=directory_type,
            is_edit=is_edit,
            edit_num=edit_num,
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )

    # Implement os.PathLike[str]
    def __fspath__(self) -> str:
        return fspath(self.path)

    def __str__(self) -> str:
        return str(self.path)


def _get_normalized_path(direntry: os.DirEntry[str]) -> Path:
    return Path(os.path.normpath(os.fspath(direntry))).resolve()
