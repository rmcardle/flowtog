from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from flowtog.config import CollectionConfig


class DirectoryType(Enum):
    ORIGINALS = "originals_dir"
    PHOTOS = "photos_dir"
    PREVIOUS_EDITS = "previous_edits_dir"
    RAW = "raw_dir"
    REJECTED = "rejected_dir"
    UNSORTED = "unsorted_dir"
    OTHER = None


@dataclass(frozen=True)
class CollectionDirectories:
    _directories_by_type: dict[DirectoryType, Path]
    _type_by_directory: dict[Path, DirectoryType] = field(init=False)

    @classmethod
    def from_collection(cls, collection: CollectionConfig) -> Self:
        return cls(
            _directories_by_type=CollectionDirectories._get_directories_by_type(collection),
        )

    @staticmethod
    def _get_directories_by_type(collection: CollectionConfig) -> dict[DirectoryType, Path]:
        return {DirectoryType(directory_type): directory
                for directory_type, directory in collection.directories.items()}

    def __post_init__(self) -> None:
        self._init_type_by_directory()

    def _init_type_by_directory(self) -> None:
        type_by_directory = {directory: directory_type
                             for directory_type, directory in self._directories_by_type.items()}
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_type_by_directory", type_by_directory)

    def __iter__(self) -> Iterator[Path]:
        return (d for d in self._directories_by_type.values())

    def __getitem__(self, directory_type: DirectoryType) -> Path:
        return self._directories_by_type[directory_type]

    @property
    def valid_directories(self) -> list[Path]:
        return [d for d in self._dirs if d.is_dir()]

    @property
    def _dirs(self) -> list[Path]:
        return list(self._directories_by_type.values())

    def get_directory_type(self, path: Path) -> DirectoryType:
        return self._type_by_directory.get(path, DirectoryType.OTHER)
