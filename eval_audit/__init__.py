"""eval-audit — study-specification, reanalysis, and reporting toolkit for agent benchmarks."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("eval-audit")
except PackageNotFoundError:  # editable / source-checkout fallback before install
    __version__ = "unknown"

__all__ = ["__version__"]
