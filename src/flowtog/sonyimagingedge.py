import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final
from winreg import HKEY_LOCAL_MACHINE, REG_SZ, OpenKey, QueryValueEx

import pywinauto.timings  # pyright: ignore [reportMissingTypeStubs]
from pywinauto import Application, WindowSpecification, application  # pyright: ignore [reportMissingTypeStubs]
from pywinauto.application import ProcessNotFoundError  # pyright: ignore [reportMissingTypeStubs]

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType

if TYPE_CHECKING:
    from flowtog.collectionfiles import CollectionFiles

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

_CHANGE_DIR_RETRIES: Final[int] = 10
_CHANGE_DIR_RETRY_DELAY_SECS: Final[float] = 0.1


class SonyImagingEdge:
    @staticmethod
    def edit_file(file: Path, collection_files: CollectionFiles) -> bool:
        if not (group := collection_files.get_group_by_file(file)):
            _LOG.error(f"The file group for the specified file could not be found in the collection\n\t{file}")
            return False

        if not (raw_file := group.try_get_single_file_from_type(FileType.RAW)):
            _LOG.error(f"Could not get the RAW file for group {group}")
            return False

        if not (app := _launch_sie_edit(raw_file.path)):
            _LOG.error("Could not launch Sony Imaging Edge Edit")
            return False

        # if not _wait_for_main_window(app):
        #     _LOG.error("Could not locate main window")
        #     return False

        while app.is_process_running():
            if not (output_dialog := _wait_for_output_dialog(app)):
                # The process has exited
                break

            _set_output_dialog_file_type(output_dialog)

            # Get the current file name BEFORE we change the directory
            output_dialog_file_name = _get_output_dialog_file_name(output_dialog)

            save_directory = collection_files.directories[DirectoryType.PREVIOUS_EDITS]
            if not _set_output_dialog_directory(output_dialog, save_directory):
                _LOG.error("Could not set the output dialog directory")
                return False

            if save_file_name := _get_save_file_name(output_dialog_file_name, collection_files):
                _LOG.debug(f"Setting file name to {save_file_name}...")
                _set_output_dialog_file_name(output_dialog, save_file_name)
            else:
                _LOG.error(f"Could not get the new file name for file {output_dialog_file_name}")
                # _get_save_file_name() may have failed because the user exported a file that is not in the collection.
                # Don't return False though because they might still export a file that IS in the collection.

            # _LOG.debug("Waiting for the output dialog to close...")
            if not _wait_for_window(output_dialog, wait_for="exists", wait_not=True):
                # The process has exited
                break

        _LOG.debug("Sony Imaging Edge Edit has exited")
        return True


def _get_sie_edit_path() -> Path | None:
    try:
        with OpenKey(HKEY_LOCAL_MACHINE, r"SOFTWARE\Sony Corporation\Imaging Edge") as key:
            value, reg_type = QueryValueEx(key, "InstalledLocation")
    except (OSError, FileNotFoundError, PermissionError):
        return None

    if reg_type != REG_SZ:
        return None

    sie_edit_path: Path = Path(value) / "Edit.exe"
    return sie_edit_path if sie_edit_path.is_file() else None


def _launch_sie_edit(file: Path) -> Application | None:
    if not (sie_edit_path := _get_sie_edit_path()):
        _LOG.error("Could not locate Sony Imaging Edge Edit")
        return None

    try:
        process_id = application.process_from_module(sie_edit_path)  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]
    except ProcessNotFoundError:
        process_id = None
    else:
        _LOG.debug("Sony Imaging Edge Edit is already running")

    cmdline: str = subprocess.list2cmdline([sie_edit_path, file])
    app = Application(backend="win32").start(cmdline)  # pyright: ignore [reportUnknownMemberType]

    return Application().connect(process=process_id) if process_id else app  # pyright: ignore [reportUnknownMemberType, reportUnknownArgumentType]


# This isn't currently needed but could be useful in future
# def _wait_for_main_window(app: Application) -> bool:
#     # We can't use app.top_window because Edit shows a small progress bar window before loading the main window
#     main_window: WindowSpecification = app.window(title="Edit")  # pyright: ignore [reportUnknownMemberType]
#
#     _LOG.debug("Waiting for main window...")
#     try:
#         main_window.wait(wait_for="enabled", timeout=60)  # pyright: ignore [reportUnknownMemberType]
#     except pywinauto.timings.TimeoutError:
#         return False
#
#     return True


def _wait_for_output_dialog(app: Application) -> WindowSpecification | None:
    output_dialog: WindowSpecification = \
        app.window(title="Output", class_name="#32770")  # pyright: ignore [reportUnknownMemberType]

    # _LOG.debug("Waiting for the output dialog...")
    if _wait_for_window(output_dialog, wait_for="enabled"):
        return output_dialog

    return None


def _wait_for_window(window: WindowSpecification,
                     *,
                     wait_for: str,
                     wait_not: bool = False) -> bool:
    while window.app.is_process_running():  # pyright: ignore [reportUnknownMemberType]
        try:
            if wait_not:
                window.wait_not(wait_for_not=wait_for)  # pyright: ignore [reportUnknownMemberType]
            else:
                window.wait(wait_for=wait_for)  # pyright: ignore [reportUnknownMemberType]
        except pywinauto.timings.TimeoutError:
            continue
        else:
            return True
    return False


def _set_output_dialog_file_type(output_dialog: WindowSpecification) -> None:
    output_dialog.SaveAsTypeComboBox.select(0)  # pyright: ignore [reportUnknownMemberType]


def _set_output_dialog_directory(output_dialog: WindowSpecification, directory: Path) -> bool:
    _LOG.debug(f"Setting directory to {directory}...")
    # Set the text of the "File name" text box
    _set_output_dialog_file_name(output_dialog, str(directory))  # pyright: ignore [reportUnknownMemberType]

    # Make sure that the text has changed before we click the "Save" button
    if _get_output_dialog_file_name(output_dialog) != directory:
        _LOG.error('The text of the "File name" text box did not change')
        return False

    retries = 0
    while True:
        # _LOG.debug("Changing directory...")
        # Click the "Save" button to change the directory
        output_dialog.SaveButton.click()  # pyright: ignore [reportUnknownMemberType]

        # _LOG.debug("Checking that directory has changed...")
        # The "File name" text box will change back to the file name when the directory is changed
        if _get_output_dialog_file_name(output_dialog) != directory:
            break

        if retries >= _CHANGE_DIR_RETRIES:
            _LOG.error(f"Change directory retry limit reached - retried {retries} times")
            return False

        time.sleep(_CHANGE_DIR_RETRY_DELAY_SECS)
        retries += 1

    _LOG.debug(f"Retried {retries} times waiting for the directory to change")
    return True


def _get_output_dialog_file_name(output_dialog: WindowSpecification) -> Path:
    return Path(output_dialog.FileNameEdit.get_line(0))  # pyright: ignore [reportUnknownMemberType, reportUnknownArgumentType]


def _set_output_dialog_file_name(output_dialog: WindowSpecification, file_name: str) -> None:
    output_dialog.FileNameEdit.set_text(file_name)  # pyright: ignore [reportUnknownMemberType]


def _get_save_file_name(file_name: Path, collection_files: CollectionFiles) -> str | None:
    if not (group := collection_files.get_group_by_name(file_name.stem)):
        return None
    return f"{group}-{group.next_edit_num:02d}.JPG"
