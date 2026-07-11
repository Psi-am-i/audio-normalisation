#!/usr/bin/env python3
"""
Psi's DJnormalizerButInAgoodWay

A green-terminal-styled GUI front-end over the normalizer core. Folder pickers
instead of typed paths, a dark-green tinted background photo, and one bad DJ
joke per session, dropped when you least expect it.

The terminal text is drawn directly on the background canvas (transparent — the
photo shows through). Buttons have a subtly filled, clickable body with hover
and press feedback. Third front-end over normalizer.py — same engine as the
manual CLI and the autowatch daemon.
"""

import queue
import random
import sys
import threading
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

import normalizer

APP_TITLE = "Psi's DJnormalizerButInAgoodWay"
WIN_W, WIN_H = 900, 680

# Palette
GREEN = "#3bff6a"
BRIGHT = "#b6ffcb"
DIM_GREEN = "#2a9c4c"
FAIL_RED = "#ff5c57"
DARK = "#04120a"

BTN_FILL = "#0f2c1c"
BTN_FILL_HOVER = "#1c5334"
BTN_FILL_DISABLED = "#0a1a11"

# Cross-platform monospace: Menlo (macOS), Consolas (Windows), else generic.
if sys.platform == "darwin":
    MONO_FAMILY = "Menlo"
elif sys.platform.startswith("win"):
    MONO_FAMILY = "Consolas"
else:
    MONO_FAMILY = "DejaVu Sans Mono"

MONO = (MONO_FAMILY, 13)
MONO_TITLE = (MONO_FAMILY, 21, "bold")
MONO_STATUS = (MONO_FAMILY, 14, "bold")
# Button font is sized at runtime (see _build_ui): Tk's point size renders
# differently across platforms/Tk versions, so a fixed 12pt can overflow the
# button bodies on some machines.
BTN_FONT_MAX, BTN_FONT_MIN = 12, 9

POPUP_ROW_H = 30  # row height of the FORMAT/BITRATE pull-up menus

# Geometry (everything drawn on the canvas)
FRAME_X0, FRAME_X1 = 40, WIN_W - 40
STATUS_Y = 58
LOG_FRAME_TOP, LOG_FRAME_BOT = 78, WIN_H - 112
LOG_X, LOG_TOP = FRAME_X0 + 20, LOG_FRAME_TOP + 14
LOG_W = (FRAME_X1 - 20) - LOG_X
LOG_BOTTOM = LOG_FRAME_BOT - 12
LINE_GAP = 3

BTN_BAR_TOP, BTN_BAR_BOT = WIN_H - 98, WIN_H - 42
BTN_H = 38

