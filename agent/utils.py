import itertools
import json
import re
import urllib.request
from pathlib import Path
from pprint import pformat
from threading import Thread
from typing import TYPE_CHECKING, Any, TypeGuard, get_args, get_origin, override

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition, RectType

from .log import log

if TYPE_CHECKING:
    import numpy as np
    from maa.context import Context

DEFAULT_RESOLUTION = (1280, 720)


REQ_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"
}


def open_req(req: urllib.request.Request):
    proxies = urllib.request.getproxies()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))

    return opener.open(req)


class github:
    @classmethod
    def get_latest_release_ver(
        cls,
        release_api_url: str,
        *,
        reg: str | None = None,
    ) -> str | None:
        """失败返回 None，存在 reg 则返回 group(1)"""
        try:
            with open_req(
                urllib.request.Request(
                    url=release_api_url,
                    headers=REQ_HEADER,
                )
            ) as response:
                data: dict = json.loads(response.read().decode("utf-8"))
                ver = data.get("tag_name")
                if ver is None:
                    return None
                if isinstance(ver, str):
                    if reg is None:
                        return ver.lstrip("v")
                    _match = re.search(reg, ver)
                    if _match is None:
                        log.error(f"Match failed: {release_api_url} {reg} {_match}")
                        return None
                    return _match.group(1)
                raise ValueError(f"ver = {ver!r}")
        except Exception as e:
            log.error(
                f"'{cls.__name__}.{cls.get_latest_release_ver.__name__}' execution failed: {e}"
            )

        return None


def check_ver(new_ver_str: str, old_ver_str: str) -> bool:
    new_ver = list(re.sub(r"^\D*(\d.*\d)\D*$", r"\1", new_ver_str).split("."))
    new_ver_add_num = list(str(new_ver[-1]).split("+"))
    new_ver = (
        [int(v) for v in (*new_ver[:-1], new_ver_add_num[0])],
        [int(v) for v in new_ver_add_num[1:]],
    )

    old_ver = list(re.sub(r"^\D*(\d.*\d)\D*$", r"\1", old_ver_str).split("."))
    old_ver_add_num = list(str(old_ver[-1]).split("+"))
    old_ver = (
        [int(v) for v in (*old_ver[:-1], old_ver_add_num[0])],
        [int(v) for v in old_ver_add_num[1:]],
    )

    for i in range(2):
        for new, old in itertools.zip_longest(new_ver[i], old_ver[i], fillvalue=0):
            if new > old:
                return True
            if new < old:
                break
        else:
            continue
        break
    return False


def get_project_version() -> str | None:
    for path in itertools.chain(
        Path.cwd().iterdir(),
        p.iterdir() if (p := Path("assets")).is_dir() else (),
    ):
        if path.stem == "interface" and path.suffix.startswith(".json"):
            try:
                interface = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log.error(f'解码 "{path}" 失败: {e} {e!r}')
                return None
            if not isinstance(interface, dict):
                log.error("interface 不是 dict")
                return None
            if (ver_current := interface.get("version")) is None:
                log.error("interface 中没有 version")
                return None
            return ver_current
    return None


def check_release() -> None:
    for path in itertools.chain(
        Path.cwd().iterdir(),
        p.iterdir() if (p := Path("assets")).is_dir() else (),
    ):
        if path.stem == "interface" and path.suffix.startswith(".json"):
            if (ver_current := get_project_version()) is None:
                return

            ver_release = github.get_latest_release_ver(
                "https://api.github.com/repos/op200/NTEToolbox/releases/latest"
            )
            if ver_release is None:
                log.warning("获取 Github Release 失败")
                return

            if check_ver(ver_release, ver_current):
                log.info(
                    f"有新版本: {ver_current} -> {ver_release}。"
                    "在此下载: https://github.com/op200/NTEToolbox/releases"
                )
            return
    log.error("获取 interface 文件失败")


@AgentServer.custom_recognition("启动测试")
class Adswq(CustomRecognition):
    @override
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> RectType | CustomRecognition.AnalyzeResult | None:
        Thread(target=check_release, daemon=True).start()

        controller = context.tasker.controller

        from .setting import maa_option

        if maa_option.file_path.is_file():
            maa_option_dict = maa_option.read()
            log.info(
                f'检查配置文件 "{maa_option.file_path}" (不代表当前配置，修改配置后需要重启才是实际配置):'
            )
            log.debug(f"{maa_option.file_path}:\n{pformat(maa_option_dict)}")
            log.info(
                "maafw 日志写入: " + ("启用" if maa_option_dict["logging"] else "关闭")
            )

        success: bool = True

        img: np.typing.NDArray = controller.post_screencap().get(wait=True)

        h, w = img.shape[:2]
        if (w, h) != DEFAULT_RESOLUTION:
            log.error(
                f"截图分辨率 {w} x {h} 不是 {DEFAULT_RESOLUTION[0]} x {DEFAULT_RESOLUTION[1]}"
            )
            success = False
        if w * 9 != h * 16:
            log.error(f"截图分辨率 {w} x {h} 不是 16:9")
            success = False

        if success is False:
            return None

        return [0, 0, w, h]


def type_match[T](val: Any, t: type[T]) -> TypeGuard[T]:
    """
    检查值是否匹配给定的类型（支持泛型）

    支持的类型包括：
    - 基本类型: int, str, list, dict, tuple, set
    - 泛型类型: list[str], dict[str, int], tuple[int, ...]
    - 联合类型: int | str, Union[int, str]
    - 可选类型: Optional[str]
    - 嵌套泛型: list[list[str]], dict[str, list[int]]

    Args:
        val: 要检查的值
        t: 目标类型，可以是普通类型或泛型

    Returns:
        bool: 值是否匹配目标类型

    """
    t_org = get_origin(t)

    # 如果不是泛型类型，直接使用 isinstance
    if t_org is None:
        return isinstance(val, t)

    # 首先检查是否是 b_org 的实例
    if not isinstance(val, t_org):
        return False

    # 获取类型参数
    args = get_args(t)
    if not args:  # 没有类型参数，如 List
        return True

    # 根据不同的原始类型进行检查
    if t_org is list:
        # list[T] 检查
        if len(args) == 1:
            elem_type = args[0]
            return all(type_match(item, elem_type) for item in val)

    elif t_org is tuple:
        # tuple[T1, T2, ...] 或 tuple[T, ...] 检查
        if len(args) == 2 and args[1] is ...:  # 可变长度元组
            elem_type = args[0]
            return all(type_match(item, elem_type) for item in val)
        # 固定长度元组
        if len(val) != len(args):
            return False
        return all(type_match(item, t) for item, t in zip(val, args, strict=False))

    elif t_org is dict:
        # dict[K, V] 检查
        if len(args) == 2:
            key_type, value_type = args
            return all(
                type_match(k, key_type) and type_match(v, value_type)
                for k, v in val.items()
            )

    elif t_org is set:
        # set[T] 检查
        if len(args) == 1:
            elem_type = args[0]
            return all(type_match(item, elem_type) for item in val)

    elif t_org is frozenset:
        # frozenset[T] 检查
        if len(args) == 1:
            elem_type = args[0]
            return all(type_match(item, elem_type) for item in val)

    elif hasattr(t_org, "__name__") and t_org.__name__ == "Union":
        # Union[T1, T2, ...] 或 T1 | T2 检查
        return any(type_match(val, t) for t in args)

    return True


class Manual_stop(BaseException):
    pass
