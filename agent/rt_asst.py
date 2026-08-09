import enum
import itertools
import os
import re
import struct
import time
import traceback
import zlib
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, LiteralString, override

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.define import OCRResult

from .log import log
from .maafw_tools import get_img
from .utils import Manual_stop, type_match
from .virtual_key import Win_virtual_key

if TYPE_CHECKING:
    from maa.context import Context
    from maa.controller import Controller

    from .maafw_tools import Img


STR_EQ: Final[set[LiteralString]] = {
    "打开",
    "开门",
    "拿走",
    "打包",
    "采摘",
    "采集",
    "揪",
}
STR_NOT_EQ: Final[set[LiteralString]] = {
    "坐下",
    "驾驶",
}
STR_IN: Final[tuple[LiteralString, ...]] = (
    "卡",
    "永恒之心",
    "宝石",
    "星",
    "翠",
    "金",
    "华海",
    "止痛药",
    "晶",
    "几何",
    "瓶",
    "画",
    "饮",
    "墨",
    "罐",
    "声机",
    "玉",
    "望远镜",
    "游戏机",
    "手机",
    "碗",
    "相机",
    "薯片",
    "模型",
    "酸奶",
    "手办",
    "玩偶",
    "纸钞",
    "摆件",
    "气泡水",
    "银行文件",
    "漫画",
    # 大世界
    "猎人攻略",
    "劲爽",
    "包裹",  # 避役的包裹
    "遗失",  # 钱包、储物柜钥匙
    "公文包",
    "速食",  # 早餐袋
    "巧克力",
    "一箱",  # 一箱xx
    "再来一口",
)
STR_NOT_IN: Final[tuple[LiteralString, ...]] = (
    "激活",
    "使用",
)
assert all(map(bool, itertools.chain(STR_EQ, STR_NOT_EQ, STR_IN, STR_NOT_IN)))
assert all(
    (seq not in STR_NOT_EQ) and all((sni not in seq) for sni in STR_NOT_IN)
    for seq in STR_EQ
)
assert all(
    all((sni not in si) for sni in STR_NOT_IN) and (si not in STR_NOT_EQ)
    for si in STR_IN
)

OCR_ROI: Final = [770, 228, 200, 336]


@lru_cache(maxsize=256)
def is_自动拾取_need_str(text: str, /) -> bool:
    return (
        (text not in STR_NOT_EQ)
        and all((sni not in text) for sni in STR_NOT_IN)
        and ((text in STR_EQ) or any((si in text) for si in STR_IN))
    )


@dataclass(kw_only=True, slots=True)
class Rt_asst_option:
    自动拾取: bool
    永远拾取: bool
    S级鱼截图: bool
    金色鱼截图: bool
    鱼截图冷却时间: int


def get_option(context: Context, argv: CustomAction.RunArg, /) -> Rt_asst_option:
    node_obj = context.get_node_object(argv.node_name)
    if node_obj is None:
        log.error("获取 node_object 失败")
        raise RuntimeError
    attach = node_obj.attach
    del context, argv

    try:
        自动拾取 = attach.get("自动拾取")
        if not isinstance(自动拾取, bool):
            raise TypeError("自动拾取 类型不是 bool")

        永远拾取 = attach.get("永远拾取")
        if not isinstance(永远拾取, bool):
            raise TypeError("永远拾取 类型不是 bool")

        S级鱼截图 = attach.get("S级鱼截图", False)
        if not isinstance(S级鱼截图, bool):
            raise TypeError("S级鱼截图 类型不是 bool")

        金色鱼截图 = attach.get("金色鱼截图", False)
        if not isinstance(金色鱼截图, bool):
            raise TypeError("金色鱼截图 类型不是 bool")

        鱼截图冷却时间 = attach.get("鱼截图冷却时间", attach.get("S级鱼截图冷却时间", 5))
        if not isinstance(鱼截图冷却时间, int):
            raise TypeError("鱼截图冷却时间 类型不是 int")
        if 鱼截图冷却时间 < 0:
            raise ValueError("鱼截图冷却时间 不能小于 0")
    except Exception as e:
        log.error(f"选项初始化错误: {e} {e!r}\n{traceback.format_exc()}")
        raise

    return Rt_asst_option(
        自动拾取=自动拾取,
        永远拾取=永远拾取,
        S级鱼截图=S级鱼截图,
        金色鱼截图=金色鱼截图,
        鱼截图冷却时间=鱼截图冷却时间,
    )


class 自动拾取_type(enum.Enum):
    no = enum.auto()
    once = enum.auto()
    all = enum.auto()


