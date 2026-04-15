import logging
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import DirectoryType
from flowtog.filetype import FileType
from flowtog.metadatatype import MetadataType
from flowtog.path_utils import get_filename_stem

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata

_LOG = logging.getLogger(__name__)

_HIERARCHY_PARENTS: Final[list[str]] = ["People"]
_HIERARCHY_SEPARATOR: Final[str] = "|"

_KEYWORD_PREFIX: Final[str] = (
    _HIERARCHY_SEPARATOR.join(_HIERARCHY_PARENTS) + _HIERARCHY_SEPARATOR
    if _HIERARCHY_PARENTS else ""
)


def sync_people(collection_files: CollectionFiles, collection_metadata: CollectionMetadata) -> None:
    if not (xmp_files := collection_files.get_files_by_directory_and_type(DirectoryType.PHOTOS, FileType.XMP)):
        _LOG.warning("No XMP files found in Photos directory")
        return

    for xmp_file in xmp_files:
        _sync_people_in_file(xmp_file, collection_metadata)


def _sync_people_in_file(file: CollectionFile, collection_metadata: CollectionMetadata) -> None:
    current_metadata_by_type = collection_metadata.get_metadata(file)

    current_people = _get_set_from_metadata_by_type(current_metadata_by_type, MetadataType.PERSON_IN_IMAGE)
    current_flat_keywords = _get_set_from_metadata_by_type(current_metadata_by_type, MetadataType.SUBJECT)
    current_hierarchical_keywords = _get_set_from_metadata_by_type(current_metadata_by_type,
                                                                   MetadataType.HIERARCHICAL_SUBJECT)

    new_hierarchical_keywords, new_flat_keywords = _calculate_new_keywords(current_people,
                                                                           current_flat_keywords,
                                                                           current_hierarchical_keywords)

    new_metadata_by_type: dict[MetadataType, str | list[str]] = {}
    if current_hierarchical_keywords != new_hierarchical_keywords:
        new_metadata_by_type[MetadataType.HIERARCHICAL_SUBJECT] = list(new_hierarchical_keywords)
    if current_flat_keywords != new_flat_keywords:
        new_metadata_by_type[MetadataType.SUBJECT] = list(new_flat_keywords)

    if not new_metadata_by_type:
        return

    collection_metadata.set_metadata(file, new_metadata_by_type)

    _log_keyword_changes(file,
                         current_hierarchical_keywords,
                         new_hierarchical_keywords,
                         current_flat_keywords,
                         new_flat_keywords)


def _get_set_from_metadata_by_type(metadata_by_type: dict[MetadataType, str | list[str]],
                                   metadata_type: MetadataType) -> set[str]:
    if (metadata := metadata_by_type.get(metadata_type)) is None:
        return set()
    if isinstance(metadata, list):
        return set(metadata)
    return {metadata}


def _calculate_new_keywords(current_people: Iterable[str],
                            current_flat_keywords: set[str],
                            current_hierarchical_keywords: set[str]) -> tuple[set[str], set[str]]:
    current_flattened_hierarchical_keywords = _flatten_keywords(current_hierarchical_keywords)
    current_flat_only_keywords = current_flat_keywords - current_flattened_hierarchical_keywords

    # Remove hierarchical keywords from flat keywords
    # current_flat_only_keywords = {k for k in current_flat_only_keywords if _HIERARCHY_SEPARATOR not in k}

    current_non_people_hierarchical_keywords = {
        keyword for keyword in current_hierarchical_keywords
        if not _KEYWORD_PREFIX or not keyword.startswith(_KEYWORD_PREFIX)
    }
    new_people_hierarchical_keywords = _people_to_hierarchical_keywords(current_people)
    new_hierarchical_keywords = current_non_people_hierarchical_keywords | new_people_hierarchical_keywords
    new_flattened_hierarchical_keywords = _flatten_keywords(new_hierarchical_keywords)
    new_flat_keywords = new_flattened_hierarchical_keywords | current_flat_only_keywords

    return new_hierarchical_keywords, new_flat_keywords


def _people_to_hierarchical_keywords(people: Iterable[str]) -> set[str]:
    return {_KEYWORD_PREFIX + person.strip() for person in people if person.strip()}


def _flatten_keywords(hierarchical_keywords: Iterable[str]) -> set[str]:
    flat_keywords: set[str] = set()
    for hierarchical_keyword in hierarchical_keywords:
        if not hierarchical_keyword:
            continue
        flat_keywords.update(_flatten_keyword(hierarchical_keyword))
    return flat_keywords


def _flatten_keyword(hierarchical_keyword: str) -> set[str]:
    return {element.strip() for element in hierarchical_keyword.split(_HIERARCHY_SEPARATOR)}


def _log_keyword_changes(xmp_file: CollectionFile,
                         old_hierarchical_keywords: set[str],
                         new_hierarchical_keywords: set[str],
                         old_flat_keywords: set[str],
                         new_flat_keywords: set[str]) -> None:
    hierarchical_changes = _get_keyword_changes(old_hierarchical_keywords, new_hierarchical_keywords)
    flat_changes = _get_keyword_changes(old_flat_keywords, new_flat_keywords)

    if any(flat_changes):
        _LOG.info(f"{get_filename_stem(xmp_file)}: Metadata changed\n"
                  "\t" + _get_keyword_changes_string(flat_changes))
    if any(hierarchical_changes):
        _LOG.debug("\t" + _get_keyword_changes_string(hierarchical_changes))


def _get_keyword_changes(old_keywords: set[str],
                         new_keywords: set[str]) -> tuple[list[str], list[str]]:
    added = list(new_keywords - old_keywords)
    removed = list(old_keywords - new_keywords)
    return added, removed


def _get_keyword_changes_string(metadata_changes: tuple[Iterable[str], Iterable[str]]) -> str:
    added = ", ".join(metadata_changes[0])
    removed = ", ".join(metadata_changes[1])
    return " - ".join(
        ([f"Added: {added}"] if added else []) +
        ([f"Removed: {removed}"] if removed else [])  # noqa: COM812
    )
