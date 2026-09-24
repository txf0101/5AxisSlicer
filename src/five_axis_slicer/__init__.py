"""Five-axis additive manufacturing workbench."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("five-axis-slicer")
except PackageNotFoundError:  # Source checkout before installation.
    __version__ = "2.6.2"

__all__ = ["__version__"]