def reco_自动拾取(
    context: Context, img: Img, /
) -> (
    Literal[自动拾取_type.no, 自动拾取_type.once]
    | tuple[Literal[自动拾取_type.all], int]
):
    """
    先识别所有字符串，若都是可拾取项，则全部拾取，否则判断当前选项是否为可拾取项

    :return: 当类型为 all 时，附带 OCR 的 list[str] 的 len
    """
    all_text_reco_detail = context.run_recognition(
        reco_自动拾取.__name__ + "_all_text",
        img,
        pipeline_override={
            reco_自动拾取.__name__ + "_all_text": {
                "recognition": {
                    "type": "OCR",
                    "param": {"roi": OCR_ROI},
                },
            }
        },
    )
    if all_text_reco_detail is None or all_text_reco_detail.box is None:
        return 自动拾取_type.no

    at_all_results = all_text_reco_detail.all_results
    if not type_match(at_all_results, Sequence[OCRResult]):
        log.error(
            f"{reco_自动拾取.__name__}_all_text OCR 结果不是 Sequence[OCRResult] 类型"
        )
        return 自动拾取_type.no

    at_all_rt = [r.text for r in at_all_results if r.score > 0.7]
    if at_all_rt:
        if all(
            at_all_rt_bool := tuple[bool, ...](map(is_自动拾取_need_str, at_all_rt))
        ):
            log.debug(at_all_rt)
            return (自动拾取_type.all, len(at_all_rt))
        if not any(at_all_rt_bool):
            # 如果全都不匹配，则提前终止
            return 自动拾取_type.no

    # 判断当前选项
    color_reco_detail = context.run_recognition(
        reco_自动拾取.__name__ + "_color",
        img,
        pipeline_override={
            reco_自动拾取.__name__ + "_color": {
                "recognition": {
                    "type": "ColorMatch",
                    "param": {
                        "roi": OCR_ROI,
                        "lower": [192, 68, 118],
                        "upper": [208, 74, 124],
                    },
                }
            }
        },
    )
    if color_reco_detail is None or color_reco_detail.box is None:
        return 自动拾取_type.no

    box = color_reco_detail.box
    text_reco_detail = context.run_recognition(
        reco_自动拾取.__name__ + "_text",
        img,
        pipeline_override={
            reco_自动拾取.__name__ + "_text": {
                "recognition": {
                    "type": "OCR",
                    "param": {"roi": [box.x, box.y - 10, box.w + 100, box.h + 20]},
                },
            }
        },
    )
    if text_reco_detail is None or text_reco_detail.box is None:
        return 自动拾取_type.no

    t_all_results = text_reco_detail.all_results
    if not type_match(t_all_results, Sequence[OCRResult]):
        log.error(
            f"{reco_自动拾取.__name__}_text OCR 结果不是 Sequence[OCRResult] 类型"
        )
        return 自动拾取_type.no

    t_all_results = [r for r in t_all_results if r.score > 0.7]
    match len(t_all_results):
        case 0:
            return 自动拾取_type.no
        case 1:
            text = t_all_results[0].text
            log.debug(text)
            return (
                自动拾取_type.once if is_自动拾取_need_str(text) else 自动拾取_type.no
            )
        case _:
            log.debug("识别到多个字符串，取消按键操作")
            return 自动拾取_type.no


def pick_with_wheel(hwnd: int, /):
    Win_virtual_key.F.tap(hwnd)
    # ctypes.windll.user32.mouse_event(0x0800, 0, 0, -120, 0)
    Win_virtual_key.Msg(hwnd).wheel("down")
    time.sleep(0.03)


拾取轮间间隔: Final[float] = 0.15  # 过小会无法拾取


S_RANK_GOLDEN_BG_ROI: Final = [480, 200, 280, 280]
S_RANK_ICON_ROI: Final = [660, 190, 140, 130]
S_RANK_ICON_TEMPLATE: Final = "fish/s_rank_icon.png"
FISH_SCREENSHOT_ROOT_ENV: Final = "NTE_TOOLBOX_INSTALL_ROOT"


@dataclass(kw_only=True, slots=True)
class FishScreenshotState:
    last_save_time: float = float("-inf")


def reco_golden_fish(context: Context, img: Img, /) -> bool:
    golden_bg_reco_detail = context.run_recognition(
        reco_golden_fish.__name__,
        img,
        pipeline_override={
            reco_golden_fish.__name__: {
                "recognition": {
                    "type": "ColorMatch",
                    "param": {
                        "roi": S_RANK_GOLDEN_BG_ROI,
                        "method": 4,
                        "lower": [210, 105, 0],
                        "upper": [255, 225, 80],
                        "count": 3500,
                    },
                },
            }
        },
    )
    return not (golden_bg_reco_detail is None or golden_bg_reco_detail.box is None)


def reco_s_rank_fish(context: Context, img: Img, /) -> bool:
    s_icon_reco_detail = context.run_recognition(
        reco_s_rank_fish.__name__,
        img,
        pipeline_override={
            reco_s_rank_fish.__name__: {
                "recognition": {
                    "type": "FeatureMatch",
                    "param": {
                        "roi": S_RANK_ICON_ROI,
                        "template": S_RANK_ICON_TEMPLATE,
                        "ratio": 0.72,
                        "count": 8,
                    },
                },
            }
        },
    )
    return not (s_icon_reco_detail is None or s_icon_reco_detail.box is None)


