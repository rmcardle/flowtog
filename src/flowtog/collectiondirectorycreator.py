import logging
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import CollectionDirectories
from flowtog.menu import get_yes_no

if TYPE_CHECKING:
    from pathlib import Path

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


def create_directories(collection: CollectionConfig) -> None:
    _LOG.debug("Create directories")

    existing_dirs, dirs_to_create = _get_directories(collection)

    _display_directories(existing_dirs, dirs_to_create)

    if not dirs_to_create:
        _LOG.info("All directories already exist")
        return

    if not get_yes_no(prompt="Would you like to create these directories"):
        return

    _create_directories(dirs_to_create)

    # TODO: Copy example toml
    # _copy_example_config()


def _get_directories(collection: CollectionConfig) -> tuple[list[Path], list[Path]]:
    directories = CollectionDirectories.from_collection(collection)

    existing_dirs: list[Path] = []
    dirs_to_create: list[Path] = []

    for directory in directories:
        if directory.is_dir():
            existing_dirs.append(directory)
        else:
            dirs_to_create.append(directory)

    return existing_dirs, dirs_to_create


def _display_directories(existing_dirs: list[Path], dirs_to_create: list[Path]) -> None:
    for directory_list in (existing_dirs, dirs_to_create):
        if not directory_list:
            continue

        # ruff: disable[T201] print
        if directory_list == existing_dirs:
            print("Existing Directories:")
        else:
            print("Directories to Create:")

        for directory in directory_list:
            print(f"  {directory}")

        print()
        # ruff: enable[T201] print


def _create_directories(directories: list[Path]) -> None:
    for directory in directories:
        _LOG.info(f"Creating {directory}")
        directory.mkdir(parents=True)
