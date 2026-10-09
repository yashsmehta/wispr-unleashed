"""Require a double Esc press to cancel Wispr Flow while a session is running.

Wispr Flow cancels a hands-free recording on a single Esc. While recording,
this CGEventTap swallows the first physical Esc and re-posts it only to the
frontmost app, so that app still gets its Esc but Wispr never sees it; a
second Esc within DOUBLE_PRESS_WINDOW seconds is passed through (Wispr
cancels) and `on_cancel` fires so the session can end. Requires accessibility
permission for the terminal app.
"""

import threading
import time

try:
    from Quartz import (
        CGEventTapCreate,
        CGEventTapEnable,
        CGEventMaskBit,
        CGEventCreateCopy,
        CGEventGetIntegerValueField,
        CGEventPostToPid,
        CFMachPortCreateRunLoopSource,
        CFMachPortInvalidate,
        CFRunLoopGetCurrent,
        CFRunLoopAddSource,
        CFRunLoopRun,
        CFRunLoopStop,
        kCFRunLoopCommonModes,
        kCGHIDEventTap,
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
    )

    from AppKit import NSWorkspace

    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False

DOUBLE_PRESS_WINDOW = 2.0  # seconds
WISPR_BUNDLE_ID = "com.electron.wispr-flow"

_ESC_KEYCODE = 53
_KEYCODE_FIELD = 9  # kCGKeyboardEventKeycode
_AUTOREPEAT_FIELD = 8  # kCGKeyboardEventAutorepeat
_SOURCE_STATE_FIELD = 45  # kCGEventSourceStateID
_PHYSICAL_KEYBOARD = 1  # kCGEventSourceStateHIDSystemState

_tap = None
_runloop = None
_thread = None
_on_first_press = None
_on_cancel = None
_armed_at = None  # monotonic time of the swallowed first press
_passing = False  # True while the current Esc press is being passed through
_forward_pid = None  # frontmost app receiving the swallowed press, if any


def _frontmost_pid() -> int | None:
    """PID of the frontmost app, or None if it's Wispr itself (or unknown)."""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None or app.bundleIdentifier() == WISPR_BUNDLE_ID:
        return None
    return app.processIdentifier()


def _callback(_proxy, event_type, event, _refcon):
    """Swallow a lone Esc; let a second Esc within the window through."""
    global _armed_at, _passing, _forward_pid

    if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
        if _tap is not None:
            CGEventTapEnable(_tap, True)
        return event

    if CGEventGetIntegerValueField(event, _KEYCODE_FIELD) != _ESC_KEYCODE:
        return event
    if CGEventGetIntegerValueField(event, _SOURCE_STATE_FIELD) != _PHYSICAL_KEYBOARD:
        return event

    if event_type == kCGEventKeyDown and not CGEventGetIntegerValueField(
        event, _AUTOREPEAT_FIELD
    ):
        now = time.monotonic()
        if _armed_at is not None and now - _armed_at <= DOUBLE_PRESS_WINDOW:
            _armed_at = None
            _passing = True
            if _on_cancel:
                _on_cancel()
        else:
            _armed_at = now
            _passing = False
            _forward_pid = _frontmost_pid()
            if _on_first_press:
                _on_first_press()

    # Key-up and auto-repeat follow the decision made on the initial key-down
    if _passing:
        return event
    if _forward_pid is not None:
        # Direct delivery bypasses global taps/monitors, so Wispr doesn't see it
        CGEventPostToPid(_forward_pid, CGEventCreateCopy(event))
    return None


def start(on_first_press=None, on_cancel=None) -> bool:
    """Start guarding Esc. Returns True if the tap was installed."""
    global _tap, _runloop, _thread, _on_first_press, _on_cancel, _armed_at, _passing, _forward_pid

    if not _HAS_QUARTZ:
        return False
    if _tap is not None:
        return True

    _on_first_press = on_first_press
    _on_cancel = on_cancel
    _armed_at = None
    _passing = False
    _forward_pid = None

    mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp)
    # Prefer the HID-level tap so we run before any other app's session tap
    for location in (kCGHIDEventTap, kCGSessionEventTap):
        _tap = CGEventTapCreate(
            location, kCGHeadInsertEventTap, 0, mask, _callback, None
        )
        if _tap is not None:
            break
    if _tap is None:
        return False

    source = CFMachPortCreateRunLoopSource(None, _tap, 0)
    ready = threading.Event()

    def run():
        global _runloop
        _runloop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(_runloop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(_tap, True)
        ready.set()
        CFRunLoopRun()

    _thread = threading.Thread(target=run, daemon=True)
    _thread.start()
    ready.wait(timeout=1.0)
    return True


def stop():
    """Stop guarding Esc (single Esc reaches Wispr again)."""
    global _tap, _runloop, _thread, _on_first_press, _on_cancel

    if _tap is None:
        return

    CGEventTapEnable(_tap, False)
    CFMachPortInvalidate(_tap)
    if _runloop is not None:
        CFRunLoopStop(_runloop)

    thread = _thread
    _tap = None
    _runloop = None
    _thread = None
    _on_first_press = None
    _on_cancel = None

    if thread is not None:
        thread.join(timeout=1.0)
