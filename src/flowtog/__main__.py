import argparse
import logging
import sys
from enum import Enum, auto
from pathlib import Path
from typing import Final

from flowtog import __version__
from flowtog.collectiondirectories import DirectoryType
from flowtog.collectiondirectorycreator import create_directories
from flowtog.collectionfilemover import move_edit_files, move_group_to_rejected, move_sorted_files
from flowtog.collectionfiles import CollectionFiles
from flowtog.collectionmetadata import CollectionMetadata
from flowtog.collectionvalidator import CollectionValidator
from flowtog.config import Config
from flowtog.diskusagereporter import report_media_usage
from flowtog.filegroup import FileGroup
from flowtog.filetype import FileType
from flowtog.log_utils import LogStartExit
from flowtog.mediachecker import check_media
from flowtog.menu import get_menu_choice
from flowtog.metadatasession import MetadataSession, validate_exiftool
from flowtog.peoplekeywordsync import sync_people
from flowtog.peoplereporter import report_people
from flowtog.photoimporter import import_photos
from flowtog.sonyimagingedge import SonyImagingEdge
from flowtog.videoimporter import import_videos

_LOG: Final[logging.Logger] = logging.getLogger(__package__)
_LOG.setLevel(logging.INFO)

_root_dir: Path


def _main() -> None:
    _configure_logger()
    with LogStartExit(_LOG, logging.DEBUG, f"Flowtog {__version__}"):
        args = _parse_arguments()

        if not _set_root_dir(args):
            return

        _LOG.info(f"Root directory: {_root_dir}")

        if not validate_exiftool():
            _LOG.error("ExifTool not found")
            return

        if args.edit:
            SonyImagingEdge.launch(args.edit)
            return

        while _show_main_menu():
            pass


def _show_main_menu() -> bool:
    match get_menu_choice(
        [
            "_Create directories",
            "_Import photos and videos from media",
            "Check media for _uncopied files",
            "_Move sorted photos",
            "Move selected photo to _rejected",
            "Launch Sony Imaging Edge _Edit",
            "_Sync people to keywords",
            "_Validate collection",
            None,
            "E_xit",
        ],
        title="Main Menu",
        escape_choice="x",
    ):
        case "c":
            _create_directories()
        case "i":
            _import_files()
        case "u":
            _check_media()
        case "m":
            _move_sorted_files()
        case "r":
            _move_to_rejected()
        case "e":
            _edit_raw()
        case "s":
            _sync_people()
        case "v":
            _validate_collection()
        case _:
            return False

    return True


def _create_directories() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Create directories"):
        config = Config.load(_root_dir)
        create_directories(config.collection)


def _import_files() -> None:
    config = Config.load(_root_dir)

    with LogStartExit(_LOG, logging.DEBUG, "Import photos from media"):
        collection_files = CollectionFiles.from_collection(config.collection)
        import_photos(collection_files)

    print()  # noqa: T201 print

    with LogStartExit(_LOG, logging.DEBUG, "Import videos from media"):
        import_videos(collection_files.directories)

    print()  # noqa: T201 print

    report_media_usage()


def _check_media() -> None:
    config = Config.load(_root_dir)

    with LogStartExit(_LOG, logging.DEBUG, "Check media for uncopied files"):
        check_media(config)


def _move_sorted_files() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Move sorted photos"):
        config = Config.load(_root_dir)
        collection_files = CollectionFiles.from_collection(config.collection)

        if (last_group := _prompt_for_group(collection_files, allow_all=True)) == _GroupSelection.NONE:
            return

        with MetadataSession() as metadata_session:
            collection_metadata = CollectionMetadata.from_collection_files(collection_files,
                                                                           DirectoryType.UNSORTED,
                                                                           metadata_session)

            move_sorted_files(collection_files,
                              collection_metadata,
                              last_group=None if last_group == _GroupSelection.ALL else last_group)

            move_edit_files(collection_files)


