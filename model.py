"""Data model for a 4-shaft weaving draft."""

from dataclasses import dataclass, field

NUM_SHAFTS = 4
DEFAULT_WARP_COLOR = "#1f3b73"
DEFAULT_WEFT_COLOR = "#e8c872"
# Thread thickness is relative: 1.0 is a standard thread, 2.0 twice as thick.
DEFAULT_THICKNESS = 1.0
MIN_THICKNESS, MAX_THICKNESS = 0.25, 4.0


def _fit(values: list, length: int, default) -> list:
    """Trim or pad a per-thread list to the given length."""
    return list(values[:length]) + [default] * (length - len(values))


def _thicknesses(value, length: int) -> list[float]:
    """Per-thread thicknesses. A single number (older drafts) applies to every thread."""
    if not isinstance(value, (list, tuple)):
        value = [value] * length
    return [float(v) for v in _fit(value, length, DEFAULT_THICKNESS)]


def format_ranges(indices: list[int]) -> str:
    """Write 0-based indices as 1-based ranges, e.g. "1-4, 9, 13-23/2"."""
    nums = sorted(i + 1 for i in indices)
    parts, i = [], 0
    while i < len(nums):
        j = i
        if i + 1 < len(nums):
            step = nums[i + 1] - nums[i]
            while j + 1 < len(nums) and nums[j + 1] - nums[j] == step:
                j += 1
            # A stepped run only reads well with at least three threads.
            if step > 1 and j - i < 2:
                j = i
        if j == i:
            parts.append(str(nums[i]))
        else:
            step = nums[i + 1] - nums[i]
            parts.append(f"{nums[i]}-{nums[j]}" + (f"/{step}" if step > 1 else ""))
        i = j + 1
    return ", ".join(parts)


def thickness_summary(values: list[float], noun: str) -> str:
    """Describe per-thread thicknesses, e.g. "2 on ends 5-8; 1 on all other ends"."""
    groups: dict[float, list[int]] = {}
    for i, v in enumerate(values):
        groups.setdefault(v, []).append(i)
    if len(groups) <= 1:
        return f"{values[0]:g} on all {noun}s" if values else f"no {noun}s"
    # List the exceptions, then the most common thickness as "all other".
    common = max(groups, key=lambda v: len(groups[v]))
    parts = [
        f"{v:g} on {noun if len(idx) == 1 else noun + 's'} {format_ranges(idx)}"
        for v, idx in sorted(groups.items()) if v != common
    ]
    parts.append(f"{common:g} on all other {noun}s")
    return "; ".join(parts)


