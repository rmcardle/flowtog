import os
import re
from collections.abc import Mapping  # noqa: TC003
from dataclasses import Field, dataclass, field, fields
from typing import Final, Self

import win32com.client
from dataclass_binder import Binder

from flowtog.path_utils import get_extension_lower

_CONFIG_FILE_NAME: Final[str] = "flowtog.toml"
_DEFAULT_FILENAME_REGEX: Final[str] = r"^(?P<group_name>DSC(?P<file_num>\d{5}))(?:-(?P<edit_num>\d+))?$"
_DEFAULT_FILENAME_FORMAT: Final[str] = "DSC{file_num:05d}"


def _directory_field(default: str = "") -> str:
    return field(default=default, metadata={"is_directory_field": True})


@dataclass(frozen=True)
class CollectionConfig:
    filename_regex: str = _DEFAULT_FILENAME_REGEX
    filename_pattern: re.Pattern[str] = field(init=False)
    filename_format: str = _DEFAULT_FILENAME_FORMAT

    originals_dir: str = _directory_field("Originals")
    photos_dir: str = _directory_field("Photos")
    previous_edits_dir: str = _directory_field("Previous Edits")
    raw_dir: str = _directory_field("Raw")
    rejected_dir: str = _directory_field("Rejected")
    unsorted_dir: str = _directory_field("Unsorted")

    start_num: int = 1
    selected_rating: int = 3

    def __post_init__(self) -> None:
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "filename_pattern", re.compile(self.filename_regex))

    @property
    def directories(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in self.directory_fields}

    @property
    def directory_fields(self) -> list[Field[str]]:
        return [f for f in fields(self) if f.metadata.get("is_directory_field")]


@dataclass(frozen=True)
class Person:
    groups: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class Config:
    collection: Mapping[str, CollectionConfig] = field(default_factory=dict[str, CollectionConfig])
    people: Mapping[str, Person] = field(default_factory=dict[str, Person])

    @classmethod
    def load(cls, config_file_path: str | None) -> Self:
        if config_file_path is None or not os.path.isfile(config_file_path):
            return cls(collection={
                "DSC": CollectionConfig(),
            })
        config = Binder(cls).parse_toml(config_file_path)
        config._normalize_paths(os.path.dirname(config_file_path))  # noqa: SLF001
        return config

    def _normalize_paths(self, base_dir: str) -> None:
        base_dir = os.path.abspath(base_dir)
        for collection in self.collection.values():
            for collection_field in collection.directory_fields:
                value: str = getattr(collection, collection_field.name)
                value = _normalize_path(value, base_dir)
                value = _follow_shortcut(value)
                # Use __setattr__ to avoid FrozenInstanceError
                object.__setattr__(collection, collection_field.name, value)


def _normalize_path(path: str, base_dir: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))


def _follow_shortcut(shortcut_path: str) -> str:
    if get_extension_lower(shortcut_path) != ".lnk":
        return shortcut_path

    target = _get_shortcut_target(shortcut_path)
    return _normalize_path(target, os.path.dirname(shortcut_path))


# Based on https://stackoverflow.com/a/571573
def _get_shortcut_target(path: str) -> str:
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(path)
    target = shortcut.Targetpath
    return target if target != "" else path
