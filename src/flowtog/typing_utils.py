from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable


def is_str_list(value: object) -> TypeGuard[list[str]]:
    return (isinstance(value, list)
            and _is_all_str(value))  # pyright: ignore [reportUnknownArgumentType]


def is_all_str(value: Iterable[object]) -> TypeGuard[Iterable[str]]:
    return _is_all_str(value)


def _is_all_str(value: Iterable[object]) -> bool:
    return all(isinstance(item, str) for item in value)
