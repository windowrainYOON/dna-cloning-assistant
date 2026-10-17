"""A native macOS window around the local UI.

The app's screen is HTML, but it should open as its own window rather than a
browser tab. macOS already ships the renderer — WebKit — so the window is a
plain Cocoa `NSWindow` holding a `WKWebView`, reached through PyObjC. That is
the smallest dependency that still gives a real app window: nothing is
bundled except the PyObjC bridge, and no browser is involved.

`open_window` returns only when the window closes. If PyObjC is missing (any
non-macOS machine, or a checkout without the build extras) it returns False
and the caller falls back to the browser, so `python3 run.py` keeps working
everywhere with no install.
"""

from __future__ import annotations

import sys

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 860
MIN_WIDTH = 900
MIN_HEIGHT = 600


def available() -> bool:
    """True when a native window can be opened on this machine."""
    if sys.platform != "darwin":
        return False
    try:
        import AppKit  # noqa: F401
        import WebKit  # noqa: F401
    except Exception:
        return False
    return True


def open_window(url: str, title: str = "DNA Cloning Assistant") -> bool:
    """Show the UI in a native window; return False if that is not possible.

    Must be called on the main thread — AppKit refuses to run anywhere else —
    so the HTTP server runs in a background thread while this owns the process.
    """
    if not available():
        return False
    try:
        import AppKit
        import WebKit
        from Foundation import NSURL, NSURLRequest, NSObject
    except Exception:
        return False

    try:
        class AppDelegate(NSObject):
            def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
                return True

        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
        delegate = AppDelegate.alloc().init()
        app.setDelegate_(delegate)

        frame = AppKit.NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        style = (AppKit.NSWindowStyleMaskTitled
                 | AppKit.NSWindowStyleMaskClosable
                 | AppKit.NSWindowStyleMaskMiniaturizable
                 | AppKit.NSWindowStyleMaskResizable)
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False)
        window.setTitle_(title)
        window.setMinSize_(AppKit.NSMakeSize(MIN_WIDTH, MIN_HEIGHT))
        window.center()

        config = WebKit.WKWebViewConfiguration.alloc().init()
        web = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, config)
        web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        window.setContentView_(web)
        web.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

        window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)
        app.run()
        return True
    except Exception as exc:  # a broken bridge should not take the app down
        print(f"네이티브 창을 열지 못했습니다 ({exc}); 브라우저로 엽니다.", file=sys.stderr)
        return False
