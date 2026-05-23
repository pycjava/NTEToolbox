import contextlib
import ctypes
import enum
from ctypes import wintypes
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Literal, Self, override

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType


class Win_virtual_key(enum.Enum):
    @dataclass(slots=True, frozen=True)
    class Value:
        code: int
        desc: str

    VK_LBUTTON = Value(0x01, "Left mouse button")
    VK_RBUTTON = Value(0x02, "Right mouse button")
    VK_CANCEL = Value(0x03, "Control-break processing")
    VK_MBUTTON = Value(0x04, "Middle mouse button")
    VK_XBUTTON1 = Value(0x05, "X1 mouse button")
    VK_XBUTTON2 = Value(0x06, "X2 mouse button")
    VK_BACK = Value(0x08, "Backspace key")
    VK_TAB = Value(0x09, "Tab key")
    VK_CLEAR = Value(0x0C, "Clear key")
    VK_RETURN = Value(0x0D, "Enter key")
    VK_SHIFT = Value(0x10, "Shift key")
    VK_CONTROL = Value(0x11, "Ctrl key")
    VK_MENU = Value(0x12, "Alt key")
    VK_PAUSE = Value(0x13, "Pause key")
    VK_CAPITAL = Value(0x14, "Caps lock key")
    VK_KANA = Value(0x15, "IME Kana mode")
    VK_HANGUL = Value(0x15, "IME Hangul mode")
    VK_IME_ON = Value(0x16, "IME On")
    VK_JUNJA = Value(0x17, "IME Junja mode")
    VK_FINAL = Value(0x18, "IME final mode")
    VK_HANJA = Value(0x19, "IME Hanja mode")
    VK_KANJI = Value(0x19, "IME Kanji mode")
    VK_IME_OFF = Value(0x1A, "IME Off")
    VK_ESCAPE = Value(0x1B, "Esc key")
    VK_CONVERT = Value(0x1C, "IME convert")
    VK_NONCONVERT = Value(0x1D, "IME nonconvert")
    VK_ACCEPT = Value(0x1E, "IME accept")
    VK_MODECHANGE = Value(0x1F, "IME mode change request")
    VK_SPACE = Value(0x20, "Spacebar key")
    VK_PRIOR = Value(0x21, "Page up key")
    VK_NEXT = Value(0x22, "Page down key")
    VK_END = Value(0x23, "End key")
    VK_HOME = Value(0x24, "Home key")
    VK_LEFT = Value(0x25, "Left arrow key")
    VK_UP = Value(0x26, "Up arrow key")
    VK_RIGHT = Value(0x27, "Right arrow key")
    VK_DOWN = Value(0x28, "Down arrow key")
    VK_SELECT = Value(0x29, "Select key")
    VK_PRINT = Value(0x2A, "Print key")
    VK_EXECUTE = Value(0x2B, "Execute key")
    VK_SNAPSHOT = Value(0x2C, "Print screen key")
    VK_INSERT = Value(0x2D, "Insert key")
    VK_DELETE = Value(0x2E, "Delete key")
    VK_HELP = Value(0x2F, "Help key")
    _0 = Value(0x30, "0 key")
    _1 = Value(0x31, "1 key")
    _2 = Value(0x32, "2 key")
    _3 = Value(0x33, "3 key")
    _4 = Value(0x34, "4 key")
    _5 = Value(0x35, "5 key")
    _6 = Value(0x36, "6 key")
    _7 = Value(0x37, "7 key")
    _8 = Value(0x38, "8 key")
    _9 = Value(0x39, "9 key")
    A = Value(0x41, "A key")
    B = Value(0x42, "B key")
    C = Value(0x43, "C key")
    D = Value(0x44, "D key")
    E = Value(0x45, "E key")
    F = Value(0x46, "F key")
    G = Value(0x47, "G key")
    H = Value(0x48, "H key")
    I = Value(0x49, "I key")  # noqa: E741
    J = Value(0x4A, "J key")
    K = Value(0x4B, "K key")
    L = Value(0x4C, "L key")
    M = Value(0x4D, "M key")
    N = Value(0x4E, "N key")
    O = Value(0x4F, "O key")  # noqa: E741
    P = Value(0x50, "P key")
    Q = Value(0x51, "Q key")
    R = Value(0x52, "R key")
    S = Value(0x53, "S key")
    T = Value(0x54, "T key")
    U = Value(0x55, "U key")
    V = Value(0x56, "V key")
    W = Value(0x57, "W key")
    X = Value(0x58, "X key")
    Y = Value(0x59, "Y key")
    Z = Value(0x5A, "Z key")
    VK_LWIN = Value(0x5B, "Left Windows logo key")
    VK_RWIN = Value(0x5C, "Right Windows logo key")
    VK_APPS = Value(0x5D, "Application key")
    VK_SLEEP = Value(0x5F, "Computer Sleep key")
    VK_NUMPAD0 = Value(0x60, "Numeric keypad 0 key")
    VK_NUMPAD1 = Value(0x61, "Numeric keypad 1 key")
    VK_NUMPAD2 = Value(0x62, "Numeric keypad 2 key")
    VK_NUMPAD3 = Value(0x63, "Numeric keypad 3 key")
    VK_NUMPAD4 = Value(0x64, "Numeric keypad 4 key")
    VK_NUMPAD5 = Value(0x65, "Numeric keypad 5 key")
    VK_NUMPAD6 = Value(0x66, "Numeric keypad 6 key")
    VK_NUMPAD7 = Value(0x67, "Numeric keypad 7 key")
    VK_NUMPAD8 = Value(0x68, "Numeric keypad 8 key")
    VK_NUMPAD9 = Value(0x69, "Numeric keypad 9 key")
    VK_MULTIPLY = Value(0x6A, "Multiply key")
    VK_ADD = Value(0x6B, "Add key")
    VK_SEPARATOR = Value(0x6C, "Separator key")
    VK_SUBTRACT = Value(0x6D, "Subtract key")
    VK_DECIMAL = Value(0x6E, "Decimal key")
    VK_DIVIDE = Value(0x6F, "Divide key")
    VK_F1 = Value(0x70, "F1 key")
    VK_F2 = Value(0x71, "F2 key")
    VK_F3 = Value(0x72, "F3 key")
    VK_F4 = Value(0x73, "F4 key")
    VK_F5 = Value(0x74, "F5 key")
    VK_F6 = Value(0x75, "F6 key")
    VK_F7 = Value(0x76, "F7 key")
    VK_F8 = Value(0x77, "F8 key")
    VK_F9 = Value(0x78, "F9 key")
    VK_F10 = Value(0x79, "F10 key")
    VK_F11 = Value(0x7A, "F11 key")
    VK_F12 = Value(0x7B, "F12 key")
    VK_F13 = Value(0x7C, "F13 key")
    VK_F14 = Value(0x7D, "F14 key")
    VK_F15 = Value(0x7E, "F15 key")
    VK_F16 = Value(0x7F, "F16 key")
    VK_F17 = Value(0x80, "F17 key")
    VK_F18 = Value(0x81, "F18 key")
    VK_F19 = Value(0x82, "F19 key")
    VK_F20 = Value(0x83, "F20 key")
    VK_F21 = Value(0x84, "F21 key")
    VK_F22 = Value(0x85, "F22 key")
    VK_F23 = Value(0x86, "F23 key")
    VK_F24 = Value(0x87, "F24 key")
    VK_NUMLOCK = Value(0x90, "Num lock key")
    VK_SCROLL = Value(0x91, "Scroll lock key")
    VK_LSHIFT = Value(0xA0, "Left Shift key")
    VK_RSHIFT = Value(0xA1, "Right Shift key")
    VK_LCONTROL = Value(0xA2, "Left Ctrl key")
    VK_RCONTROL = Value(0xA3, "Right Ctrl key")
    VK_LMENU = Value(0xA4, "Left Alt key")
    VK_RMENU = Value(0xA5, "Right Alt key")
    VK_BROWSER_BACK = Value(0xA6, "Browser Back key")
    VK_BROWSER_FORWARD = Value(0xA7, "Browser Forward key")
    VK_BROWSER_REFRESH = Value(0xA8, "Browser Refresh key")
    VK_BROWSER_STOP = Value(0xA9, "Browser Stop key")
    VK_BROWSER_SEARCH = Value(0xAA, "Browser Search key")
    VK_BROWSER_FAVORITES = Value(0xAB, "Browser Favorites key")
    VK_BROWSER_HOME = Value(0xAC, "Browser Start and Home key")
    VK_VOLUME_MUTE = Value(0xAD, "Volume Mute key")
    VK_VOLUME_DOWN = Value(0xAE, "Volume Down key")
    VK_VOLUME_UP = Value(0xAF, "Volume Up key")
    VK_MEDIA_NEXT_TRACK = Value(0xB0, "Next Track key")
    VK_MEDIA_PREV_TRACK = Value(0xB1, "Previous Track key")
    VK_MEDIA_STOP = Value(0xB2, "Stop Media key")
    VK_MEDIA_PLAY_PAUSE = Value(0xB3, "Play/Pause Media key")
    VK_LAUNCH_MAIL = Value(0xB4, "Start Mail key")
    VK_LAUNCH_MEDIA_SELECT = Value(0xB5, "Select Media key")
    VK_LAUNCH_APP1 = Value(0xB6, "Start Application 1 key")
    VK_LAUNCH_APP2 = Value(0xB7, "Start Application 2 key")
    VK_OEM_1 = Value(
        0xBA,
        "It can vary by keyboard. For the US ANSI keyboard , the Semicolon and Colon key",
    )
    VK_OEM_PLUS = Value(0xBB, "For any country/region, the Equals and Plus key")
    VK_OEM_COMMA = Value(0xBC, "For any country/region, the Comma and Less Than key")
    VK_OEM_MINUS = Value(0xBD, "For any country/region, the Dash and Underscore key")
    VK_OEM_PERIOD = Value(
        0xBE, "For any country/region, the Period and Greater Than key"
    )
    VK_OEM_2 = Value(
        0xBF,
        "It can vary by keyboard. For the US ANSI keyboard, the Forward Slash and Question Mark key",
    )
    VK_OEM_3 = Value(
        0xC0,
        "It can vary by keyboard. For the US ANSI keyboard, the Grave Accent and Tilde key",
    )
    VK_GAMEPAD_A = Value(0xC3, "Gamepad A button")
    VK_GAMEPAD_B = Value(0xC4, "Gamepad B button")
    VK_GAMEPAD_X = Value(0xC5, "Gamepad X button")
    VK_GAMEPAD_Y = Value(0xC6, "Gamepad Y button")
    VK_GAMEPAD_RIGHT_SHOULDER = Value(0xC7, "Gamepad Right Shoulder button")
    VK_GAMEPAD_LEFT_SHOULDER = Value(0xC8, "Gamepad Left Shoulder button")
    VK_GAMEPAD_LEFT_TRIGGER = Value(0xC9, "Gamepad Left Trigger button")
    VK_GAMEPAD_RIGHT_TRIGGER = Value(0xCA, "Gamepad Right Trigger button")
    VK_GAMEPAD_DPAD_UP = Value(0xCB, "Gamepad D-pad Up button")
    VK_GAMEPAD_DPAD_DOWN = Value(0xCC, "Gamepad D-pad Down button")
    VK_GAMEPAD_DPAD_LEFT = Value(0xCD, "Gamepad D-pad Left button")
    VK_GAMEPAD_DPAD_RIGHT = Value(0xCE, "Gamepad D-pad Right button")
    VK_GAMEPAD_MENU = Value(0xCF, "Gamepad Menu/Start button")
    VK_GAMEPAD_VIEW = Value(0xD0, "Gamepad View/Back button")
    VK_GAMEPAD_LEFT_THUMBSTICK_BUTTON = Value(0xD1, "Gamepad Left Thumbstick button")
    VK_GAMEPAD_RIGHT_THUMBSTICK_BUTTON = Value(0xD2, "Gamepad Right Thumbstick button")
    VK_GAMEPAD_LEFT_THUMBSTICK_UP = Value(0xD3, "Gamepad Left Thumbstick up")
    VK_GAMEPAD_LEFT_THUMBSTICK_DOWN = Value(0xD4, "Gamepad Left Thumbstick down")
    VK_GAMEPAD_LEFT_THUMBSTICK_RIGHT = Value(0xD5, "Gamepad Left Thumbstick right")
    VK_GAMEPAD_LEFT_THUMBSTICK_LEFT = Value(0xD6, "Gamepad Left Thumbstick left")
    VK_GAMEPAD_RIGHT_THUMBSTICK_UP = Value(0xD7, "Gamepad Right Thumbstick up")
    VK_GAMEPAD_RIGHT_THUMBSTICK_DOWN = Value(0xD8, "Gamepad Right Thumbstick down")
    VK_GAMEPAD_RIGHT_THUMBSTICK_RIGHT = Value(0xD9, "Gamepad Right Thumbstick right")
    VK_GAMEPAD_RIGHT_THUMBSTICK_LEFT = Value(0xDA, "Gamepad Right Thumbstick left")
    VK_OEM_4 = Value(
        0xDB,
        "It can vary by keyboard. For the US ANSI keyboard, the Left Brace key",
    )
    VK_OEM_5 = Value(
        0xDC,
        "It can vary by keyboard. For the US ANSI keyboard, the Backslash and Pipe key",
    )
    VK_OEM_6 = Value(
        0xDD,
        "It can vary by keyboard. For the US ANSI keyboard, the Right Brace key",
    )
    VK_OEM_7 = Value(
        0xDE,
        "It can vary by keyboard. For the US ANSI keyboard, the Apostrophe and Double Quotation Mark key",
    )
    VK_OEM_8 = Value(
        0xDF,
        "It can vary by keyboard. For the Canadian CSA keyboard, the Right Ctrl key",
    )
    VK_OEM_102 = Value(
        0xE2,
        "It can vary by keyboard. For the European ISO keyboard, the Backslash and Pipe key",
    )
    VK_PROCESSKEY = Value(0xE5, "IME PROCESS key")
    VK_PACKET = Value(
        0xE7,
        'Used to pass Unicode characters as if they were keystrokes. The VK_PACKET key is the low word of a 32-bit Virtual Key value used for non-keyboard input methods. For mor"e information, see Remark in" [KEYBDINPUT]Value(/en-us/windows/win32/api/winuser/ns-winuser-keybdinput), [SendInput]Value(/en-us/windows/win32/api/winuser/nf-winuser-sendinput), [WM_KEYDOW"N]Value(wm-keydown), and [WM_KEYUP]Value(wm"-keyup)',
    )
    VK_ATTN = Value(0xF6, "Attn key")
    VK_CRSEL = Value(0xF7, "CrSel key")
    VK_EXSEL = Value(0xF8, "ExSel key")
    VK_EREOF = Value(0xF9, "Erase EOF key")
    VK_PLAY = Value(0xFA, "Play key")
    VK_ZOOM = Value(0xFB, "Zoom key")
    VK_NONAME = Value(0xFC, "Reserved")
    VK_PA1 = Value(0xFD, "PA1 key")
    VK_OEM_CLEAR = Value(0xFE, "Clear key")

    def tap(self, hwnd: wintypes.HWND | int, /) -> None:
        """点击 key"""
        self.Msg(hwnd, [self]).tap()

    class Msg(contextlib.AbstractContextManager):
        def __init__(
            self,
            hwnd: wintypes.HWND | int,
            keys: Iterable[Win_virtual_key | int] = (),
            /,
            api: Literal["Send", "Post"] = "Post",
            force_focus: bool = True,
        ) -> None:
            self.hwnd = hwnd
            self.keys = keys
            self.api = api
            self.force_focus = force_focus
            """focus 相关纯 AI 写的"""

            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32  # 附加线程需要

            # 焦点恢复用
            self._original_focus = None
            self._thread_attached = False

        def _force_focus(self) -> None:
            """AI"""
            cur_thread = self._kernel32.GetCurrentThreadId()

            # 用 byref 传递一个 wintypes.DWORD 来接收进程 ID
            process_id = wintypes.DWORD()
            target_thread = self._user32.GetWindowThreadProcessId(
                self.hwnd, ctypes.byref(process_id)
            )
            if target_thread == 0:
                raise OSError("GetWindowThreadProcessId failed")

            if cur_thread != target_thread:
                if not self._user32.AttachThreadInput(cur_thread, target_thread, True):
                    raise OSError("AttachThreadInput failed")
                self._thread_attached = True

            self._original_focus = self._user32.GetFocus()
            self._user32.SetFocus(self.hwnd)

        def _restore_focus(self) -> None:
            """AI"""
            if self._original_focus:
                self._user32.SetFocus(self._original_focus)

            if self._thread_attached:
                cur_thread = self._kernel32.GetCurrentThreadId()
                process_id = wintypes.DWORD()
                target_thread = self._user32.GetWindowThreadProcessId(
                    self.hwnd, ctypes.byref(process_id)
                )
                # target_thread 为 0 时可以不处理（窗口可能已不存在）
                if target_thread != 0:
                    self._user32.AttachThreadInput(cur_thread, target_thread, False)
                self._thread_attached = False

        @override
        def __enter__(self) -> Self:
            """进入 with 时按下键"""
            self.down()
            return self

        @override
        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: TracebackType | None,
        ) -> bool | None:
            """退出 with 时抬起键"""
            self.up()
            return None

        class Post_msg_msg(enum.Enum):
            WM_CLOSE = 0x0010  # 请求关闭窗口
            WM_KEYDOWN = 0x0100  # 按键按下
            WM_KEYUP = 0x0101  # 按键释放
            WM_CHAR = 0x0102  # 字符输入
            WM_MOUSEMOVE = 0x0200  # 鼠标移动
            WM_LBUTTONDOWN = 0x0201  # 左键按下
            WM_LBUTTONUP = 0x0202  # 左键释放
            WM_RBUTTONDOWN = 0x0204  # 右键按下
            WM_RBUTTONUP = 0x0205  # 右键释放
            WM_MOUSEWHEEL = 0x020A  # 滚轮

        def _make_key_lparam(
            self,
            vkey: int,
            is_keyup: bool,
            repeat: int = 1,
        ) -> int:
            """
            构造键盘消息的 lParam，自动获取真实扫描码并判断扩展键。

            Parameters
            ----------
            vkey : int
                虚拟键码 (VK_*)。用于查表得到物理扫描码，
                并决定该键是否为扩展键。
            is_keyup : bool
                True 表示 WM_KEYUP，False 表示 WM_KEYDOWN。
            repeat : int
                重复次数，绝大部分情况为 1。

            Returns
            -------
            int
                32 位 lParam 值。

            """
            MAPVK_VK_TO_VSC = 0
            # 获取操作系统记录的物理扫描码（部分键可能返回 0，但通常安全）
            scan_code = ctypes.windll.user32.MapVirtualKeyW(vkey, MAPVK_VK_TO_VSC)

            # 常见扩展键虚拟键码集合
            # 这些键必须设置 lParam 第 24 位，否则会被误认为普通键/左修饰键
            EXTENDED_KEYS = {
                0x2D,  # VK_INSERT
                0x2E,  # VK_DELETE
                0x21,  # VK_PRIOR  (Page Up)
                0x22,  # VK_NEXT   (Page Down)
                0x23,  # VK_END
                0x24,  # VK_HOME
                0x25,  # VK_LEFT
                0x26,  # VK_UP
                0x27,  # VK_RIGHT
                0x28,  # VK_DOWN
                0x6F,  # VK_DIVIDE (小键盘 /)
                0xA3,  # VK_RCONTROL
                0xA5,  # VK_RMENU   (右 Alt)
                0x5B,  # VK_LWIN
                0x5C,  # VK_RWIN
                0x5D,  # VK_APPS
                # 以下媒体键在多数键盘上也属于扩展键
                0xAD,  # VK_VOLUME_MUTE
                0xAE,  # VK_VOLUME_DOWN
                0xAF,  # VK_VOLUME_UP
                0xB0,  # VK_MEDIA_NEXT_TRACK
                0xB1,  # VK_MEDIA_PREV_TRACK
                0xB2,  # VK_MEDIA_STOP
                0xB3,  # VK_MEDIA_PLAY_PAUSE
                0xA6,  # VK_BROWSER_BACK
                0xA7,  # VK_BROWSER_FORWARD
                0xA8,  # VK_BROWSER_REFRESH
                0xA9,  # VK_BROWSER_STOP
                0xAA,  # VK_BROWSER_SEARCH
                0xAB,  # VK_BROWSER_FAVORITES
                0xAC,  # VK_BROWSER_HOME
            }

            lparam = repeat & 0xFFFF  # bit 0–15
            lparam |= (scan_code & 0xFF) << 16  # bit 16–23
            if vkey in EXTENDED_KEYS:
                lparam |= 1 << 24  # bit 24: extended key
            if is_keyup:
                lparam |= 1 << 30  # bit 30: previous key state (up)
                lparam |= 1 << 31  # bit 31: transition state (up)

            return lparam

        def _send_msg(
            self,
            msg: Post_msg_msg,
            wparam: int,
            lparam: int,
        ) -> bool:
            """
            调用 winapi 发送按键消息

            :param msg: 消息 ID
            :param wparam: 消息附加参数1 - vk code
            :param lparam: 消息附加参数2 - 使用 make_key_lparam 构造
            """
            return (
                self._user32.PostMessageW
                if self.api == "Post"
                else self._user32.SendMessageW
            )(self.hwnd, msg.value, wparam, lparam)

        def down(self, keys: Iterable[Win_virtual_key | int] | None = None) -> None:
            """按下 key"""
            if self.force_focus:
                self._force_focus()
            for vk_code in (
                (key if isinstance(key, int) else key.value.code)
                for key in (self.keys if keys is None else keys)
            ):
                self._send_msg(
                    self.Post_msg_msg.WM_KEYDOWN,
                    vk_code,
                    self._make_key_lparam(vk_code, False),
                )

        def up(self, keys: Iterable[Win_virtual_key | int] | None = None) -> None:
            """抬起 key"""
            for vk_code in (
                (key if isinstance(key, int) else key.value.code)
                for key in (self.keys if keys is None else keys)
            ):
                self._send_msg(
                    self.Post_msg_msg.WM_KEYUP,
                    vk_code,
                    self._make_key_lparam(vk_code, True),
                )
            if self.force_focus:
                self._restore_focus()

        def tap(self, keys: Iterable[Win_virtual_key | int] | None = None) -> None:
            """点击 key"""
            self.down(keys)
            self.up(keys)

        def click(
            self,
            x: int,
            y: int,
            /,
            button: Literal["left", "right"] = "left",
        ) -> None:
            """
            **AI** (对异环窗口不起作用，暂无实际作用) 向目标窗口的客户区相对坐标 (x, y) 发送一次鼠标点击消息。

            Parameters
            ----------
            x : int
                客户区 X 坐标（像素），范围 0~65535。
            y : int
                客户区 Y 坐标（像素），范围 0~65535。
            button : str, optional
                "left" 发送左键点击，"right" 发送右键点击，默认 "left"。

            Notes
            -----
            - 此方法直接构造并投递窗口消息，**不依赖键盘焦点**，因此不会调用
            `_force_focus()` 或 `_restore_focus()`。
            - 若目标窗口正在被其他线程锁定或处于挂起状态，消息可能被丢弃；
            对于高强度自动化场景，建议结合 `SendInput` 或 UI Automation 使用。

            """
            # 客户区坐标打包为 lParam（低 X 高 Y）
            lparam = (y & 0xFFFF) << 16 | (x & 0xFFFF)

            # 根据按钮类型确定对应的消息和 wParam
            if button == "left":
                down_msg = self.Post_msg_msg.WM_LBUTTONDOWN
                up_msg = self.Post_msg_msg.WM_LBUTTONUP
                wparam_down = 0x0001  # MK_LBUTTON
            else:
                down_msg = self.Post_msg_msg.WM_RBUTTONDOWN
                up_msg = self.Post_msg_msg.WM_RBUTTONUP
                wparam_down = 0x0002  # MK_RBUTTON

            # 发送按下与抬起，完成一次完整点击
            self._send_msg(down_msg, wparam_down, lparam)
            self._send_msg(up_msg, 0, lparam)

        def wheel(self, direction: Literal["up", "down"], amount: int = 1, /) -> None:
            """
            **AI** 向 self.hwnd 指定的窗口发送 WM_MOUSEWHEEL 消息以模拟滚动。

            :param direction: 'up' 表示向上 (向前) 滚动，'down' 表示向下 (向后) 滚动。
            :param amount: 滚动格数，默认为 1。每格对应 WHEEL_DELTA (120)。
            """
            # 1. 构造 wParam
            #    高16位：滚轮增量。向上滚动为正，向下滚动为负。
            #    低16位：修饰键状态。当前我们不使用任何修饰键，填0。
            delta = amount * 120
            if direction == "down":
                delta = -delta  # 向下滚动，传递负值
            wparam = delta << 16  # 将增量左移16位，放到高16位[reference:8]

            # 2. 构造 lParam
            #    lParam 包含鼠标光标的屏幕坐标。低16位为X，高16位为Y。
            #    这里我们简单地传递 0, 0 作为坐标。
            lparam = 0

            # 3. 使用 SendMessage 或 PostMessage 发送消息
            if self.force_focus:
                self._force_focus()
            self._send_msg(self.Post_msg_msg.WM_MOUSEWHEEL, wparam, lparam)
            if self.force_focus:
                self._restore_focus()
