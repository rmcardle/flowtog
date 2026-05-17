import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import CollectionDirectories, DirectoryType, directories_are_missing
from flowtog.filetype import FileType
from flowtog.log_utils import log_file_path
from flowtog.metadatatype import MetadataType
from flowtog.path_utils import FilePair, move_files

if TYPE_CHECKING:
    from pathlib import Path

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.config import CollectionConfig
    from flowtog.filegroup import FileGroup
    from flowtog.metadatasession import MetadataSession

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass
class _MovePlan:
    moves: list[FilePair] = field(default_factory=list[FilePair])
    xmp_file_to_remove_rating: Path | None = None


@dataclass
class _SelectedGroupMovePlan:
    moves: list[FilePair] = field(default_factory=list[FilePair])
    xmp_destination_file: Path | None = None


###############
# Orchestrate

def move_sorted_files(collection_files: CollectionFiles,
                      collection_metadata: CollectionMetadata,
                      *,
                      last_group: FileGroup | None = None) -> None:
    directories = collection_files.directories
    if directories_are_missing(
        directories[DirectoryType.ORIGINALS],
        directories[DirectoryType.PHOTOS],
        directories[DirectoryType.PREVIOUS_EDITS],
        directories[DirectoryType.RAW],
        directories[DirectoryType.REJECTED],
        directories[DirectoryType.UNSORTED],
    ):
        return

    for group in collection_files.groups_in_unsorted_dir:
        if last_group and group.group_num > last_group.group_num:
            break

        if (_group_has_type_with_multiple_files(group)
                or _group_missing_raw_or_jpeg(group)
                or _group_has_other_files(group)):
            continue

        move_plan = _plan_move_group_to_sorted(group,
                                               directories,
                                               collection_metadata,
                                               collection_files.collection.selected_rating)
        _execute_move_plan(move_plan, collection_metadata.metadata_session)


def move_edit_files(collection_files: CollectionFiles) -> None:
    directories = collection_files.directories
    if directories_are_missing(
        directories[DirectoryType.ORIGINALS],
        directories[DirectoryType.PHOTOS],
        directories[DirectoryType.PREVIOUS_EDITS],
    ):
        return

    for group in collection_files.selected_groups_with_edits:
        if (_group_missing_raw_or_jpeg(group)
                or _group_has_other_files(group)):
            continue

        selected_move_plan = _plan_move_selected_edit_layout(group, directories)
        _execute_move_plan(_MovePlan(moves=selected_move_plan.moves))


def move_group_to_rejected(group: FileGroup, collection: CollectionConfig) -> None:
    directories = CollectionDirectories.from_collection(collection)
    if directories_are_missing(
        directories[DirectoryType.REJECTED],
    ):
        return

    move_plan = _plan_move_group_to_rejected(group, directories)
    _execute_move_plan(move_plan)


############
# Validate

def _group_has_type_with_multiple_files(group: FileGroup) -> bool:
    if not (type_to_multiple_files := _get_group_file_types_with_multiple_files(group)):
        return False

    lines = [f"Ignoring group {group} - Group has multiple files of the same type"]
    for file_type, files in type_to_multiple_files.items():
        lines.extend(f"\t{file_type.value} - {file}" for file in files)

    _LOG.error("\n".join(lines))
    return True


def _get_group_file_types_with_multiple_files(group: FileGroup) -> dict[FileType, list[CollectionFile]]:
    type_to_multiple_files: dict[FileType, list[CollectionFile]] = {}

    for file_type in group.file_types:
        if file_type == FileType.JPEG and group.has_edits:
            continue

        files = group.file_type_to_files[file_type]
        if len(files) > 1:
            type_to_multiple_files[file_type] = files

    return type_to_multiple_files


def _group_missing_raw_or_jpeg(group: FileGroup) -> bool:
    return _group_missing_file_types(group, [FileType.RAW, FileType.JPEG])


def _group_missing_file_types(group: FileGroup, file_types: list[FileType]) -> bool:
    missing_types = [file_type for file_type in file_types if file_type not in group.file_types]

    if not missing_types:
        return False

    missing_type_str = ", ".join(file_type.value for file_type in missing_types)

    _LOG.error(f"Ignoring group {group} - Group is missing required file type {missing_type_str}")
    return True


def _group_has_other_files(group: FileGroup) -> bool:
    if FileType.OTHER not in group.file_types:
        return False

    log_file_path(_LOG,
                  logging.ERROR,
                  f"Ignoring group {group} - Group has unrecognized files",
                  group.file_type_to_files[FileType.OTHER])
    return True


########
# Plan

def _plan_move_group_to_sorted(group: FileGroup,
                               directories: CollectionDirectories,
                               collection_metadata: CollectionMetadata,
                               selected_rating: int) -> _MovePlan:
    if _is_selected(group, collection_metadata, selected_rating):
        return _plan_move_group_to_selected(group, directories)

    return _plan_move_group_to_rejected(group, directories)


