import logging
from typing import Iterable

from flowtog.collectionfile import CollectionFile


def log_file_path(logger: logging.Logger,
                  level: int,
                  msg: str,
                  files: CollectionFile | Iterable[CollectionFile]) -> None:
    files_iterable = files if isinstance(files, Iterable) else [files]
    lines = [msg, *[f"\t{f.path}" for f in files_iterable]]
    logger.log(level, "\n".join(lines))
