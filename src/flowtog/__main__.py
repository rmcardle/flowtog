import argparse
import logging
import sys
from typing import Final

from flowtog import __version__
from flowtog.collectionfileimporter import import_files
from flowtog.collectionfilemover import move_sorted_files
from flowtog.collectionfiles import CollectionFiles
from flowtog.collectionmetadata import CollectionMetadata
from flowtog.collectionvalidator import CollectionValidator
from flowtog.config import Config
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
            "_Import photos from media",
            "_Move sorted photos",
            "_Sync people to keywords",
            "_Validate collection",
            None,
            "E_xit",
        ],
        title="Main Menu",
        escape_choice="x",
    ):
        case "i":
            _import_files()
        case "m":
            _move_sorted_files()
        case "s":
            _sync_people()
        case "v":
            _validate_collection()
        case _:
            return False

    return True


def _import_files() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    with MetadataSession() as metadata_session:
        import_files(collection_files, metadata_session)


def _move_sorted_files() -> None:
    config: Config = Config.load(f"{_ROOT_DIR}\\flowtog.toml")
    collection = config.collection["DSC"]
    collection_files = CollectionFiles.from_collection(collection)

    with MetadataSession() as metadata_session:
        collection_metadata = CollectionMetadata.from_collection_files(collection_files, metadata_session)

        move_sorted_files(collection_files, collection_metadata)


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
