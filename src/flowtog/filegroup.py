from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from flowtog.filetype import FileType

if TYPE_CHECKING:
    from flowtog.collectionfile import CollectionFile


@dataclass(frozen=True)
class FileGroup:
    group_name: str
    group_num: int
    files: list[CollectionFile]
    _files_by_type: dict[FileType, list[CollectionFile]] = field(init=False)

    @classmethod
    def from_files(cls, group_name: str, group_num: int, files: list[CollectionFile]) -> Self:
        return cls(
            group_name=group_name,
            group_num=group_num,
            files=files,
        )

    def __post_init__(self) -> None:
        self._init_files_by_type()

    def _init_files_by_type(self) -> None:
        files_by_type: dict[FileType, list[CollectionFile]] = defaultdict(list)
        for file in self.files:
            files_by_type[file.file_type].append(file)

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_files_by_type", files_by_type)

    @property
    def file_types(self) -> list[FileType]:
        return list(self._files_by_type.keys())

    def get_type_files(self, file_type: FileType) -> list[CollectionFile]:
        return self._files_by_type[file_type]

    @property
    def has_edits(self) -> bool:
        return (FileType.JPEG in self.file_types
                and any(f.is_edit for f in self.get_type_files(FileType.JPEG)))

    @property
    def next_edit_num(self) -> int:
        return max(e.edit_num for e in self.files) + 1
