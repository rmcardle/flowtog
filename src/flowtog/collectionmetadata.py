from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from flowtog.filetype import FileType
from flowtog.metadatatype import MetadataType

if TYPE_CHECKING:
    from pathlib import Path

    from flowtog.collectiondirectories import DirectoryType
    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.metadatasession import MetadataSession, MetadataTypeToValues


@dataclass(frozen=True)
class CollectionMetadata:
    _collections_files: CollectionFiles
    _directories: list[DirectoryType]
    _metadata_session: MetadataSession
    _xmp_files: list[CollectionFile] = field(init=False)

    @classmethod
    def from_collection_files(cls,
                              collection_files: CollectionFiles,
                              directories: DirectoryType | list[DirectoryType],
                              metadata_session: MetadataSession) -> Self:
        return cls(
            _collections_files=collection_files,
            _directories=directories if isinstance(directories, list) else [directories],
            _metadata_session=metadata_session,
        )

    def __post_init__(self) -> None:
        self._init_xmp_files()
        self._load_metadata()

    def _init_xmp_files(self) -> None:
        xmp_files: list[CollectionFile] = []
        for directory_type in self._directories:
            xmp_files += self._collections_files.get_directory_files_by_type(directory_type, FileType.XMP)
        # Use __setattr__ to avoid FrozenInstanceError
        object.__setattr__(self, "_xmp_files", xmp_files)

    def _load_metadata(self) -> None:
        self._metadata_session.load_metadata(self._xmp_files)

    def get_metadata(self, file: CollectionFile) -> MetadataTypeToValues:
        return self._metadata_session.get_metadata(file)

    def set_metadata(self, file: CollectionFile, metadata_type_to_values: MetadataTypeToValues) -> None:
        self._metadata_session.set_metadata(file.path, metadata_type_to_values)

    def get_rating(self, file: CollectionFile) -> int | None:
        if not ((xmp_path := self._get_xmp_path(file))
                and (rating := self._metadata_session.get_metadata_by_type(xmp_path, MetadataType.RATING))):
            return None
        if isinstance(rating, int):
            return rating
        if isinstance(rating, str):
            return int(rating)
        raise TypeError

    def _get_xmp_path(self, file: CollectionFile) -> Path | None:
        if file.file_type == FileType.XMP:
            return file.path

        if file.file_type != FileType.JPEG:
            raise ValueError

        return next((xmp_file.path
                     for xmp_file in self._xmp_files
                     if (xmp_file.filename_stem == file.filename_stem
                         and xmp_file.directory == file.directory)),
                    None)
