"""Render a Draft to a printable PDF page.

Two layouts:
  "tie_up":    threading, tie-up, treadling and drawdown (treadle loom).
  "lift_plan": the tie-up and treadling merged into one shaft-per-pick
               plan, for a loom without a tie-up.
"""

from itertools import accumulate

from matplotlib.collections import PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from model import NUM_SHAFTS, Draft, thickness_summary

PAGE_SHORT, PAGE_LONG = 8.27, 11.69  # A4, inches
PAGE_MARGIN = 0.5
MAX_CELL = 0.22  # inches

GRID_LINE = "#9a9a9a"
MARK = "#222222"


def _edges(thickness: list[float]) -> list[float]:
    """Cell boundaries, in cell units, for threads of the given thickness."""
    return [0.0, *accumulate(thickness)]


def render_pdf(draft: Draft, path: str, layout: str = "tie_up", lowered: bool = True,
               colors: bool = True, title: str = "") -> None:
    ends, picks = draft.num_ends, draft.num_picks
    lift = layout == "lift_plan"
    right_cols = NUM_SHAFTS if lift else draft.num_treadles
    # Warp columns and weft rows are sized by thread thickness.
    xs = _edges(draft.warp_thickness)
    ys = _edges(draft.weft_thickness)

    # Layout in cell units. x grows right, y grows down.
    strip = 2 if colors else 0  # warp colour row plus a gap
    thread_y = strip
    lower_y = thread_y + NUM_SHAFTS + 1
    right_x = xs[-1] + 1
    weft_x = right_x + right_cols + 1
    width = (weft_x + 1 if colors else weft_x - 1) + 3  # room for pick numbers
    height = lower_y + ys[-1] + 2
    left, top = 2.0, 1.0  # shaft numbers on the left, headings on top
    header = 0.9  # inches for the title block
    footer = 0.8  # inches for the thickness summary and note

    units_w, units_h = width + left, height + top
    landscape = units_w > units_h
    page_w, page_h = (PAGE_LONG, PAGE_SHORT) if landscape else (PAGE_SHORT, PAGE_LONG)
    cell = min(MAX_CELL, (page_w - 2 * PAGE_MARGIN) / units_w,
               (page_h - 2 * PAGE_MARGIN - header - footer) / units_h)
    font = max(4.0, min(9.0, cell * 72 * 0.6))

    fig = Figure(figsize=(page_w, page_h))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, page_w)
    ax.set_ylim(page_h, 0)
    ax.axis("off")

    ox, oy = PAGE_MARGIN + left * cell, PAGE_MARGIN + header + top * cell
    rects, fills = [], []

    def rect(x0, y0, x1, y1, fill):
        rects.append(Rectangle((ox + x0 * cell, oy + y0 * cell), (x1 - x0) * cell,
                               (y1 - y0) * cell))
        fills.append(fill)

    def box(col, row, fill):
        rect(col, row, col + 1, row + 1, fill)

    def warp_box(end, row, fill):  # one warp end's column, one unit tall
        rect(xs[end], row, xs[end + 1], row + 1, fill)

    def weft_box(col, pick, fill):  # one unit wide, one pick's row below lower_y
        rect(col, lower_y + ys[pick], col + 1, lower_y + ys[pick + 1], fill)

    def pick_mid(pick):
        return lower_y + (ys[pick] + ys[pick + 1]) / 2

    def text(col, row, s, **kw):
        kw.setdefault("ha", "center")
        kw.setdefault("va", "center")
        kw.setdefault("fontsize", font)
        ax.text(ox + col * cell, oy + row * cell, s, **kw)

    def heading(col, row, s):
        text(col, row - 0.5, s, ha="left", fontsize=font + 1, weight="bold")

    # Warp colours and threading
    if colors:
        for c, color in enumerate(draft.warp_colors):
            warp_box(c, 0, color)
        heading(0, 0, "Warp colours")
    for r in range(NUM_SHAFTS):
        shaft = NUM_SHAFTS - r
        text(-0.8, thread_y + r + 0.5, str(shaft))
        for c, s in enumerate(draft.threading):
            warp_box(c, thread_y + r, MARK if s == shaft else "white")
    heading(0, thread_y, "Threading")
    for c in range(3, ends, 4):
        text((xs[c] + xs[c + 1]) / 2, thread_y + NUM_SHAFTS + 0.5, str(c + 1),
             fontsize=font * 0.8, color="#555")

    # Drawdown
    for r, row in enumerate(draft.color_drawdown()):
        for c, color in enumerate(row):
            rect(xs[c], lower_y + ys[r], xs[c + 1], lower_y + ys[r + 1], color)
    text(0, lower_y + ys[-1] + 0.8, "Drawdown", ha="left", fontsize=font + 1, weight="bold")

    # Right-hand side: tie-up + treadling, or the merged lift plan
    if lift:
        plan = draft.lift_plan(lowered=lowered)
        for r, shafts in enumerate(plan):
            for c in range(NUM_SHAFTS):
                marked = c + 1 in shafts
                weft_box(right_x + c, r, MARK if marked else "white")
                if marked and cell * (ys[r + 1] - ys[r]) >= 0.12:
                    text(right_x + c + 0.5, pick_mid(r), str(c + 1), color="white",
                         fontsize=font * 0.85)
        for c in range(NUM_SHAFTS):
            text(right_x + c + 0.5, lower_y - 0.5, str(c + 1))
        heading(right_x, lower_y - 1, "Shafts lowered" if lowered else "Shafts raised")
        action = "Lower" if lowered else "Raise"
        note = (f"{action} the marked shafts for each pick, starting from pick 1 at the top. "
                + ("Lowered shafts are the ones not lifted in the rising-shed drawdown."
                   if lowered else ""))
    else:
        for r in range(NUM_SHAFTS):
            for c, shafts in enumerate(draft.tie_up):
                box(right_x + c, thread_y + r, MARK if NUM_SHAFTS - r in shafts else "white")
        heading(right_x, thread_y, "Tie-up")
        for r, pressed in enumerate(draft.treadling):
            for c in range(draft.num_treadles):
                weft_box(right_x + c, r, MARK if c + 1 in pressed else "white")
        for c in range(draft.num_treadles):
            text(right_x + c + 0.5, lower_y + ys[-1] + 0.6, str(c + 1))
        heading(right_x, lower_y, "Treadling")
        note = "Rising shed: tied shafts are lifted. Treadle from pick 1 at the top."

    # Weft colours and pick numbers
    if colors:
        for r, color in enumerate(draft.weft_colors):
            weft_box(weft_x, r, color)
        heading(weft_x, lower_y, "Weft")
    num_x = (weft_x + 1 if colors else weft_x - 1) + 0.3
    for r in range(picks):
        if ys[r + 1] - ys[r] >= 0.5:  # skip numbers on picks too thin to label
            text(num_x, pick_mid(r), str(r + 1), ha="left", fontsize=font * 0.8, color="#555")

    ax.add_collection(PatchCollection(rects, facecolors=fills, edgecolors=GRID_LINE,
                                      linewidths=0.4))

    summary = f"{ends} ends × {picks} picks, {NUM_SHAFTS} shafts"
    if not lift:
        summary += f", {draft.num_treadles} treadles"
    ax.text(PAGE_MARGIN, PAGE_MARGIN, title or "Weaving draft", fontsize=14, weight="bold",
            va="top")
    ax.text(PAGE_MARGIN, PAGE_MARGIN + 0.28, summary, fontsize=9, va="top", color="#444")
    footer_lines = [
        f"Warp thickness: {thickness_summary(draft.warp_thickness, 'end')}",
        f"Weft thickness: {thickness_summary(draft.weft_thickness, 'pick')}",
        note,
    ]
    ax.text(PAGE_MARGIN, oy + height * cell + 0.15, "\n".join(footer_lines), fontsize=8,
            va="top", color="#444", wrap=True, linespacing=1.5)

    fig.savefig(path)
