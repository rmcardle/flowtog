from collections.abc import Callable, Generator
from functools import wraps
from typing import ParamSpec, TypeVar

type NumberRange = tuple[int, int] | None
type NumberRangeCoroutine = Generator[NumberRange, int | None]
type MissingRangeCoroutine = Generator[NumberRange, int]

P = ParamSpec("P")  # Parameters
Y = TypeVar("Y")    # Yielded Values
S = TypeVar("S")    # Sent Values
R = TypeVar("R")    # Return Value


def coroutine[**P, Y, S, R](func: Callable[P, Generator[Y, S, R]]) -> Callable[P, Generator[Y, S, R]]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Generator[Y, S, R]:
        f = func(*args, **kwargs)
        next(f)
        return f
    return wrapper


@coroutine
def get_number_range() -> NumberRangeCoroutine:
    first_num: int | None = None
    previous_num = 0
    num_range: NumberRange = None

    while True:
        current_num: int | None = yield num_range

        if current_num is None:
            num_range = None if first_num is None else (first_num, previous_num)
            first_num = None
            continue

        expected_num = previous_num + 1

        if first_num is None:
            first_num = current_num
            num_range = None
        elif current_num in (previous_num, expected_num):
            num_range = None
        else:
            num_range = first_num, previous_num
            first_num = current_num

        previous_num = current_num


@coroutine
def get_missing_range(start_num: int = 0, *, skip_modulo: int | None = None) -> MissingRangeCoroutine:
    previous_num = start_num - 1
    missing_range: NumberRange = None
    while True:
        current_num: int = yield missing_range
        expected_num = previous_num + 1
        if skip_modulo and expected_num % skip_modulo == 0:
            expected_num += 1
        if current_num == expected_num:
            missing_range = None
        else:
            first_missing = previous_num + 1
            last_missing = current_num - 1
            missing_range = first_missing, last_missing
        previous_num = current_num


def format_range(number_range: NumberRange,
                 format_spec: str | None = None,
                 field_name: str | None = None) -> str:
    assert number_range

    def format_value(value: int) -> str:
        if not format_spec:
            return str(value)
        if not field_name:
            return format_spec.format(value)
        return format_spec.format(**{field_name: value})

    first = format_value(number_range[0])
    last = format_value(number_range[1])

    return first if number_range[0] == number_range[1] else f"{first}-{last}"
