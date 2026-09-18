#!/usr/bin/env python3
"""uidrv —— 跨平台 GUI 驱动（合成输入）。

同一套命令，两个后端：
  macOS   : CoreGraphics (CGEventPost)      —— 需「辅助功能」权限
  Windows : SendInput / mouse_event          —— 需与目标程序同权限级别

用法:
    python uidrv.py <command> [args]

命令:
    info                      显示平台、屏幕尺寸、缩放比例、权限自检
    activate NAME             把目标应用/窗口切到前台（NAME 为应用名或窗口标题片段）
    pos                       打印当前鼠标位置
    move X Y                  移动鼠标
    click X Y [--double]      左键单击
    rclick X Y                右键单击
    scroll X Y DY             滚轮（DY 为负 = 向下）
    key NAME [--cmd]          按键；--cmd = Cmd(mac) / Ctrl(win)
                              也支持直接传键码：key 33 --cmd
    paste "文本"               走剪贴板粘贴（中文/长文本最稳）
    type "文本"                逐字符合成（短文本；Windows 上不保证支持中文）
    shot PATH                 截屏保存

坐标约定（重要）:
    macOS   : 传「逻辑点」。截图是 Retina 物理像素，逻辑点 = 像素 ÷ 2
    Windows : 传「物理像素」（本脚本启动时已声明 DPI 感知，故与截图 1:1）
    locate.py 输出的坐标已按此约定换算好，直接用即可。
"""
import ctypes
import os
import subprocess
import sys
import time

IS_MAC = sys.platform == 'darwin'
IS_WIN = os.name == 'nt'

# ----------------------------------------------------------------------------
# 键名 → 各平台键码
# ----------------------------------------------------------------------------
MAC_KEY = {
    'return': 36, 'enter': 36, 'tab': 48, 'esc': 53, 'escape': 53, 'space': 49,
    'delete': 51, 'backspace': 51, 'up': 126, 'down': 125, 'left': 123, 'right': 124,
    'home': 115, 'end': 119, 'pageup': 116, 'pagedown': 121,
    'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7, 'c': 8, 'v': 9,
    'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15, 'y': 16, 't': 17,
    '1': 18, '2': 19, '3': 20, '4': 21, '6': 22, '5': 23, '=': 24, '9': 25,
    '7': 26, '-': 27, '8': 28, '0': 29, ']': 30, 'o': 31, 'u': 32, '[': 33,
    'i': 34, 'p': 35, 'l': 37, 'j': 38, 'k': 40, ',': 43, '/': 44, 'n': 45,
    'm': 46, '.': 47,
}

WIN_KEY = {
    'return': 0x0D, 'enter': 0x0D, 'tab': 0x09, 'esc': 0x1B, 'escape': 0x1B,
    'space': 0x20, 'delete': 0x08, 'backspace': 0x08,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    '[': 0xDB, ']': 0xDD, '-': 0xBD, '=': 0xBB, ',': 0xBC, '.': 0xBE, '/': 0xBF,
}
for _c in 'abcdefghijklmnopqrstuvwxyz':
    WIN_KEY[_c] = ord(_c.upper())
for _d in '0123456789':
    WIN_KEY[_d] = ord(_d)

KEYMAP = MAC_KEY if IS_MAC else WIN_KEY

