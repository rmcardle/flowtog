import os

PathArg = str | os.PathLike[str] | os.DirEntry[str]


def get_directory(path: PathArg) -> str:
    return os.path.dirname(get_path(path))


def get_filename(path: PathArg) -> str:
    return os.path.basename(_get_name(path))


def get_filename_stem(path: PathArg) -> str:
    return os.path.splitext(_get_name(path))[0]


def get_extension_lower(path: PathArg) -> str:
    return os.path.splitext(_get_name(path))[1].lower()


def get_path(path: PathArg) -> str:
    if isinstance(path, os.DirEntry):
        return path.path
    if isinstance(path, os.PathLike):
        return os.fspath(path)
    return path


# noinspection PyUnresolvedReferences
def _get_name(path: PathArg) -> str:
    if isinstance(path, os.DirEntry):
        return path.name
    if isinstance(path, os.PathLike):
        return os.path.basename(os.fspath(path))
    return os.path.basename(path)
