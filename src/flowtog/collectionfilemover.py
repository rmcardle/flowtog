import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from flowtog.collectiondirectories import CollectionDirectories, DirectoryType
from flowtog.filetype import FileType
from flowtog.log_utils import log_file_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.config import CollectionConfig
    from flowtog.filegroup import FileGroup

_LOG = logging.getLogger(__name__)


def move_sorted_files(collection_files: CollectionFiles,
                      collection_metadata: CollectionMetadata,
                      *,
                      last_group: FileGroup | None = None) -> None:
    _LOG.debug("Move sorted photos")

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
        _move_sorted_group(group, directories, is_selected=is_selected)


def move_to_rejected(group: FileGroup, collection: CollectionConfig) -> None:
    _LOG.debug("Move selected photo to rejected")

    directories = CollectionDirectories.from_collection(collection)
    if _has_missing_directories(directories[DirectoryType.REJECTED]):
        return

    _move_sorted_group(group, directories, is_selected=False)


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

        files = group.files_by_type[file_type]
        if len(files) > 1:
            log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Multiple {file_type.value} files", files)
            has_multiple = True

    return has_multiple


def _is_selected(group: FileGroup, collection_metadata: CollectionMetadata, selected_rating: int) -> bool:
    if FileType.XMP in group.file_types:
        if not (xmp_files := group.files_by_type[FileType.XMP]):
            raise AssertionError

        if len(xmp_files) != 1:
            raise AssertionError

        if ((rating := collection_metadata.get_rating(xmp_files[0]))
                and rating >= selected_rating):
            return True

    return False


@dataclass(frozen=True)
class CollectionFileMoveRecord:
    source_file: Path
    destination_file: Path


def _move_sorted_group(group: FileGroup, directories: CollectionDirectories, *, is_selected: bool) -> None:
    moves: list[CollectionFileMoveRecord] = []

    if not is_selected:
        moves += _get_moves(group.files, directories[DirectoryType.REJECTED])
    else:
        if FileType.OTHER in group.file_types:
            files = group.files_by_type[FileType.OTHER]
            log_file_path(_LOG, logging.ERROR, f"Ignoring {group.group_name} - Group has other files", files)
            return

        moves += _get_moves(group.files_by_type[FileType.RAW], directories[DirectoryType.RAW])

        if group.has_edits:
            moves += _get_edit_moves(group, directories)
        else:
            # Move XMP files first so that any programs watching the photos dir can read the
            # XMP file as soon as the JPEG file appears
            moves += _get_moves(group.files_by_type[FileType.XMP], directories[DirectoryType.PHOTOS])
            moves += _get_moves(group.files_by_type[FileType.JPEG], directories[DirectoryType.PHOTOS])

    if existing_destination_files := [move.destination_file for move in moves if move.destination_file.exists()]:
        log_file_path(
            _LOG,
            logging.ERROR,
            f"Ignoring {group.group_name} - One or more group files already exist in the destination directories",
            existing_destination_files,
        )
        return

    for move in moves:
        _LOG.info(f"Moving {move.source_file} -> {move.destination_file}")
        move.source_file.rename(move.destination_file)

    if is_selected:
        # TODO: Remove rating
        pass


def _get_moves(files: Iterable[CollectionFile], destination_dir: Path) -> list[CollectionFileMoveRecord]:
    return [CollectionFileMoveRecord(Path(file), destination_dir / file.filename) for file in files]


def _get_edit_moves(group: FileGroup, directories: CollectionDirectories) -> list[CollectionFileMoveRecord]:
    # RAW files are already handled, we only need to handle JPEG and XMP files here
    raise NotImplementedError
