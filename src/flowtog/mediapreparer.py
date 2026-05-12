import logging
from typing import TYPE_CHECKING, Final

from flowtog.dcf_utils import get_dcf_image_root, is_dcf_media
from flowtog.path_utils import get_removable_media

if TYPE_CHECKING:
    from pathlib import Path

    from flowtog.collectionfiles import CollectionFiles

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

_DCF_DIR_NAME: Final[str] = "100MSDCF"
_DUMMY_FILE_EXTENSION: Final[str] = ".000"


def prepare_media(collection_files: CollectionFiles) -> None:
    if not (found_media := list(get_removable_media())):
        _LOG.error("No removable media found")
        return

    if len(found_media) > 1:
        _LOG.error("Multiple removable media found")
        return

    media = found_media[0]

    if is_dcf_media(media):
        _LOG.error(f"{media} already contains a DCF image root directory (DCIM)")
        return

    _LOG.debug(f"Preparing media {media}")

    next_num = (collection_files.last_group_num + 1) % 10000
    if next_num == 0:
        _LOG.info("The next group number is 0001 so nothing needs to be done")
        return

    dcf_dir = get_dcf_image_root(media) / _DCF_DIR_NAME
    dcf_dir.mkdir(parents=True)

    dummy_file = _get_dummy_file(dcf_dir, collection_files)
    dummy_file.open(mode="w").close()

    _LOG.debug(f"Created empty file {dummy_file}")

    _LOG.info(f"{media} has been prepared. The next group number is {next_num:04d}")


def _get_dummy_file(dcf_dir: Path, collection_files: CollectionFiles) -> Path:
    filename_format = collection_files.collection.filename_format
    file_num = collection_files.last_group_num
    return dcf_dir / (filename_format.format(file_num=file_num) + _DUMMY_FILE_EXTENSION)
