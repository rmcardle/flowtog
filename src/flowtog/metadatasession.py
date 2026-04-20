import logging
import os
from contextlib import AbstractContextManager, suppress
from typing import TYPE_CHECKING, Any, Final, Self

from exiftool import ExifTool, ExifToolHelper  # pyright: ignore [reportMissingTypeStubs]

from flowtog.metadatatype import MetadataType

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from types import TracebackType

# Update _validate_metadata_value_type() if these are changed
type MetadataScalar = str | int
type MetadataValue = MetadataScalar | list[MetadataScalar]
type MetadataTypeToValues = dict[MetadataType, MetadataValue]

_LOG = logging.getLogger(__name__)

_EXIFTOOL_ARGS: Final[list[str]] = [
    "-G1",  # Print the specific location group name for each tag (e.g. "XMP-dc:Subject" instead of just "Subject")
    # "-n",   # Disable print conversion for all tags (see https://exiftool.org/under.html)
]
_EXIFTOOL_SOURCE_FILE_TAG: Final[str] = "SourceFile"


class MetadataSession(AbstractContextManager["MetadataSession"]):
    _exif_tool_helper: ExifToolHelper
    _path_to_metadata_type_to_values: dict[str, MetadataTypeToValues]

    def __init__(self) -> None:
        self._exif_tool_helper = ExifToolHelper(common_args=_EXIFTOOL_ARGS)
        self._path_to_metadata_type_to_values = {}

    def __enter__(self) -> Self:
        self._exif_tool_helper.__enter__()
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_value: BaseException | None,
                 traceback: TracebackType | None,
                 /) -> bool | None:
        self._exif_tool_helper.__exit__(exc_type, exc_value, traceback)  # pyright: ignore [reportUnknownMemberType]

    def load_metadata(self, paths: Iterable[str | os.PathLike[str]]) -> None:
        file_system_paths = [os.fspath(path) if isinstance(path, os.PathLike) else path for path in paths]
        if paths_to_load := {path for path in file_system_paths if path not in self._path_to_metadata_type_to_values}:
            self._read_metadata(paths_to_load)

    def get_metadata(self, path: str | os.PathLike[str]) -> MetadataTypeToValues:
        self.load_metadata([path])
        fspath = os.fspath(path) if isinstance(path, os.PathLike) else path
        return self._path_to_metadata_type_to_values[fspath]

    def get_metadata_by_type(self,
                             path: str | os.PathLike[str],
                             metadata_type: MetadataType) -> MetadataValue | None:
        return self.get_metadata(path).get(metadata_type)

    def _read_metadata(self, paths: str | Iterable[str]) -> None:
        tags_list: list[dict[str, Any]] = self._exif_tool_helper.get_tags(paths, _get_tag_names())  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]
        for tag_name_to_tags in tags_list:
            source_file = tag_name_to_tags.get(_EXIFTOOL_SOURCE_FILE_TAG)
            assert isinstance(source_file, str)
            source_file = os.path.normpath(source_file)
            self._path_to_metadata_type_to_values[source_file] = _get_metadata_type_to_values(tag_name_to_tags)

    def set_metadata(self, path: Path, metadata_type_to_values: MetadataTypeToValues) -> None:
        args = ["-overwrite_original"]

        for metadata_type, metadata_value in metadata_type_to_values.items():
            if isinstance(metadata_value, list):
                args.extend([f"-{metadata_type.value}={m}" for m in metadata_value])
            else:
                args.extend(f"-{metadata_type.value}={metadata_value}")

        args.append(str(path))

        self._exif_tool_helper.execute(*args)  # pyright: ignore [reportUnknownMemberType]


def validate_exiftool() -> bool:
    try:
        with ExifTool() as exif_tool:
            version = exif_tool.execute("-ver")
            _LOG.debug(f"ExifTool version {version}")
            return True
    except FileNotFoundError:
        return False


def _get_tag_names() -> list[str]:
    return [t.value for t in MetadataType]


def _get_metadata_type_to_values(tags: Mapping[str, Any]) -> MetadataTypeToValues:
    metadata_type_to_values: MetadataTypeToValues = {}

    for tag, value in tags.items():
        _validate_metadata_value_type(value)

        # Ignore tags that don't have a corresponding MetadataType
        with suppress(ValueError):
            metadata_type_to_values[MetadataType(tag)] = value

    return metadata_type_to_values


def _validate_metadata_value_type(value: Any) -> None:  # noqa: ANN401 any-type
    if not (isinstance(value, str | int)
            or ((isinstance(value, list))
                and all(isinstance(i, str | int) for i in value))):  # pyright: ignore [reportUnknownVariableType]
        raise TypeError
