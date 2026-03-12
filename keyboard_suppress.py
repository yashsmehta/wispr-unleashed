"""Suppress programmatic keyboard input (e.g. Wispr Flow paste) on macOS.

Uses a CGEventTap to intercept injected keyboard events while letting
physical keyboard input pass through. Requires accessibility permission
for the terminal app.
"""

import threading

try:
    from Quartz import (
        CGEventTapCreate, CGEventTapEnable, CGEventMaskBit,
        CGEventGetIntegerValueField,
        CFMachPortCreateRunLoopSource, CFMachPortInvalidate,
        CFRunLoopGetCurrent, CFRunLoopAddSource, CFRunLoopRun, CFRunLoopStop,
        kCFRunLoopCommonModes,
        kCGSessionEventTap, kCGHeadInsertEventTap,
        kCGEventKeyDown, kCGEventKeyUp,
    )
    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False

# CGEvent field / source state constants
_SOURCE_STATE_FIELD = 45   # kCGEventSourceStateID
_PHYSICAL_KEYBOARD = 1     # kCGEventSourceStateHIDSystemState

_tap = None
_runloop = None
_thread = None


def _callback(proxy, event_type, event, refcon):
    """Block keyboard events that aren't from the physical keyboard."""
    source = CGEventGetIntegerValueField(event, _SOURCE_STATE_FIELD)
    if source != _PHYSICAL_KEYBOARD:
        return None   # suppress injected event
    return event      # pass physical keyboard through


def available() -> bool:
    """Check if keyboard suppression is possible (Quartz + accessibility)."""
    if not _HAS_QUARTZ:
        return False
    # AXIsProcessTrusted checks accessibility permission without side effects
    try:
        from ApplicationServices import AXIsProcessTrusted
        return AXIsProcessTrusted()
    except ImportError:
        # Fallback: try creating a tap to test
        mask = CGEventMaskBit(kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGSessionEventTap, kCGHeadInsertEventTap, 0, mask, _callback, None,
        )
        if tap is None:
            return False
        CFMachPortInvalidate(tap)
        return True


def start():
    """Start suppressing injected keyboard events. Returns True if successful."""
    global _tap, _runloop, _thread

    if not _HAS_QUARTZ:
        return False

    if _tap is not None:
        return True

    mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp)
    _tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        0,
        mask,
        _callback,
        None,
    )

    if _tap is None:
        return False

    source = CFMachPortCreateRunLoopSource(None, _tap, 0)

    def run():
        global _runloop
        _runloop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(_runloop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(_tap, True)
        CFRunLoopRun()

    _thread = threading.Thread(target=run, daemon=True)
    _thread.start()
    return True


def stop():
    """Stop suppressing keyboard events."""
    global _tap, _runloop, _thread

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

    if thread is not None:
        thread.join(timeout=1.0)
