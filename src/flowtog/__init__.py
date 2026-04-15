import importlib.metadata
import tomllib
from pathlib import Path

# Based on
# https://pragmaticnotes.hashnode.dev/exposing-the-package-version-defined-in-pyprojecttoml-as-a-version-variable
pyproject_toml = Path(__file__).parent.parent.parent / "pyproject.toml"
if pyproject_toml.is_file():
    with pyproject_toml.open("rb") as f:
        __version__ = tomllib.load(f)["project"]["version"]
else:
    # noinspection PyRedeclaration
    __version__ = importlib.metadata.version("package")
