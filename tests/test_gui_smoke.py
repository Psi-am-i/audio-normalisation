#!/usr/bin/env python3
"""
GUI smoke test — no display interaction, but exercises the real widget code:
the FORMAT/BITRATE pull-up menus, bitrate gating for lossless formats, About
rendering, and the press/release click dispatch (including disabled buttons).

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


def pick_from_menu(app, value):
    """Press the pull-up menu row holding `value` (menu must be open)."""
    row = next(r for r in app._popup["rows"] if r["value"] == value)
    app._canvas_press(FakeEvent((row["x0"] + row["x1"]) // 2,
                                (row["y0"] + row["y1"]) // 2))


def main():
    root = tk.Tk()
    patchlevel = root.tk.call('info', 'patchlevel')
    app = gui.NormalizerGUI(root)
    root.update()

    # FORMAT pull-up menu lists the whole registry; picking a row selects it
    # and the bitrate button gates correctly for lossless/lossy
    seen = []
    for fmt in normalizer.OUTPUT_FORMATS:
        app.open_format_menu()
        assert app._popup is not None, "format menu did not open"
        assert [r["value"] for r in app._popup["rows"]] == \
            list(normalizer.OUTPUT_FORMATS), "menu rows != format registry"
        pick_from_menu(app, fmt)
        assert app._popup is None, "menu should close after a pick"
        seen.append((app.output_format, app.buttons["rate"]["enabled"]))
    assert seen == [('aiff', False), ('flac', False), ('wav', False),
                    ('mp3', True), ('aac', True)], seen

    # Pressing outside the menu closes it without changing the selection
    app.open_format_menu()
    app._canvas_press(FakeEvent(1, 1))
    assert app._popup is None and app.output_format == 'aac'

    # BITRATE pull-up menu (needs a lossy format selected)
    app.open_bitrate_menu()
    assert [r["value"] for r in app._popup["rows"]] == list(normalizer.BITRATES)
    pick_from_menu(app, 192)
    assert app.bitrate == 192, app.bitrate
    assert app.buttons["rate"]["label"] == "192k"

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

    app.open_format_menu()
    pick_from_menu(app, 'aiff')            # lossless -> rate disabled
    assert app.output_format == 'aiff'
    app._canvas_press(centre(app, "rate"))
    assert app._armed is None, "disabled button must not arm"
    assert app._popup is None, "disabled button must not open its menu"

    root.destroy()
    print(f"GUI smoke test: ALL OK (Python {sys.version.split()[0]}, "
          f"Tk {patchlevel})")


if __name__ == '__main__':
    main()
