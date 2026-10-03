"""Tkinter editor for a 4-shaft weaving draft.

Click (or drag) in the threading, tie-up and treadling grids to edit the
draft, colour warp ends and picks from the colour bar, then press Run to
weave the drawdown. Darker lines mark every fourth warp end, and the lines bar
adds your own guide lines after chosen ends and picks.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from model import DEFAULT_WARP_COLOR, DEFAULT_WEFT_COLOR, GROUP_SIZE, NUM_SHAFTS, Draft
from presets import PRESETS
from print_draft import render_pdf

CELL = 18
MARGIN = 34
GAP = CELL

GRID_LINE = "#b0b0b0"
EMPTY = "#ffffff"
MARK = "#222222"
STALE_TEXT = "#a03030"
GROUP_LINE = ("#6e6e6e", 2)  # colour and width of the line after every fourth end
GUIDE_LINE = ("#000000", 3)  # lines added by the user

DEFAULT_PRESET = "Twill 2/2 right-hand"
CUSTOM_NAME = "Custom"  # shown once the threading, tie-up or treadling is edited

_RANGE = re.compile(r"^(\d+)(?:-(\d+)(?:/(\d+))?)?$")


def parse_ranges(text: str, count: int, noun: str) -> list[int]:
    """Turn "1-4, 9, 12-20/2" or "all" into 0-based indices below count.

    "a-b/n" takes every n-th thread from a to b.
    """
    text = text.strip().lower()
    if text == "all":
        return list(range(count))
    indices = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        m = _RANGE.match(part)
        if not m:
            raise ValueError(f"“{part}” is not a number or range like 3-8.")
        start = int(m.group(1))
        end = int(m.group(2) or start)
        step = int(m.group(3) or 1)
        if start < 1 or end < start or step < 1:
            raise ValueError(f"“{part}” is not a valid range.")
        if end > count:
            raise ValueError(f"{noun} {end} is beyond the last {noun} ({count}).")
        indices.extend(range(start - 1, end, step))
    if not indices:
        raise ValueError(f"Enter the {noun}s to colour, e.g. 1-4, 9 or all.")
    return indices


class DraftEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("4-Shaft Draft Designer")

        self.brush = "#b8322a"  # colour applied to threads
        # Guide lines, stored as the end or pick number each line follows.
        self.v_lines, self.h_lines = set(), set()
        self.result = None  # colour grid from the last Run
        self.stale = True
        self._paint_value = None  # value applied while dragging

        self._build_controls()
        self._build_color_bar()
        self._build_lines_bar()
        self._build_canvas()
        self.load_draft(Draft(**PRESETS[DEFAULT_PRESET]))

        self.bind("<Command-r>", lambda e: self.run())
        self.bind("<Control-r>", lambda e: self.run())

    # ---------- layout ----------

    def _build_controls(self):
        bar = ttk.Frame(self, padding=6)
        bar.pack(side=tk.TOP, fill=tk.X)

        self.ends_var = tk.IntVar()
        self.treadles_var = tk.IntVar()
        self.picks_var = tk.IntVar()
        for label, var, hi in (
            ("Ends", self.ends_var, 200),
            ("Treadles", self.treadles_var, 10),
            ("Picks", self.picks_var, 200),
        ):
            ttk.Label(bar, text=label).pack(side=tk.LEFT, padx=(8, 2))
            spin = ttk.Spinbox(bar, from_=1, to=hi, width=4, textvariable=var,
                               command=self.resize)
            spin.pack(side=tk.LEFT)
            spin.bind("<Return>", lambda e: self.resize())
            spin.bind("<FocusOut>", lambda e: self.resize())

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        ttk.Label(bar, text="Preset").pack(side=tk.LEFT, padx=(0, 2))
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        preset = ttk.Combobox(bar, textvariable=self.preset_var, state="readonly",
                              values=list(PRESETS), width=22, height=len(PRESETS))
        preset.pack(side=tk.LEFT)
        preset.bind("<<ComboboxSelected>>",
                    lambda e: self.load_draft(Draft(**PRESETS[self.preset_var.get()])))

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(bar, text="Clear", command=self.clear).pack(side=tk.LEFT)
        ttk.Button(bar, text="Open…", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(bar, text="Save…", command=self.save_file).pack(side=tk.LEFT)
        ttk.Button(bar, text="Print…", command=self.print_dialog).pack(side=tk.LEFT)

        run = ttk.Button(bar, text="▶ Run", command=self.run)
        run.pack(side=tk.RIGHT)

        self.status = ttk.Label(self, padding=(8, 2))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_color_bar(self):
        bar = ttk.Frame(self, padding=(6, 0, 6, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Colour").pack(side=tk.LEFT, padx=(8, 4))
        # tk.Button ignores background colours on macOS, so the swatch is a canvas.
        self.swatch = tk.Canvas(bar, width=36, height=20, highlightthickness=1,
                                highlightbackground=GRID_LINE, cursor="hand2")
        self.swatch.pack(side=tk.LEFT)
        self.swatch.bind("<Button-1>", lambda e: self.pick_brush())
        self._paint_swatch()
        ttk.Button(bar, text="Choose…", command=self.pick_brush).pack(side=tk.LEFT, padx=(4, 0))

        self.warp_range = tk.StringVar()
        self.weft_range = tk.StringVar()
        for label, var, command in (
            ("Warp ends", self.warp_range, self.color_warp),
            ("Weft picks", self.weft_range, self.color_weft),
        ):
            ttk.Label(bar, text=label).pack(side=tk.LEFT, padx=(14, 2))
            entry = ttk.Entry(bar, textvariable=var, width=14)
            entry.pack(side=tk.LEFT)
            entry.bind("<Return>", lambda e, cmd=command: cmd())
            ttk.Button(bar, text="Apply", command=command).pack(side=tk.LEFT, padx=(2, 0))

        ttk.Label(bar, text="e.g. 1-4, 9, 13-24/2 or all", foreground="#777").pack(
            side=tk.LEFT, padx=(10, 0))

    def _build_lines_bar(self):
        bar = ttk.Frame(self, padding=(6, 0, 6, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Lines").pack(side=tk.LEFT, padx=(8, 4))
        self.v_lines_range = tk.StringVar()
        self.h_lines_range = tk.StringVar()
        for label, var, command in (
            ("Vertical after ends", self.v_lines_range, self.add_v_lines),
            ("Horizontal after picks", self.h_lines_range, self.add_h_lines),
        ):
            ttk.Label(bar, text=label).pack(side=tk.LEFT, padx=(14, 2))
            entry = ttk.Entry(bar, textvariable=var, width=12)
            entry.pack(side=tk.LEFT)
            entry.bind("<Return>", lambda e, cmd=command: cmd())
            ttk.Button(bar, text="Add", command=command).pack(side=tk.LEFT, padx=(2, 0))

        ttk.Button(bar, text="Clear lines", command=self.clear_lines).pack(side=tk.LEFT,
                                                                           padx=(14, 0))
        ttk.Label(bar, text="e.g. 8, 16 or 8-48/8", foreground="#777").pack(
            side=tk.LEFT, padx=(10, 0))

    def _build_canvas(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(frame, background="#f4f4f4", highlightthickness=0)
        xs = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        ys = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "_paint_value", None))

    # Regions: top-left corner, columns and rows, in canvas coordinates.
    def _origins(self):
        ends, treadles, picks = len(self.threading), len(self.tie_up), len(self.treadling)
        right_x = MARGIN + ends * CELL + GAP
        thread_y = MARGIN + CELL + GAP
        lower_y = thread_y + NUM_SHAFTS * CELL + GAP
        return {
            "warp_colors": (MARGIN, MARGIN, ends, 1),
            "threading": (MARGIN, thread_y, ends, NUM_SHAFTS),
            "tie_up": (right_x, thread_y, treadles, NUM_SHAFTS),
            "drawdown": (MARGIN, lower_y, ends, picks),
            "treadling": (right_x, lower_y, treadles, picks),
            "weft_colors": (right_x + treadles * CELL + GAP, lower_y, 1, picks),
        }

    # ---------- state ----------

    def load_draft(self, draft: Draft):
        self.threading = list(draft.threading)
        self.tie_up = [set(s) for s in draft.tie_up]
        self.treadling = [set(t) for t in draft.treadling]
        self.warp_colors = list(draft.warp_colors)
        self.weft_colors = list(draft.weft_colors)
        self._sync_spinboxes()
        self._trim_lines()
        self.run()

    def current_draft(self) -> Draft:
        return Draft(threading=self.threading, tie_up=self.tie_up, treadling=self.treadling,
                     warp_colors=self.warp_colors, weft_colors=self.weft_colors)

    def _sync_spinboxes(self):
        self.ends_var.set(len(self.threading))
        self.treadles_var.set(len(self.tie_up))
        self.picks_var.set(len(self.treadling))

    def resize(self):
        try:
            ends = max(1, self.ends_var.get())
            treadles = max(1, self.treadles_var.get())
            picks = max(1, self.picks_var.get())
        except tk.TclError:
            self._sync_spinboxes()
            return
        if (ends, treadles, picks) == (len(self.threading), len(self.tie_up), len(self.treadling)):
            return
        # New ends continue a straight draw; new treadles and picks start empty.
        self.threading = self.threading[:ends] + [
            i % NUM_SHAFTS + 1 for i in range(len(self.threading), ends)
        ]
        self.tie_up = self.tie_up[:treadles] + [set() for _ in range(treadles - len(self.tie_up))]
        self.treadling = [
            {t for t in pick if t <= treadles} for pick in self.treadling[:picks]
        ] + [set() for _ in range(picks - len(self.treadling))]
        # The model trims or pads the colour lists to match.
        draft = self.current_draft()
        self.warp_colors, self.weft_colors = draft.warp_colors, draft.weft_colors
        self._sync_spinboxes()
        self._trim_lines()
        self.mark_custom()

    def clear(self):
        self.tie_up = [set() for _ in self.tie_up]
        self.treadling = [set() for _ in self.treadling]
        self.threading = [i % NUM_SHAFTS + 1 for i in range(len(self.threading))]
        self.warp_colors = [DEFAULT_WARP_COLOR] * len(self.threading)
        self.weft_colors = [DEFAULT_WEFT_COLOR] * len(self.treadling)
        self.mark_custom()

    def mark_stale(self):
        self.stale = True
        self.redraw()

    def mark_custom(self):
        """The draft no longer matches its preset or file, so rename it."""
        self.preset_var.set(CUSTOM_NAME)
        self.mark_stale()

    def run(self):
        try:
            self.result = self.current_draft().color_drawdown()
        except ValueError as err:
            messagebox.showerror("Invalid draft", str(err))
            return
        self.stale = False
        self.redraw()

    # ---------- thread colours ----------

    def _paint_swatch(self):
        self.swatch.delete("all")
        self.swatch.create_rectangle(0, 0, 40, 24, fill=self.brush, outline="")

    def pick_brush(self):
        color = colorchooser.askcolor(self.brush, title="Thread colour")[1]
        if color:
            self.brush = color
            self._paint_swatch()

    def _color_threads(self, colors, text, noun):
        try:
            indices = parse_ranges(text, len(colors), noun)
        except ValueError as err:
            messagebox.showerror("Can't apply colour", str(err))
            return
        for i in indices:
            colors[i] = self.brush
        self.mark_stale()

    def color_warp(self):
        self._color_threads(self.warp_colors, self.warp_range.get(), "end")

    def color_weft(self):
        self._color_threads(self.weft_colors, self.weft_range.get(), "pick")

    # ---------- guide lines ----------

    def _add_lines(self, lines, text, count, noun):
        try:
            indices = parse_ranges(text, count, noun)
        except ValueError as err:
            messagebox.showerror("Can't add lines", str(err))
            return
        lines.update(i + 1 for i in indices)  # a line follows each listed end or pick
        # Lines don't change the cloth, so no Run is needed.
        self.redraw()

    def add_v_lines(self):
        self._add_lines(self.v_lines, self.v_lines_range.get(), len(self.threading), "end")

    def add_h_lines(self):
        self._add_lines(self.h_lines, self.h_lines_range.get(), len(self.treadling), "pick")

    def clear_lines(self):
        self.v_lines.clear()
        self.h_lines.clear()
        self.redraw()

    def _trim_lines(self):
        """Drop lines past the last end or pick after the draft shrinks."""
        self.v_lines = {n for n in self.v_lines if n <= len(self.threading)}
        self.h_lines = {n for n in self.h_lines if n <= len(self.treadling)}

    # ---------- editing ----------

    def _hit(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for name, (ox, oy, cols, rows) in self._origins().items():
            col, row = int((x - ox) // CELL), int((y - oy) // CELL)
            if x >= ox and y >= oy and col < cols and row < rows:
                return name, col, row
        return None

    def on_press(self, event):
        hit = self._hit(event)
        if not hit:
            return
        name, col, row = hit
        if name == "tie_up":
            self._paint_value = (NUM_SHAFTS - row) not in self.tie_up[col]
        elif name == "treadling":
            self._paint_value = (col + 1) not in self.treadling[row]
        self._apply(hit)

    def on_drag(self, event):
        hit = self._hit(event)
        if hit:
            self._apply(hit)

    def _apply(self, hit):
        name, col, row = hit
        shaft = NUM_SHAFTS - row  # shaft 1 is the bottom row
        if name == "threading":
            values, i, value = self.threading, col, shaft
        elif name == "warp_colors":
            values, i, value = self.warp_colors, col, self.brush
        elif name == "weft_colors":
            values, i, value = self.weft_colors, row, self.brush
        elif name in ("tie_up", "treadling") and self._paint_value is not None:
            # Toggle grids: set or clear one mark, following the drag's paint value.
            cell, mark = ((self.tie_up[col], shaft) if name == "tie_up"
                          else (self.treadling[row], col + 1))
            if (mark in cell) == self._paint_value:
                return
            cell.symmetric_difference_update({mark})
            self.mark_custom()
            return
        else:
            return
        if values[i] != value:
            values[i] = value
            # Colours don't change the weave structure, so the name stays.
            if name == "threading":
                self.mark_custom()
            else:
                self.mark_stale()

    # ---------- drawing ----------

    def _cell(self, region, col, row, fill):
        x, y = region[0] + col * CELL, region[1] + row * CELL
        self.canvas.create_rectangle(x, y, x + CELL, y + CELL, fill=fill, outline=GRID_LINE)

    def _fade(self, color, amount=0.65):
        """Blend a colour toward white."""
        r, g, b = (v / 257 for v in self.winfo_rgb(color))
        return "#%02x%02x%02x" % tuple(int(v + (255 - v) * amount) for v in (r, g, b))

    def _label(self, region, text):
        self.canvas.create_text(region[0], region[1] - 9, text=text, anchor="w")

    def redraw(self):
        c = self.canvas
        c.delete("all")
        o = self._origins()

        r = o["warp_colors"]
        for col, color in enumerate(self.warp_colors):
            self._cell(r, col, 0, color)
        self._label(r, "Warp colours")

        r = o["threading"]
        ox, oy = r[:2]
        for row in range(NUM_SHAFTS):
            shaft = NUM_SHAFTS - row
            c.create_text(ox - 10, oy + row * CELL + CELL / 2, text=str(shaft))
            for col, s in enumerate(self.threading):
                self._cell(r, col, row, MARK if s == shaft else EMPTY)
        self._label(r, "Threading")

        r = o["tie_up"]
        for row in range(NUM_SHAFTS):
            for col, shafts in enumerate(self.tie_up):
                self._cell(r, col, row, MARK if NUM_SHAFTS - row in shafts else EMPTY)
        self._label(r, "Tie-up")

        r = o["treadling"]
        ox, oy, treadles, picks = r
        for row, pressed in enumerate(self.treadling):
            for col in range(treadles):
                self._cell(r, col, row, MARK if col + 1 in pressed else EMPTY)
        for col in range(treadles):
            c.create_text(ox + col * CELL + CELL / 2, oy + picks * CELL + 10, text=str(col + 1))
        self._label(r, "Treadling")

        r = o["weft_colors"]
        for row, color in enumerate(self.weft_colors):
            self._cell(r, 0, row, color)
        self._label(r, "Weft")

        r = o["drawdown"]
        ox, oy, ends, picks = r
        # A stale drawdown keeps the last result, faded, until Run is pressed.
        if self.result is not None:
            faded = {}
            for row, cells in enumerate(self.result[:picks]):
                for col, color in enumerate(cells[:ends]):
                    if self.stale:
                        color = faded.setdefault(color, self._fade(color))
                    self._cell(r, col, row, color)
        c.create_text(ox, oy + picks * CELL + 10, text="Drawdown", anchor="w")
        if self.stale:
            self.status.configure(text="Draft changed — press Run (⌘R) to update the drawdown.",
                                  foreground=STALE_TEXT)
        else:
            self.status.configure(
                text=f"{ends} ends × {picks} picks, {treadles} treadles. Rising shed.",
                foreground="")

        # Group lines every fourth end, then the user's guide lines on top.
        groups = range(GROUP_SIZE, ends, GROUP_SIZE)
        columns = [o["warp_colors"], o["threading"], o["drawdown"]]
        rows = [o["drawdown"], o["treadling"], o["weft_colors"]]
        for lines, (color, width) in ((groups, GROUP_LINE), (self.v_lines, GUIDE_LINE)):
            for n in lines:
                for ox, oy, _, height in columns:
                    c.create_line(ox + n * CELL, oy, ox + n * CELL, oy + height * CELL,
                                  fill=color, width=width)
        color, width = GUIDE_LINE
        for n in self.h_lines:
            for ox, oy, length, _ in rows:
                c.create_line(ox, oy + n * CELL, ox + length * CELL, oy + n * CELL,
                              fill=color, width=width)

        _, _, x2, y2 = c.bbox("all")
        c.configure(scrollregion=(0, 0, x2 + MARGIN, y2 + MARGIN))

    # ---------- files ----------

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Draft", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                draft = Draft.from_dict(json.load(f))
        except (OSError, ValueError, KeyError) as err:
            messagebox.showerror("Could not open draft", str(err))
            return
        self.preset_var.set(draft.name or Path(path).stem)
        self.load_draft(draft)

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Draft", "*.json")])
        if path:
            with open(path, "w") as f:
                draft = self.current_draft()
                draft.name = self.preset_var.get()
                json.dump(draft.to_dict(), f, indent=2)

    # ---------- printing ----------

    def print_dialog(self):
        try:
            draft = self.current_draft()
        except ValueError as err:
            messagebox.showerror("Invalid draft", str(err))
            return

        dlg = tk.Toplevel(self)
        dlg.title("Print draft")
        dlg.transient(self)
        dlg.resizable(False, False)
        body = ttk.Frame(dlg, padding=14)
        body.pack(fill=tk.BOTH)

        title = tk.StringVar(value=self.preset_var.get())
        layout = tk.StringVar(value="tie_up")
        lowered = tk.BooleanVar(value=True)
        colors = tk.BooleanVar(value=True)

        ttk.Label(body, text="Title").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=title, width=32).grid(row=0, column=1, sticky="we", pady=(0, 8))

        ttk.Label(body, text="Loom").grid(row=1, column=0, sticky="nw")
        ttk.Radiobutton(body, text="Treadle loom: tie-up and treadling", variable=layout,
                        value="tie_up").grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(body, text="No tie-up: combined shaft plan per pick", variable=layout,
                        value="lift_plan").grid(row=2, column=1, sticky="w")

        shed = ttk.Frame(body, padding=(20, 2, 0, 6))
        shed.grid(row=3, column=1, sticky="w")
        shed_buttons = [
            ttk.Radiobutton(shed, text="Show shafts to lower", variable=lowered, value=True),
            ttk.Radiobutton(shed, text="Show shafts to raise", variable=lowered, value=False),
        ]
        for b in shed_buttons:
            b.pack(anchor="w")

        def update_shed(*_):
            state = "normal" if layout.get() == "lift_plan" else "disabled"
            for b in shed_buttons:
                b.configure(state=state)
        layout.trace_add("write", update_shed)
        update_shed()

        ttk.Checkbutton(body, text="Include thread colours", variable=colors).grid(
            row=4, column=1, sticky="w", pady=(0, 10))

        def options():
            return dict(layout=layout.get(), lowered=lowered.get(),
                        v_lines=sorted(self.v_lines), h_lines=sorted(self.h_lines),
                        colors=colors.get(), title=title.get().strip())

        def preview():
            path = os.path.join(tempfile.gettempdir(), "weaving-draft-print.pdf")
            if self._write_pdf(draft, path, options()):
                dlg.destroy()
                show_in_viewer(path)

        def save_pdf():
            path = filedialog.asksaveasfilename(parent=dlg, defaultextension=".pdf",
                                                filetypes=[("PDF", "*.pdf")])
            if path and self._write_pdf(draft, path, options()):
                dlg.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save PDF…", command=save_pdf).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Print…", command=preview).pack(side=tk.LEFT)
        ttk.Label(body, text="Print opens the page in your PDF viewer; press ⌘P there to print.",
                  foreground="#777").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        dlg.grab_set()

    def _write_pdf(self, draft, path, opts) -> bool:
        try:
            render_pdf(draft, path, **opts)
        except OSError as err:
            messagebox.showerror("Could not create PDF", str(err))
            return False
        return True


def show_in_viewer(path):
    """Open a file in the system's default viewer."""
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    elif sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", path], check=False)


if __name__ == "__main__":
    DraftEditor().mainloop()
