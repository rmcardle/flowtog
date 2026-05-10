import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Final, Self

from flowtog.log_utils import log_file_path

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


class DirectoryType(Enum):
    ORIGINALS = "originals_dir"
    PHOTOS = "photos_dir"
    PREVIOUS_EDITS = "previous_edits_dir"
    RAW = "raw_dir"
    REJECTED = "rejected_dir"
    UNSORTED = "unsorted_dir"
    VIDEOS = "videos_dir"
    VIDEOS_PROXY = "videos_proxy_dir"
    OTHER = None


@dataclass(frozen=True)
class CollectionDirectories:
    _directory_type_to_path: dict[DirectoryType, Path]
    _path_to_directory_type: dict[Path, DirectoryType] = field(init=False)

    @classmethod
    def from_collection(cls, collection: CollectionConfig) -> Self:
        return cls(
            _directory_type_to_path=CollectionDirectories._get_directory_type_to_path(collection),
        )

    @staticmethod
    def _get_directory_type_to_path(collection: CollectionConfig) -> dict[DirectoryType, Path]:
        return {DirectoryType(directory_type): path
                for directory_type, path in collection.get_directory_field_name_to_path().items()}

    def __post_init__(self) -> None:
        self._init_path_to_directory_type()

    def _init_path_to_directory_type(self) -> None:
        path_to_directory_type = {directory: directory_type
                                  for directory_type, directory in self._directory_type_to_path.items()}
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_path_to_directory_type", path_to_directory_type)

    def __iter__(self) -> Iterator[Path]:
        return (d for d in self._directory_type_to_path.values())

    def __getitem__(self, directory_type: DirectoryType) -> Path:
        return self._directory_type_to_path[directory_type]

    @property
    def valid_directories(self) -> Iterator[Path]:
        yield from (d for d in self._dirs if d.is_dir())

    @property
    def _dirs(self) -> Iterator[Path]:
        yield from self._directory_type_to_path.values()

    def get_directory_type(self, path: Path) -> DirectoryType:
        return self._path_to_directory_type.get(path, DirectoryType.OTHER)


def directories_are_missing(*directories: Path) -> bool:
    missing_directories = [directory for directory in directories if not directory.is_dir()]

    if not missing_directories:
        return False

    log_file_path(_LOG, logging.ERROR, "One or more required directories is missing", missing_directories)
    return True