@dataclass
class Draft:
    """A 4-shaft weaving draft.

    threading: shaft number (1-4) for each warp end, left to right.
    tie_up:    tie_up[t] is the set of shafts (1-4) tied to treadle t+1.
    treadling: for each pick, top to bottom, the set of treadles (1-based)
               pressed. A single int is accepted and stored as a one-item set.
    warp_colors: colour ("#rrggbb") of each warp end; padded with the default.
    weft_colors: colour of each pick; padded with the default.
    warp_thickness: relative thickness of each warp end (1.0 = standard);
                    padded with the default.
    weft_thickness: relative thickness of each pick.

    Uses a rising-shed convention: tied shafts are lifted, so the warp
    shows on the face wherever its shaft is raised.
    """

    threading: list[int] = field(default_factory=list)
    tie_up: list[set[int]] = field(default_factory=list)
    treadling: list[set[int]] = field(default_factory=list)
    name: str = ""
    warp_colors: list[str] = field(default_factory=list)
    weft_colors: list[str] = field(default_factory=list)
    warp_thickness: list[float] = field(default_factory=list)
    weft_thickness: list[float] = field(default_factory=list)

    def __post_init__(self):
        self.tie_up = [set(shafts) for shafts in self.tie_up]
        self.treadling = [
            {pick} if isinstance(pick, int) else set(pick) for pick in self.treadling
        ]
        self.warp_colors = _fit(self.warp_colors, self.num_ends, DEFAULT_WARP_COLOR)
        self.weft_colors = _fit(self.weft_colors, self.num_picks, DEFAULT_WEFT_COLOR)
        self.warp_thickness = _thicknesses(self.warp_thickness, self.num_ends)
        self.weft_thickness = _thicknesses(self.weft_thickness, self.num_picks)
        self.validate()

    @property
    def num_treadles(self) -> int:
        return len(self.tie_up)

    @property
    def num_ends(self) -> int:
        return len(self.threading)

    @property
    def num_picks(self) -> int:
        return len(self.treadling)

    def validate(self) -> None:
        """Raise ValueError if any shaft or treadle number is out of range."""
        for i, shaft in enumerate(self.threading, 1):
            if not 1 <= shaft <= NUM_SHAFTS:
                raise ValueError(f"end {i}: shaft {shaft} is not in 1-{NUM_SHAFTS}")
        for t, shafts in enumerate(self.tie_up, 1):
            bad = [s for s in shafts if not 1 <= s <= NUM_SHAFTS]
            if bad:
                raise ValueError(f"treadle {t}: shafts {bad} are not in 1-{NUM_SHAFTS}")
        for p, treadles in enumerate(self.treadling, 1):
            bad = [t for t in treadles if not 1 <= t <= self.num_treadles]
            if bad:
                raise ValueError(f"pick {p}: treadles {bad} are not in 1-{self.num_treadles}")
        for noun, values in (("end", self.warp_thickness), ("pick", self.weft_thickness)):
            for i, t in enumerate(values, 1):
                if not MIN_THICKNESS <= t <= MAX_THICKNESS:
                    raise ValueError(f"{noun} {i}: thickness {t:g} is not in "
                                     f"{MIN_THICKNESS:g}-{MAX_THICKNESS:g}")

    def raised_shafts(self, pick: int) -> set[int]:
        """Shafts lifted on a pick (0-based index)."""
        raised = set()
        for treadle in self.treadling[pick]:
            raised |= self.tie_up[treadle - 1]
        return raised

    def lift_plan(self, lowered: bool = False) -> list[set[int]]:
        """Tie-up and treadling combined: the shafts to move on each pick.

        By default these are the shafts to raise (rising shed). With
        lowered=True they are the shafts to sink instead - the other
        shafts - so the same face of the cloth is woven on a sinking shed.
        """
        all_shafts = set(range(1, NUM_SHAFTS + 1))
        return [
            all_shafts - raised if lowered else raised
            for raised in (self.raised_shafts(p) for p in range(self.num_picks))
        ]

    def drawdown(self) -> list[list[bool]]:
        """Grid of picks x ends; True where the warp is on top."""
        return [
            [shaft in raised for shaft in self.threading]
            for raised in (self.raised_shafts(p) for p in range(self.num_picks))
        ]

    def color_drawdown(self) -> list[list[str]]:
        """Grid of picks x ends giving the colour seen in each cell."""
        return [
            [self.warp_colors[end] if up else self.weft_colors[pick]
             for end, up in enumerate(row)]
            for pick, row in enumerate(self.drawdown())
        ]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "threading": list(self.threading),
            "tie_up": [sorted(s) for s in self.tie_up],
            "treadling": [sorted(t) for t in self.treadling],
            "warp_colors": list(self.warp_colors),
            "weft_colors": list(self.weft_colors),
            "warp_thickness": list(self.warp_thickness),
            "weft_thickness": list(self.weft_thickness),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Draft":
        return cls(
            threading=data["threading"],
            tie_up=data["tie_up"],
            treadling=data["treadling"],
            name=data.get("name", ""),
            warp_colors=data.get("warp_colors", []),
            weft_colors=data.get("weft_colors", []),
            warp_thickness=data.get("warp_thickness", []),
            weft_thickness=data.get("weft_thickness", []),
        )

    def __str__(self) -> str:
        """Text rendering: threading on top, tie-up to the right,
        treadling beside the drawdown. '#' = warp up, '.' = weft up."""
        lines = []
        for shaft in range(NUM_SHAFTS, 0, -1):
            row = "".join(str(shaft) if s == shaft else " " for s in self.threading)
            ties = "".join("X" if shaft in t else "." for t in self.tie_up)
            lines.append(f"{row} | {ties}")
        lines.append("-" * self.num_ends + "-+-" + "-" * self.num_treadles)
        for pick, row in enumerate(self.drawdown()):
            cells = "".join("#" if up else "." for up in row)
            marks = "".join(
                "o" if t in self.treadling[pick] else " "
                for t in range(1, self.num_treadles + 1)
            )
            lines.append(f"{cells} | {marks}")
        return "\n".join(lines)


if __name__ == "__main__":
    # 2/2 twill: straight draw threading, standard twill tie-up, walked treadling.
    twill = Draft(
        name="2/2 twill",
        threading=[1, 2, 3, 4] * 4,
        tie_up=[{1, 2}, {2, 3}, {3, 4}, {4, 1}],
        treadling=[1, 2, 3, 4] * 2,
    )
    print(twill.name)
    print(twill)
