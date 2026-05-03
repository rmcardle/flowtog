from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections import Counter
    from pathlib import Path

    from flowtog.config import CategoryConfig, Config

_REPORT_FILE_NAME: Final[str] = "people.txt"


def report_people(people_counts: Counter[str], config: Config) -> None:
    lines: list[str] = [datetime.now(tz=UTC).astimezone().strftime("%A, %B %d, %Y, %I:%M %p %Z")]

    for category_name, category in config.categories.items():
        if not category.report:
            continue

        if not (category_lines := _report_category(people_counts, category_name, category, config)):
            continue

        if lines:
            lines.append("")

        if len(config.categories) > 1:
            lines.append(category_name.title())
            lines.append("=" * len(category_name))
            lines.append("")

        lines.extend(category_lines)

    report_path = _get_report_path(config)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _report_category(people_counts: Counter[str],
                     category_name: str,
                     category: CategoryConfig,
                     config: Config) -> list[str]:
    lines: list[str] = []

    group_to_people: dict[str, list[tuple[str, int]]] = {group_name: [] for group_name in category.groups}

    all_people = set(config.people) | set(people_counts)

    for person_name in all_people:
        count = people_counts[person_name]
        for group_name in _get_category_groups(person_name, category_name, config):
            group_to_people[group_name].append((person_name, count))

    for group_name, group_people_counts in group_to_people.items():
        if not group_people_counts:
            continue

        # Sort descending by count and then ascending by name
        group_people_counts.sort(key=lambda item: (-item[1], item[0]))

        if lines:
            lines.append("")

        lines.append(group_name)
        for person_name, count in group_people_counts:
            lines.append(f"\t{count}\t{person_name}")

    return lines


def _get_category_groups(person_name: str, category_name: str, config: Config) -> tuple[str, ...]:
    person = config.people.get(person_name)
    if person and category_name in person.categories:
        return person.categories[category_name]

    category = config.categories[category_name]
    if category.default_group:
        return (category.default_group,)

    return ()


def _get_report_path(config: Config) -> Path:
    return config.collection.photos_dir.parent / _REPORT_FILE_NAME
