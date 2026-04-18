import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType
from flowtog.log_utils import log_file_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.filegroup import FileGroup

_LOG = logging.getLogger(__name__)


class _MoveState:
    def __init__(self, collection_files: CollectionFiles, collection_metadata: CollectionMetadata) -> None:
        self.collection_metadata = collection_metadata
        self.selected_rating = collection_files.collection.selected_rating
        self.rejected_dir = collection_files.directories.get_directory_path(DirectoryType.REJECTED)
        self.raw_dir = collection_files.directories.get_directory_path(DirectoryType.RAW)
        self.photos_dir = collection_files.directories.get_directory_path(DirectoryType.PHOTOS)


def move_sorted_files(collection_files: CollectionFiles, collection_metadata: CollectionMetadata) -> None:
    state = _MoveState(collection_files, collection_metadata)

    for directory in (state.rejected_dir, state.raw_dir, state.photos_dir):
        if not directory.exists():
            _LOG.error(f"{directory} does not exist")
            return

    for group in collection_files.groups_in_unsorted_dir:
        _move_sorted_group(state, group)


@dataclass(frozen=True)
class CollectionFileMoveRecord:
    source_file: Path
    destination_file: Path


def _move_sorted_group(state: _MoveState, group: FileGroup) -> None:
    if _check_multiple_files(group):
        return

    moves: list[CollectionFileMoveRecord] = []

    if not _is_selected(state, group):
        moves += _get_moves(group.files, state.rejected_dir)
    else:
        if FileType.OTHER in group.file_types:
            files = group.get_type_files(FileType.OTHER)
            log_file_path(_LOG, logging.ERROR, f"Ignoring {group.group_name} - Group has other files", files)
            return

        moves += _get_moves(group.get_type_files(FileType.RAW), state.raw_dir)

        if group.has_edits:
            moves += _get_edit_moves(state, group)
        else:
            # Move XMP files first so that any programs watching the photos dir can read the
            # XMP file as soon as the JPEG file appears
            moves += _get_moves(group.get_type_files(FileType.XMP), state.photos_dir)
            moves += _get_moves(group.get_type_files(FileType.JPEG), state.photos_dir)

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

    # TODO: Remove rating


def _check_multiple_files(group: FileGroup) -> bool:
    has_multiple = False
    for file_type in group.file_types:
        if FileType.JPEG and group.has_edits:
            continue
        files = group.get_type_files(file_type)
        if len(files) > 1:
            log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Multiple {file_type.value} files", files)
            has_multiple = True
    return has_multiple


def _is_selected(state: _MoveState, group: FileGroup) -> bool:
    if FileType.XMP in group.file_types:
        if not (xmp_files := group.get_type_files(FileType.XMP)):
            raise AssertionError

        if len(xmp_files) != 1:
            raise AssertionError

        xmp_file = xmp_files[0]

        if ((rating := state.collection_metadata.get_rating(xmp_file))
                and rating >= state.selected_rating):
            return True

    return False


def _get_moves(files: Iterable[CollectionFile], destination_dir: Path) -> list[CollectionFileMoveRecord]:
    return [CollectionFileMoveRecord(Path(file), destination_dir / file.filename) for file in files]


def _get_edit_moves(state: _MoveState, group: FileGroup) -> list[CollectionFileMoveRecord]:
    # RAW files are already handled, we only need to handle JPEG and XMP files here
    raise NotImplementedError
