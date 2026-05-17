import argparse
import logging
import os
import sys
from enum import Enum, auto
from io import TextIOBase
from pathlib import Path
from typing import Final, TextIO

from flowtog import __version__
from flowtog.collectiondirectories import DirectoryType
from flowtog.collectiondirectorycreator import create_directories
from flowtog.collectionfilemover import move_edit_files, move_group_to_rejected, move_sorted_files
from flowtog.collectionfiles import CollectionFiles
from flowtog.collectionmetadata import CollectionMetadata
from flowtog.collectionvalidator import CollectionValidator
from flowtog.config import Config, find_related_config_file, resolve_config_file
from flowtog.diskusagereporter import report_media_usage
from flowtog.filegroup import FileGroup
from flowtog.filetype import FileType
from flowtog.log_utils import LogStartExit
from flowtog.mediachecker import check_media
from flowtog.mediapreparer import prepare_media
from flowtog.menu import get_menu_choice, get_yes_no, pause
from flowtog.metadatasession import MetadataSession, validate_exiftool
from flowtog.peoplekeywordsync import sync_people
from flowtog.peoplereporter import report_people
from flowtog.photoimporter import import_photos
from flowtog.process_utils import processes_are_running
from flowtog.sonyimagingedge import edit_file
from flowtog.videoimporter import import_videos

_LOG: Final[logging.Logger] = logging.getLogger(__package__)
_LOG.setLevel(logging.DEBUG)

_LOG_FILE_NAME: Final[str] = "flowtog-log.txt"
_LOG_FILE_LEVEL: Final[int] = logging.DEBUG
_LOG_FILE_FORMAT: Final[str] = "%(asctime)s <%(levelname)s> %(name)s: %(message)s"

_LOG_CONSOLE_LEVEL: Final[int] = logging.INFO
_LOG_CONSOLE_FORMAT: Final[str] = "%(message)s"


_CHECK_RUNNING_PROCESS_FILENAMES: Final[list[str]] = [
    "aspect.exe",
    "Mylio.exe",
]

_config_file: Path


def _main() -> None:
    args = _parse_arguments()

    if not (config_file := _get_config_file(args)):
        return

    global _config_file  # noqa: PLW0603 global-statement
    _config_file = config_file

    _configure_loggers()

    with LogStartExit(_LOG, logging.DEBUG, f"Flowtog {__version__}"):
        _LOG.info(f"Root directory: {_config_file.parent}")

        if not validate_exiftool():
            _LOG.error("ExifTool not found")
            return

        if args.edit:
            _edit_photo(args.edit)
            return

        while _show_main_menu():
            pass


def _show_main_menu() -> bool:
    match get_menu_choice(
        [
            "_Create directories",
            "_Prepare media",
            "Check media for _uncopied files",
            "_Import photos and videos from media",
            "_Move sorted photos",
            "Move selected photo to _rejected",
            "_Edit photo with Sony Imaging Edge Edit",
            "_Sync people to keywords",
            "_Validate collection",
            "View _log file",
            None,
            "E_xit",
        ],
        title="Main Menu",
        escape_choice="x",
    ):
        case "c":
            _create_directories()
        case "p":
            _prepare_media()
        case "u":
            _check_media()
        case "i":
            _import_files()
        case "m":
            _move_sorted_files()
        case "r":
            _move_to_rejected()
        case "e":
            _edit_photo()
        case "s":
            _sync_people()
        case "v":
            _validate_collection()
        case "l":
            _view_log_file()
        case _:
            return False

    return True


def _create_directories() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Create directories"):
        config = Config.load(_config_file)
        create_directories(config.collection)


def _prepare_media() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Prepare media"):
        config = Config.load(_config_file)
        collection_files = CollectionFiles.from_collection(config.collection)

        prepare_media(collection_files)


def _check_media() -> None:
    config = Config.load(_config_file)

    with LogStartExit(_LOG, logging.DEBUG, "Check media for uncopied files"):
        check_media(config)


def _import_files() -> None:
    config = Config.load(_config_file)

    with LogStartExit(_LOG, logging.DEBUG, "Import photos from media"):
        collection_files = CollectionFiles.from_collection(config.collection)
        import_photos(collection_files)

    print()  # noqa: T201 print

    with LogStartExit(_LOG, logging.DEBUG, "Import videos from media"):
        import_videos(collection_files.directories)

    print()  # noqa: T201 print

    report_media_usage()