# ----------------------------------------------------------------------------
# macOS 后端
# ----------------------------------------------------------------------------
if IS_MAC:
    _CG = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    _AS = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')

    class _CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    _CG.CGEventCreate.restype = ctypes.c_void_p
    _CG.CGEventGetLocation.restype = _CGPoint
    _CG.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    _CG.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, _CGPoint, ctypes.c_uint32]
    _CG.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
    _CG.CGEventCreateScrollWheelEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32]
    _CG.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    _CG.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    _CG.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    _CG.CGEventKeyboardSetUnicodeString.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
    _CG.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

    HID = 0x0
    MOVE, LDOWN, LUP, RDOWN, RUP = 5, 1, 2, 3, 4
    CMD_FLAG = 0x100000

    def _pos():
        p = _CG.CGEventGetLocation(_CG.CGEventCreate(None))
        return p.x, p.y

    def _move(x, y):
        _CG.CGEventPost(HID, _CG.CGEventCreateMouseEvent(None, MOVE, _CGPoint(x, y), 0))

    def _click(x, y, double=False, right=False):
        _move(x, y); time.sleep(0.15)
        down, up = (RDOWN, RUP) if right else (LDOWN, LUP)
        for _ in range(2 if double else 1):
            _CG.CGEventPost(HID, _CG.CGEventCreateMouseEvent(None, down, _CGPoint(x, y), 0))
            time.sleep(0.05)
            _CG.CGEventPost(HID, _CG.CGEventCreateMouseEvent(None, up, _CGPoint(x, y), 0))
            time.sleep(0.12)

    def _scroll(x, y, dy):
        _move(x, y); time.sleep(0.1)
        _CG.CGEventPost(HID, _CG.CGEventCreateScrollWheelEvent(None, 0, 1, int(dy)))
        time.sleep(0.15)

    def _key(name, cmd=False):
        kc = KEYMAP.get(str(name).lower())
        if kc is None and str(name).isdigit():
            kc = int(name)
        if kc is None:
            raise SystemExit(f'unknown key: {name}')
        flags = CMD_FLAG if cmd else 0
        d = _CG.CGEventCreateKeyboardEvent(None, kc, True)
        u = _CG.CGEventCreateKeyboardEvent(None, kc, False)
        if flags:
            _CG.CGEventSetFlags(d, flags); _CG.CGEventSetFlags(u, flags)
        _CG.CGEventPost(HID, d); time.sleep(0.03); _CG.CGEventPost(HID, u); time.sleep(0.1)

    def _type(text):
        for ch in text:
            buf = ctypes.create_string_buffer(ch.encode('utf-16-le'))
            d = _CG.CGEventCreateKeyboardEvent(None, 0, True)
            _CG.CGEventKeyboardSetUnicodeString(d, len(ch), buf)
            _CG.CGEventPost(HID, d); time.sleep(0.02)
            u = _CG.CGEventCreateKeyboardEvent(None, 0, False)
            _CG.CGEventPost(HID, u); time.sleep(0.02)
        time.sleep(0.15)

    def _paste(text):
        subprocess.run('pbcopy', input=text.encode('utf-8'), check=True)
        time.sleep(0.2); _key('v', cmd=True)

    def _activate(name):
        subprocess.run(['open', '-a', name], check=False); time.sleep(0.6)

    def _shot(path):
        subprocess.run(['screencapture', '-x', path], check=True)

    def _info():
        trusted = bool(_AS.AXIsProcessTrusted())
        print(f'platform: macOS')
        print(f'accessibility_trusted: {trusted}'
              + ('' if trusted else '   ← 需在「系统设置→隐私与安全性→辅助功能」加入调用方 App'))
        try:
            out = subprocess.run(['system_profiler', 'SPDisplaysDataType'],
                                 capture_output=True, text=True).stdout
            for line in out.splitlines():
                if 'Resolution' in line:
                    print('display:' + line.split(':', 1)[1].strip())
        except Exception:
            pass
        print('coord_space: logical points (截图物理像素 ÷ 2)')

