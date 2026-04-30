import logging
import re
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Final

from psutil import disk_partitions

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType

if TYPE_CHECKING:
    from flowtog.collectionfiles import CollectionFiles

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# https://web.archive.org/web/20180517065732/http://cipa.jp/std/documents/e/DC-009-2010_E.pdf
_DCIM_DIR_NAME: Final[str] = "DCIM"
_DCF_DIRECTORY_REGEX: Final[str] = r"^(?P<dir_num>\d{3})(?P<free_chars>[A-Z0-9_]{5})$"
_DCF_OBJECT_REGEX: Final[str] = r"^(?P<free_chars>[A-Z0-9_]{4})(?P<file_num>\d{4})(?P<extension>\.[A-Z0-9_]{3})$"
_DCF_DIRECTORY_PATTERN: Final[re.Pattern[str]] = re.compile(_DCF_DIRECTORY_REGEX)
_DCF_OBJECT_PATTERN: Final[re.Pattern[str]] = re.compile(_DCF_OBJECT_REGEX)

_RAW_EXTENSION: Final[str] = ".ARW"


class _ImportState:
    def __init__(self, collection_files: CollectionFiles) -> None:
        last_raw_size, last_raw_modified_time = _get_last_raw_size_and_modified_time(collection_files)
        self.collection_files = collection_files
        self.filename_format = collection_files.collection.filename_format
        self.unsorted_dir = collection_files.directories[DirectoryType.UNSORTED]
        self.last_raw_size = last_raw_size
        self.last_raw_modified_time = last_raw_modified_time
        self.last_source_file_num = collection_files.last_group_num % 10000
        self.last_destination_file_num = collection_files.last_group_num
        self.import_file_pairs: list[Path] = []

    @property
    def next_source_file_num(self) -> int:
        return self.last_source_file_num + 1 if self.last_source_file_num < 9999 else 1  # noqa: PLR2004

    @property
    def next_source_file_name(self) -> str:
        return self.filename_format.format(file_num=self.next_source_file_num)

    def add_import_file(self, source_file: Path, source_file_num: int) -> None:
        destination_file_name, destination_file_num = self._get_destination_file(source_file)
        destination_file = self.unsorted_dir / destination_file_name

        self.import_file_pairs.append(source_file)
        self.import_file_pairs.append(destination_file)

        self.last_source_file_num = source_file_num
        self.last_destination_file_num = destination_file_num

    def _get_destination_file(self, source_file: Path) -> tuple[str, int]:
        if not (match := _DCF_OBJECT_PATTERN.match(source_file.name)):
            raise AssertionError

        if not (free_chars := match.group("free_chars")):
            raise AssertionError
        assert free_chars[0] != "_"
        assert free_chars[-1] == "0"

        if not (file_num_str := match.group("file_num")):
            raise AssertionError
        file_num = int(file_num_str)

        if not (extension := match.group("extension")):
            raise AssertionError

        destination_file_num = self._get_destination_file_num(file_num)
        ten_thousands = destination_file_num // 10000
        assert ten_thousands < 10  # noqa: PLR2004
        free_chars = free_chars[:-1] + str(ten_thousands)

        destination_file_name = free_chars + file_num_str + extension
        return destination_file_name, destination_file_num

    def _get_destination_file_num(self, file_num: int) -> int:
        assert file_num < 10000  # noqa: PLR2004
        ten_thousands = self.last_destination_file_num // 10000
        if (self.last_source_file_num == 9999  # noqa: PLR2004
                and file_num == 1):
            ten_thousands += 1
        return (ten_thousands * 10000) + file_num


def _get_last_raw_size_and_modified_time(collection_files: CollectionFiles) -> tuple[int | None, datetime | None]:
    if not (last_group := collection_files.last_group):
        # If the collection is empty, we can return None, otherwise there's a problem
        assert collection_files.group_count == 0
        return None, None
    raw_files = last_group.file_type_to_files[FileType.RAW]
    if len(raw_files) != 1:
        raise AssertionError
    raw_file = raw_files[0]
    return raw_file.size, raw_file.modified_time


def import_files(collection_files: CollectionFiles) -> None:
    state = _ImportState(collection_files)

    if not state.unsorted_dir.exists():
        _LOG.error(f"{state.unsorted_dir} does not exist")
        return

    dcf_media_list = _find_dcf_media()
    if len(dcf_media_list) < 1:
        _LOG.error("No camera media found")
        return
    if len(dcf_media_list) > 1:
        _LOG.error("Multiple camera media found")
        return

    _scan_dcf_media(state, dcf_media_list[0])

    _copy_files(state.import_file_pairs)


def _find_dcf_media() -> list[Path]:
    dcf_media: list[Path] = []

    for partition in disk_partitions(all=False):
        partition_path = Path(partition.mountpoint)
        try:
            if (partition_path / _DCIM_DIR_NAME).is_dir():
                dcf_media.append(partition_path)
        except PermissionError:
            _LOG.debug(f"Permission error accessing {partition_path}")

    return dcf_media


