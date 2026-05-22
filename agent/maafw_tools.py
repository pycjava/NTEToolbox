import time
from typing import TYPE_CHECKING

from .log import log

if TYPE_CHECKING:
    import numpy as np
    from maa.controller import Controller

type Img = np.typing.NDArray


def get_img(controller: Controller, /) -> Img:
    """每次获取新截图要使用新的 controller"""
    start_time = time.time()
    while True:
        try:
            img = controller.post_screencap().get(wait=True)
        except Exception as e:
            log.debug(e)
            if time.time() - start_time > 10:
                log.error("获取截图超时")
                raise
            time.sleep(0.5)
            continue
        return img
