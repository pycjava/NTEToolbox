import sys

from ._version import __version__ as _package_version
from .global_val import Exit_code
from .log import log

if sys.version_info < (3, 14):  # noqa: UP036
    log.error("Python 版本必须 >= 3.14")
    sys.exit(Exit_code.py_ver_not_supported.value)

try:
    import maa  # noqa: F401
except ModuleNotFoundError:
    log.error("maafw 未安装，执行以下命令以安装或更新: python -m pip install -U maafw")
    sys.exit(Exit_code.import_failed.value)

from . import fish, piano, rt_asst, setting, utils

__all__ = [
    "fish",
    "piano",
    "rt_asst",
    "setting",
    "utils",
]

__version__ = utils.get_project_version() or _package_version
