from argparse import ArgumentTypeError
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from flowtog.filetype import FileType
from flowtog.metadatatype import MetadataType
from flowtog.path_utils import get_filename_stem

if TYPE_CHECKING:
    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.metadatasession import MetadataByType, MetadataSession, MetadataValue


@dataclass(frozen=True)
class CollectionMetadata:
    _files: CollectionFiles
    _metadata_session: MetadataSession

    @classmethod
    def from_collection_files(cls, collection_files: CollectionFiles, metadata_session: MetadataSession) -> Self:
        return cls(
            _files=collection_files,
            _metadata_session=metadata_session,
        )

    def __post_init__(self) -> None:
        self._load_metadata()

    def _load_metadata(self) -> None:
        self._metadata_session.load_metadata(self._files.get_files_by_type(FileType.XMP))

    def get_metadata(self, file: CollectionFile) -> MetadataByType:
        return self._metadata_session.get_metadata(file)

    def get_rating(self, file: CollectionFile) -> int | None:
        if not ((xmp_path := self._get_xmp_path(file))
                and (rating := self._metadata_session.get_metadata_by_type(xmp_path, MetadataType.RATING))):
            return None
        if isinstance(rating, int):
            return rating
        if isinstance(rating, str):
            return int(rating)
        raise ArgumentTypeError

    def set_metadata(self, file: CollectionFile, metadata_by_type: MetadataByType) -> None:
        self._metadata_session.set_metadata(file, metadata_by_type)

    def _get_xmp_path(self, file: CollectionFile) -> str | None:
        if file.file_type == FileType.XMP:
            return file.path

        assert file.file_type == FileType.JPEG

        # TODO: Find a match in CollectionFiles instead of just guessing
        # This way will not work if the extension is not lowercase
        xmp_file_path = get_filename_stem(file) + ".xmp"

        for xmp_file in self._files.get_files_by_type(FileType.XMP):
            if xmp_file.path == xmp_file_path:
                return xmp_file.path

        return None
