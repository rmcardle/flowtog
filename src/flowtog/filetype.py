from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class FileType(Enum):
    RAW = "RAW"
    JPEG = "JPEG"
    XMP = "XMP"
    OTHER = "Other"


_extension_file_types: dict[str, FileType] = {
    ".arw": FileType.RAW,
    ".jpg": FileType.JPEG,
    ".jpeg": FileType.JPEG,
    ".xmp": FileType.XMP,
}


def get_file_type(path: Path) -> FileType:
    return _extension_file_types.get(path.suffix.lower(), FileType.OTHER)
