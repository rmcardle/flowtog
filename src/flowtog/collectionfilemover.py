import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import CollectionDirectories, DirectoryType
from flowtog.filetype import FileType
from flowtog.log_utils import log_file_path
from flowtog.metadatatype import MetadataType
from flowtog.path_utils import FilePair, move_files

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.config import CollectionConfig
    from flowtog.filegroup import FileGroup
    from flowtog.metadatasession import MetadataSession

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


def move_sorted_files(collection_files: CollectionFiles,
                      collection_metadata: CollectionMetadata,
                      *,
                      last_group: FileGroup | None = None) -> None:
    directories = collection_files.directories
    if _has_missing_directories(directories[DirectoryType.REJECTED],
                                directories[DirectoryType.RAW],
                                directories[DirectoryType.PHOTOS]):
        return

    for group in collection_files.get_groups_by_directory(DirectoryType.UNSORTED):
        if last_group and group.group_num > last_group.group_num:
            return

        if _has_multiple_files(group):
            continue

        is_selected = _is_selected(group, collection_metadata, collection_files.collection.selected_rating)
        _move_sorted_group(group, directories, collection_metadata.metadata_session, is_selected=is_selected)


def move_to_rejected(group: FileGroup, collection: CollectionConfig, metadata_session: MetadataSession) -> None:
    directories = CollectionDirectories.from_collection(collection)
    if _has_missing_directories(directories[DirectoryType.REJECTED]):
        return

    _move_sorted_group(group, directories, metadata_session, is_selected=False)


def _has_missing_directories(*directories: Path) -> bool:
    has_missing_directories = False

    for directory in directories:
        if not directory.is_dir():
            _LOG.error(f"{directory} does not exist")
            has_missing_directories = True

    return has_missing_directories


def _has_multiple_files(group: FileGroup) -> bool:
    has_multiple = False

    for file_type in group.file_types:
        if FileType.JPEG and group.has_edits:
            continue

        files = group.file_type_to_files[file_type]
        if len(files) > 1:
            log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Multiple {file_type.value} files", files)
            has_multiple = True

    return has_multiple


def _is_selected(group: FileGroup, collection_metadata: CollectionMetadata, selected_rating: int) -> bool:
    if FileType.XMP not in group.file_types:
        return False

    xmp_file = group.get_single_file_from_type(FileType.XMP)
    rating = collection_metadata.get_rating(xmp_file)
    return rating is not None and rating >= selected_rating


def _move_sorted_group(group: FileGroup,
                       directories: CollectionDirectories,
                       metadata_session: MetadataSession,
                       *,
                       is_selected: bool) -> None:
    moves: list[FilePair] = []
    xmp_destination_file: Path | None = None

    if not is_selected:
        moves += _get_moves(group.files, directories[DirectoryType.REJECTED])
    else:
        if FileType.OTHER in group.file_types:
            files = group.file_type_to_files[FileType.OTHER]
            log_file_path(_LOG, logging.ERROR, f"Ignoring {group.group_name} - Group has other files", files)
            return

        moves += _get_moves(group.file_type_to_files[FileType.RAW], directories[DirectoryType.RAW])

        if group.has_edits:
            moves += _get_edit_moves(group, directories)
        else:
            # Move XMP files first so that any programs watching the photos dir can read the
            # XMP file as soon as the JPEG file appears
            xmp_moves = list(_get_moves(group.file_type_to_files[FileType.XMP], directories[DirectoryType.PHOTOS]))
            assert len(xmp_moves) == 1
            _, xmp_destination_file = xmp_moves[0]
            moves += xmp_moves

            moves += _get_moves(group.file_type_to_files[FileType.JPEG], directories[DirectoryType.PHOTOS])

    if not move_files(moves):
        _LOG.error(f"Group was not moved\n\t{'\n\t'.join(map(str, group.files))}")

    if is_selected and xmp_destination_file:
        metadata_session.set_metadata(xmp_destination_file, {MetadataType.RATING: ""})


def _get_moves(files: Iterable[CollectionFile], destination_dir: Path) -> Iterator[FilePair]:
    yield from ((Path(file), destination_dir / file.filename) for file in files)


def _get_edit_moves(group: FileGroup, directories: CollectionDirectories) -> Iterator[FilePair]:
    # RAW files are already handled, we only need to handle JPEG and XMP files here
    raise NotImplementedError
