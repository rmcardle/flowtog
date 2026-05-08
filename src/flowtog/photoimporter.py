import logging
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import DirectoryType
from flowtog.dcf_utils import DCFObjectName, get_dcf_dirs, get_dcf_media
from flowtog.filetype import FileType
from flowtog.numberrange import format_range, get_number_range
from flowtog.path_utils import FilePair, copy_files, get_size_and_modified_time

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime
    from pathlib import Path

    from flowtog.collectionfiles import CollectionFiles

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

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
        self.import_file_pairs: list[FilePair] = []

    @property
    def next_source_file_num(self) -> int:
        return self.last_source_file_num + 1 \
            if self.last_source_file_num < 9999 \
            else 1  # noqa: PLR2004 magic-value-comparison

    @property
    def next_source_file_name(self) -> str:
        return self.filename_format.format(file_num=self.next_source_file_num)

    def add_import_file(self, source_file: Path, source_file_num: int) -> None:
        destination_file_name, destination_file_num = self._get_destination_file_and_num(source_file)
        destination_file = self.unsorted_dir / destination_file_name

        self.import_file_pairs.append((source_file, destination_file))

        self.last_source_file_num = source_file_num
        self.last_destination_file_num = destination_file_num

    def _get_destination_file_and_num(self, source_file: Path) -> tuple[str, int]:
        dcf_object_name = DCFObjectName.from_path(source_file)

        assert dcf_object_name.free_chars[0] != "_"
        assert dcf_object_name.free_chars[-1] == "0"

        destination_file_num = self._get_destination_file_num(dcf_object_name.file_num)
        ten_thousands = destination_file_num // 10000
        assert ten_thousands < 10  # noqa: PLR2004 magic-value-comparison
        free_chars = dcf_object_name.free_chars[:-1] + str(ten_thousands)

        destination_file_name = free_chars + str(dcf_object_name.file_num) + dcf_object_name.extension
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
        if collection_files.group_count == 0:
            return None, None

        msg = "collection_files.last_group is None but the collection is not empty"
        raise ValueError(msg)

    raw_file = last_group.get_single_file_from_type(FileType.RAW)
    return raw_file.size, raw_file.modified_time


def import_photos(collection_files: CollectionFiles) -> None:
    state = _ImportState(collection_files)

    if not state.unsorted_dir.is_dir():
        _LOG.error(f"{state.unsorted_dir} does not exist or is not a directory")
        return

    found_media = False
    for media in get_dcf_media():
        found_media = True
        _scan_dcf_media(state, media)

    if not found_media:
        _LOG.error("No DCF media found")
        return

    if not copy_files(state.import_file_pairs):
        _LOG.error("Files were not copied")


def _scan_dcf_media(state: _ImportState, dcf_media: Path) -> None:
    for dcf_dir in get_dcf_dirs(dcf_media):
        sorted_files = sorted(p for p in dcf_dir.iterdir() if p.is_file())

        if not _dcf_dir_matches_expected(state, dcf_dir, sorted_files):
            _LOG.debug(f"Ignoring {dcf_dir}")
            continue

        _scan_dcf_dir(state, dcf_dir, sorted_files)


def _dcf_dir_matches_expected(state: _ImportState, dcf_dir: Path, sorted_files: Collection[Path]) -> bool:
    if not state.last_raw_size:
        return True

    last_imported_raw_file, first_sorted_raw_file = \
        _get_last_imported_and_first_sorted_raw_files(state, sorted_files)

    if not first_sorted_raw_file:
        _LOG.warning(f"No RAW files found in {dcf_dir}")
        return False

    if last_imported_raw_file:
        if not _check_last_raw_match(state, last_imported_raw_file, allow_newer=False):
            _LOG.debug(f"Size and last modified time for RAW file {last_imported_raw_file} do not match expected")
            return False
    elif not _check_last_raw_match(state, first_sorted_raw_file, allow_newer=True):
        _LOG.debug(f"Last modified time for RAW file {first_sorted_raw_file} is earlier than expected")
        return False

    return True


def _get_last_imported_and_first_sorted_raw_files(state: _ImportState,
                                                  sorted_files: Collection[Path]) -> tuple[Path | None, Path | None]:
    last_imported_raw_file: Path | None = None
    first_sorted_raw_file: Path | None = None

    for file in sorted_files:
        if file.suffix != _RAW_EXTENSION:
            continue

        if not first_sorted_raw_file:
            first_sorted_raw_file = file

        if (not last_imported_raw_file
                and _get_file_num(file) == state.last_source_file_num):
            last_imported_raw_file = file

        if first_sorted_raw_file and last_imported_raw_file:
            break

    return last_imported_raw_file, first_sorted_raw_file


def _check_last_raw_match(state: _ImportState, file: Path, *, allow_newer: bool) -> bool:
    assert state.last_raw_size
    assert state.last_raw_modified_time

    file_size, file_modified_time = get_size_and_modified_time(file)

    if allow_newer:
        return file_modified_time >= state.last_raw_modified_time

    return (file_size == state.last_raw_size
            and file_modified_time == state.last_raw_modified_time)


def _scan_dcf_dir(state: _ImportState, dcf_dir: Path, sorted_files: Collection[Path]) -> None:
    start_file_num = state.next_source_file_num
    next_expected_not_found_message_logged = False
    last_raw_file: Path | None = None
    number_range_coroutine = get_number_range()

    def log_ignored_file_range(ignored_file_num: int | None) -> None:
        if not (ignored_file_range := number_range_coroutine.send(ignored_file_num)):
            return

        ignored_files = format_range(ignored_file_range, state.filename_format, "file_num")
        _LOG.debug(f"Ignoring {ignored_files} in {dcf_dir} - Not next expected file")

    for path in sorted_files:
        if not (file_num := _get_file_num(path)):
            _LOG.debug(f"Ignoring {path} - Could not get file number")
            continue

        if file_num < start_file_num:
            continue

        if file_num not in (state.last_source_file_num, state.next_source_file_num):
            if not next_expected_not_found_message_logged:
                _LOG.debug(f"Next expected file {state.next_source_file_name} not found in {dcf_dir}")
                next_expected_not_found_message_logged = True
            log_ignored_file_range(file_num)
            continue

        # noinspection PyTypeChecker
        state.add_import_file(path, file_num)

        if path.suffix == _RAW_EXTENSION:
            last_raw_file = path

    # Log any remaining ignored files
    log_ignored_file_range(None)

    if last_raw_file:
        state.last_raw_size, state.last_raw_modified_time = get_size_and_modified_time(last_raw_file)


def _get_file_num(file: Path) -> int | None:
    try:
        return DCFObjectName.from_path(file).file_num
    except ValueError:
        return None
