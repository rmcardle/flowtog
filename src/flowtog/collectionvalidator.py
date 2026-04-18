import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Self

from flowtog.collectiondirectories import DirectoryType
from flowtog.filegroup_utils import MissingRangeCoroutine, format_range, get_missing_range
from flowtog.filetype import FileType
from flowtog.log_utils import log_file_path
from flowtog.path_utils import in_same_dir

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.config import CollectionConfig
    from flowtog.filegroup import FileGroup

_LOG: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionValidator:
    _files: CollectionFiles
    _collection: CollectionConfig
    _collection_metadata: CollectionMetadata

    @classmethod
    def from_collection_files(cls, collection_files: CollectionFiles, collection_metadata: CollectionMetadata) -> Self:
        return cls(
            _files=collection_files,
            _collection=collection_files.collection,
            _collection_metadata=collection_metadata,
        )

    def validate(self) -> None:
        _LOG.debug("Validate collection")

        missing_range_coroutine = get_missing_range(self._collection.start_num, skip_modulo=10000)

        for group_name in self._files.group_names:
            file_group = self._files.get_group_by_name(group_name)
            assert file_group

            self._validate_file_number(missing_range_coroutine, file_group)
            self._validate_group(file_group)

    def _validate_file_number(self, missing_range_coroutine: MissingRangeCoroutine, file_group: FileGroup) -> None:
        if missing_range := missing_range_coroutine.send(file_group.group_num):
            missing_files = format_range(missing_range, self._collection.filename_format, "file_num")
            _LOG.error(f"{missing_files}: Missing")

    def _validate_group(self, group: FileGroup) -> None:
        for file_type in group.file_types:
            files = group.get_type_files(file_type)
            if file_type == FileType.JPEG and group.has_edits:
                self._validate_edits(group, files)
            elif file_type == FileType.OTHER:
                self._validate_other_files(group, files)
            else:
                self._validate_allowed_dirs(group, file_type, files)
                self._validate_multiple(group, file_type, list(files))

        self._validate_missing(group)
        self._validate_xmp_same_dir(group)

    @staticmethod
    def _validate_other_files(group: FileGroup, files: Iterable[CollectionFile]) -> None:
        log_file_path(_LOG, logging.WARNING, f"{group.group_name}: Other files", files)

    def _validate_allowed_dirs(self,
                               group: FileGroup,
                               file_type: FileType,
                               files: Iterable[CollectionFile]) -> None:
        # Edits are handled in _validate_edit_dirs() so we don't need to worry about those here
        for file in files:
            if file.directory_type not in _get_file_type_allowed_dir_types()[file_type]:
                log_file_path(_LOG,
                              logging.ERROR,
                              f"{group.group_name}: {file_type.value} file in incorrect folder",
                              file)
            if file_type == FileType.JPEG \
                    and (rating := self._collection_metadata.get_rating(file)) \
                    and rating >= self._collection.selected_rating \
                    and file.directory_type in [DirectoryType.UNSORTED, DirectoryType.REJECTED]:
                log_file_path(_LOG,
                              logging.WARNING,
                              f"{file_type.value} file with rating {self._collection.selected_rating} or higher "
                              f"(rating {rating}) in {file.directory_type.value}",
                              file)

    @staticmethod
    def _validate_multiple(group: FileGroup, file_type: FileType, files: Collection[CollectionFile]) -> None:
        if len(files) > 1:
            log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Multiple {file_type.value} files", files)

    @staticmethod
    def _validate_missing(group: FileGroup) -> None:
        if len(group.get_type_files(FileType.RAW)) < 1:
            _LOG.error(f"{group.group_name}: Missing RAW file")

        if len(group.get_type_files(FileType.JPEG)) < 1:
            _LOG.error(f"{group.group_name}: Missing JPEG file")

    @staticmethod
    def _validate_xmp_same_dir(group: FileGroup) -> None:
        if FileType.XMP not in group.file_types:
            return

        jpeg_files_by_filename_stem: dict[str, list[CollectionFile]] = defaultdict(list)
        for jpeg_file in group.get_type_files(FileType.JPEG):
            jpeg_files_by_filename_stem[jpeg_file.filename_stem].append(jpeg_file)

        invalid_xmp_files = [
            xmp_file for xmp_file in group.get_type_files(FileType.XMP)
            if not any(
                in_same_dir(xmp_file.direntry, jpeg_file.direntry)
                for jpeg_file in jpeg_files_by_filename_stem[xmp_file.filename_stem]
            )
        ]

        if invalid_xmp_files:
            log_file_path(_LOG,
                          logging.ERROR,
                          f"{group.group_name}: XMP files without matching JPEG file",
                          invalid_xmp_files)

    def _validate_edits(self, group: FileGroup, files: list[CollectionFile]) -> None:
        self._validate_edit_duplicates(group, files)
        self._validate_edit_nums(group, files)
        self._validate_edit_dirs(group, files)

    @staticmethod
    def _validate_edit_duplicates(group: FileGroup, group_files: list[CollectionFile]) -> None:
        files_by_name: dict[str, list[CollectionFile]] = defaultdict(list)
        for file in group_files:
            files_by_name[file.filename].append(file)

        for filename, files in files_by_name.items():
            if len(files) > 1:
                log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Duplicates of {filename}", files)

    @staticmethod
    def _validate_edit_nums(group: FileGroup, files: list[CollectionFile]) -> None:
        edit_nums = sorted({f.edit_num for f in files if f.is_edit})
        missing_range_coroutine = get_missing_range(1)
        if missing_edits := [
            format_range(missing_range)
            for edit_num in edit_nums
            if (missing_range := missing_range_coroutine.send(edit_num))
        ]:
            _LOG.error(f"{group.group_name}: Missing edits {', '.join(missing_edits)}")

    def _validate_edit_dirs(self, group: FileGroup, files: list[CollectionFile]) -> None:
        sorted_files = sorted(files, key=lambda file: file.edit_num)

        original = sorted_files[0]
        if original.edit_num != 0 or original.is_edit:
            log_file_path(_LOG, logging.ERROR, f"{group.group_name}: Missing original for edit", original)
        elif original.directory_type != DirectoryType.ORIGINALS:
            log_file_path(_LOG,
                          logging.ERROR,
                          f'{group.group_name}: Original not in "{self._collection.originals_dir}" directory',
                          original)

        current = sorted_files[-1]
        if current.directory_type != DirectoryType.PHOTOS:
            log_file_path(_LOG,
                          logging.ERROR,
                          f'{group.group_name}: Current edit not in "{self._collection.photos_dir}" directory',
                          current)

        for previous_edit in sorted_files[1:-1]:
            if previous_edit.directory_type != DirectoryType.PREVIOUS_EDITS:
                log_file_path(_LOG,
                              logging.ERROR,
                              f'{group.group_name}: Previous edit not in '
                              f'"{self._collection.previous_edits_dir}" directory',
                              previous_edit)


def _get_file_type_allowed_dir_types() -> dict[FileType, list[DirectoryType]]:
    return {
        FileType.RAW:  [
            DirectoryType.REJECTED,
            DirectoryType.RAW,
            DirectoryType.UNSORTED,
        ],
        FileType.JPEG: [
            DirectoryType.ORIGINALS,
            DirectoryType.PHOTOS,
            DirectoryType.PREVIOUS_EDITS,
            DirectoryType.REJECTED,
            DirectoryType.UNSORTED,
        ],
        FileType.XMP:  [
            DirectoryType.REJECTED,
            DirectoryType.PHOTOS,
            DirectoryType.UNSORTED,
        ],
    }
