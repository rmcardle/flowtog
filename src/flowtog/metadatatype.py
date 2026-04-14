from enum import Enum


class MetadataType(Enum):
    DateTimeOriginal = "ExifIFD:DateTimeOriginal"
    OffsetTimeOriginal = "ExifIFD:OffsetTimeOriginal"
    Rating = "XMP-xmp:Rating"
    PersonInImage = "XMP-iptcExt:PersonInImage"
    Subject = "XMP-dc:Subject"
    HierarchicalSubject = "XMP-lr:hierarchicalSubject"
