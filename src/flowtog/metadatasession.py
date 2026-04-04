import os
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Final, Iterable, List, Mapping, Self, Type, overload

from exiftool import ExifToolHelper

from flowtog.metadatatype import MetadataType


_EXIFTOOL_ARGS: Final[List[str]] = [
    "-G1",  # Print the specific location group name for each tag (e.g. "XMP-dc:Subject" instead of just "Subject")
    # "-n",   # Disable print conversion for all tags (see https://exiftool.org/under.html)
]
_EXIFTOOL_SOURCE_FILE_TAG: Final[str] = "SourceFile"


class MetadataSession (AbstractContextManager):
    _et: ExifToolHelper
    _metadata_by_type_by_path: dict[str, dict[MetadataType, str]]

    def __init__(self) -> None:
        self._et = ExifToolHelper(common_args=_EXIFTOOL_ARGS)
        self._metadata_by_type_by_path = {}

    def __enter__(self) -> Self:
        self._et.__enter__()
        return self

    def __exit__(self,
                 exc_type: Type[BaseException] | None,
                 exc_value: BaseException | None,
                 traceback: TracebackType | None,
                 /) -> bool | None:
        self._et.__exit__(exc_type, exc_value, traceback)

    def begin(self):
        self._et.run()

    def end(self):
        self._et.terminate()

    @overload
    def get_metadata(self,
                     path: str | os.PathLike[str],
                     metadata_type: MetadataType) \
            -> str | None:
        ...

    @overload
    def get_metadata(self,
                     paths: Iterable[str | os.PathLike[str]],
                     metadata_type: MetadataType) \
            -> dict[str | os.PathLike[str], str | None]:
        ...

    def get_metadata(self,
                     paths: str | os.PathLike[str] | Iterable[str | os.PathLike[str]],
                     metadata_type: MetadataType) \
            -> str | dict[str | os.PathLike[str], str | None] | None:
        # Convert paths to a list even if it is Iterable because we need to iterate over it multiple times
        original_paths = [paths] if (is_single_path := isinstance(paths, (str, os.PathLike))) else list(paths)

        # Convert os.PathLike to str
        file_system_paths = [os.fspath(path) if isinstance(path, os.PathLike) else path for path in original_paths]

        paths_to_read = {path for path in file_system_paths if path not in self._metadata_by_type_by_path}
        self._read_metadata(paths_to_read)

        # We need to return the original paths as the keys to the dict so that callers can find them
        metadata_by_path = {
            original_path: self._metadata_by_type_by_path[file_system_path].get(metadata_type)
            for original_path, file_system_path in zip(original_paths, file_system_paths)
        }
        return metadata_by_path[original_paths[0]] if is_single_path else metadata_by_path

    def _read_metadata(self, paths: str | Iterable[str]) -> None:
        tags_list: list[dict[str, str]] = self._et.get_tags(paths, _get_tag_names())
        for tags in tags_list:
            assert (source_file := tags.get(_EXIFTOOL_SOURCE_FILE_TAG))
            source_file = os.path.normpath(source_file)
            self._metadata_by_type_by_path[source_file] = _get_metadata_by_type(tags)


def _get_tag_names() -> List[str]:
    return [t.value for t in MetadataType]


def _get_metadata_by_type(tags: Mapping[str, str]) -> dict[MetadataType, str]:
    metadata_by_type: dict[MetadataType, str] = {}
    for tag, value in tags.items():
        try:
            metadata_by_type[MetadataType(tag)] = value
        except ValueError:
            pass
    return metadata_by_type
