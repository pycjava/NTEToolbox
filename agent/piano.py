import enum
import itertools
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Final,
    Literal,
    LiteralString,
    NamedTuple,
    cast,
    override,
)

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from .global_val import Exit_code
from .log import log
from .virtual_key import Win_virtual_key

if TYPE_CHECKING:
    from maa.context import Context
    from maa.job import Job


type Key_name = Literal["Z", "X", "C", "V", "B", "N", "M","A", "S", "D", "F", "G", "H", "J", "Q", "W", "E", "R", "T", "Y", "U"]  # fmt: off


LOW_PITCH_OVERFLOW_LINE, HIGH_PITCH_OVERFLOW_LINE = 59, 96


DEFAULT_KN__MIDI: Final[dict[Key_name, int]] = {
    **{"Z": 60, "X": 62, "C": 64, "V": 65, "B": 67, "N": 69, "M": 71},  # noqa: PIE800
    **{"A": 72, "S": 74, "D": 76, "F": 77, "G": 79, "H": 81, "J": 83},  # noqa: PIE800
    **{"Q": 84, "W": 86, "E": 88, "R": 89, "T": 91, "Y": 93, "U": 95},  # noqa: PIE800
}

CTRL_CHANGE_KN__MIDI: Final[dict[Key_name, int]] = {  # -1
    kn: DEFAULT_KN__MIDI[kn] - 1
    for kn in itertools.chain(
        ("C", "M"),
        ("D", "J"),
        ("E", "U"),
    )
}
SHIFT_CHANGE_KN__MIDI: Final[dict[Key_name, int]] = {  # +1
    kn: DEFAULT_KN__MIDI[kn] + 1
    for kn in itertools.chain(
        ("Z", "V", "B"),
        ("A", "F", "G"),
        ("Q", "R", "T"),
    )
}


@dataclass(slots=True, kw_only=True, frozen=True)
class Key:
    class Mode(enum.Enum):
        always = enum.auto()

        only_ctrl = enum.auto()
        no_ctrl = enum.auto()

        only_shift = enum.auto()
        no_shift = enum.auto()

    mode: Mode
    code: int


MIDI_SUFFIX_SET: Final[set[LiteralString]] = {".mid", ".midi"}


def get_midi_range(all_midi: list[int], /) -> tuple[int, int, list[int], list[int]]:
    midi_min_list = [midi for midi in all_midi if midi <= LOW_PITCH_OVERFLOW_LINE]
    midi_max_list = [midi for midi in all_midi if midi >= HIGH_PITCH_OVERFLOW_LINE]
    return min(all_midi), max(all_midi), midi_min_list, midi_max_list