def _is_selected(group: FileGroup, collection_metadata: CollectionMetadata, selected_rating: int) -> bool:
    if FileType.XMP not in group.file_types:
        return False

    xmp_file = group.get_single_file_from_type(FileType.XMP)
    rating = collection_metadata.get_rating(xmp_file)
    return rating is not None and rating >= selected_rating


def _plan_move_group_to_selected(group: FileGroup,
                                 directories: CollectionDirectories) -> _MovePlan:
    if group.has_edits:
        selected_move_plan = _plan_move_unsorted_group_with_edits_to_selected(group, directories)
    else:
        selected_move_plan = _plan_move_group_without_edits_to_selected(group, directories)

    return _MovePlan(
        moves=selected_move_plan.moves,
        xmp_file_to_remove_rating=selected_move_plan.xmp_destination_file,
    )


def _plan_move_group_to_rejected(group: FileGroup,
                                 directories: CollectionDirectories) -> _MovePlan:
    moves: list[FilePair] = []

    for file in group.files:
        _add_file_to_dir_move_if_needed(moves, file, directories[DirectoryType.REJECTED])

    return _MovePlan(
        moves=moves,
    )


def _plan_move_unsorted_group_with_edits_to_selected(group: FileGroup,
                                                     directories: CollectionDirectories) -> _SelectedGroupMovePlan:
    moves: list[FilePair] = []

    _add_file_to_dir_move_if_needed(moves,
                                    group.get_single_file_from_type(FileType.RAW),
                                    directories[DirectoryType.RAW])

    selected_move_plan = _plan_move_selected_edit_layout(group, directories)

    return _SelectedGroupMovePlan(
        moves=moves + selected_move_plan.moves,
        xmp_destination_file=selected_move_plan.xmp_destination_file,
    )


def _plan_move_selected_edit_layout(group: FileGroup,
                                    directories: CollectionDirectories) -> _SelectedGroupMovePlan:
    moves: list[FilePair] = []

    xmp_file = group.get_single_file_from_type(FileType.XMP) if FileType.XMP in group.file_types else None
    xmp_destination_file = None

    jpeg_files = sorted(group.file_type_to_files[FileType.JPEG], key=lambda f: f.edit_num)
    last_file_index = len(jpeg_files) - 1

    for i, jpeg_file in enumerate(jpeg_files):
        if i < last_file_index:
            destination_dir = (directories[DirectoryType.PREVIOUS_EDITS]
                               if jpeg_file.is_edit
                               else directories[DirectoryType.ORIGINALS])
        else:  # last_file_index
            destination_dir = directories[DirectoryType.PHOTOS]

            if xmp_file:
                xmp_destination_file = destination_dir / (jpeg_file.path.stem + xmp_file.path.suffix)
                _add_path_move_if_needed(moves, xmp_file.path, xmp_destination_file)

        _add_file_to_dir_move_if_needed(moves, jpeg_file, destination_dir)

    return _SelectedGroupMovePlan(
        moves=moves,
        xmp_destination_file=xmp_destination_file,
    )


def _plan_move_group_without_edits_to_selected(group: FileGroup,
                                               directories: CollectionDirectories) -> _SelectedGroupMovePlan:
    moves: list[FilePair] = []

    _add_file_to_dir_move_if_needed(moves,
                                    group.get_single_file_from_type(FileType.RAW),
                                    directories[DirectoryType.RAW])

    photos_dir = directories[DirectoryType.PHOTOS]

    if FileType.XMP in group.file_types:
        xmp_file = group.get_single_file_from_type(FileType.XMP)
        xmp_destination_file = photos_dir / xmp_file.filename
        _add_path_move_if_needed(moves, xmp_file.path, xmp_destination_file)
    else:
        xmp_destination_file = None

    _add_file_to_dir_move_if_needed(moves,
                                    group.get_single_file_from_type(FileType.JPEG),
                                    photos_dir)

    return _SelectedGroupMovePlan(
        moves=moves,
        xmp_destination_file=xmp_destination_file,
    )


def _add_path_move_if_needed(moves: list[FilePair], source_file: Path, destination_file: Path) -> None:
    if source_file == destination_file:
        return
    moves.append((source_file, destination_file))


def _add_file_to_dir_move_if_needed(moves: list[FilePair], file: CollectionFile, destination_dir: Path) -> None:
    _add_path_move_if_needed(moves, file.path, destination_dir / file.filename)


###########
# Execute

def _execute_move_plan(move_plan: _MovePlan, metadata_session: MetadataSession | None = None) -> None:
    if not move_plan.moves:
        return

    if not move_files(move_plan.moves):
        formatted_moves = "\n\t".join(f"{source} -> {destination}" for source, destination in move_plan.moves)
        _LOG.error(f"Group was not moved\n\t{formatted_moves}")
        return

    if metadata_session and move_plan.xmp_file_to_remove_rating:
        metadata_session.set_metadata(move_plan.xmp_file_to_remove_rating, {MetadataType.RATING: ""})
