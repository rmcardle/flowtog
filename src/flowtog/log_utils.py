import os
from collections.abc import Iterable
from os import fspath
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import logging
    from types import TracebackType


class LogStartExit:
    def __init__(self,
                 logger: logging.Logger,
                 level: int,
                 name: str) -> None:
        self.logger = logger
        self.level = level
        self.name = name

    def __enter__(self) -> Self:
        self.logger.log(self.level, "%s starting", self.name)
        return self

    def __exit__(self,
                 exc_type: type[BaseException] | None,
                 exc_value: BaseException | None,
                 traceback: TracebackType | None,
                 /) -> bool | None:
        self.logger.log(self.level, "%s exiting", self.name)


def log_file_path(logger: logging.Logger,
                  level: int,
                  msg: str,
                  paths: os.PathLike[str] | Iterable[os.PathLike[str]]) -> None:
    paths_iterable = paths if isinstance(paths, Iterable) else [paths]
    lines = [msg, *[f"\t{fspath(f)}" for f in paths_iterable]]
    logger.log(level, "\n".join(lines))
