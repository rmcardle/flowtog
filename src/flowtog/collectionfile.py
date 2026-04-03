import os
from dataclasses import dataclass
from os import fspath

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType


@dataclass
class CollectionFile(os.PathLike):
    direntry: os.DirEntry[str]
    path: str
    filename: str
    file_type: FileType
    directory_type: DirectoryType
    is_edit: bool
    edit_num: int

    def __fspath__(self) -> str:
        return fspath(self.direntry)
