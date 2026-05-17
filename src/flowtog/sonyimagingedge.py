import ctypes
import logging
import subprocess
import time
from ctypes import FormatError, create_unicode_buffer
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final
from winreg import HKEY_LOCAL_MACHINE, REG_SZ, OpenKey, QueryValueEx

import pywinauto.timings  # pyright: ignore [reportMissingTypeStubs]
from pywinauto import Application, WindowSpecification, application  # pyright: ignore [reportMissingTypeStubs]
from pywinauto.application import ProcessNotFoundError  # pyright: ignore [reportMissingTypeStubs]
from pywinauto.remote_memory_block import RemoteMemoryBlock  # pyright: ignore [reportMissingTypeStubs]

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType

if TYPE_CHECKING:
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.filegroup import FileGroup

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

_CHANGE_DIR_RETRIES: Final[int] = 10
_CHANGE_DIR_RETRY_DELAY_SECS: Final[float] = 0.1

_WM_USER: Final[int] = 0x0400
_CDM_FIRST: Final[int] = _WM_USER + 100
_CDM_GETFILEPATH: Final[int] = _CDM_FIRST + 1
_CDM_GETFOLDERPATH: Final[int] = _CDM_FIRST + 2


@dataclass(frozen=True)
class GroupSaveInfo:
    group: FileGroup
    save_file: Path
    edit_num: int


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

    if not _handle_output_dialogs(app, collection_files):
        return False

    _LOG.debug("Sony Imaging Edge Edit has exited")
    return True


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


def _handle_output_dialogs(app: Application, collection_files: CollectionFiles) -> bool:
    group_name_to_save_info: dict[str, GroupSaveInfo] = {}

    # Enable pywinauto logging
    # actionlogger.enable()

    while app.is_process_running():
        if not (output_dialog := _wait_for_output_dialog(app)):
            # The process has exited
            break

        _set_output_dialog_file_type(output_dialog)

        if not (original_file_path := _get_output_dialog_file_path(output_dialog)):
            _LOG.error("Could not get the file path of the output dialog")
            return False

        if group_save_info := _get_group_save_info(original_file_path,
                                                   collection_files,
                                                   group_name_to_save_info):
            group_name_to_save_info[group_save_info.group.group_name] = group_save_info

            _set_output_dialog_directory(output_dialog, group_save_info.save_file.parent)
            _set_output_dialog_file_name_text(output_dialog, group_save_info.save_file.name)
        else:
            # If this file isn't in the collection, don't return False
            # Keep handling output dialogs because the user might still export a file that IS in the collection
            pass

        # _LOG.debug("Waiting for the output dialog to close...")
        if not _wait_for_window(output_dialog, wait_for="exists", wait_not=True):
            # The process has exited
            break

    return True


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
    # Set the "Save as type" combo box to "JPEG Files (*.JPG)"
    output_dialog.SaveAsTypeComboBox.select(0)  # pyright: ignore [reportUnknownMemberType]


def _get_output_dialog_file_path(output_dialog: WindowSpecification) -> Path | None:
    file_name = _send_message_with_buffer(output_dialog, _CDM_GETFILEPATH)
    return Path(Path(file_name).name) if file_name else None


def _get_group_save_info(original_file_name: Path,
                         collection_files: CollectionFiles,
                         group_name_to_save_info: dict[str, GroupSaveInfo]) -> GroupSaveInfo | None:
    if not (group := collection_files.get_group_by_file(original_file_name, must_be_in_group=False)):
        _LOG.error(f"Could not get the collection file group for file {original_file_name}")
        return None

    if group_save_info := group_name_to_save_info.get(group.group_name):
        edit_num = group_save_info.edit_num + 1 if group_save_info.save_file.is_file() else group_save_info.edit_num
    else:
        edit_num = group.next_edit_num

    save_directory = _get_save_directory(group, collection_files)
    save_file_name = f"{group}-{edit_num:02d}.JPG"

    return GroupSaveInfo(
        group=group,
        save_file=save_directory / save_file_name,
        edit_num=edit_num,
    )


def _get_save_directory(group: FileGroup, collection_files: CollectionFiles) -> Path:
    if group.is_in_unsorted:
        return collection_files.directories[DirectoryType.UNSORTED]
    if group.is_in_rejected:
        return collection_files.directories[DirectoryType.REJECTED]
    return collection_files.directories[DirectoryType.PHOTOS]


def _set_output_dialog_directory(output_dialog: WindowSpecification, directory: Path) -> bool:
    if ((dialog_directory := _send_message_with_buffer(output_dialog, _CDM_GETFOLDERPATH))
            and Path(dialog_directory) == directory):
        _LOG.debug(f"Directory is already set to to {directory}")
        return True

    _LOG.debug(f"Setting directory to {directory}...")
    # Set the text of the "File name" text box
    _set_output_dialog_file_name_text(output_dialog, str(directory))  # pyright: ignore [reportUnknownMemberType]

    # Make sure that the text has changed before we click the "Save" button
    if Path(_get_output_dialog_file_name_text(output_dialog)) != directory:
        _LOG.error('The text of the "File name" text box did not change')
        return False

    retries = 0
    while True:
        # _LOG.debug("Changing directory...")
        # Click the "Save" button to change the directory
        output_dialog.SaveButton.click()  # pyright: ignore [reportUnknownMemberType]

        # _LOG.debug("Checking that directory has changed...")
        if not (dialog_directory := _get_output_dialog_directory(output_dialog)):
            _LOG.error("Could not get the current directory of the output dialog")
            return False

        if dialog_directory == directory:
            break

        if retries >= _CHANGE_DIR_RETRIES:
            _LOG.error(f"Change directory retry limit reached - retried {retries} times")
            return False

        time.sleep(_CHANGE_DIR_RETRY_DELAY_SECS)
        retries += 1

    _LOG.debug(f"Retried {retries} times waiting for the directory to change")
    return True


def _send_message_with_buffer(window: WindowSpecification, message: int) -> str | None:
    window_wrapper = window.wrapper_object()  # pyright: ignore [reportUnknownVariableType]
    char_count = 260  # Start with the legacy MAX_PATH size and grow if needed

    while True:
        remote_buffer = RemoteMemoryBlock(window_wrapper, size=_char_count_to_bytes(char_count))  # pyright: ignore [reportUnknownArgumentType]

        try:
            result = window_wrapper.send_message(message, char_count, remote_buffer)  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]

            if result <= 0:
                _LOG.error(FormatError())
                return None

            if result > char_count:
                char_count = result  # pyright: ignore [reportUnknownVariableType]
                continue

            local_buffer = create_unicode_buffer(result)  # pyright: ignore [reportUnknownArgumentType]
            remote_buffer.Read(local_buffer, size=_char_count_to_bytes(result))  # pyright: ignore [reportUnknownMemberType, reportUnknownArgumentType]

            return local_buffer.value

        finally:
            remote_buffer.CleanUp()


def _char_count_to_bytes(char_count: int) -> int:
    return char_count * ctypes.sizeof(ctypes.c_wchar)


def _set_output_dialog_file_name_text(output_dialog: WindowSpecification, file_name: str) -> None:
    output_dialog.FileNameEdit.set_text(file_name)  # pyright: ignore [reportUnknownMemberType]


def _get_output_dialog_file_name_text(output_dialog: WindowSpecification) -> str:
    return output_dialog.FileNameEdit.get_line(0)  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]


def _get_output_dialog_directory(output_dialog: WindowSpecification) -> Path | None:
    directory = _send_message_with_buffer(output_dialog, _CDM_GETFOLDERPATH)
    return Path(directory) if directory else None

