import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Self

from flowtog.path_utils import PathArg, get_directory


class DirectoryType(Enum):
    Originals = "originals_dir"
    Photos = "photos_dir"
    PreviousEdits = "previous_edits_dir"
    Raw = "raw_dir"
    Rejected = "rejected_dir"
    Unsorted = "unsorted_dir"
    Other = None


@dataclass(frozen=True)
class CollectionDirectories:
    directories_by_type: dict[DirectoryType, str]
    type_by_normalized_directory: dict[str, DirectoryType] = field(init=False)

    @classmethod
    def from_collection(cls, collection) -> Self:
        return cls(
            directories_by_type=CollectionDirectories._get_directories_by_type(collection),
        )

    @staticmethod
    def _get_directories_by_type(collection) -> dict[DirectoryType, str]:
        return {DirectoryType(directory_type): directory
                for directory_type, directory in collection.directories.items()}

    def __post_init__(self) -> None:
        self._init_type_by_normalized_directory()

    def _init_type_by_normalized_directory(self) -> None:
        type_by_normalized_directory: dict[str, DirectoryType] = {}
        for directory_type, directory in self.directories_by_type.items():
            # directories_by_type were already made absolute in Config.load()
            # so we only need to normalize case
            type_by_normalized_directory[os.path.normcase(directory)] = directory_type
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "type_by_normalized_directory", type_by_normalized_directory)

    @property
    def valid_directories(self) -> list[str]:
        return [d for d in self._dirs if os.path.isdir(d)]

    @property
    def _dirs(self) -> list[str]:
        return list(self.directories_by_type.values())

    def get_directory_type(self, file: PathArg) -> DirectoryType:
        # The file path should already be absolute because we only used absolute paths with os.scandir()
        # so we only need to normalize case for comparison
        file_dir = os.path.normcase(get_directory(file))
        return self.type_by_normalized_directory.get(file_dir, DirectoryType.Other)
