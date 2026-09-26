"""Library of traditional 4-shaft drafts, all written for a rising shed.

Each preset is a dict of Draft keyword arguments. Treadle numbers are
1-based; tie-up sets list the shafts lifted by each treadle.
"""

from model import DEFAULT_WARP_COLOR as NAVY

CREAM = "#f2ead3"
GOLD = "#e8c872"
RED = "#b8322a"
GREEN = "#2e6b45"
BLACK = "#262626"
WHITE = "#fbfaf6"
YELLOW = "#e9c046"

TWILL_2_2 = [{1, 2}, {2, 3}, {3, 4}, {1, 4}]
TABBY = [{1, 3}, {2, 4}]
STRAIGHT = [1, 2, 3, 4]
POINT = [1, 2, 3, 4, 3, 2]
GOOSE_EYE = [1, 2, 3, 4, 1, 2, 3, 4, 3, 2, 1, 4, 3, 2]
ROSEPATH = [1, 2, 3, 4, 1, 4, 3, 2]


def repeat(seq, length):
    """Repeat a sequence out to the given length."""
    return [seq[i % len(seq)] for i in range(length)]


def stripes(*runs):
    """Colour sequence from (colour, count) pairs."""
    return [color for color, count in runs for _ in range(count)]


def with_tabby(pattern_picks, pattern_color, tabby_color=CREAM, tabby=(5, 6)):
    """Follow every pattern pick with a tabby pick, alternating the two tabbies.

    Returns (treadling, weft_colors).
    """
    treadling, colors = [], []
    for i, treadle in enumerate(pattern_picks):
        treadling += [treadle, tabby[i % 2]]
        colors += [pattern_color, tabby_color]
    return treadling, colors


# ----- overshot: blocks A-D sit on shaft pairs 1-2, 2-3, 3-4, 4-1 -----

_OVERSHOT_BLOCKS = {"A": (1, 2), "B": (2, 3), "C": (3, 4), "D": (4, 1)}
# Rising shed: lift the two shafts outside a block so the pattern floats over it.
_OVERSHOT_TREADLE = {"A": 1, "B": 2, "C": 3, "D": 4}
OVERSHOT_TIE_UP = [{3, 4}, {1, 4}, {1, 2}, {2, 3}, {1, 3}, {2, 4}]


def overshot_threading(blocks):
    """Thread (block, ends) pairs so shafts alternate odd/even for tabby."""
    ends = []
    for name, count in blocks:
        pair = _OVERSHOT_BLOCKS[name]
        for _ in range(count):
            want_odd = not ends or ends[-1] % 2 == 0
            ends.append(next(s for s in pair if (s % 2 == 1) == want_odd))
    return ends


