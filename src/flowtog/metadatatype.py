from enum import Enum


class MetadataType(Enum):
    RATING = "XMP-xmp:Rating"
    PERSON_IN_IMAGE = "XMP-iptcExt:PersonInImage"
    SUBJECT = "XMP-dc:Subject"
    HIERARCHICAL_SUBJECT = "XMP-lr:hierarchicalSubject"
