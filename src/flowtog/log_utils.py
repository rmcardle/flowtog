import os
from collections.abc import Iterable
from os import fspath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging


def log_file_path(logger: logging.Logger,
                  level: int,
                  msg: str,
                  paths: os.PathLike[str] | Iterable[os.PathLike[str]]) -> None:
    paths_iterable = paths if isinstance(paths, Iterable) else [paths]
    lines = [msg, *[f"\t{fspath(f)}" for f in paths_iterable]]
    logger.log(level, "\n".join(lines))
