import re
from collections.abc import (
    Mapping,  # noqa: TC003 typing-only-standard-library-import  # Used at runtime by dataclass_binder
)
from dataclasses import Field, dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self

import win32com.client
from dataclass_binder import Binder

from flowtog.path_utils import get_extension_lower

if TYPE_CHECKING:
    import os

_CONFIG_FILE_NAME: Final[str] = "flowtog.toml"
_DEFAULT_FILENAME_REGEX: Final[str] = r"^(?P<group_name>DSC(?P<file_num>\d{5}))(?:-(?P<edit_num>\d+))?$"
_DEFAULT_FILENAME_FORMAT: Final[str] = "DSC{file_num:05d}"


def _directory_field(default: str = "") -> Path:
    return field(default=Path(default), metadata={"is_directory_field": True})


@dataclass(frozen=True)
class CollectionConfig:
    filename_regex: str = _DEFAULT_FILENAME_REGEX
    filename_pattern: re.Pattern[str] = field(init=False)
    filename_format: str = _DEFAULT_FILENAME_FORMAT

    # ruff: disable[RUF009] function-call-in-dataclass-default-argument
    originals_dir: Path = _directory_field("Originals")
    photos_dir: Path = _directory_field("Photos")
    previous_edits_dir: Path = _directory_field("Previous Edits")
    raw_dir: Path = _directory_field("Raw")
    rejected_dir: Path = _directory_field("Rejected")
    unsorted_dir: Path = _directory_field("Unsorted")
    # ruff: enable[RUF009] function-call-in-dataclass-default-argument

    start_num: int = 1
    selected_rating: int = 3

    def __post_init__(self) -> None:
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "filename_pattern", re.compile(self.filename_regex))

    @property
    def directories(self) -> dict[str, Path]:
        return {f.name: getattr(self, f.name) for f in self.directory_fields}

    @property
    def directory_fields(self) -> list[Field[str]]:
        return [f for f in fields(self) if f.metadata.get("is_directory_field")]


@dataclass(frozen=True)
class Person:
    groups: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Config:
    collection: CollectionConfig
    people: Mapping[str, Person] = field(default_factory=dict[str, Person])

    @classmethod
    def load(cls, config_file: str | os.PathLike[str] | Path) -> Self:
        config_file_path = Path(config_file)
        if config_file_path.is_file():
            config = Binder(cls).parse_toml(config_file_path)
        else:
            config = cls(
                collection=CollectionConfig(),
            )

        config._normalize_paths(config_file_path.parent)
        return config


    def _normalize_paths(self, base_dir: Path) -> None:
        base_dir = base_dir.absolute()
        for collection_field in self.collection.directory_fields:
            value: Path = getattr(self.collection, collection_field.name)
            value = _normalize_path(value, base_dir)
            value = _follow_shortcut(value)
            # Use __setattr__ to avoid FrozenInstanceError
            object.__setattr__(self.collection, collection_field.name, value)


def _normalize_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def _follow_shortcut(shortcut_path: Path) -> Path:
    if get_extension_lower(shortcut_path) != ".lnk":
        return shortcut_path

    target = _get_shortcut_target(shortcut_path)
    return _normalize_path(target, shortcut_path.parent)


# Based on https://stackoverflow.com/a/571573
def _get_shortcut_target(path: Path) -> Path:
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(path))
    target = shortcut.Targetpath
    return Path(target) if target else path
