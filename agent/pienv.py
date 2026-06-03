"""Forked from https://github.com/MAA1999/M9A/blob/1a1dfe8acee4255cf7132786e9964646c7071cad/agent/utils/pienv.py"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ENV_CLIENT_LANGUAGE",
    "ENV_CLIENT_MAAFW_VERSION",
    "ENV_CLIENT_NAME",
    "ENV_CLIENT_VERSION",
    "ENV_CONTROLLER",
    "ENV_INTERFACE_VERSION",
    "ENV_RESOURCE",
    "ENV_VERSION",
    "Controller",
    "Env",
    "GamepadConfig",
    "MacOSConfig",
    "PlayCoverConfig",
    "Resource",
    "Win32Config",
    "env",
]

_module_logger = logging.getLogger(__name__)


# PI v2.5.0 environment variable keys.
ENV_INTERFACE_VERSION = "PI_INTERFACE_VERSION"
ENV_CLIENT_NAME = "PI_CLIENT_NAME"
ENV_CLIENT_VERSION = "PI_CLIENT_VERSION"
ENV_CLIENT_LANGUAGE = "PI_CLIENT_LANGUAGE"
ENV_CLIENT_MAAFW_VERSION = "PI_CLIENT_MAAFW_VERSION"
ENV_VERSION = "PI_VERSION"
ENV_CONTROLLER = "PI_CONTROLLER"
ENV_RESOURCE = "PI_RESOURCE"


def _as_string(value: object) -> str:
    return "" if value is None else str(value)


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _as_string_list(value: Any) -> list[str]:
    return (
        [_as_string(item) for item in value if item is not None]
        if isinstance(value, list)
        else []
    )


@dataclass(kw_only=True, frozen=True, slots=True)
class Win32Config:
    class_regex: str = ""
    window_regex: str = ""
    screencap: str = ""
    mouse: str = ""
    keyboard: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Win32Config | None:
        if not isinstance(data, dict):
            return None
        return cls(
            class_regex=_as_string(data.get("class_regex")),
            window_regex=_as_string(data.get("window_regex")),
            screencap=_as_string(data.get("screencap")),
            mouse=_as_string(data.get("mouse")),
            keyboard=_as_string(data.get("keyboard")),
        )


@dataclass(kw_only=True, frozen=True, slots=True)
class MacOSConfig:
    title_regex: str = ""
    screencap: str = ""
    input: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> MacOSConfig | None:
        if not isinstance(data, dict):
            return None
        return cls(
            title_regex=_as_string(data.get("title_regex")),
            screencap=_as_string(data.get("screencap")),
            input=_as_string(data.get("input")),
        )


@dataclass(kw_only=True, frozen=True, slots=True)
class PlayCoverConfig:
    uuid: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> PlayCoverConfig | None:
        if not isinstance(data, dict):
            return None
        return cls(uuid=_as_string(data.get("uuid")))


@dataclass(kw_only=True, frozen=True, slots=True)
class GamepadConfig:
    class_regex: str = ""
    window_regex: str = ""
    gamepad_type: str = ""
    screencap: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> GamepadConfig | None:
        if not isinstance(data, dict):
            return None
        return cls(
            class_regex=_as_string(data.get("class_regex")),
            window_regex=_as_string(data.get("window_regex")),
            gamepad_type=_as_string(data.get("gamepad_type")),
            screencap=_as_string(data.get("screencap")),
        )


@dataclass(kw_only=True, frozen=True, slots=True)
class Controller:
    name: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""
    type: str = ""
    display_short_side: int | None = None
    display_long_side: int | None = None
    display_raw: bool | None = None
    permission_required: bool = False
    attach_resource_path: list[str] = field(default_factory=list)
    option: list[str] = field(default_factory=list)
    win32: Win32Config | None = None
    adb: Any = None
    macos: MacOSConfig | None = None
    playcover: PlayCoverConfig | None = None
    gamepad: GamepadConfig | None = None
    wlroots: Any = None

    @classmethod
    def from_dict(cls, data: Any) -> Controller:
        if not isinstance(data, dict):
            raise TypeError("PI_CONTROLLER is not a JSON object")
        return cls(
            name=_as_string(data.get("name")),
            label=_as_string(data.get("label")),
            description=_as_string(data.get("description")),
            icon=_as_string(data.get("icon")),
            type=_as_string(data.get("type")),
            display_short_side=_as_int(data.get("display_short_side")),
            display_long_side=_as_int(data.get("display_long_side")),
            display_raw=_as_bool(data.get("display_raw")),
            permission_required=bool(data.get("permission_required", False)),
            attach_resource_path=_as_string_list(data.get("attach_resource_path")),
            option=_as_string_list(data.get("option")),
            win32=Win32Config.from_dict(data.get("win32")),
            adb=data.get("adb"),
            macos=MacOSConfig.from_dict(data.get("macos")),
            playcover=PlayCoverConfig.from_dict(data.get("playcover")),
            gamepad=GamepadConfig.from_dict(data.get("gamepad")),
            wlroots=data.get("wlroots"),
        )


@dataclass(kw_only=True, frozen=True, slots=True)
class Resource:
    name: str = ""
    label: str = ""
    description: str = ""
    icon: str = ""
    path: list[str] = field(default_factory=list)
    controller: list[str] = field(default_factory=list)
    option: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> Resource:
        if not isinstance(data, dict):
            raise TypeError("PI_RESOURCE is not a JSON object")
        return cls(
            name=_as_string(data.get("name")),
            label=_as_string(data.get("label")),
            description=_as_string(data.get("description")),
            icon=_as_string(data.get("icon")),
            path=_as_string_list(data.get("path")),
            controller=_as_string_list(data.get("controller")),
            option=_as_string_list(data.get("option")),
        )


@dataclass(kw_only=True, frozen=True, slots=True)
class Env:
    interface_version: str = field(
        default_factory=lambda: os.getenv(ENV_INTERFACE_VERSION, "")
    )
    client_name: str = field(default_factory=lambda: os.getenv(ENV_CLIENT_NAME, ""))
    client_version: str = field(
        default_factory=lambda: os.getenv(ENV_CLIENT_VERSION, "")
    )
    client_language: str = field(
        default_factory=lambda: os.getenv(ENV_CLIENT_LANGUAGE, "")
    )
    client_maafw_version: str = field(
        default_factory=lambda: os.getenv(ENV_CLIENT_MAAFW_VERSION, "")
    )
    version: str = field(default_factory=lambda: os.getenv(ENV_VERSION, ""))
    controller_raw: str = field(default_factory=lambda: os.getenv(ENV_CONTROLLER, ""))
    resource_raw: str = field(default_factory=lambda: os.getenv(ENV_RESOURCE, ""))

    @staticmethod
    def _parse_json_env(env_key: str, raw: str, parser: Any) -> Any:
        if not raw:
            return None

        try:
            return parser(json.loads(raw))
        except Exception as exc:
            _module_logger.warning("failed to parse %s: %s", env_key, exc)
            return None

    def __post_init__(self) -> None:
        _module_logger.info(
            "PI environment initialized: interface_version=%s client_name=%s client_version=%s client_language=%s client_maafw_version=%s pi_version=%s controller_ok=%s resource_ok=%s",
            self.interface_version,
            self.client_name,
            self.client_version,
            self.client_language,
            self.client_maafw_version,
            self.version,
            self.controller is not None,
            self.resource is not None,
        )

    @property
    def controller(self):
        return self._parse_json_env(
            ENV_CONTROLLER, self.controller_raw, Controller.from_dict
        )

    @property
    def resource(self):
        return self._parse_json_env(ENV_RESOURCE, self.resource_raw, Resource.from_dict)

    @property
    def project_version(self) -> str:
        return self.version

    @property
    def controller_type(self) -> str:
        return current.type if (current := self.controller) else ""

    @property
    def controller_name(self) -> str:
        current = self.controller
        return current.name if current else ""

    @property
    def resource_name(self) -> str:
        current = self.resource
        return current.name if current else ""

    @property
    def resource_label(self) -> str:
        return current.label or current.name if (current := self.resource) else ""

    @property
    def resource_paths(self) -> list[str]:
        return list(current.path) if (current := self.resource) else []


env = Env()
