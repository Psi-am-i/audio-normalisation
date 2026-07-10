#!/usr/bin/env python3
"""
GUI smoke test — no display interaction, but exercises the real widget code:
format/bitrate cycling, bitrate gating for lossless formats, About rendering,
and the press/release click dispatch (including the disabled-button case).

Needs a Python with tkinter and a display session (macOS: any GUI login).
Run:  python3 tests/test_gui_smoke.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk  # noqa: E402
import gui            # noqa: E402
import normalizer     # noqa: E402


class FakeEvent:
    def __init__(self, x, y):
        self.x, self.y = x, y


def centre(app, name):
    x0, y0, x1, y1 = app.buttons[name]["bounds"]
    return FakeEvent((x0 + x1) // 2, (y0 + y1) // 2)


def main():
    root = tk.Tk()
    patchlevel = root.tk.call('info', 'patchlevel')
    app = gui.NormalizerGUI(root)
    root.update()

    # Format cycling matches the registry, bitrate button gates correctly
    seen = []
    for _ in range(len(normalizer.OUTPUT_FORMATS)):
        app.toggle_format()
        seen.append((app.output_format, app.buttons["rate"]["enabled"]))
    assert seen == [('flac', False), ('wav', False), ('mp3', True),
                    ('aac', True), ('aiff', False)], seen

    # Bitrate cycling (needs a lossy format selected)
    for _ in range(3):
        app.toggle_format()   # aiff -> flac -> wav -> mp3
    assert app.output_format == 'mp3'
    rates = [app.bitrate]
    for _ in range(3):
        app.toggle_bitrate()
        rates.append(app.bitrate)
    assert rates == [320, 256, 192, 320], rates

    # About renders
    app.show_about()
    root.update()

    # Press/release on ABOUT fires; drag-away cancels; disabled button inert
    fired = []
    app.buttons["about"]["cmd"] = lambda: fired.append(1)
    e = centre(app, "about")
    app._canvas_press(e)
    app._canvas_release(e)
    assert fired == [1], "click did not fire"

    app._canvas_press(e)
    app._canvas_release(FakeEvent(1, 1))   # released off the button
    assert fired == [1], "drag-away should not fire"

    app.toggle_format()
    app.toggle_format()                    # mp3 -> aac -> aiff (rate disabled)
    assert app.output_format == 'aiff'
    app._canvas_press(centre(app, "rate"))
    assert app._armed is None, "disabled button must not arm"

    root.destroy()
    print(f"GUI smoke test: ALL OK (Python {sys.version.split()[0]}, "
          f"Tk {patchlevel})")


if __name__ == '__main__':
    main()
