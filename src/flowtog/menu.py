# ruff: noqa: T201 print

from msvcrt import getwch
from typing import Final

_ESCAPE: Final[str] = "\x1b"
_ANSI_UNDERLINE: Final[str] = _ESCAPE + "[4m"
_ANSI_RESET: Final[str] = _ESCAPE + "[m"


def pause() -> None:
    print("Press any key to continue . . . ", end="")
    getwch()
    print("\n")


def get_choice(choices: list[str],
               *,
               prompt: str = "What is your choice",
               prompt_show_choices: bool = True,
               escape_choice: str = _ESCAPE) -> str:
    _show_prompt(choices,
                 prompt=prompt,
                 prompt_show_choices=prompt_show_choices,
                 include_escape=bool(escape_choice))

    while True:
        key = getwch().lower()
        if key in choices:
            print(f"{key}\n")
            return key
        if key == _ESCAPE and escape_choice:
            print("Esc\n")
            return escape_choice


def get_yes_no(*,
               prompt: str = "What is your choice",
               prompt_show_choices: bool = True) -> bool:
    return get_choice(["y", "n"],
                      prompt=prompt,
                      prompt_show_choices=prompt_show_choices,
                      escape_choice="") == "y"


def get_menu_choice(items: list[str | None],
                    *,
                    title: str = "",
                    prompt: str = "What is your choice",
                    prompt_show_choices: bool = True,
                    escape_choice: str = _ESCAPE) -> str:
    if title:
        print()
        print(title)
    print()

    choices, display_items = _get_choices_and_display_items(items)

    for item in display_items:
        print(f"  {item}")

    return get_choice(choices,
                      prompt=prompt,
                      prompt_show_choices=prompt_show_choices,
                      escape_choice=escape_choice)


def _get_choices_and_display_items(items: list[str | None]) -> tuple[list[str], list[str]]:
    choices: list[str] = []
    display_items: list[str] = []
    for item in items:
        choice, display_text = _get_choice_and_display_item(item)
        if choice:
            choices += choice
        display_items.append(display_text)
    return choices, display_items


def _get_choice_and_display_item(item: str | None) -> tuple[str, str]:
    if not item:
        return "", ""

    underscore_index = item.find("_")
    if underscore_index == -1 or underscore_index == len(item) - 1:
        return "", item

    before_underscore = item[:underscore_index]
    choice_char = item[underscore_index + 1]
    after_accelerator = item[underscore_index + 2:]

    display_text = before_underscore + _ANSI_UNDERLINE + choice_char + _ANSI_RESET + after_accelerator

    return choice_char.lower(), display_text


def _show_prompt(choices: list[str],
                 *,
                 prompt: str,
                 prompt_show_choices: bool,
                 include_escape: bool) -> None:
    if not (prompt or prompt_show_choices):
        return

    print()

    if prompt:
        print(prompt, end=" ")

    if prompt_show_choices:
        if choices != ["y", "n"]:
            choices = sorted(choices)
        if include_escape:
            choices.append("Esc")
        print(f"({','.join(choices)})?", end=" ")

    print(end="", flush=True)