def _move_sorted_files() -> None:
    if processes_are_running(_CHECK_RUNNING_PROCESS_FILENAMES):
        return

    with LogStartExit(_LOG, logging.DEBUG, "Move sorted photos"):
        config = Config.load(_config_file)
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
        config = Config.load(_config_file)
        collection_files = CollectionFiles.from_collection(config.collection)

        while True:
            group = _prompt_for_group(collection_files)
            if not isinstance(group, FileGroup):
                return

            move_group_to_rejected(group, config.collection)
            print()  # noqa: T201 print


def _edit_photo(paths: list[Path] | None = None) -> None:
    with (LogStartExit(_LOG, logging.DEBUG, "Edit photo with Sony Imaging Edge Edit")):
        config = Config.load(_config_file)
        collection_files = CollectionFiles.from_collection(config.collection)

        edit_files = paths

        while not edit_files:
            group = _prompt_for_group(collection_files)
            if not isinstance(group, FileGroup):
                return

            if single_file := group.try_get_single_file_from_type(FileType.RAW):
                edit_files = [single_file.path]
                break

        if (edit_file(edit_files, collection_files)
                and get_yes_no(prompt="Would you like to move edit files to their correct locations?")):
            # collection_files has a stale view of the file system so reinitialize it
            collection_files = CollectionFiles.from_collection(config.collection)
            move_edit_files(collection_files)

    # If path was specified, we were not run interactively
    # Pause so the user can read any errors or messages before the console window closes
    if paths:
        pause()


def _sync_people() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Sync people to keywords"):
        config = Config.load(_config_file)
        collection_files = CollectionFiles.from_collection(config.collection)

        with MetadataSession() as metadata_session:
            collection_metadata = CollectionMetadata.from_collection_files(collection_files,
                                                                           DirectoryType.PHOTOS,
                                                                           metadata_session)

            people_counts = sync_people(collection_files, config, collection_metadata)
            report_people(people_counts, config)


def _validate_collection() -> None:
    with LogStartExit(_LOG, logging.DEBUG, "Validate collection"):
        config = Config.load(_config_file)
        collection_files = CollectionFiles.from_collection(config.collection)

        with MetadataSession() as metadata_session:
            collection_metadata = CollectionMetadata.from_collection_files(collection_files,
                                                                           DirectoryType.UNSORTED,
                                                                           metadata_session)

            validator = CollectionValidator.from_collection_files(collection_files, collection_metadata)
            validator.validate()


def _view_log_file() -> None:
    os.startfile(_get_log_file_path())  # noqa: S606 start-process-with-no-shell


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


def _configure_loggers() -> None:
    _configure_logger(_get_log_file_path(), _LOG_FILE_LEVEL, _LOG_FILE_FORMAT)
    _configure_logger(sys.stdout, _LOG_CONSOLE_LEVEL, _LOG_CONSOLE_FORMAT)


def _configure_logger(destination: str | os.PathLike[str] | TextIO,
                      level: int | str,
                      fmt: str | None = None) -> None:
    # The standard streams (sys.stdout, etc.) are type hinted as TextIO but inherit from TextIOBase at runtime
    handler = (logging.StreamHandler(destination)
               if isinstance(destination, TextIOBase)
               else logging.FileHandler(destination))  # pyright: ignore [reportArgumentType]
    handler.setLevel(level)
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    _LOG.addHandler(handler)


def _get_log_file_path() -> Path:
    return _config_file.parent / _LOG_FILE_NAME


def _get_config_file(args: argparse.Namespace) -> Path | None:
    if args.edit and len(args.edit) > 0 and (config_file := find_related_config_file(args.edit[0])):
        return config_file

    if not args.root_dir:
        # _LOG isn't configured yet so we need to use print
        print("A collection directory is required")  # noqa: T201 print
        return None

    if config_file := resolve_config_file(args.root_dir):
        return config_file

    # _LOG isn't configured yet so we need to use print
    print("The specified collection directory does not exist")  # noqa: T201 print
    return None


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
                        nargs="+",
                        type=Path,
                        help="edit FILE with Sony Imaging Edge Edit",
                        metavar="FILE")

    parser.add_argument("-h", "--help", action="help", help="show this help message and exit")
    parser.add_argument("-v", "--version", action="version", version=version_message)

    return parser.parse_args()


if __name__ == "__main__":
    _main()
