from enum import Enum


class MetadataType(Enum):
    DATE_TIME_ORIGINAL = "ExifIFD:DateTimeOriginal"
    OFFSET_TIME_ORIGINAL = "ExifIFD:OffsetTimeOriginal"
    RATING = "XMP-xmp:Rating"
    PERSON_IN_IMAGE = "XMP-iptcExt:PersonInImage"
    SUBJECT = "XMP-dc:Subject"
    HIERARCHICAL_SUBJECT = "XMP-lr:hierarchicalSubject"
