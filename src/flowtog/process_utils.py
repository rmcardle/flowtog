import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from psutil import process_iter

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


def processes_are_running(process_filenames: Iterable[str]) -> bool:
    if not (matching_process_filenames := set(_get_matching_process_filenames(process_filenames))):
        return False

    _LOG.error(f"The following programs cannot be running\n\t{'\n\t'.join(matching_process_filenames)}")
    return True


def _get_matching_process_filenames(process_filenames: Iterable[str]) -> Iterator[str]:
    return (running_process_filename
            for running_process_filename in _get_running_process_filenames()
            if running_process_filename in process_filenames)


def _get_running_process_filenames() -> Iterator[str]:
    return (Path(running_process.info["exe"]).name
            for running_process in process_iter(["exe"])
            if running_process.info["exe"])