# ----------------------------------------------------------------------------
# Windows 后端
# ----------------------------------------------------------------------------
elif IS_WIN:
    from ctypes import wintypes
    _u32 = ctypes.windll.user32

    # 声明 DPI 感知，否则 125%/150% 缩放下坐标会系统性偏移
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
    except Exception:
        try:
            _u32.SetProcessDPIAware()
        except Exception:
            pass

    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
    MOUSEEVENTF_WHEEL = 0x0800
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL = 0x11

    class _POINT(ctypes.Structure):
        _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

    def _pos():
        p = _POINT(); _u32.GetCursorPos(ctypes.byref(p)); return p.x, p.y

    def _move(x, y):
        _u32.SetCursorPos(int(x), int(y)); time.sleep(0.05)

    def _click(x, y, double=False, right=False):
        _move(x, y); time.sleep(0.15)
        down, up = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if right \
            else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
        for _ in range(2 if double else 1):
            _u32.mouse_event(down, 0, 0, 0, 0); time.sleep(0.05)
            _u32.mouse_event(up, 0, 0, 0, 0); time.sleep(0.12)

    def _scroll(x, y, dy):
        _move(x, y); time.sleep(0.1)
        # Windows: 正数向上，WHEEL_DELTA=120/格
        _u32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(dy) * 120, 0)
        time.sleep(0.15)

    def _key(name, cmd=False):
        vk = KEYMAP.get(str(name).lower())
        if vk is None and str(name).isdigit():
            vk = int(name)
        if vk is None:
            raise SystemExit(f'unknown key: {name}')
        if cmd:
            _u32.keybd_event(VK_CONTROL, 0, 0, 0); time.sleep(0.03)
        _u32.keybd_event(vk, 0, 0, 0); time.sleep(0.03)
        _u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        if cmd:
            time.sleep(0.03); _u32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)

    def _paste(text):
        # 剪贴板桥接需要一个临时文件（中文不能逐字符合成）。
        # 用完必须删掉——否则粘贴过的内容会留在临时目录里。
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            ps = (f"Set-Clipboard -Value ([IO.File]::ReadAllText('{tmp}',"
                  f"[Text.Encoding]::UTF8))")
            subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, check=False)
            time.sleep(0.3)
            _key('v', cmd=True)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _type(text):
        # Windows 的逐字符合成对中文不可靠，统一退化为剪贴板粘贴
        _paste(text)

    def _activate(name):
        hwnd = _u32.FindWindowW(None, name)
        if not hwnd:
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _cb(h, _):
                n = ctypes.create_unicode_buffer(512)
                _u32.GetWindowTextW(h, n, 512)
                if name.lower() in n.value.lower() and _u32.IsWindowVisible(h):
                    found.append(h)
                    return False
                return True

            _u32.EnumWindows(_cb, 0)
            hwnd = found[0] if found else 0
            if found and len(found) > 1:
                print(f'warning: {len(found)} windows matched, using the first', file=sys.stderr)
            if not found:
                print(f'window not found: {name}', file=sys.stderr)
                return
        _u32.SetForegroundWindow(hwnd); time.sleep(0.5)

    def _shot(path):
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=False).save(path)

    def _info():
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        w = _u32.GetSystemMetrics(0); h = _u32.GetSystemMetrics(1)
        print('platform: windows')
        print(f'primary_screen: {w}x{h} (physical px, DPI-aware)')
        print('coord_space: physical pixels (与截图 1:1)')
        try:
            import PIL  # noqa: F401
            print('pillow: ok')
        except ImportError:
            print('pillow: MISSING  ← pip install Pillow（截屏与定位都需要）')

else:
    raise SystemExit('unsupported platform: only macOS / Windows are supported')


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd, a = sys.argv[1], sys.argv[2:]

    if cmd == 'info':
        _info()
    elif cmd == 'activate':
        _activate(a[0])
    elif cmd == 'pos':
        print(_pos())
    elif cmd == 'move':
        _move(float(a[0]), float(a[1]))
    elif cmd == 'click':
        _click(float(a[0]), float(a[1]), double='--double' in a)
    elif cmd == 'rclick':
        _click(float(a[0]), float(a[1]), right=True)
    elif cmd == 'scroll':
        _scroll(float(a[0]), float(a[1]), float(a[2]))
    elif cmd == 'key':
        _key(a[0], cmd='--cmd' in a)
    elif cmd == 'paste':
        _paste(a[0])
    elif cmd == 'type':
        _type(a[0])
    elif cmd == 'shot':
        _shot(a[0]); print('saved', a[0])
    else:
        print('unknown command:', cmd)


if __name__ == '__main__':
    main()
