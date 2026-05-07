import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import CollectionDirectories
from flowtog.dcf_utils import get_dcf_media

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flowtog.config import Config

_LOG: Final[logging.Logger] = logging.getLogger(__name__)
_LOG_UNMATCHED_FILE_COUNT_MAX: Final[int] = 100

_FILE_NAME_KEY_DCF_OBJECT_REGEX: Final[str] = \
    r"^(?:[0-9]{8}-[0-9]{6}-)?(?:[A-Z0-9_]{4})(?P<key>\d{4})(?:\.[A-Z0-9_]{3})$"
_FILE_NAME_KEY_SONY_XAVCS_REGEX: Final[str] = \
    r"^(?:[0-9]{8}-[0-9]{6}-)?(?:[A-Z]{1})(?P<key>\d{4})(?:[A-Z]{1}\d{2})?(?:\.[A-Z0-9_]{3})$"
_FILE_NAME_KEY_SONY_AVCHD_REGEX: Final[str] = \
    r"^(?:[0-9]{8}-[0-9]{6}-)?(?P<key>[0-9]{5})(?:\.[A-Z0-9_]{3})$"
_FILE_NAME_KEY_DCF_OBJECT_PATTERN: Final[re.Pattern[str]] = re.compile(_FILE_NAME_KEY_DCF_OBJECT_REGEX)
_FILE_NAME_KEY_SONY_XAVCS_PATTERN: Final[re.Pattern[str]] = re.compile(_FILE_NAME_KEY_SONY_XAVCS_REGEX)
_FILE_NAME_KEY_SONY_AVCHD_PATTERN: Final[re.Pattern[str]] = re.compile(_FILE_NAME_KEY_SONY_AVCHD_REGEX)
_FILE_NAME_KEY_PATTERNS: list[re.Pattern[str]] = [
    _FILE_NAME_KEY_DCF_OBJECT_PATTERN,
    _FILE_NAME_KEY_SONY_XAVCS_PATTERN,
    _FILE_NAME_KEY_SONY_AVCHD_PATTERN,
]

type FileKey = tuple[str, float, int]


def check_media(config: Config) -> None:
    key_to_path: dict[FileKey, str] = {}
    for collection_dir in _get_collection_dirs(config):
        for entry in _get_file_entries_recursive(collection_dir):
            if (file_key := _get_file_key(entry)) in key_to_path:
                _LOG.warning("A file with same file number, date, and size was already found "
                             f"in the collection directory\n\t{key_to_path[file_key]}\n\t{entry.path}")
            key_to_path[file_key] = entry.path

    found_media = False
    for media in get_dcf_media():
        found_media = True

        unmatched_files = [entry.path for entry in _get_file_entries_recursive(media)
                           if _get_file_key(entry) not in key_to_path]

        if unmatched_files:
            msg = f"{len(unmatched_files)} files on media {media} were not found in the collection directory"
            if len(unmatched_files) <= _LOG_UNMATCHED_FILE_COUNT_MAX:
                msg += f"\n\t{'\n\t'.join(sorted(unmatched_files))}"
            _LOG.warning(msg)
        else:
            _LOG.info(f"All files on media {media} were found in the collection directory")

    if not found_media:
        _LOG.error("No DCF media found")
        return


def _get_collection_dirs(config: Config) -> Iterator[Path]:
    yield config.base_dir
    for collection_dir in CollectionDirectories.from_collection(config.collection):
        if not _is_ancestor_of(config.base_dir, collection_dir):
            yield collection_dir


def _is_ancestor_of(path1: Path, path2: Path) -> bool:
    try:
        path2.relative_to(path1)
    except ValueError:
        return False
    else:
        return True


def _get_file_entries_recursive(path: Path | os.DirEntry[str]) -> Iterator[os.DirEntry[str]]:
    scan_path = path if isinstance(path, Path) else path.path
    with os.scandir(scan_path) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                yield from _get_file_entries_recursive(entry)
            else:
                yield entry


def _get_file_key(entry: os.DirEntry[str]) -> FileKey:
    entry_stat = entry.stat()
    return _get_file_name_key(entry.name), entry_stat.st_mtime, entry_stat.st_size


def _get_file_name_key(file_name: str) -> str:
    for pattern in _FILE_NAME_KEY_PATTERNS:
        if not (match := pattern.match(file_name)):
            continue
        if not (key := match.group("key")):
            continue
        return key
    return file_name
