"""Data model for a 4-shaft weaving draft."""

from dataclasses import dataclass, field

NUM_SHAFTS = 4
DEFAULT_WARP_COLOR = "#1f3b73"
DEFAULT_WEFT_COLOR = "#e8c872"
GROUP_SIZE = 4  # warp ends are marked off in groups of four


def _fit(colors: list[str], length: int, default: str) -> list[str]:
    """Trim or pad a colour list to the given length."""
    return list(colors[:length]) + [default] * (length - len(colors))


@dataclass
class Draft:
    """A 4-shaft weaving draft.

    threading: shaft number (1-4) for each warp end, left to right.
    tie_up:    tie_up[t] is the set of shafts (1-4) tied to treadle t+1.
    treadling: for each pick, top to bottom, the set of treadles (1-based)
               pressed. A single int is accepted and stored as a one-item set.
    warp_colors: colour ("#rrggbb") of each warp end; padded with the default.
    weft_colors: colour of each pick; padded with the default.

    Uses a rising-shed convention: tied shafts are lifted, so the warp
    shows on the face wherever its shaft is raised.
    """

    threading: list[int] = field(default_factory=list)
    tie_up: list[set[int]] = field(default_factory=list)
    treadling: list[set[int]] = field(default_factory=list)
    name: str = ""
    warp_colors: list[str] = field(default_factory=list)
    weft_colors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.tie_up = [set(shafts) for shafts in self.tie_up]
        self.treadling = [
            {pick} if isinstance(pick, int) else set(pick) for pick in self.treadling
        ]
        self.warp_colors = _fit(self.warp_colors, self.num_ends, DEFAULT_WARP_COLOR)
        self.weft_colors = _fit(self.weft_colors, self.num_picks, DEFAULT_WEFT_COLOR)
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
        return [[shaft in raised for shaft in self.threading] for raised in self.lift_plan()]

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
