import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self

from flowtog.path_utils import get_removable_media

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

# https://web.archive.org/web/20180517065732/http://cipa.jp/std/documents/e/DC-009-2010_E.pdf
_DCF_IMAGE_ROOT_DIR: Final[str] = "DCIM"
_DCF_DIRECTORY_REGEX: Final[str] = r"^(?P<dir_num>\d{3})(?P<free_chars>[A-Z0-9_]{5})$"
_DCF_OBJECT_REGEX: Final[str] = r"^(?P<free_chars>[A-Z0-9_]{4})(?P<file_num>\d{4})(?P<extension>\.[A-Z0-9_]{3})$"
_DCF_DIRECTORY_PATTERN: Final[re.Pattern[str]] = re.compile(_DCF_DIRECTORY_REGEX)
_DCF_OBJECT_PATTERN: Final[re.Pattern[str]] = re.compile(_DCF_OBJECT_REGEX)


def get_dcf_media() -> Iterator[Path]:
    for media in get_removable_media():
        if (media / _DCF_IMAGE_ROOT_DIR).is_dir():
            yield media


def is_dcf_media(path: Path) -> bool:
    return get_dcf_image_root(path).is_dir()


def get_dcf_image_root(dcf_media: Path) -> Path:
    return dcf_media / _DCF_IMAGE_ROOT_DIR


def get_dcf_dirs(dcf_media: Path) -> Iterator[Path]:
    if not is_dcf_media(dcf_media):
        msg = f"The DCF image root directory (DCIM) was not found on the specified media\n\t{dcf_media}"
        raise FileNotFoundError(msg)

    # Path.iterdir() yields objects in arbitrary order so we need to sort them
    for path in sorted(get_dcf_image_root(dcf_media).iterdir()):
        if not path.is_dir() or not _DCF_DIRECTORY_PATTERN.match(path.name):
            _LOG.debug(f"Ignoring {path} - Not a DCF directory")
            continue

        yield path


@dataclass(frozen=True)
class DCFObjectName:
    free_chars: str
    file_num: int
    extension: str

    @classmethod
    def from_path(cls, path: Path) -> Self:
        if not (match := _DCF_OBJECT_PATTERN.match(path.name)):
            msg = f"{path.name} is not a valid DCF object name"
            raise ValueError(msg)

        free_chars = match.group("free_chars")
        file_num_str = match.group("file_num")
        extension = match.group("extension")

        if (free_chars is None
                or file_num_str is None
                or extension is None):
            msg = f"Could not parse DCF object name {path.name}"
            raise ValueError(msg)

        return cls(
            free_chars=free_chars,
            file_num=int(file_num_str),
            extension=extension,
        )
