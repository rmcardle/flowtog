from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


class MetadataType(Enum):
    RATING = "XMP-xmp:Rating"
    PERSON_IN_IMAGE = "XMP-iptcExt:PersonInImage"
    SUBJECT = "XMP-dc:Subject"
    HIERARCHICAL_SUBJECT = "XMP-lr:hierarchicalSubject"

    @classmethod
    def get_tag_names(cls) -> Iterator[str]:
        yield from (t.value for t in MetadataType)