def overshot(blocks, pattern_color=RED):
    """Overshot threading woven as drawn in (tromp as writ)."""
    picks = [_OVERSHOT_TREADLE[name] for name, count in blocks for _ in range(count // 2)]
    treadling, weft = with_tabby(picks, pattern_color)
    threading = overshot_threading(blocks)
    return dict(threading=threading, tie_up=OVERSHOT_TIE_UP, treadling=treadling,
                warp_colors=[CREAM] * len(threading), weft_colors=weft)


# ----- summer and winter: shafts 1-2 tie-downs, 3 = block A, 4 = block B -----

_SW_UNIT = {"A": [1, 3, 2, 3], "B": [1, 4, 2, 4]}
# Treadles 1-2 weave pattern on A, 3-4 on B (x and y tie-downs), 5-6 are tabby.
SW_TIE_UP = [{1, 4}, {2, 4}, {1, 3}, {2, 3}, {1, 2}, {3, 4}]


def summer_and_winter(blocks, pattern_color=RED):
    threading = [s for name, units in blocks for _ in range(units) for s in _SW_UNIT[name]]
    first = {"A": 1, "B": 3}
    picks = []
    for name, units in blocks:
        x, y = first[name], first[name] + 1
        picks += [x, y, y, x] * units  # "x y y x" pairs
    treadling, weft = with_tabby(picks, pattern_color)
    return dict(threading=threading, tie_up=SW_TIE_UP, treadling=treadling,
                warp_colors=[CREAM] * len(threading), weft_colors=weft)


# ----- monk's belt: block A on shafts 1-2, block B on 3-4 -----

def monks_belt():
    threading = [1, 2] * 4 + [3, 4] * 2 + [1, 2] * 2 + [3, 4] * 4 + [1, 2] * 2 + [3, 4] * 2
    # Treadle 1 lifts 1-2 (pattern floats over B), treadle 2 lifts 3-4 (over A).
    picks = [2] * 4 + [1] * 6 + [2] * 4 + [1] * 2 + [2] * 4
    treadling, weft = with_tabby(picks, RED, tabby=(3, 4))
    return dict(threading=threading, tie_up=[{1, 2}, {3, 4}, {1, 3}, {2, 4}],
                treadling=treadling, warp_colors=[CREAM] * len(threading),
                weft_colors=weft)


# ----- colour-and-weave -----

LOG_CABIN = stripes(*[(NAVY, 1), (CREAM, 1)] * 4, *[(CREAM, 1), (NAVY, 1)] * 4)
HOUNDSTOOTH = stripes((BLACK, 4), (WHITE, 4))
PLAID = stripes((NAVY, 6), (GREEN, 8), (NAVY, 2), (RED, 2), (NAVY, 2), (GREEN, 8),
                (NAVY, 6), (YELLOW, 2))


PRESETS = {
    "Plain weave": dict(
        threading=repeat(STRAIGHT, 24), tie_up=TABBY, treadling=repeat([1, 2], 24)),
    "Basket weave 2×2": dict(
        threading=repeat(STRAIGHT, 24), tie_up=[{1, 2}, {3, 4}],
        treadling=repeat([1, 1, 2, 2], 24)),
    "Warp rib": dict(
        threading=repeat(STRAIGHT, 24), tie_up=TABBY, treadling=repeat([1, 1, 2, 2], 24)),
    "Weft rib": dict(
        threading=repeat([1, 3, 2, 4], 24), tie_up=TABBY, treadling=repeat([1, 2], 24)),

    "Twill 2/2 right-hand": dict(
        threading=repeat(STRAIGHT, 24), tie_up=TWILL_2_2, treadling=repeat(STRAIGHT, 24)),
    "Twill 2/2 left-hand": dict(
        threading=repeat(STRAIGHT, 24), tie_up=TWILL_2_2, treadling=repeat([4, 3, 2, 1], 24)),
    "Twill 1/3 (weft-faced)": dict(
        threading=repeat(STRAIGHT, 24), tie_up=[{1}, {2}, {3}, {4}],
        treadling=repeat(STRAIGHT, 24)),
    "Twill 3/1 (warp-faced)": dict(
        threading=repeat(STRAIGHT, 24), tie_up=[{1, 2, 3}, {2, 3, 4}, {1, 3, 4}, {1, 2, 4}],
        treadling=repeat(STRAIGHT, 24)),
    "Broken twill": dict(
        threading=repeat([1, 2, 4, 3], 24), tie_up=TWILL_2_2,
        treadling=repeat([1, 2, 4, 3], 24)),
    "Herringbone": dict(
        threading=repeat([1, 2, 3, 4] * 2 + [2, 1, 4, 3] * 2, 32), tie_up=TWILL_2_2,
        treadling=repeat(STRAIGHT, 24)),
    "Chevron (point twill)": dict(
        threading=repeat(POINT, 24), tie_up=TWILL_2_2, treadling=repeat(STRAIGHT, 24)),
    "Bird's eye": dict(
        threading=repeat(POINT, 24), tie_up=TWILL_2_2, treadling=repeat(POINT, 24)),
    "Goose eye": dict(
        threading=repeat(GOOSE_EYE, 28), tie_up=TWILL_2_2, treadling=repeat(GOOSE_EYE, 28)),
    "Rosepath": dict(
        threading=repeat(ROSEPATH, 32), tie_up=TWILL_2_2, treadling=repeat(ROSEPATH, 32)),
    "Rosepath, point treadled": dict(
        threading=repeat(ROSEPATH, 32), tie_up=TWILL_2_2, treadling=repeat(POINT, 24)),

    "Houndstooth": dict(
        threading=repeat(STRAIGHT, 32), tie_up=TWILL_2_2, treadling=repeat(STRAIGHT, 32),
        warp_colors=repeat(HOUNDSTOOTH, 32), weft_colors=repeat(HOUNDSTOOTH, 32)),
    "Log cabin": dict(
        threading=repeat(STRAIGHT, 32), tie_up=TABBY, treadling=repeat([1, 2], 32),
        warp_colors=repeat(LOG_CABIN, 32), weft_colors=repeat(LOG_CABIN, 32)),
    "Twill plaid": dict(
        threading=repeat(STRAIGHT, 72), tie_up=TWILL_2_2, treadling=repeat(STRAIGHT, 72),
        warp_colors=repeat(PLAID, 72), weft_colors=repeat(PLAID, 72)),

    "Monk's belt": monks_belt(),
    "Summer and winter": summer_and_winter([("A", 2), ("B", 2), ("A", 2), ("B", 2)]),
    "Overshot star": overshot([("A", 6), ("B", 4), ("C", 4), ("D", 8),
                               ("C", 4), ("B", 4), ("A", 6)]),
    "Overshot diamond": overshot([("A", 4), ("B", 4), ("C", 4), ("D", 4),
                                  ("A", 4), ("D", 4), ("C", 4), ("B", 4)]),
}
