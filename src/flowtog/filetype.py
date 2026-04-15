from enum import Enum
from typing import TYPE_CHECKING

from flowtog.path_utils import get_extension_lower

if TYPE_CHECKING:
    import os


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


def get_file_type(file: os.DirEntry[str]) -> FileType:
    return _extension_file_types.get(get_extension_lower(file), FileType.OTHER)
