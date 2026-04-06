from dataclasses import dataclass
from re import Pattern
from typing import Self

from flowtog.config import CollectionConfig
from flowtog.path_utils import PathArg, get_filename_stem


@dataclass(frozen=True)
class CollectionFilenameParser:
    pattern: Pattern[str]
    format: str

    @classmethod
    def from_collection(cls, collection: CollectionConfig) -> Self:
        return cls(
            pattern=collection.filename_pattern,
            format=collection.filename_format,
        )

    def get_group_name(self, path: PathArg) -> str | None:
        return self._get_filename_match_group(path, "group_name")

    def get_file_num(self, path: PathArg) -> int | None:
        return int(file_num) if (file_num := self._get_filename_match_group(path, "file_num")) else None

    def get_edit_num(self, path: PathArg) -> str | None:
        return self._get_filename_match_group(path, "edit_num")

    def _get_filename_match_group(self, path: PathArg, match_group: str) -> str | None:
        return self._get_match_group(get_filename_stem(path), match_group)

    def _get_match_group(self, string: str, match_group: str) -> str | None:
        return match.group(match_group) if (match := self.pattern.match(string)) else None
