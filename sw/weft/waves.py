"""ASCII waveforms and run-length traces for snapshot ("expect") tests.

Inspired by Hardcaml's waveterm expect tests: the rendered text is committed
next to the test, and any timing change shows up as a diff in code review.
"""

from __future__ import annotations


def runs(levels: list[int]) -> str:
    """Run-length encode a per-cycle level list: ``1*120 0*434 1*868``."""
    if not levels:
        return ""
    out = []
    cur, n = levels[0], 0
    for v in levels:
        if v == cur:
            n += 1
        else:
            out.append(f"{cur}*{n}")
            cur, n = v, 1
    out.append(f"{cur}*{n}")
    return " ".join(out)


def ascii(signals: dict[str, list[int]], cycles_per_col: int = 1, max_cols: int = 120, start: int = 0) -> str:
    """Render 1-bit signals as ASCII art, one character per ``cycles_per_col`` cycles.

    ``‾`` high, ``_`` low, ``/`` and ``\\`` for columns containing an edge.
    """
    width = max(len(s) for s in signals.values()) if signals else 0
    name_w = max((len(n) for n in signals), default=0)
    lines = []
    ncols = min(max_cols, (width - start + cycles_per_col - 1) // cycles_per_col)
    for name, lv in signals.items():
        row = []
        prev = lv[start] if start < len(lv) else 0
        for col in range(ncols):
            chunk = lv[start + col * cycles_per_col: start + (col + 1) * cycles_per_col]
            if not chunk:
                row.append(" ")
                continue
            if all(c == chunk[0] for c in chunk) and chunk[0] == prev:
                row.append("‾" if chunk[0] else "_")
            else:
                row.append("/" if chunk[-1] else "\\")
            prev = chunk[-1]
        lines.append(f"{name:>{name_w}} {''.join(row)}")
    scale = f"{'':>{name_w}} |{'':<{ncols - 2}}|  {ncols * cycles_per_col} cycles, {cycles_per_col}/col"
    return "\n".join(lines + [scale]) + "\n"
