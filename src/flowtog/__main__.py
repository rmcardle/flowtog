import argparse
import logging
import sys
from enum import Enum, auto
from typing import Final

from flowtog import __version__
from flowtog.collectiondirectorycreator import create_directories
from flowtog.collectionfileimporter import import_files
from flowtog.collectionfilemover import move_sorted_files, move_to_rejected
from flowtog.collectionfiles import CollectionFiles
from flowtog.collectionmetadata import CollectionMetadata
from flowtog.collectionvalidator import CollectionValidator
from flowtog.config import Config
from flowtog.filegroup import FileGroup
from flowtog.menu import get_menu_choice
from flowtog.metadatasession import MetadataSession, validate_exiftool
from flowtog.syncpeople import sync_people

_LOG: Final[logging.Logger] = logging.getLogger(__package__)
_LOG.setLevel(logging.INFO)

_ROOT_DIR: Final[str] = r""


def _main(args: argparse.Namespace) -> None:
    _configure_logger(args)

    _LOG.debug(f"Flowtog {__version__} starting")

    if not validate_exiftool():
        _LOG.error("ExifTool not found")
        return

    _LOG.info(f"Root directory: {_ROOT_DIR}")

    while _show_main_menu():
        pass

    _LOG.debug(f"Flowtog {__version__} exiting")


def _show_main_menu() -> bool:
    match get_menu_choice(
        [
            "_Create directories",
            "_Import photos from media",
            "_Move sorted photos",
            "Move selected photo to _rejected",
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
        case "m":
            _move_sorted_files()
        case "r":
            _move_to_rejected()
        case "s":
            _sync_people()
        case "v":
            _validate_collection()
        case _:
            return False

    return True


def _create_directories() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]

    create_directories(collection)


def _import_files() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    import_files(collection_files)


def _move_sorted_files() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    if (last_group := _prompt_for_group(collection_files, allow_all=True)) == _GroupSelection.NONE:
        return

    with MetadataSession() as metadata_session:
        collection_metadata = CollectionMetadata.from_collection_files(collection_files, metadata_session)

        move_sorted_files(collection_files,
                          collection_metadata,
                          last_group=None if last_group == _GroupSelection.ALL else last_group)


def _move_to_rejected() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    while True:
        group = _prompt_for_group(collection_files)
        if not isinstance(group, FileGroup):
            return

        move_to_rejected(group, collection)
        print()  # noqa: T201 print


def _sync_people() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    with MetadataSession() as metadata_session:
        collection_metadata = CollectionMetadata.from_collection_files(collection_files, metadata_session)

        sync_people(collection_files, collection_metadata)


def _validate_collection() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    with MetadataSession() as metadata_session:
        collection_metadata = CollectionMetadata.from_collection_files(collection_files, metadata_session)

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


def _configure_logger(args: argparse.Namespace) -> None:
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_formatter = logging.Formatter("%(message)s")
    stdout_handler.setFormatter(stdout_formatter)

    # TODO: add file handler

    _LOG.addHandler(stdout_handler)


def _parse_arguments() -> argparse.Namespace:
    description = "A workflow tool for photographers."

    version_message = (
        f"%(prog)s (Flowtog) {__version__}\n"
        f"Copyright (c) 2025-26 Riley McArdle\n"
        "Distributed under the terms of the GNU General Public License version 3"
    )

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
    )

    options_group = parser.add_argument_group("options")
    options_group.add_argument("-h", "--help", action="help", help="show this help message and exit")
    options_group.add_argument("-v", "--version", action="version", version=version_message)

    return parser.parse_args()


if __name__ == "__main__":
    _main(_parse_arguments())
