import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from flowtog.dcf_utils import get_dcf_dirs, is_dcf_media
from flowtog.path_utils import FilePair, copy_files, get_modified_time, get_removable_media

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flowtog.config import CollectionConfig

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

_TIMESTAMP_PREFIX_FORMAT: Final[str] = "%Y%m%d-%H%M%S-"

_SONY_AVCHD_VIDEO_DIR: Final[Path] = Path("PRIVATE/AVCHD/BDMV/STREAM")

_SONY_XAVCS_DIR: Final[Path] = Path("PRIVATE/M4ROOT")
_SONY_XAVCS_VIDEO_DIR: Final[Path] = _SONY_XAVCS_DIR / "CLIP"
_SONY_XAVCS_PROXY_DIR: Final[Path] = _SONY_XAVCS_DIR / "SUB"
_SONY_XAVCS_THUMBNAIL_DIR: Final[Path] = _SONY_XAVCS_DIR / "THMBNL"
_SONY_XAVCS_FILE_REGEX: Final[str] = (
    r"^C(?P<file_num>\d{4})(?:(?P<type_char>[MST])(?:\d{2}))?(?P<extension>\.[A-Z0-9_]{3})$"
)
_SONY_XAVCS_FILE_PATTERN: Final[re.Pattern[str]] = re.compile(_SONY_XAVCS_FILE_REGEX)

# https://community.gopro.com/s/article/GoPro-Camera-File-Naming-Convention?language=en_US
_GOPRO_PROXY_DIR: Final[str] = "Proxy"
_GOPRO_FILE_REGEX: Final[str] = r"^G(?P<type_char>[HPRSX])(?P<file_num>\d{6})(?P<extension>\.[A-Z0-9_]{3})$"
_GOPRO_FILE_PATTERN: Final[re.Pattern[str]] = re.compile(_GOPRO_FILE_REGEX)


@dataclass
class VideoFileBundle:
    video_file: Path | None = field(default=None)
    proxy_file: Path | None = field(default=None)
    other_files: list[Path] = field(default_factory=list[Path])

    @property
    def all_files(self) -> Iterator[Path]:
        yield from (file for file in (self.video_file, self.proxy_file, *self.other_files) if file is not None)

    def set_video_file(self, file: Path) -> None:
        self._set_single_file("video_file", file)

    def set_proxy_file(self, file: Path) -> None:
        self._set_single_file("proxy_file", file)

    def _set_single_file(self,
                         field_name: Literal["video_file", "proxy_file"],
                         file: Path) -> None:
        existing = getattr(self, field_name)
        if existing:
            bundle_files = "\n\t".join(map(str, self.all_files))
            msg = (f"Cannot add {field_name} {file} - bundle already contains {field_name} {existing}\n"
                   f"\t{bundle_files}")
            raise RuntimeError(msg)

        setattr(self, field_name, file)


def import_videos(collection: CollectionConfig) -> None:
    bundles: list[VideoFileBundle] = []

    for media in get_removable_media():
        bundles.extend(_get_sony_avchd_bundles(media))
        bundles.extend(_get_sony_xavcs_bundles(media))
        bundles.extend(_get_gopro_bundles(media))

    for bundle in bundles:
        _copy_bundle(bundle, collection.videos_dir, collection.videos_proxy_dir)


def _copy_bundle(bundle: VideoFileBundle, videos_dir: Path, proxy_dir: Path) -> None:
    file_pairs: list[FilePair] = []

    if not bundle.video_file:
        bundle_files = "\n\t".join(map(str, bundle.all_files))
        _LOG.error(f"Bundle does not have a video file\n\t{bundle_files}")
        return

    video_modified_time_local = get_modified_time(bundle.video_file).astimezone()
    timestamp_prefix = video_modified_time_local.strftime(_TIMESTAMP_PREFIX_FORMAT)

    def get_destination_file(destination_dir: Path, file_name: str) -> Path:
        nonlocal timestamp_prefix
        return destination_dir / (timestamp_prefix + file_name)

    for source_file in [bundle.video_file, *bundle.other_files]:
        destination_file = get_destination_file(videos_dir, source_file.name)
        file_pairs.append((source_file, destination_file))

    if bundle.proxy_file:
        source_file = bundle.proxy_file

        # Use the video file's stem instead of the proxy's original stem
        destination_file_stem = get_destination_file(videos_dir, bundle.video_file.name).stem

        destination_extension = source_file.suffix

        # GoPro LRV (Low-Res Video) files are actually just MP4
        if destination_extension.lower() == ".lrv":
            destination_extension = ".MP4"

        # The destination_file_stem already has the timestamp prefix so do not use get_destination_file()
        destination_file = proxy_dir / (destination_file_stem + destination_extension)

        file_pairs.append((source_file, destination_file))

    if not copy_files(file_pairs):
        bundle_files = "\n\t".join(map(str, bundle.all_files))
        _LOG.error(f"Bundle was not copied\n\t{bundle_files}")


