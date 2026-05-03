import re
from collections.abc import (
    Mapping,
)
from dataclasses import Field, dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Self

import win32com.client
from dataclass_binder import Binder

from flowtog.typing_utils import is_str_list

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

    def get_directory_field_name_to_path(self) -> dict[str, Path]:
        return {f.name: getattr(self, f.name) for f in self.get_directory_fields()}

    @classmethod
    def get_directory_fields(cls) -> list[Field[str]]:
        return [f for f in fields(cls) if f.metadata.get("is_directory_field")]


@dataclass(frozen=True)
class GroupConfig:
    hierarchical_keyword: tuple[str, ...] = field(default_factory=tuple)
    keyword_include_person: bool = field(default=False)

    def __post_init__(self) -> None:
        # Make fields deeply immutable
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "hierarchical_keyword", tuple(self.hierarchical_keyword))


@dataclass(frozen=True)
class CategoryConfig:
    groups: tuple[str, ...] = field(default_factory=tuple)
    required: bool = field(default=False)
    default_group: str | None = field(default=None)
    allow_multiple: bool = field(default=False)
    report: bool = field(default=False)
    keyword_include_person: bool = field(default=False)

    def __post_init__(self) -> None:
        # Make fields deeply immutable
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "groups", tuple(self.groups))


@dataclass(frozen=True)
class PersonConfig:
    groups: tuple[str, ...] = field(default_factory=tuple)
    categories: Mapping[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])

    def __post_init__(self) -> None:
        # Make fields deeply immutable
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "groups", tuple(self.groups))
        object.__setattr__(self,
                           "categories",
                           MappingProxyType({
                               key: tuple(value)
                               for key, value in self.categories.items()
                           }))

    @property
    def effective_groups(self) -> tuple[str, ...]:
        category_groups = [
            group
            for groups in self.categories.values()
            for group in groups
        ]
        return tuple(dict.fromkeys([*self.groups, *category_groups]))


# The class is only shallowly immutable, but it is only used transiently and not exposed publicly
@dataclass(frozen=True)
class _RawConfig:
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    categories: Mapping[str, CategoryConfig] = field(default_factory=dict[str, CategoryConfig])
    groups: Mapping[str, GroupConfig] = field(default_factory=dict[str, GroupConfig])
    people: Mapping[str, Mapping[str, Any]] = field(default_factory=dict[str, Mapping[str, Any]])