def _move_to_rejected() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Move selected photo to rejected"):
        config = Config.load(_root_dir)
        collection_files = CollectionFiles.from_collection(config.collection)

        while True:
            group = _prompt_for_group(collection_files)
            if not isinstance(group, FileGroup):
                return

            move_group_to_rejected(group, config.collection)
            print()  # noqa: T201 print


def _edit_raw() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Launch Sony Imaging Edge Edit"):
        config = Config.load(_root_dir)
        collection_files = CollectionFiles.from_collection(config.collection)

        while True:
            group = _prompt_for_group(collection_files)
            if not isinstance(group, FileGroup):
                return

            if (FileType.RAW in group.file_types
                    and (raw_files := group.file_type_to_files[FileType.RAW])
                    and len(raw_files) == 1):
                raw_file = raw_files[0]
                break

        SonyImagingEdge.launch(raw_file.path)


def _sync_people() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Sync people to keywords"):
        config = Config.load(_root_dir)
        collection_files = CollectionFiles.from_collection(config.collection)

        with MetadataSession() as metadata_session:
            collection_metadata = CollectionMetadata.from_collection_files(collection_files,
                                                                           DirectoryType.PHOTOS,
                                                                           metadata_session)

            people_counts = sync_people(collection_files, config, collection_metadata)
            report_people(people_counts, config)


def _validate_collection() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Validate collection"):
        config = Config.load(_root_dir)
        collection_files = CollectionFiles.from_collection(config.collection)

        with MetadataSession() as metadata_session:
            collection_metadata = CollectionMetadata.from_collection_files(collection_files,
                                                                           DirectoryType.UNSORTED,
                                                                           metadata_session)

            validator = CollectionValidator.from_collection_files(collection_files, collection_metadata)
            validator.validate()


class _GroupSelection(Enum):
    ALL = auto()
    NONE = auto()


def _prompt_for_group(collection_files: CollectionFiles,
                      *,
                      allow_all: bool = False) -> FileGroup | _GroupSelection:
    group: FileGroup | _GroupSelection = _GroupSelection.NONE
    while group == _GroupSelection.NONE:
        prompt = 'Group number or "all" (Enter to cancel): ' if allow_all else "Group number (Enter to cancel): "
        if not (group_num := input(prompt)):
            return _GroupSelection.NONE

        if allow_all and group_num.lower() in ("a", "all"):
            return _GroupSelection.ALL

        try:
            group_num = int(group_num)
        except ValueError:
            continue

        group = collection_files.get_group_by_num(group_num) or _GroupSelection.NONE

    return group


def _configure_logger() -> None:
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_formatter = logging.Formatter("%(message)s")
    stdout_handler.setFormatter(stdout_formatter)

    # TODO: add file handler

    _LOG.addHandler(stdout_handler)


def _set_root_dir(args: argparse.Namespace) -> bool:
    global _root_dir  # noqa: PLW0603 global-statement

    if not args.root_dir:
        _LOG.error("A collection directory is required")
        return False

    root_dir = Path(args.root_dir)
    if not root_dir.is_dir():
        _LOG.error("The specified collection directory does not exist")
        return False

    _root_dir = root_dir

    return True


def _parse_arguments() -> argparse.Namespace:
    description: Final[str] = "A workflow tool for photographers."

    version_message: Final[str] = (
        f"Flowtog {__version__}\n"
        "Copyright \u24B8 2025-26 Riley McArdle\n"
        "License GPLv3: GNU GPL version 3 <https://gnu.org/licenses/gpl.html>.\n"
        "This is free software: you are free to change and redistribute it.\n"
        "There is NO WARRANTY, to the extent permitted by law."
    )

    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     add_help=False)

    parser.add_argument("root_dir",
                        nargs="?",
                        type=Path,
                        help="collection directory",
                        metavar="DIR")

    parser.add_argument("-e", "--edit",
                        type=Path,
                        help="edit FILE with Sony Imaging Edge Edit",
                        metavar="FILE")

    parser.add_argument("-h", "--help", action="help", help="show this help message and exit")
    parser.add_argument("-v", "--version", action="version", version=version_message)

    return parser.parse_args()


if __name__ == "__main__":
    _main()
