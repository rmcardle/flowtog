from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from flowtog.filetype import FileType

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flowtog.collectionfile import CollectionFile


@dataclass(frozen=True)
class FileGroup:
    group_name: str
    group_num: int
    files: list[CollectionFile]
    file_type_to_files: dict[FileType, list[CollectionFile]] = field(init=False)

    @classmethod
    def from_files(cls, group_name: str, group_num: int, files: list[CollectionFile]) -> Self:
        return cls(
            group_name=group_name,
            group_num=group_num,
            files=files,
        )

    def __post_init__(self) -> None:
        self._init_file_type_to_files()

    def _init_file_type_to_files(self) -> None:
        file_type_to_files: dict[FileType, list[CollectionFile]] = defaultdict(list)
        for file in self.files:
            file_type_to_files[file.file_type].append(file)

        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "file_type_to_files", file_type_to_files)

    @property
    def file_types(self) -> Iterator[FileType]:
        yield from self.file_type_to_files.keys()

    @property
    def has_edits(self) -> bool:
        return (FileType.JPEG in self.file_types
                and any(f.is_edit for f in self.file_type_to_files[FileType.JPEG]))

    @property
    def next_edit_num(self) -> int:
        return max(e.edit_num for e in self.files) + 1

    def get_single_file_from_type(self, file_type: FileType) -> CollectionFile:
        if len(files := self.file_type_to_files.get(file_type, [])) == 1:
            return files[0]

        msg = "\n\t".join([f"The group {self.group_name} does not contain exactly one {file_type} file "
                           f"(it has {len(files)})",
                           *(str(file.path) for file in files)])
        raise ValueError(msg)
