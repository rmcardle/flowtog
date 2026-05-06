import logging
import os
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from psutil import disk_partitions

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


PathArg = str | os.PathLike[str] | os.DirEntry[str]
type FilePair = tuple[Path, Path]


def get_path(path: PathArg) -> Path:
    return Path(path.path) if isinstance(path, os.DirEntry) else Path(path)


def get_size(path: PathArg | os.stat_result) -> int:
    stat_result = _get_stat(path)
    return stat_result.st_size


def get_modified_time(path: PathArg | os.stat_result) -> datetime:
    stat_result = _get_stat(path)
    return datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)


def get_size_and_modified_time(path: PathArg | os.stat_result) -> tuple[int, datetime]:
    stat_result = _get_stat(path)
    return get_size(stat_result), get_modified_time(stat_result)


def _get_stat(path: PathArg | os.stat_result) -> os.stat_result:
    if isinstance(path, os.stat_result):
        return path
    if isinstance(path, os.DirEntry):
        return path.stat()
    return os.stat(path)  # noqa: PTH116 os-stat


def get_removable_media() -> Iterator[Path]:
    if platform.system() != "Windows":
        msg = f"{get_removable_media.__name__}() does not currently support {platform.system()}"
        raise NotImplementedError(msg)

    partitions = disk_partitions(all=False)
    for partition in sorted(partitions, key=lambda p: p.mountpoint):
        if "removable" in partition.opts:
            yield Path(partition.mountpoint)


def copy_files(file_pairs: Iterable[FilePair]) -> bool:
    if not file_pairs:
        _LOG.info("No files to copy")
        return False

    copy_file_pairs: list[FilePair] = []

    for source_file, destination_file in file_pairs:
        if destination_file.exists():
            if files_match(source_file, destination_file):
                _LOG.debug(f"Ignoring {source_file} - destination file {destination_file} already exists and "
                           f"matches source file")
                continue
            _LOG.error(f"Aborting copy - destination file {destination_file} already exists but does not match "
                       f"source file {source_file}")
            return False

        copy_file_pairs.append((source_file, destination_file))

    for source_file, destination_file in copy_file_pairs:
        copy_file(source_file, destination_file)

    return True


def copy_file(source_file: Path, destination_file: Path) -> None:
    _LOG.info(f"Copying {source_file} -> {destination_file}")
    assert not destination_file.exists()
    source_file.copy(destination_file)


def files_match(file1: PathArg, file2: PathArg) -> bool:
    return get_size_and_modified_time(file1) == get_size_and_modified_time(file2)
