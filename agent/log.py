"""Forked from https://github.com/MAA1999/M9A/blob/1a1dfe8acee4255cf7132786e9964646c7071cad/agent/utils/logger.py"""

import datetime
import enum
import html
import logging
import sys
from pathlib import Path
from typing import Literal, Self, TextIO, cast, override

from .pienv import env

__all__ = [
    "change_console_level",
    "log",
    "setup_logger",
]

LEVEL_SHORT_NAMES = {
    "INFO": "info",
    "ERROR": "err",
    "WARNING": "warn",
    "DEBUG": "debug",
    "CRITICAL": "critical",
    "SUCCESS": "success",
    "TRACE": "trace",
}

ANSI_LEVEL_COLORS = {
    "TRACE": "\033[36m",
    "DEBUG": "\033[32m",
    "INFO": "\033[34m",
    "SUCCESS": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m\033[37m",
}

HTML_LEVEL_COLORS = {
    "TRACE": "royalblue",
    "DEBUG": "forestgreen",
    "INFO": "deepskyblue",
    "SUCCESS": "forestgreen",
    "WARNING": "darkorange",
    "ERROR": "crimson",
    "CRITICAL": "firebrick",
}


class Client(enum.Enum):
    mxu = "MXU"
    mfaa = "MFAAVALONIA"

    @classmethod
    def from_name(cls, name: str) -> Self | None:
        return cast("dict[str, Self]", cls._value2member_map_).get(name)


_client = Client.from_name(env.client_name.strip().upper())


def _resolve_console_stream() -> TextIO:
    match _client:
        case Client.mxu:
            return sys.stdout
        case Client.mfaa:
            return sys.stderr
        case None:  # 控制台
            return sys.stderr
        case _:
            raise ValueError(f"client = {_client!r}")


def _short_level_name(level_name: str) -> str:
    return LEVEL_SHORT_NAMES.get(level_name, level_name.lower())


def _ansi_level_color(level_name: str) -> str:
    return ANSI_LEVEL_COLORS.get(level_name, "")


def _format_mxu_html_message(level_name: str, message: str) -> str:
    color = HTML_LEVEL_COLORS.get(level_name, "inherit")
    return f'<span style="color:{color}">{html.escape(message)}</span>'


class _ConsoleFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        level_name = record.levelname
        message = record.getMessage()

        match _client:
            case Client.mxu:
                return _format_mxu_html_message(level_name, message)
            case Client.mfaa:
                return f"{_short_level_name(level_name)}:{message}"
            case None:  # 控制台
                level_color = _ansi_level_color(level_name)
                color_reset = "\033[0m" if level_color else ""
                return (
                    f"{datetime.datetime.now().strftime('%Y.%m.%d %H:%M:%S.%f')[:-4]} "
                    f"{level_color}{message}{color_reset}"
                )
            case _:
                raise ValueError(f"client = {_client!r}")


_std_logger = logging.getLogger("_std_logger")


type Logging_level = Literal[
    "CRITICAL", "FATAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "NOTSET"
]


def setup_logger(console_level: Logging_level = "INFO") -> logging.Logger:
    """设置 logger"""
    _std_logger.handlers.clear()
    _std_logger.setLevel(logging.DEBUG)
    _std_logger.propagate = False

    console_handler = logging.StreamHandler(_resolve_console_stream())
    console_handler.setLevel(
        logging.getLevelNamesMapping().get(console_level, logging.INFO)
    )
    console_handler.setFormatter(_ConsoleFormatter())
    _std_logger.addHandler(console_handler)

    return _std_logger


def change_console_level(level: Logging_level = "DEBUG"):
    """动态修改控制台日志等级"""
    setup_logger(console_level=level)
    log.info(f"控制台日志等级已更改为: {level}")


log = setup_logger("INFO" if Path("agent", "__init__.py").is_file() else "DEBUG")
