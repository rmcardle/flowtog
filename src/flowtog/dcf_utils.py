import logging
import re
from typing import TYPE_CHECKING, Final

from flowtog.path_utils import get_removable_media

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# https://web.archive.org/web/20180517065732/http://cipa.jp/std/documents/e/DC-009-2010_E.pdf
_DCF_IMAGE_ROOT_DIR: Final[str] = "DCIM"
_DCF_DIRECTORY_REGEX: Final[str] = r"^(?P<dir_num>\d{3})(?P<free_chars>[A-Z0-9_]{5})$"
_DCF_DIRECTORY_PATTERN: Final[re.Pattern[str]] = re.compile(_DCF_DIRECTORY_REGEX)


def get_dcf_media() -> Iterator[Path]:
    for media in get_removable_media():
        try:
            if (media / _DCF_IMAGE_ROOT_DIR).is_dir():
                yield media
        except PermissionError:
            _LOG.debug(f"Permission error accessing {media}")


def is_dcf_media(path: Path) -> bool:
    return _get_dcf_image_root(path).is_dir()


def get_dcf_dirs(dcf_media: Path) -> Iterator[Path]:
    if not is_dcf_media(dcf_media):
        msg = f"The DCF image root directory (DCIM) was not found on the specified media\n\t{dcf_media}"
        raise FileNotFoundError(msg)

    # Path.iterdir() yields objects in arbitrary order so we need to sort them
    for path in sorted(_get_dcf_image_root(dcf_media).iterdir()):
        if not path.is_dir() or not _DCF_DIRECTORY_PATTERN.match(path.name):
            _LOG.debug(f"Ignoring {path} - Not a DCF directory")
            continue

        yield path


def _get_dcf_image_root(dcf_media: Path) -> Path:
    return dcf_media / _DCF_IMAGE_ROOT_DIR
