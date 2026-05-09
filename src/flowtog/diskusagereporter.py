import logging
from typing import TYPE_CHECKING, Final

import psutil
from humanize import naturalsize

from flowtog.path_utils import get_removable_media

if TYPE_CHECKING:
    from pathlib import Path

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


def report_disk_usage(path: Path) -> None:
    try:
        disk_usage = psutil.disk_usage(str(path))
    except PermissionError:
        return

    total = naturalsize(disk_usage.total, binary=True)
    used = naturalsize(disk_usage.used, binary=True)
    free = naturalsize(disk_usage.free, binary=True)
    free_percent = disk_usage.free / disk_usage.total * 100

    _LOG.info(f"{path} - {total} total, {used} ({disk_usage.percent}%) used, {free} ({free_percent:.1f}%) free")


def report_media_usage() -> None:
    for media in get_removable_media():
        report_disk_usage(media)
