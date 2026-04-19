import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Self

from flowtog.path_utils import PathArg, get_directory

if TYPE_CHECKING:
    from collections.abc import Iterator

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
    _type_by_normalized_directory: dict[str, DirectoryType] = field(init=False)

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
        self._init_type_by_normalized_directory()

    def _init_type_by_normalized_directory(self) -> None:
        type_by_normalized_directory: dict[str, DirectoryType] = {}
        for directory_type, directory in self._directories_by_type.items():
            # directories_by_type were already made absolute in Config.load()
            # so we only need to normalize case
            type_by_normalized_directory[os.path.normcase(directory)] = directory_type
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_type_by_normalized_directory", type_by_normalized_directory)

    def __iter__(self) -> Iterator[Path]:
        return (Path(d) for d in self._directories_by_type.values())

    def __getitem__(self, directory_type: DirectoryType) -> Path:
        return Path(self._directories_by_type[directory_type])

    @property
    def valid_directories(self) -> list[str]:
        return [str(d) for d in self._dirs if d.is_dir()]

    @property
    def _dirs(self) -> list[Path]:
        return list(self._directories_by_type.values())

    def get_directory_type(self, file: PathArg) -> DirectoryType:
        # The file path should already be absolute because we only used absolute paths with os.scandir()
        # so we only need to normalize case for comparison
        file_dir = os.path.normcase(get_directory(file))
        return self._type_by_normalized_directory.get(file_dir, DirectoryType.OTHER)