DJ_JOKES = [
    "Why did the DJ get thrown out of the library? Way too many sick beats.",
    "I asked for something by The Doors. He opened the fridge for four minutes.",
    "My tracks were too quiet, so I had a word. Now they're proper -12 LUFS-teners.",
    "Why did the compressor dump the limiter? Couldn't handle the attack.",
    "Two speakers walk into a bar. Barman says 'sorry, we don't do gigs.'",
    "What do you call a DJ who normalizes to -12? Consistently employed.",
    "I told the crowd I'd normalize the vibe. They said 'mate, just -12 and chill.'",
    "Why did the AIFF look down on the MP3? Nothing to compress about.",
    "I lost my DJ job. Turns out 'reading the room' isn't optional.",
    "What's a DJ's least favourite veg? Beetroot. Too many drops.",
    "Why did the DJ bring a ladder to the club? To reach the high notes.",
    "Normalized my whole set so every track hits the same. Therapist calls it progress.",
    "The bassline knocked on the door. I didn't let it in — no headroom.",
    "Why don't DJs ever get locked out? They always carry the sickest keys.",
    # --- genres ---
    "I made a house track so deep the neighbours filed it under basement.",
    "My dubstep tune has trust issues — it drops everyone.",
    "Why did the trance track never get to the point? It kept building.",
    "I wrote a minimal techno tune, then removed the tune. Purists wept. I charged extra.",
    "Ambient producers never finish a set — they just fade out of the conversation.",
    "Drum & bass: 170 excellent reasons to go check your pulse.",
    "Acid house called. It's still 303-ing on about the good old days.",
    "Techno walks into a bar. And a kick. And a hat. And another kick. And another...",
    # --- gear ---
    "My 808 doesn't knock — it applies for planning permission.",
    "Told my synth to filter itself. Now it won't talk to me. Total cutoff.",
    "My modular rig is 90% patch cables and 10% regret.",
    "Sidechain: because even my kick drum needs a bit of personal space.",
    "I bought a noise gate. Now my hiss has a bedtime.",
    "The compressor told the mix 'you're a bit much.' The mix said 'you have no idea.'",
    "Why did the CDJ dump the turntable? Too much baggage and no needle for the drama.",
    # --- bands ---
    "Booked Kraftwerk. Very precise — left exactly on the beat, on the hour, via autobahn.",
    "Aphex Twin sent me a track. My speakers are still filing the paperwork.",
    "Deadmau5 turned up in the head. Bouncer said 'ears only past this point.'",
    "Hired Daft Punk's electrician. Rewired the booth and we all Got Lucky.",
    # --- for the geeks (yes, the binary decodes) ---
    "There are 10 types of DJs: those who count in binary, and those who don't.",
    "Even the bassline compiles: 01100010 01100001 01110011 01110011.",
    "My favourite BPM is 128 — a clean power of two. Even the CPU nods along.",
]

DJ_OUTRO = [
    "Set's levelled. Go forth and clear the low end.",
    "All normalized. If it still sounds bad, that's a you problem.",
    "Done. Your trim knobs can finally retire.",
    "Levels locked at -12. The dancefloor thanks you.",
    "01000100 01001111 01001110 01000101. (That's DONE, for the humans.)",
    "Normalized, levelled, four-on-the-floor-ready. Off you pop.",
]

ABOUT_LINES = [
    "---- about -------------------------------------------------",
    "Made for DJ's. Every file this app makes will play on",
    "Pioneer / AlphaTheta gear as shown below. It also levels",
    "every track, so no more fighting the trim: one consistent,",
    "club-ready loudness (-12 LUFS, EBU R128) across your whole",
    "set. LUFS is how loud a track *actually* sounds to human",
    "ears. Originals untouched.",
    "",
    "---- formats (click FORMAT / BITRATE to pick) ---------------",
    "AIFF  lossless 24-bit, uncompressed. The safe default.",
    "      Plays on ALL Pioneer/CDJ gear. Biggest files.",
    "FLAC  lossless, compressed (much smaller). NEWER GEAR ONLY:",
    "      CDJ-3000 / 2000NXS2 / TOUR1, XDJ-1000MK2 / RX2 / RX3 /",
    "      XZ / AZ, Opus Quad. NOT: CDJ-2000NXS & older, CDJ-900,",
    "      XDJ-700 / 1000 / RX.",
    "      (Mac Finder won't preview FLAC art — it IS embedded.)",
    "WAV   lossless 16-bit, uncompressed. Plays on ALL gear.",
    "      (24-bit WAV upsets some CDJs; WAV can't hold cover art.)",
    "MP3   the granddaddy of lossy formats — good at high bitrates.",
    "      320/256/192 kbps. Plays on ALL gear.",
    "AAC   (.m4a) lossy like MP3 but more modern — better at the",
    "      same size/bitrate. 320/256/192 kbps. All modern gear:",
    "      CDJ-350/850/900/2000 onward, all XDJs.",
    "",
    "Requires FFmpeg (GPLv3) — bundled inside this app, so you",
    "install nothing. Source: ffmpeg.org.  Made by Picnic Labs / Psi.",
    "------------------------------------------------------------",
]


