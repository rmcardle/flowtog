import logging
from collections import Counter
from typing import TYPE_CHECKING, Final

from flowtog.collectiondirectories import DirectoryType
from flowtog.config import get_person_category_groups
from flowtog.filetype import FileType
from flowtog.metadatatype import MetadataType
from flowtog.typing_utils import is_all_str

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flowtog.collectionfile import CollectionFile
    from flowtog.collectionfiles import CollectionFiles
    from flowtog.collectionmetadata import CollectionMetadata
    from flowtog.config import CategoryConfig, Config
    from flowtog.metadatasession import MetadataTypeToValues

_LOG: Final[logging.Logger] = logging.getLogger(__name__)

_HIERARCHY_SEPARATOR: Final[str] = "|"


def sync_people(collection_files: CollectionFiles,
                config: Config,
                collection_metadata: CollectionMetadata) -> Counter[str]:
    if not (xmp_files := collection_files.get_directory_files_by_type(DirectoryType.PHOTOS, FileType.XMP)):
        _LOG.warning("No XMP files found in Photos directory")
        return Counter()

    people_counts: Counter[str] = Counter()

    for xmp_file in xmp_files:
        people = _sync_people_in_file(xmp_file, config, collection_metadata)
        people_counts.update(people)

    return people_counts


def _sync_people_in_file(file: CollectionFile, config: Config, collection_metadata: CollectionMetadata) -> set[str]:
    current_metadata_type_to_values = collection_metadata.get_metadata(file)

    current_people = _get_set_from_metadata_type_to_values(current_metadata_type_to_values,
                                                           MetadataType.PERSON_IN_IMAGE)
    current_flat_keywords = _get_set_from_metadata_type_to_values(current_metadata_type_to_values,
                                                                  MetadataType.SUBJECT)
    current_hierarchical_keywords = _get_set_from_metadata_type_to_values(current_metadata_type_to_values,
                                                                          MetadataType.HIERARCHICAL_SUBJECT)

    new_hierarchical_keywords, new_flat_keywords = _calculate_new_keywords(current_people,
                                                                           current_flat_keywords,
                                                                           current_hierarchical_keywords,
                                                                           config)

    new_metadata_type_to_values: MetadataTypeToValues = {}
    if current_hierarchical_keywords != new_hierarchical_keywords:
        new_metadata_type_to_values[MetadataType.HIERARCHICAL_SUBJECT] = list(new_hierarchical_keywords)
    if current_flat_keywords != new_flat_keywords:
        new_metadata_type_to_values[MetadataType.SUBJECT] = list(new_flat_keywords)

    if new_metadata_type_to_values:
        collection_metadata.set_metadata(file, new_metadata_type_to_values)

        _log_keyword_changes(file,
                             current_hierarchical_keywords,
                             new_hierarchical_keywords,
                             current_flat_keywords,
                             new_flat_keywords)

    return current_people


def _get_set_from_metadata_type_to_values(metadata_type_to_values: MetadataTypeToValues,
                                          metadata_type: MetadataType) -> set[str]:
    if (value := metadata_type_to_values.get(metadata_type)) is None:
        return set()

    if isinstance(value, list):
        if not is_all_str(value):
            raise TypeError
        return set(value)

    if not isinstance(value, str):
        raise TypeError

    return {value}


# noinspection PyUnusedLocal
def _calculate_new_keywords(current_people: Iterable[str],
                            current_flat_keywords: set[str],  # noqa: ARG001 unused-function-argument
                            current_hierarchical_keywords: set[str],  # noqa: ARG001 unused-function-argument
                            config: Config) -> tuple[set[str], set[str]]:
    # With configurable groups, it is difficult to determine which keywords we manage and which were added externally.
    # So for now, we'll just say that external keywords are unsupported and replace all existing keywords with new ones.
    # We'll keep the previous code here to use as a starting point if we want to add that functionality back in later.
    # Remove noinspection and noqa comments above if the previous code is uncommented.

    # current_flattened_hierarchical_keywords = _flatten_keywords(current_hierarchical_keywords)
    # current_flat_only_keywords = current_flat_keywords - current_flattened_hierarchical_keywords
    #
    # current_non_people_hierarchical_keywords = {
    #     keyword for keyword in current_hierarchical_keywords
    #     if not _KEYWORD_PREFIX or not keyword.startswith(_KEYWORD_PREFIX)
    # }
    new_people_hierarchical_keywords = _people_to_hierarchical_keywords(current_people, config)
    # new_hierarchical_keywords = current_non_people_hierarchical_keywords | new_people_hierarchical_keywords
    new_hierarchical_keywords = new_people_hierarchical_keywords
    new_flattened_hierarchical_keywords = _flatten_keywords(new_hierarchical_keywords)
    # new_flat_keywords = new_flattened_hierarchical_keywords | current_flat_only_keywords
    new_flat_keywords = new_flattened_hierarchical_keywords

    return new_hierarchical_keywords, new_flat_keywords


def _people_to_hierarchical_keywords(people: Iterable[str], config: Config) -> set[str]:
    hierarchical_keywords: set[str] = set()

    for person_name in people:
        person = config.people.get(person_name)

        for category_name, category in config.categories.items():
            group_names = get_person_category_groups(person, category_name, config)
            for group_name in group_names:
                hierarchical_keywords.add(
                    _get_group_hierarchical_keywords(group_name, person_name, config, category))

        if not person:
            continue

        for group_name in person.groups:
            hierarchical_keywords.add(_get_group_hierarchical_keywords(group_name, person_name, config))

    return hierarchical_keywords


def _get_group_hierarchical_keywords(group_name: str,
                                     person_name: str,
                                     config: Config,
                                     category: CategoryConfig | None = None) -> str:
    group = config.groups.get(group_name)
    hierarchical_keyword_parts: list[str] = []

    if category and category.hierarchical_keyword_prefix:
        hierarchical_keyword_parts.extend(category.hierarchical_keyword_prefix)

    if group and group.hierarchical_keyword:
        hierarchical_keyword_parts.extend(group.hierarchical_keyword)
    else:
        hierarchical_keyword_parts.append(group_name)

    if ((category and category.keyword_include_person) or
            (group and group.keyword_include_person)):
        hierarchical_keyword_parts.append(person_name)

    return _HIERARCHY_SEPARATOR.join(hierarchical_keyword_parts)


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
        _LOG.info(f"{xmp_file.filename_stem}: Metadata changed\n"
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
    return " - ".join(([f"Added: {added}"] if added else []) +
                      ([f"Removed: {removed}"] if removed else []))
