import enum
import time
import traceback
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, override

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


STR_EQ = {
    "打开",
    "开门",
}
STR_IN = (
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
)
STR_NOT_IN = (
    "激活",
    "使用",
)


@dataclass(kw_only=True, slots=True)
class Rt_asst_option:
    自动拾取: bool


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
    except Exception as e:
        log.error(f"选项初始化错误: {e} {e!r}\n{traceback.format_exc()}")
        raise

    return Rt_asst_option(
        自动拾取=自动拾取,
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
                    "param": {"roi": [766, 204, 220, 394]},
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
    if at_all_rt and all(
        (
            all((sni not in s) for sni in STR_NOT_IN)
            and ((s in STR_EQ) or any((si in s) for si in STR_IN))
        )
        for s in at_all_rt
    ):
        return (自动拾取_type.all, len(at_all_rt))

    # 判断当前选项
    color_reco_detail = context.run_recognition(
        reco_自动拾取.__name__ + "_color",
        img,
        pipeline_override={
            reco_自动拾取.__name__ + "_color": {
                "recognition": {
                    "type": "ColorMatch",
                    "param": {
                        "roi": [766, 204, 110, 394],
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
                自动拾取_type.once
                if (
                    all((sni not in text) for sni in STR_NOT_IN)
                    and ((text in STR_EQ) or any((si in text) for si in STR_IN))
                )
                else 自动拾取_type.no
            )
        case _:
            log.debug("识别到多个字符串，取消按键操作")
            return 自动拾取_type.no


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

        _ss = time.time()
        with suppress(Manual_stop):
            while not context.tasker.stopping:
                controller: Controller = context.tasker.controller
                img: Img = get_img(controller)

                if option.自动拾取:
                    match reco_自动拾取(context, img):
                        case 自动拾取_type.once:
                            Win_virtual_key.F.tap(hwnd)
                        case (自动拾取_type.all, num):
                            for _ in range(num):
                                Win_virtual_key.F.tap(hwnd)
                                # ctypes.windll.user32.mouse_event(0x0800, 0, 0, -120, 0)
                                Win_virtual_key.Msg(hwnd).wheel("down")
                                time.sleep(0.05)
                            time.sleep(0.1)

                if (_sth := time.time() - _ss) > 0.3:
                    if _sth > 0.8:
                        log.warning(f"{实时辅助.__name__} 单次循环时间过长: {_sth}")
                    else:
                        log.debug(f"{实时辅助.__name__} 单次循环时间: {_sth}")
                _ss = time.time()

        return True