def _get_sony_avchd_bundles(media_dir: Path) -> Iterator[VideoFileBundle]:
    if not (avchd_dir := media_dir / _SONY_AVCHD_VIDEO_DIR).is_dir():
        return

    # Path.iterdir() yields objects in arbitrary order so we need to sort them
    for path in sorted(avchd_dir.iterdir()):
        if not path.is_file():
            _LOG.warning(f"Ignoring {path} - Not a file")
            continue

        if path.suffix.lower() != ".mts":
            _LOG.warning(f"Ignoring {path} - Not an MTS file")
            continue

        yield VideoFileBundle(
            video_file=path,
        )


@dataclass(frozen=True)
class _NumberedTypedFile:
    path: Path
    file_num: int
    type_char: str | None


def _get_numbered_typed_files(source_dir: Path, pattern: re.Pattern[str]) -> Iterator[_NumberedTypedFile]:
    # Path.iterdir() yields objects in arbitrary order so we need to sort them
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            _LOG.warning(f"Ignoring {path} - Not a file")
            continue

        if not (match := pattern.match(path.name)):
            _LOG.warning(f"Ignoring {path} - Not a recognized file name pattern")
            continue

        if not (file_num := match.group("file_num")):
            _LOG.warning(f"Ignoring {path} - Could not determine file number")
            continue

        type_char = match.group("type_char")

        yield _NumberedTypedFile(
            path=path,
            file_num=int(file_num),
            type_char=type_char,
        )


def _get_sony_xavcs_bundles(media_dir: Path) -> Iterator[VideoFileBundle]:
    if not (media_dir / _SONY_XAVCS_DIR).is_dir():
        return

    file_num_to_bundle: dict[int, VideoFileBundle] = defaultdict(VideoFileBundle)

    for path in (
        media_dir / _SONY_XAVCS_VIDEO_DIR,
        media_dir / _SONY_XAVCS_PROXY_DIR,
        media_dir / _SONY_XAVCS_THUMBNAIL_DIR,
    ):
        if not path.is_dir():
            continue

        for xavcs_file in _get_numbered_typed_files(path, _SONY_XAVCS_FILE_PATTERN):
            _add_sony_xavcs_file_to_bundle(file_num_to_bundle[xavcs_file.file_num], xavcs_file)

    yield from file_num_to_bundle.values()


def _add_sony_xavcs_file_to_bundle(bundle: VideoFileBundle, file: _NumberedTypedFile) -> None:
    if not file.type_char:
        if file.path.suffix.lower() == ".mp4":
            bundle.set_video_file(file.path)
        else:
            msg = f'Video file {file.path} has an unexpected file type character "{file.type_char}"'
            raise RuntimeError(msg)
        return

    match file.type_char:
        case "M" | "T":  # Metadata or Thumbnail
            bundle.other_files.append(file.path)

        case "S":  # Proxy
            bundle.set_proxy_file(file.path)

        case _:
            _LOG.warning(f'Ignoring {file.path} - Unrecognized file type character "{file.type_char}"')


def _get_gopro_bundles(media_dir: Path) -> Iterator[VideoFileBundle]:
    if not is_dcf_media(media_dir):
        return

    file_num_to_bundle: dict[int, VideoFileBundle] = defaultdict(VideoFileBundle)

    for dcf_dir in get_dcf_dirs(media_dir):
        for path in (
                dcf_dir,
                dcf_dir / _GOPRO_PROXY_DIR,
        ):
            if not path.is_dir():
                continue

            for gopro_file in _get_numbered_typed_files(path, _GOPRO_FILE_PATTERN):
                _add_gopro_file_to_bundle(file_num_to_bundle[gopro_file.file_num], gopro_file)

    yield from file_num_to_bundle.values()


def _add_gopro_file_to_bundle(bundle: VideoFileBundle, file: _NumberedTypedFile) -> None:
    if not file.type_char:
        _LOG.warning(f"Ignoring {file.path} - Could not determine file type character")
        return

    match file.type_char:
        case "H" | "X":  # Video
            if file.path.parent.name.lower() == _GOPRO_PROXY_DIR.lower():
                bundle.set_proxy_file(file.path)
            elif file.path.suffix.lower() == ".mp4":
                bundle.set_video_file(file.path)
            else:
                bundle.other_files.append(file.path)

        case "R":  # Proxy
            bundle.set_proxy_file(file.path)

        case _:
            _LOG.warning(f'Ignoring {file.path} - Unrecognized file type character "{file.type_char}"')
