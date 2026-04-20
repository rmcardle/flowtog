import os
from pathlib import Path

PathArg = str | os.PathLike[str] | os.DirEntry[str]


def get_path(path: PathArg) -> Path:
    return Path(path.path) if isinstance(path, os.DirEntry) else Path(path)
