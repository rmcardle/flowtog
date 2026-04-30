import contextlib
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Final
from winreg import HKEY_LOCAL_MACHINE, REG_SZ, OpenKey, QueryValueEx

from pywinauto import Application, WindowSpecification, application, timings  # pyright: ignore [reportMissingTypeStubs]

if TYPE_CHECKING:
    import os

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


class SonyImagingEdge:
    @staticmethod
    def launch(raw_file: str | os.PathLike[str]) -> None:
        raw_path = Path(raw_file)
        save_dir = raw_path.parent

        sie_edit_path = _get_sie_edit_path()
        if sie_edit_path is None:
            _LOG.error("Couldn't locate Sony Imaging Edge Edit.")
            return

        with contextlib.suppress(application.ProcessNotFoundError):
            if application.process_from_module(sie_edit_path):  # pyright: ignore [reportUnknownMemberType]
                _LOG.error("Sony Imaging Edge Edit is already running.")
                return

        cmdline: str = subprocess.list2cmdline([sie_edit_path, raw_path])
        app: Application = Application(backend="win32").start(cmdline)  # pyright: ignore [reportUnknownMemberType]

        # We can't use app.top_window because Edit shows a small progress bar window before loading the main window
        main_window: WindowSpecification = app.window(title="Edit")  # pyright: ignore [reportUnknownMemberType]

        _LOG.debug("Waiting for main window...")
        main_window.wait(wait_for="enabled", timeout=60)  # pyright: ignore [reportUnknownMemberType]

        while app.is_process_running():
            output_dialog: WindowSpecification = \
                app.window(title="Output", class_name="#32770")  # pyright: ignore [reportUnknownMemberType]

            _LOG.debug("Waiting for output dialog...")
            if not _wait_for_window(output_dialog, wait_for="enabled"):
                return

            _LOG.debug("Setting save as type...")
            output_dialog.SaveAsTypeComboBox.select(0)  # pyright: ignore [reportUnknownMemberType]

            _LOG.debug("Setting directory...")
            output_dialog.FileNameEdit.set_text(save_dir)  # pyright: ignore [reportUnknownMemberType]

            _LOG.debug("Changing directory...")
            output_dialog.SaveButton.click()  # pyright: ignore [reportUnknownMemberType]

            _LOG.debug("Checking that directory has changed...")
            file_name = output_dialog.FileNameEdit.get_line(0)  # pyright: ignore [reportUnknownMemberType, reportUnknownVariableType]
            # FileNameEdit will change back to the filename when the directory is changed
            # If it's still set to the directory, it didn't change
            if Path(file_name) == save_dir:  # pyright: ignore [reportUnknownArgumentType
                _LOG.debug("ERROR: Couldn't change directory.")
                return

            _LOG.debug("Setting file name...")
            save_file = raw_path.stem + "-01.jpg"
            output_dialog.FileNameEdit.set_text(save_file)  # pyright: ignore [reportUnknownMemberType]

            _LOG.debug("Waiting for dialog to close...")
            _wait_for_window(output_dialog, wait_for="exists", wait_not=True)


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
        except timings.TimeoutError:
            continue
        else:
            return True
    return False
