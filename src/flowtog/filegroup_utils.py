from functools import wraps
from typing import Generator


def coroutine(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        f = func(*args, **kwargs)
        next(f)
        return f
    return wrapper


type MissingRange = tuple[int, int] | None
type MissingRangeCoroutine = Generator[MissingRange, int, None]


@coroutine
def get_missing_range(start_num: int = 0, *, skip_modulo: int | None = None) -> MissingRangeCoroutine:
    previous_num = start_num - 1
    missing_range: MissingRange = None
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


def format_range(missing_range: MissingRange,
                 format_spec: str | None = None,
                 field_name: str | None = None) -> str:
    assert missing_range

    def format_value(value: int) -> str:
        if not format_spec:
            return str(value)
        if not field_name:
            return format_spec.format(value)
        return format_spec.format(**{field_name: value})

    first = format_value(missing_range[0])
    last = format_value(missing_range[1])

    return first if missing_range[0] == missing_range[1] else f"{first}-{last}"