@dataclass(frozen=True)
class Config:
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    categories: Mapping[str, CategoryConfig] = field(default_factory=dict[str, CategoryConfig])
    groups: Mapping[str, GroupConfig] = field(default_factory=dict[str, GroupConfig])
    people: Mapping[str, PersonConfig] = field(default_factory=dict[str, PersonConfig])

    def __post_init__(self) -> None:
        # Make fields deeply immutable
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "categories", MappingProxyType(dict(self.categories)))
        object.__setattr__(self, "groups", MappingProxyType(dict(self.groups)))
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))

    @classmethod
    def load(cls, path: str | os.PathLike[str] | Path) -> Self:
        load_path = Path(path)
        if load_path.is_dir():
            load_path /= _CONFIG_FILE_NAME

        raw_config = Binder(_RawConfig).parse_toml(load_path) \
            if load_path.is_file() \
            else _RawConfig()

        config = cls(
            collection=cls._get_normalized_collection(raw_config.collection, load_path.parent),
            categories=raw_config.categories,
            groups=raw_config.groups,
            people=cls._get_people(raw_config),
        )

        config._validate_categories()
        config._validate_people()

        return config

    @staticmethod
    def _get_normalized_collection(collection: CollectionConfig, base_dir: Path) -> CollectionConfig:
        base_dir = base_dir.absolute()
        normalized_kwargs: dict[str, Any] = {}

        for collection_field in fields(CollectionConfig):
            if not collection_field.init:
                continue
            value = getattr(collection, collection_field.name)
            if collection_field in CollectionConfig.get_directory_fields():
                value = _normalize_path(value, base_dir)
                value = _follow_shortcut(value)
            normalized_kwargs[collection_field.name] = value

        return CollectionConfig(**normalized_kwargs)

    @classmethod
    def _get_people(cls, raw_config: _RawConfig) -> Mapping[str, PersonConfig]:
        people: dict[str, PersonConfig] = {}

        for person_name, person_data in raw_config.people.items():
            people[person_name] = cls._get_person(person_name, person_data, raw_config)

        return people

    @classmethod
    def _get_person(cls,
                    person_name: str,
                    person_data: Mapping[str, object],
                    raw_config: _RawConfig) -> PersonConfig:
        person_field_names = {f.name for f in fields(PersonConfig) if f.name != "categories"}
        category_names = set(raw_config.categories)

        groups = person_data.get("groups", [])
        if not is_str_list(groups):
            msg = f'The value of people."{person_name}".groups is not a list of strings'
            raise TypeError(msg)

        person_fields: dict[str, Any] = {}
        categories: dict[str, tuple[str, ...]] = {}
        for key, value in person_data.items():
            if key in person_field_names:
                person_fields[key] = value
                continue
            if key not in category_names:
                msg = f'Invalid category name "{key}" in people."{person_name}"'
                raise ValueError(msg)
            if not (isinstance(value, str) or is_str_list(value)):
                msg = f'The value of people."{person_name}"."{key}" is not a string or list of strings'
                raise TypeError(msg)
            categories[key] = tuple(value) if isinstance(value, list) else (value,)

        for category_name, category in raw_config.categories.items():
            if category_name not in categories:
                if category.default_group:
                    categories[category_name] = (category.default_group,)
                elif category.required:
                    msg = (f'Person "{person_name}" does not have a group set for'
                           f'required category "{category_name}"')
                    raise ValueError(msg)

        return PersonConfig(
            **person_fields,
            categories=categories,
        )

    def _validate_categories(self) -> None:
        for category_name, category in self.categories.items():
            category_groups_set = set(category.groups)

            if category.default_group and category.default_group not in category_groups_set:
                msg = (f'Category "{category_name}" default-group "{category.default_group}" is not in '
                       f'groups "{category_groups_set}"')
                raise ValueError(msg)

    def _validate_people(self) -> None:
        all_group_names = set(self.groups)
        all_category_group_names = {
            group_name
            for category in self.categories.values()
            for group_name in category.groups
        }

        for person_name, person in self.people.items():
            self._validate_person(person_name, person, all_group_names, all_category_group_names)

    def _validate_person(self,
                         person_name: str,
                         person: PersonConfig,
                         all_group_names: set[str],
                         all_category_group_names: set[str]) -> None:
        for category_name, category_group_names in person.categories.items():
            # This should never fail since category names were already checked during load
            # so we'll just do a simple assert here instead of repeating our code
            assert category_name in self.categories

            category = self.categories[category_name]
            if any(group_name not in category.groups for group_name in category_group_names):
                msg = (f'One or more groups in "{category_group_names}" is not in "{category.groups}" for '
                       f'person "{person_name}" and category "{category_name}"')
                raise ValueError(msg)

            if not category.allow_multiple and len(category_group_names) > 1:
                msg = (f'Person "{person_name}" has multiple groups set "{category_group_names}" for '
                       f'category "{category_name}" that does not allow multiple groups')
                raise ValueError(msg)

        for group_name in person.groups:
            if group_name in all_category_group_names:
                msg = f'Category group "{group_name}" in groups list for person "{person_name}"'
                raise ValueError(msg)

            if group_name not in all_group_names:
                msg = f'Unknown group "{group_name}" for person "{person_name}"'
                raise ValueError(msg)


def _normalize_path(path: Path, base_dir: Path) -> Path:
    return path if path.is_absolute() else base_dir / path


def _follow_shortcut(shortcut_path: Path) -> Path:
    if shortcut_path.suffix.lower() != ".lnk":
        return shortcut_path

    target = _get_shortcut_target(shortcut_path)
    return _normalize_path(target, shortcut_path.parent)


# Based on https://stackoverflow.com/a/571573
def _get_shortcut_target(path: Path) -> Path:
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(path))
    target = shortcut.Targetpath
    return Path(target) if target else path