def get_fish_screenshot_path(now: float, /) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    millis = int(now * 1000) % 1000
    safe_timestamp = re.sub(r"[^0-9_]", "", f"{timestamp}_{millis:03d}")
    save_root = os.getenv(FISH_SCREENSHOT_ROOT_ENV) or Path(os.getcwd(), "fish")
    return Path(save_root, f"fish_{safe_timestamp}.png")


def save_img(img: Img, path: Path, /) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = img.shape[:2]
    channel_num = 1 if len(img.shape) == 2 else img.shape[2]
    color_type = {1: 0, 3: 2, 4: 6}.get(channel_num)
    if color_type is None:
        log.error(f"不支持的截图通道数: {channel_num}")
        return False

    # BGR → RGB：MaaFramework 截图为 BGR 顺序，PNG 要求 RGB
    if channel_num == 3:
        img = img[..., ::-1].copy()

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    row_bytes = width * channel_num
    img_bytes = memoryview(img).tobytes()
    raw = b"".join(
        b"\x00" + img_bytes[y * row_bytes : (y + 1) * row_bytes]
        for y in range(height)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk("IHDR".encode(), struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
        + png_chunk("IDAT".encode(), zlib.compress(raw))
        + png_chunk("IEND".encode(), b"")
    )
    return True


def try_save_fish_screenshot(
    context: Context,
    img: Img,
    option: Rt_asst_option,
    state: FishScreenshotState,
    /,
) -> bool:
    need_save = False
    if option.S级鱼截图 and reco_s_rank_fish(context, img):
        need_save = True
    if option.金色鱼截图 and reco_golden_fish(context, img):
        need_save = True
    if not need_save:
        return False

    now = time.time()
    if now - state.last_save_time < option.鱼截图冷却时间:
        return False

    save_path = get_fish_screenshot_path(now)
    if not save_img(img, save_path):
        log.error(f"鱼截图保存失败: {save_path}")
        return False

    state.last_save_time = now
    log.info(f"已保存鱼截图: {save_path}")
    return True


def 自动拾取(context: Context, img: Img, hwnd: int, /) -> None:
    t_start = time.time()
    reco_自动拾取_return = reco_自动拾取(context, img)
    if (t_th_reco := time.time() - t_start) > 0.3:
        log.warning(
            f"{实时辅助.__name__} {reco_自动拾取.__name__} 耗时过长"
            + ("" if reco_自动拾取_return == 自动拾取_type.no else "，放弃执行按键")
            + f": {t_th_reco:.3f}s"
        )
        return

    if reco_自动拾取_return == 自动拾取_type.no:
        return
    if t_th_reco < 拾取轮间间隔:
        log.debug(
            f"{实时辅助.__name__} {reco_自动拾取.__name__} 耗时小于 拾取轮间间隔:"
            f"{t_th_reco:.3f} < {拾取轮间间隔}"
        )
        time.sleep(拾取轮间间隔 - t_th_reco)

    match reco_自动拾取_return:
        case 自动拾取_type.once:
            Win_virtual_key.F.tap(hwnd)
        case (自动拾取_type.all, num):
            for _ in range(num):
                pick_with_wheel(hwnd)


@AgentServer.custom_action("实时辅助")
class 实时辅助(CustomAction):
    @override
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        option: Rt_asst_option = get_option(context, argv)
        log.debug(f"{option=}")

        hwnd = context.tasker.controller.info.get("hwnd")
        if not isinstance(hwnd, int):
            log.error("获取 hwnd 失败")
            return False

        _t_loop = time.time()
        fish_screenshot_state = FishScreenshotState()

        with suppress(Manual_stop):
            while not context.tasker.stopping:
                if option.自动拾取 and option.永远拾取:
                    if Win_virtual_key.F.is_global_key_down():
                        time.sleep(0.002)
                        continue
                    for _ in range(6):
                        pick_with_wheel(hwnd)
                    time.sleep(拾取轮间间隔)
                    continue

                if option.自动拾取 or option.S级鱼截图 or option.金色鱼截图:
                    # 以下需要 API
                    controller: Controller = context.tasker.controller
                    img: Img = get_img(controller)

                    # 鱼截图
                    try_save_fish_screenshot(
                        context,
                        img,
                        option,
                        fish_screenshot_state,
                    )

                    # 自动拾取
                    if option.自动拾取:
                        自动拾取(context, img, hwnd)

                    # 本轮循环结束
                    if (_t_th := time.time() - _t_loop) > 0.3:
                        if _t_th > 0.8:
                            log.warning(
                                f"{实时辅助.__name__} 单次循环时间过长: {_t_th:.3f}s"
                            )
                        else:
                            log.debug(f"{实时辅助.__name__} 单次循环时间: {_t_th:.3f}s")
                    _t_loop = time.time()
                    continue
                time.sleep(0.05)

        return True
