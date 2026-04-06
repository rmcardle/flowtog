import os


PathArg = str | os.PathLike[str] | os.DirEntry[str]


def get_directory(path: PathArg) -> str:
    return os.path.dirname(_get_path(path))


def get_filename(path: PathArg) -> str:
    return os.path.basename(_get_name(path))


def get_filename_stem(path: PathArg) -> str:
    return os.path.splitext(_get_name(path))[0]


def get_extension(path: PathArg) -> str:
    return os.path.splitext(_get_name(path))[1]


def get_extension_lower(path: PathArg) -> str:
    return os.path.splitext(_get_name(path))[1].lower()


def is_in_dir(path: PathArg, directory: PathArg) -> bool:
    directory_path = _get_path(directory)
    return (os.path.isdir(directory_path)
            and os.path.samefile(os.path.dirname(_get_path(path)), directory_path))


def in_same_dir(path1: PathArg, path2: PathArg) -> bool:
    dir1 = os.path.dirname(_get_path(path1))
    dir2 = os.path.dirname(_get_path(path2))
    return os.path.samefile(dir1, dir2)


def _get_path(path: PathArg) -> str:
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