def resource_path(rel: str) -> str:
    """Path to a bundled resource, whether frozen (PyInstaller) or run from source."""
    base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent))
    return str(Path(base) / rel)


class NormalizerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.src_dir = None
        self.dst_dir = None
        self.output_format = normalizer.DEFAULT_OUTPUT_FORMAT
        self.bitrate = normalizer.DEFAULT_BITRATE
        self.msg_q: queue.Queue = queue.Queue()
        self.worker = None
        self.joke_told = False   # one joke per session — not per encode

        self.lines = []          # (text, color) buffer for the canvas log
        self.buttons = {}        # name -> dict(rect, text, cmd, label, ...)
        self._btns_enabled = True
        self._hover_name = None
        self._armed = None       # button pressed but not yet released
        self._popup = None       # open pull-up menu (FORMAT/BITRATE), or None

        self._build_ui()
        self._poll_queue()
        self._banner()
        self._status("Choose a SOURCE folder to begin.")

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        self.root.title(APP_TITLE)
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.resizable(False, False)
        self.root.configure(bg=DARK)

        self.canvas = tk.Canvas(
            self.root, width=WIN_W, height=WIN_H,
            highlightthickness=0, bd=0, bg=DARK,
        )
        self.canvas.pack(fill="both", expand=True)

        try:
            self.bg_img = tk.PhotoImage(file=resource_path("gui_assets/background.png"))
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        except Exception as e:
            print(f"background image not loaded: {e}", file=sys.stderr)

        self.canvas.create_text(WIN_W // 2, 28, text=APP_TITLE, fill=GREEN, font=MONO_TITLE)

        # Always-visible status line (mirrors the latest action, prominent)
        self.status_item = self.canvas.create_text(
            WIN_W // 2, STATUS_Y, text="", fill=BRIGHT, font=MONO_STATUS,
        )

        # Transparent frames (outline only)
        self.canvas.create_rectangle(
            FRAME_X0, LOG_FRAME_TOP, FRAME_X1, LOG_FRAME_BOT, outline=DIM_GREEN, width=1)
        self.canvas.create_rectangle(
            FRAME_X0, BTN_BAR_TOP, FRAME_X1, BTN_BAR_BOT, outline=DIM_GREEN, width=1)

        # (name, label, command, width weight) — weights keep the long labels
        # readable and the short BITRATE button compact.
        specs = [
            ("source", "[ SOURCE ]", self.pick_source, 1.1),
            ("dest", "[ DESTINATION ]", self.pick_dest, 1.5),
            ("fmt", "FORMAT: AIFF", self.open_format_menu, 1.3),
            ("rate", "----", self.open_bitrate_menu, 0.7),
            ("about", "ABOUT", self.show_about, 0.9),
            ("go", "> NORMALIZE", self.start, 1.5),
        ]
        cy = (BTN_BAR_TOP + BTN_BAR_BOT) // 2
        total_w = FRAME_X1 - FRAME_X0
        unit = total_w / sum(w for *_, w in specs)

        # Shared button font, shrunk until every button's widest possible
        # label (they grow a " ✓ " when confirmed) fits inside its body.
        widest = {"source": "[ SOURCE ✓ ]", "dest": "[ DESTINATION ✓ ]",
                  "fmt": "FORMAT: AIFF", "rate": "320k",
                  "about": "ABOUT", "go": "> NORMALIZE"}
        self.btn_font = tkfont.Font(family=MONO_FAMILY, size=BTN_FONT_MAX,
                                    weight="bold")
        while self.btn_font.cget("size") > BTN_FONT_MIN and any(
                self.btn_font.measure(widest[name]) > int(unit * weight) - 22
                for name, _, _, weight in specs):
            self.btn_font.configure(size=self.btn_font.cget("size") - 1)

        x = FRAME_X0
        for name, label, cmd, weight in specs:
            span = unit * weight
            self._mk_btn(name, int(x + span / 2), cy, int(span - 12), label, cmd)
            x += span
        self._update_bitrate_btn()

        # One canvas-wide dispatcher for all buttons — reliable coordinate
        # hit-testing instead of fragile per-item (text-glyph) bindings.
        # Press arms the button; the command fires on release only if the
        # release lands inside the same button (standard button semantics —
        # a click never silently disappears, and a drag-away cancels).
        self.canvas.bind("<Button-1>", self._canvas_press)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_release)
        self.canvas.bind("<Motion>", self._canvas_motion)
        self.canvas.bind("<Leave>", self._canvas_leave)

    def _mk_btn(self, name, cx, cy, w, label, cmd):
        x0, y0 = cx - w // 2, cy - BTN_H // 2
        x1, y1 = cx + w // 2, cy + BTN_H // 2
        rect = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline=DIM_GREEN, width=1, fill=BTN_FILL,
        )
        txt = self.canvas.create_text(cx, cy, text=label, fill=GREEN, font=self.btn_font)
        self.buttons[name] = {"rect": rect, "text": txt, "cmd": cmd,
                              "label": label, "bounds": (x0, y0, x1, y1),
                              "confirmed": False, "enabled": True}
        # NB: no per-item bindings here. Clicks/hover are dispatched by
        # coordinate from canvas-wide handlers (see _hit / _canvas_click) — a
        # canvas *text* item is only "hit" on its glyph pixels, so binding the
        # button meant dead-centre clicks over the label could fall through the
        # gaps between letters. Rectangle hit-testing covers the whole body.

    def _hit(self, x, y):
        """Return the name of the button whose rectangle contains (x, y)."""
        for name, b in self.buttons.items():
            x0, y0, x1, y1 = b["bounds"]
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def _btn_active(self, name):
        return self._btns_enabled and self.buttons[name]["enabled"]

    def _canvas_press(self, event):
        # An open pull-up menu captures the press: a row applies the pick,
        # anywhere else just closes it. Either way the press stops here, so a
        # click on the button under the menu toggles it shut, not shut+open.
        if self._popup:
            popup = self._popup
            row = self._popup_row_at(event.x, event.y)
            self._close_popup()
            if row:
                popup["on_pick"](row["value"])
            self._armed = None
            return
        name = self._hit(event.x, event.y)
        if not (name and self._btn_active(name)):
            self._armed = None
            return
        self._armed = name
        b = self.buttons[name]
        # Immediate, obvious press feedback: invert colours and force a paint.
        self.canvas.itemconfigure(b["rect"], fill=GREEN, outline=BRIGHT, width=2)
        self.canvas.itemconfigure(b["text"], fill=DARK)
        self.canvas.update_idletasks()

    def _canvas_release(self, event):
        armed, self._armed = self._armed, None
        if not armed:
            return
        released_on = self._hit(event.x, event.y)
        if released_on == armed and self._btn_active(armed):
            self._on_click(armed)
        else:
            self._reset_btn(armed)  # drag-away cancels

    def _canvas_motion(self, event):
        if self._popup:
            hot = self._popup_row_at(event.x, event.y)
            for row in self._popup["rows"]:
                on = row is hot
                self.canvas.itemconfigure(row["rect"], fill=BTN_FILL_HOVER if on else BTN_FILL)
                self.canvas.itemconfigure(row["text"], fill=BRIGHT if on else GREEN)
            self.canvas.configure(cursor="hand2" if hot else "")
            return
        name = self._hit(event.x, event.y)
        if name == self._hover_name:
            return
        if self._hover_name:
            self._on_hover(self._hover_name, False)
        self._hover_name = name
        if name:
            self._on_hover(name, True)

    def _canvas_leave(self, _event):
        if self._popup:
            for row in self._popup["rows"]:
                self.canvas.itemconfigure(row["rect"], fill=BTN_FILL)
                self.canvas.itemconfigure(row["text"], fill=GREEN)
            self.canvas.configure(cursor="")
        if self._hover_name:
            self._on_hover(self._hover_name, False)
            self._hover_name = None

    # ---- pull-up menus (FORMAT / BITRATE) --------------------------------

    def _open_popup(self, name, options, current, on_pick):
        """Extend a button upward into a menu of (value, label) rows."""
        self._close_popup()
        x0, y0, x1, _ = self.buttons[name]["bounds"]
        top = y0 - POPUP_ROW_H * len(options) - 4
        c = self.canvas
        c.create_rectangle(x0, top, x1, y0, fill=BTN_FILL, outline=GREEN,
                           width=2, tags="popup")
        rows = []
        for i, (value, label) in enumerate(options):
            ry0 = top + 2 + i * POPUP_ROW_H
            ry1 = ry0 + POPUP_ROW_H
            rect = c.create_rectangle(x0 + 2, ry0, x1 - 2, ry1, fill=BTN_FILL,
                                      outline="", tags="popup")
            mark = "> " if value == current else "  "
            txt = c.create_text(x0 + 10, (ry0 + ry1) // 2, anchor="w",
                                text=mark + label, fill=GREEN,
                                font=self.btn_font, tags="popup")
            rows.append({"x0": x0, "y0": ry0, "x1": x1, "y1": ry1,
                         "rect": rect, "text": txt, "value": value})
        self._popup = {"rows": rows, "on_pick": on_pick}

    def _close_popup(self):
        if self._popup:
            self._popup = None
            self.canvas.delete("popup")
            self.canvas.configure(cursor="")

    def _popup_row_at(self, x, y):
        for row in self._popup["rows"]:
            if row["x0"] <= x <= row["x1"] and row["y0"] <= y <= row["y1"]:
                return row
        return None

    def _on_hover(self, name, entering):
        if not self._btn_active(name):
            return
        b = self.buttons[name]
        self.canvas.itemconfigure(
            b["rect"], fill=BTN_FILL_HOVER if entering else BTN_FILL,
            outline=GREEN if entering else DIM_GREEN, width=2 if entering else 1)
        self.canvas.itemconfigure(b["text"], fill=BRIGHT if entering else GREEN)
        # 'hand2' is the pointing hand on every Tk platform (aqua/win32/x11)
        self.canvas.configure(cursor="hand2" if entering else "")

    def _on_click(self, name):
        b = self.buttons[name]
        try:
            b["cmd"]()
        finally:
            self.root.after(130, lambda n=name: self._reset_btn(n))

    def _reset_btn(self, name):
        b = self.buttons[name]
        if (not self._btns_enabled and name != "go") or not b["enabled"]:
            fill, outline, tc = BTN_FILL_DISABLED, DIM_GREEN, DIM_GREEN
        else:
            fill, outline, tc = BTN_FILL, DIM_GREEN, GREEN
        self.canvas.itemconfigure(b["rect"], fill=fill, outline=outline, width=1)
        self.canvas.itemconfigure(b["text"], fill=tc)

    def _set_running(self, running):
        self._btns_enabled = not running
        for name, b in self.buttons.items():
            if running:
                self.canvas.itemconfigure(b["rect"], fill=BTN_FILL_DISABLED, outline=DIM_GREEN, width=1)
                self.canvas.itemconfigure(b["text"], fill=DIM_GREEN)
            else:
                self._reset_btn(name)
        self.canvas.itemconfigure(
            self.buttons["go"]["text"], text="working..." if running else "> NORMALIZE")

    def _confirm_btn(self, name, label_with_tick):
        """Mark a button as satisfied (adds a tick, greener outline)."""
        b = self.buttons[name]
        b["confirmed"] = True
        b["label"] = label_with_tick
        self.canvas.itemconfigure(b["text"], text=label_with_tick)

    # ---- status + canvas log --------------------------------------------

    def _status(self, text, color=BRIGHT):
        self.canvas.itemconfigure(self.status_item, text=text, fill=color)

    def _print(self, text="", color=GREEN, font=None):
        self.lines.append((text, color, font or MONO))
        self._render_log()

    def _render_log(self):
        c = self.canvas
        while True:
            c.delete("logline")
            y = LOG_TOP
            overflow = False
            for text, color, font in self.lines:
                item = c.create_text(LOG_X, y, anchor="nw", text=text, fill=color,
                                     font=font, width=LOG_W, tags="logline")
                bb = c.bbox(item)
                y = bb[3] + LINE_GAP
                if bb[3] > LOG_BOTTOM:
                    overflow = True
            if overflow and len(self.lines) > 1:
                self.lines.pop(0)
                continue
            break

    def _banner(self):
        self._print(">> Psi's DJ normalizer online.", DIM_GREEN)
        self._print(">> Everything gets levelled to -12 LUFS. Originals untouched.", DIM_GREEN)
        self._print("")

    def _foreground(self):
        # After a native dialog, macOS often leaves the app in the background.
        # Pull it back to front so the next click hits a widget, not just focus.
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except tk.TclError:
            pass

    # ---- actions ---------------------------------------------------------

    def pick_source(self):
        d = filedialog.askdirectory(title="Choose the folder with your tracks")
        self._foreground()
        if d:
            self.src_dir = d
            self._confirm_btn("source", "[ SOURCE ✓ ]")
            self._print(f">> source : {d}", GREEN)
            self._status("Source set. Now choose a DESTINATION." if not self.dst_dir
                         else "Ready. Hit > NORMALIZE.")

    def pick_dest(self):
        d = filedialog.askdirectory(title="Choose where normalized files go")
        self._foreground()
        if d:
            self.dst_dir = d
            self._confirm_btn("dest", "[ DESTINATION ✓ ]")
            self._print(f">> output : {d}", GREEN)
            self._status("Ready. Hit > NORMALIZE." if self.src_dir
                         else "Destination set. Now choose a SOURCE.")

    def open_format_menu(self):
        self._open_popup(
            "fmt",
            [(f, f.upper()) for f in normalizer.OUTPUT_FORMATS],
            self.output_format, self._pick_format)

    def _pick_format(self, fmt):
        self.output_format = fmt
        self.canvas.itemconfigure(
            self.buttons["fmt"]["text"], text=f"FORMAT: {fmt.upper()}")
        self._update_bitrate_btn()
        info = normalizer.OUTPUT_FORMATS[fmt]
        self._print(f">> format : {fmt.upper()} - {info['summary']}", GREEN)
        self._print(f">> {info['gear']}", DIM_GREEN)
        self._status(f"Output format: {self._fmt_desc()}")

    def open_bitrate_menu(self):
        self._open_popup(
            "rate",
            [(b, f"{b}k") for b in normalizer.BITRATES],
            self.bitrate, self._pick_bitrate)

    def _pick_bitrate(self, rate):
        self.bitrate = rate
        self._update_bitrate_btn()
        self._print(f">> bitrate : {self.bitrate} kbps", GREEN)
        self._status(f"Output format: {self._fmt_desc()}")

    def _fmt_desc(self):
        if normalizer.OUTPUT_FORMATS[self.output_format]['lossy']:
            return f"{self.output_format.upper()} {self.bitrate}kbps"
        return self.output_format.upper()

    def _update_bitrate_btn(self):
        """BITRATE applies to MP3/AAC only; grey it out for lossless formats."""
        b = self.buttons["rate"]
        lossy = normalizer.OUTPUT_FORMATS[self.output_format]['lossy']
        b["enabled"] = lossy
        b["label"] = f"{self.bitrate}k" if lossy else "----"
        self.canvas.itemconfigure(b["text"], text=b["label"])
        self._reset_btn("rate")

    def show_about(self):
        # About must fit on screen in one go: clear the log and shrink the
        # font until every line fits the frame, in height and width.
        f = tkfont.Font(family=MONO_FAMILY, size=MONO[1])
        longest = max(ABOUT_LINES, key=len)
        while f.cget("size") > 8 and (
                len(ABOUT_LINES) * (f.metrics("linespace") + LINE_GAP)
                > LOG_BOTTOM - LOG_TOP
                or f.measure(longest) > LOG_W):
            f.configure(size=f.cget("size") - 1)
        self.lines = []
        for ln in ABOUT_LINES:
            self._print(ln, DIM_GREEN if ln.startswith("-") else GREEN, font=f)
        self._status("That's the story. Now go level some tracks.")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.src_dir:
            self._print("!! choose a SOURCE folder first", FAIL_RED)
            self._status("Please choose a SOURCE folder first.", FAIL_RED)
            self._flash_missing("source")
            return
        if not self.dst_dir:
            self._print("!! choose a DESTINATION folder first", FAIL_RED)
            self._status("Please choose a DESTINATION folder first.", FAIL_RED)
            self._flash_missing("dest")
            return
        self._set_running(True)
        self._status("Normalizing... hang tight.")
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def _flash_missing(self, name, count=6):
        """Blink a required button red to draw the eye."""
        b = self.buttons[name]
        on = count % 2 == 0
        self.canvas.itemconfigure(b["rect"], outline=FAIL_RED if on else DIM_GREEN,
                                  width=2 if on else 1)
        self.canvas.itemconfigure(b["text"], fill=FAIL_RED if on else GREEN)
        if count > 0:
            self.root.after(140, lambda: self._flash_missing(name, count - 1))
        else:
            self._reset_btn(name)

    # ---- worker thread ---------------------------------------------------

    def _run(self):
        q = self.msg_q
        fmt = self.output_format
        bitrate = self.bitrate
        try:
            files = normalizer.find_audio_files(Path(self.src_dir))
            if not files:
                q.put(("log", ("No supported audio files found in there.", FAIL_RED)))
                q.put(("done", (0, 0)))
                return
            q.put(("log", (f">> found {len(files)} track(s). spinning up...\n", DIM_GREEN)))
            # One joke per session, after a randomly chosen encode (0 = never).
            joke_after = 0 if self.joke_told else random.randint(1, len(files))
            ok = fail = 0
            for i, f in enumerate(files, 1):
                q.put(("log", (f"[{i}/{len(files)}] {f.name}", GREEN)))
                out = normalizer.get_output_filename(str(f), self.dst_dir, fmt)
                success, message = normalizer.normalize_audio(
                    str(f), out, output_format=fmt, bitrate=bitrate)
                if success:
                    ok += 1
                    q.put(("log", (f"    ok  {message}", DIM_GREEN)))
                else:
                    fail += 1
                    q.put(("log", (f"    XX  FAILED: {f.name}", FAIL_RED)))
                    q.put(("log", (f"        reason: {message}", FAIL_RED)))
                if i == joke_after:
                    self.joke_told = True
                    q.put(("log", (f"    ~ {random.choice(DJ_JOKES)}\n", GREEN)))
            q.put(("done", (ok, fail)))
        except Exception as e:
            q.put(("log", (f"!! unexpected error: {e}", FAIL_RED)))
            q.put(("done", (0, 0)))

    # ---- main-thread queue pump -----------------------------------------

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_q.get_nowait()
                if kind == "log":
                    text, color = payload
                    self._print(text, color)
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _finish(self, result):
        ok, fail = result
        self._print("")
        self._print(f"=== DONE - {ok} normalized, {fail} failed ===",
                    FAIL_RED if fail else GREEN)
        self._print(random.choice(DJ_OUTRO), DIM_GREEN)
        self._print("")
        self._status(f"Done - {ok} normalized"
                     + (f", {fail} failed." if fail else ". Nice."),
                     FAIL_RED if fail else BRIGHT)
        self._set_running(False)


def main():
    root = tk.Tk()
    NormalizerGUI(root)
    root.lift()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
