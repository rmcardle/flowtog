from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from flowtog.config import get_person_category_groups

if TYPE_CHECKING:
    from collections import Counter

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

        lines.append(category_name.title())
        lines.append("=" * len(category_name))
        lines.append("")

        lines.extend(category_lines)

    for group_name, group in config.groups.items():
        if not (group.report and (group_lines := _report_group(people_counts, group_name, config))):
            continue

        if lines:
            lines.append("")

        lines.append(group_name)
        lines.append("=" * len(group_name))
        lines.append("")

        lines.extend(group_lines)

    report_file = config.base_dir / _REPORT_FILE_NAME
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _report_category(people_counts: Counter[str],
                     category_name: str,
                     category: CategoryConfig,
                     config: Config) -> list[str]:
    lines: list[str] = []

    group_to_people: dict[str, list[tuple[str, int]]] = {group_name: [] for group_name in category.groups}

    all_people_names = set(config.people) | set(people_counts)

    for person_name in all_people_names:
        person = config.people.get(person_name)
        count = people_counts[person_name]
        for group_name in get_person_category_groups(person, category_name, config):
            group_to_people[group_name].append((person_name, count))

    for group_name, group_people_counts in group_to_people.items():
        if not group_people_counts:
            continue

        if lines:
            lines.append("")

        lines.append(group_name)
        lines.extend(_get_people_count_lines(group_people_counts))

    return lines


def _report_group(people_counts: Counter[str],
                  group_name: str,
                  config: Config) -> list[str]:
    group_people_names = {person_name for person_name, person in config.people.items() if group_name in person.groups}

    group_people_counts = [(person_name, people_counts[person_name]) for person_name in group_people_names]

    return _get_people_count_lines(group_people_counts)


def _get_people_count_lines(people_counts: list[tuple[str, int]]) -> list[str]:
    lines: list[str] = []

    # Sort descending by count and then ascending by name
    people_counts.sort(key=lambda item: (-item[1], item[0]))

    for person_name, count in people_counts:
        lines.append(f"\t{count}\t{person_name}")

    return lines