@AgentServer.custom_action("piano_play")
class Piano_play(CustomAction):
    @override
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        try:
            import music21
        except ModuleNotFoundError:
            log.error(
                "music21 未安装，执行以下命令以安装或更新: python -m pip install -U music21"
            )
            sys.exit(Exit_code.import_failed.value)

        if TYPE_CHECKING:
            import music21.common.types

        controller = context.tasker.controller

        class NoteEvent(NamedTuple):
            """用于存储音符事件的简易结构"""

            quarterbeats: music21.common.types.OffsetQL
            midi: int
            velocity: int  # 暂未使用，但可从 MIDI 中提取

        param = json.loads(argv.custom_action_param)
        assert isinstance(param, dict)
        log.debug(param)

        piano_mode = param.get("piano_mode")
        if piano_mode not in {"21", "36"}:
            log.error("钢琴模式 必须是 21 或 36")
            return False
        if TYPE_CHECKING:
            piano_mode = cast("Literal['21', '36']", piano_mode)
        log.info(f"钢琴模式: {piano_mode}")

        timeout_mode = param.get("timeout_mode")
        if timeout_mode not in {"同步时轴", "速率不变"}:
            log.error("超时模式 必须是 同步时轴 或 速率不变")
            return False
        if TYPE_CHECKING:
            timeout_mode = cast("Literal['同步时轴', '速率不变']", timeout_mode)
        log.info(f"超时模式: {timeout_mode}")

        use_custom_winapi = param.get("use_custom_winapi")
        if isinstance(use_custom_winapi, str):
            if use_custom_winapi.isdigit():
                use_custom_winapi = int(use_custom_winapi)
            else:
                log.error("使用自定义的 WinAPI 必须是整数")
                return False
        if not isinstance(use_custom_winapi, int):
            log.error(f"使用自定义的 WinAPI 类型异常: {type(use_custom_winapi)}")
            return False
        if use_custom_winapi not in {0, 1}:
            log.error("使用自定义的 WinAPI 必须是 0 或 1")
            return False
        use_custom_winapi = bool(use_custom_winapi)
        if use_custom_winapi:
            log.info("使用自定义的 WinAPI")

        midi__key: dict[int, Key] = {
            midi: Key(
                mode=(
                    Key.Mode.no_ctrl
                    if kn in CTRL_CHANGE_KN__MIDI
                    else Key.Mode.no_shift
                    if kn in SHIFT_CHANGE_KN__MIDI
                    else Key.Mode.always
                ),
                code=code,
            )
            for kn, midi in DEFAULT_KN__MIDI.items()
            if (code := Win_virtual_key[kn].value.code)
        }

        if piano_mode == "36":
            midi__key_ctrl = {
                midi: Key(mode=Key.Mode.only_ctrl, code=Win_virtual_key[kn].value.code)
                for kn, midi in CTRL_CHANGE_KN__MIDI.items()
            }
            midi__key_shift = {
                midi: Key(mode=Key.Mode.only_shift, code=Win_virtual_key[kn].value.code)
                for kn, midi in SHIFT_CHANGE_KN__MIDI.items()
            }
            midi__key |= midi__key_ctrl | midi__key_shift

        key_map: list[Key] = [midi__key[DEFAULT_KN__MIDI["Z"]]] * (
            LOW_PITCH_OVERFLOW_LINE + 1
        )
        """midi -> key 的 list index 版"""
        _val = midi__key[LOW_PITCH_OVERFLOW_LINE + 1]
        for i in range(LOW_PITCH_OVERFLOW_LINE + 1, HIGH_PITCH_OVERFLOW_LINE):
            if i in midi__key:
                _val = midi__key[i]
            key_map.append(_val)
        key_map += [midi__key[DEFAULT_KN__MIDI["U"]]] * (128 - HIGH_PITCH_OVERFLOW_LINE)

        midi_path: Path | None = (
            None if (v := param.get("midi_path")) is None else Path(v)
        )
        if midi_path is None:
            if midi_file_list := [
                p for p in Path.cwd().iterdir() if p.suffix in MIDI_SUFFIX_SET
            ]:
                midi_path = midi_file_list[0]
            else:
                log.error("当前目录下没有 midi 文件")
                return False
        elif midi_path.suffix not in MIDI_SUFFIX_SET:
            log.error(f"输入的文件后缀不属于 {MIDI_SUFFIX_SET}")
            return False

        if not midi_path.is_file():
            log.warning(f'文件 "{midi_path}" 不存在')

        try:
            midi_converted = music21.converter.parse(midi_path)
        except Exception as e:
            log.error(f"加载 MIDI 文件失败: {e}")
            raise

        if isinstance(midi_converted, music21.stream.Opus):
            target_part = midi_converted.scores.parts[0]
        elif isinstance(midi_converted, music21.stream.Score):
            target_part = midi_converted.parts[0]
        elif isinstance(midi_converted, music21.stream.Part):
            target_part = midi_converted
        else:
            raise TypeError("读取到的数据类型不正确")

        log.info(
            f"使用声部: {target_part.partName if hasattr(target_part, 'partName') else '单轨'}"
        )

        # 4. 提取所有音符事件（包含全局四分音符位置）
        notes_events: list[NoteEvent] = []
        for el in target_part.recurse().notesAndRests:
            if not el.isNote and not el.isChord:
                continue

            # 获取全局四分音符长度单位位置
            measure = el.getContextByClass("Measure")
            quarterbeats = (
                el.offset if measure is None else measure.offset + el.offset
            )  # 不应该发生，但容错

            if el.isNote:
                assert isinstance(el, music21.note.Note)
                if el.volume.velocity is not None:
                    notes_events.append(
                        NoteEvent(
                            quarterbeats=quarterbeats,
                            midi=el.pitch.midi,
                            velocity=el.volume.velocity if el.volume else 64,
                        )
                    )
            elif el.isChord:
                assert isinstance(el, music21.chord.Chord)
                if el.volume.velocity is not None:
                    for pitch in el.pitches:
                        notes_events.append(
                            NoteEvent(
                                quarterbeats=quarterbeats,
                                midi=pitch.midi,
                                velocity=el.volume.velocity if el.volume else 64,
                            )
                        )

        if not notes_events:
            log.error("没有音符")
            return False

        # 5. 获取速度
        bpm = float(param.get("bpm") or 120)
        try:
            # 尝试从乐谱中提取第一个速度标记
            for el in midi_converted.recurse().getElementsByClass("MetronomeMark"):
                bpm = el.number
                log.info(f"速度读取成功: {bpm} BPM")
                break
            else:
                log.info(f"未找到速度标记，使用指定或默认 {bpm} BPM")
        except Exception as e:
            log.warning(f"获取速度异常，使用 {bpm} BPM: {e}")
        quarter_sec: float = 60 / bpm

        # 6. 按 quarterbeats 分组音符（处理同时触发）

        grouped: dict[music21.common.types.OffsetQL, list[NoteEvent]] = defaultdict(
            list
        )
        for ne in sorted(notes_events, key=lambda x: x.quarterbeats):
            grouped[ne.quarterbeats].append(ne)

        # 7. 音高范围检查
        all_midi = [ne.midi for ne in notes_events]
        midi_min, midi_max, midi_min_list, midi_max_list = get_midi_range(all_midi)
        log.info(
            f"MIDI 范围: {midi_min} - {midi_max}, 跨度: {midi_max - midi_min}"
        )
        _max_len = len(str(max(len(midi_min_list), len(midi_max_list))))
        if midi_min <= LOW_PITCH_OVERFLOW_LINE:
            log.warning(f"警告: 低音溢出 {len(midi_min_list):<{_max_len}} 个音符")
        if midi_max >= HIGH_PITCH_OVERFLOW_LINE:
            log.warning(f"警告: 高音溢出 {len(midi_max_list):<{_max_len}} 个音符")
        del all_midi, midi_min_list, midi_max_list, midi_min, midi_max, _max_len

        # 8. 开始按时间顺序模拟按键
        hwnd = controller.info.get("hwnd")
        if not isinstance(hwnd, int):
            log.error("获取 hwnd 失败")
            return False
        KEY_MSG_INTERVAL: Final[float] = 0
        """按下和抬起键之间的间隔"""

        start_real = time.time()
        timeout: float = 0
        timeout_total: float = 0

        for qb in sorted(grouped.keys()):
            if context.tasker.stopping:
                log.info("手动终止")
                return False
            target_real = start_real + qb * quarter_sec
            now = time.time()
            timeout = target_real + timeout_total - now
            match timeout_mode:
                case "同步时轴":
                    if target_real > now:
                        time.sleep(target_real - now)
                    elif (_timeout_print := round((now - target_real) * 1000)) > 0:
                        log.warning(f"超时: {_timeout_print:>7,}ms")
                case "速率不变":
                    if timeout >= 0:
                        time.sleep(timeout)
                    elif (_timeout_print := round((-timeout) * 1000)) > 0:
                        timeout_total = now - target_real
                        log.warning(
                            f"超时: {_timeout_print:>5,}ms  {round(timeout_total * 1000):>7,}ms"
                        )

            # 收集当前时间点的所有按键
            keys: set[Key] = {key_map[ne.midi] for ne in grouped[qb]}

            post_job_list: list[Job] = []

            if all(
                k.mode not in {Key.Mode.only_ctrl, Key.Mode.only_shift} for k in keys
            ):
                # 无长按情况
                if use_custom_winapi:
                    with Win_virtual_key.Msg(hwnd, (k.code for k in keys)):
                        time.sleep(KEY_MSG_INTERVAL)
                else:
                    for key in keys:
                        post_job_list.append(controller.post_click_key(key.code))
                    for job in post_job_list:
                        job.wait()

                continue

            # 有长按情况
            key_list_always = [k for k in keys if k.mode == Key.Mode.always]
            key_list_ctrl = [
                k for k in keys if k.mode in {Key.Mode.only_ctrl, Key.Mode.no_shift}
            ]
            key_list_shift = [
                k for k in keys if k.mode in {Key.Mode.only_shift, Key.Mode.no_ctrl}
            ]

            # region: Shift and Always
            if key_list_shift:
                keys_shift = itertools.chain(key_list_shift, key_list_always)
                if use_custom_winapi:
                    with Win_virtual_key.Msg(hwnd, [Win_virtual_key.VK_SHIFT]):
                        time.sleep(KEY_MSG_INTERVAL)
                        with Win_virtual_key.Msg(hwnd, (k.code for k in keys_shift)):
                            time.sleep(KEY_MSG_INTERVAL)
                else:
                    controller.post_key_down(Win_virtual_key.VK_SHIFT.value.code).wait()

                    for key in keys_shift:
                        post_job_list.append(controller.post_click_key(key.code))
                    for job in post_job_list:
                        job.wait()

                    controller.post_key_up(Win_virtual_key.VK_SHIFT.value.code).wait()
            # endregion

            # region: Ctrl
            if key_list_ctrl:
                keys_ctrl = (
                    k
                    for k in itertools.chain(
                        key_list_ctrl, () if key_list_shift else key_list_always
                    )
                    if k.mode in {Key.Mode.only_ctrl, Key.Mode.no_shift}
                )
                if use_custom_winapi:
                    with Win_virtual_key.Msg(hwnd, [Win_virtual_key.VK_CONTROL]):
                        time.sleep(KEY_MSG_INTERVAL)
                        with Win_virtual_key.Msg(hwnd, (k.code for k in keys_ctrl)):
                            time.sleep(KEY_MSG_INTERVAL)
                else:
                    controller.post_key_down(
                        Win_virtual_key.VK_CONTROL.value.code
                    ).wait()

                    post_job_list.clear()
                    for key in keys_ctrl:
                        post_job_list.append(controller.post_click_key(key.code))
                    for job in post_job_list:
                        job.wait()

                    controller.post_key_up(Win_virtual_key.VK_CONTROL.value.code).wait()
            # endregion

        return True