def _scan_dcf_media(state: _ImportState, dcf_media: Path) -> None:
    dcim_dir = dcf_media / _DCIM_DIR_NAME

    # Path.iterdir() yields objects in arbitrary order so we need to sort them
    for path in sorted(dcim_dir.iterdir()):
        if (not path.is_dir()
                or not _DCF_DIRECTORY_PATTERN.match(path.name)):
            _LOG.debug(f"Ignoring {path} - Not a DCF directory")
            continue

        dcf_dir_sorted_files = sorted(p for p in path.iterdir() if p.is_file())

        if not _dcf_dir_matches_expected(state, path, dcf_dir_sorted_files):
            _LOG.debug(f"Ignoring {path}")
            continue

        _scan_dcf_dir(state, path, dcf_dir_sorted_files)


def _dcf_dir_matches_expected(state: _ImportState, dcf_dir: Path, dcf_dir_sorted_files: list[Path]) -> bool:
    if not state.last_raw_size:
        return True

    last_imported_raw_file, first_sorted_raw_file = \
        _get_last_imported_and_first_sorted_raw_files(state, dcf_dir_sorted_files)

    if not first_sorted_raw_file:
        _LOG.warning(f"No RAW files found in {dcf_dir}")
        return False

    if last_imported_raw_file:
        if not _check_last_raw_match(state, last_imported_raw_file, _CheckRawMatchComparison.SAME):
            _LOG.debug(f"Size and last modified time for RAW file {last_imported_raw_file} do not match expected")
            return False
    elif not _check_last_raw_match(state, first_sorted_raw_file, _CheckRawMatchComparison.SAME_OR_NEWER):
        _LOG.debug(f"Last modified time for RAW file {first_sorted_raw_file} is earlier than expected")
        return False

    return True


def _get_last_imported_and_first_sorted_raw_files(state: _ImportState,
                                                  dcf_dir_sorted_files: list[Path]) -> tuple[Path | None, Path | None]:
    last_imported_raw_file: Path | None = None
    first_sorted_raw_file: Path | None = None

    for path in dcf_dir_sorted_files:
        if path.suffix != _RAW_EXTENSION:
            continue

        if not first_sorted_raw_file:
            first_sorted_raw_file = path

        if (not last_imported_raw_file
                and _get_file_num(path) == state.last_source_file_num):
            last_imported_raw_file = path

        if first_sorted_raw_file and last_imported_raw_file:
            break

    return last_imported_raw_file, first_sorted_raw_file


class _CheckRawMatchComparison(Enum):
    SAME = auto()
    SAME_OR_NEWER = auto()


def _check_last_raw_match(state: _ImportState, file: Path, comparison: _CheckRawMatchComparison) -> bool:
    assert state.last_raw_size
    assert state.last_raw_modified_time

    file_size, file_modified_time = _get_file_size_and_modified_time(file)

    match comparison:
        case _CheckRawMatchComparison.SAME:
            return (file_size == state.last_raw_size
                    and file_modified_time == state.last_raw_modified_time)
        case _CheckRawMatchComparison.SAME_OR_NEWER:
            return file_modified_time >= state.last_raw_modified_time
        case _:
            raise NotImplementedError


def _scan_dcf_dir(state: _ImportState, dcf_dir: Path, dcf_dir_sorted_files: list[Path]) -> None:
    start_file_num = state.next_source_file_num
    next_expected_not_found_message_logged = False
    last_raw_file: Path | None = None

    for path in dcf_dir_sorted_files:
        if not (file_num := _get_file_num(path)):
            _LOG.debug(f"Ignoring {path} - Could not get file number")
            continue

        if file_num < start_file_num:
            continue

        if file_num not in (state.last_source_file_num, state.next_source_file_num):
            if not next_expected_not_found_message_logged:
                _LOG.debug(f"Next expected file {state.next_source_file_name} not found in {dcf_dir}")
                next_expected_not_found_message_logged = True
            _LOG.debug(f"Ignoring {path} - Not next expected file")
            continue

        # noinspection PyTypeChecker
        state.add_import_file(path, file_num)

        if path.suffix == _RAW_EXTENSION:
            last_raw_file = path

    if last_raw_file:
        state.last_raw_size, state.last_raw_modified_time = _get_file_size_and_modified_time(last_raw_file)


def _copy_files(file_pairs: list[Path]) -> None:
    if not file_pairs:
        _LOG.info("No files to copy")
        return

    assert len(file_pairs) % 2 == 0
    for i in range(0, len(file_pairs), 2):
        source_file, destination_file = file_pairs[i], file_pairs[i + 1]
        assert not destination_file.exists()
        _LOG.info(f"Copying {source_file} -> {destination_file}")
        source_file.copy(destination_file)


def _get_file_num(path: Path) -> int | None:
    return int(match.group("file_num")) if (match := _DCF_OBJECT_PATTERN.match(path.name)) else None


def _get_file_size_and_modified_time(file: Path) -> tuple[int, datetime]:
    file_stat = file.stat()
    return file_stat.st_size, datetime.fromtimestamp(file_stat.st_mtime, tz=UTC)
