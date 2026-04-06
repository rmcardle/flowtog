import logging
import os
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Final, Iterable, Mapping, Self

from exiftool import ExifTool, ExifToolHelper

from flowtog.metadatatype import MetadataType
from flowtog.path_utils import get_path


_LOG = logging.getLogger(__name__)

_EXIFTOOL_ARGS: Final[list[str]] = [
    "-G1",  # Print the specific location group name for each tag (e.g. "XMP-dc:Subject" instead of just "Subject")
    # "-n",   # Disable print conversion for all tags (see https://exiftool.org/under.html)
]
_EXIFTOOL_SOURCE_FILE_TAG: Final[str] = "SourceFile"


class MetadataSession (AbstractContextManager):
    _exif_tool_helper: ExifToolHelper
    _metadata_by_type_by_path: dict[str, dict[MetadataType, str | list[str]]]

    def __init__(self) -> None:
        self._exif_tool_helper = ExifToolHelper(common_args=_EXIFTOOL_ARGS)
        self._metadata_by_type_by_path = {}

    def __enter__(self) -> Self:
        self._exif_tool_helper.__enter__()
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_value: BaseException | None,
                 traceback: TracebackType | None,
                 /) -> bool | None:
        self._exif_tool_helper.__exit__(exc_type, exc_value, traceback)

    def load_metadata(self, paths: Iterable[str | os.PathLike[str]]) -> None:
        file_system_paths = [os.fspath(path) if isinstance(path, os.PathLike) else path for path in paths]
        if paths_to_load := {path for path in file_system_paths if path not in self._metadata_by_type_by_path}:
            self._read_metadata(paths_to_load)

    def get_metadata(self, path: str | os.PathLike[str]) -> dict[MetadataType, str | list[str]]:
        self.load_metadata([path])
        fspath = os.fspath(path) if isinstance(path, os.PathLike) else path
        return self._metadata_by_type_by_path[fspath]

    def get_metadata_by_type(self, path: str | os.PathLike[str], metadata_type: MetadataType) -> str | list[str] | None:
        return self.get_metadata(path).get(metadata_type)

    def _read_metadata(self, paths: str | Iterable[str]) -> None:
        tags_list: list[dict[str, str | list[str]]] = self._exif_tool_helper.get_tags(paths, _get_tag_names())
        for tags_by_tag_name in tags_list:
            source_file = tags_by_tag_name.get(_EXIFTOOL_SOURCE_FILE_TAG)
            assert isinstance(source_file, str)
            source_file = os.path.normpath(source_file)
            self._metadata_by_type_by_path[source_file] = _get_metadata_by_type(tags_by_tag_name)

    def set_metadata(self, path: str | os.PathLike[str], metadata_by_type: dict[MetadataType, str | list[str]]) -> None:
        args = ["-overwrite_original"]

        for metadata_type, metadata in metadata_by_type.items():
            args.extend([f"-{metadata_type.value}={m}" for m in metadata])

        args.append(get_path(path))

        # _LOG.debug(f"{self.set_metadata.__qualname__}(): Calling ExifToolHelper.execute() with arguments: " +
        #            " ".join(args))

        self._exif_tool_helper.execute(*args)


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


def _get_metadata_by_type(tags: Mapping[str, str | list[str]]) -> dict[MetadataType, str | list[str]]:
    metadata_by_type: dict[MetadataType, str | list[str]] = {}
    for tag, value in tags.items():
        try:
            metadata_by_type[MetadataType(tag)] = value
        except ValueError:
            pass
    return metadata_by_type
