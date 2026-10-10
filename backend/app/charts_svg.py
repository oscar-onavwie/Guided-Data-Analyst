"""Tiny, dependency-free SVG charts for the exported HTML report.

The interactive app draws charts with Recharts in the browser. The exported
report must work offline as a single file, so it embeds static SVG built from
the same backend numbers.
"""

from __future__ import annotations

from html import escape

W, H = 640, 260
PAD_L, PAD_R, PAD_T, PAD_B = 70, 16, 16, 56
ACCENT = "#0f766e"
GRID = "#d4d4d8"
TEXT = "#3f3f46"


def compact(v: float) -> str:
    """Short number label for axes and bins: 1.2k, 3.4M, 12.5."""
    return _fmt(v)


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if a >= 1_000:
        return f"{v / 1_000:.1f}k"
    if float(v).is_integer():
        return f"{int(v)}"
    if a >= 100:
        return f"{v:.0f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _frame(title: str, body: str, y_min: float, y_max: float, y_label: str) -> str:
    plot_h = H - PAD_T - PAD_B
    ticks = []
    for i in range(5):
        frac = i / 4
        val = y_min + (y_max - y_min) * frac
        y = PAD_T + plot_h * (1 - frac)
        ticks.append(
            f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
            f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="{TEXT}">{escape(_fmt(val))}</text>'
        )
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{escape(title)}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="system-ui, sans-serif"><title>{escape(title)}</title>'
        + "".join(ticks)
        + body
        + f'<text x="14" y="{PAD_T + plot_h / 2:.1f}" font-size="11" fill="{TEXT}" transform="rotate(-90 14 {PAD_T + plot_h / 2:.1f})" text-anchor="middle">{escape(y_label)}</text>'
        + "</svg>"
    )


def _y_scale(values: list[float]) -> tuple[float, float]:
    lo = min(0.0, min(values)) if values else 0.0
    hi = max(values) if values else 1.0
    if hi == lo:
        hi = lo + 1
    return lo, hi


def bar_chart(title: str, labels: list[str], values: list[float | None], y_label: str) -> str:
    vals = [v if v is not None else 0.0 for v in values]
    if not vals:
        return ""
    lo, hi = _y_scale(vals)
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    n = len(vals)
    slot = plot_w / n
    bw = max(2.0, slot * 0.7)
    zero_y = PAD_T + plot_h * (1 - (0 - lo) / (hi - lo))
    parts = []
    for i, (label, v, raw) in enumerate(zip(labels, vals, values, strict=True)):
        x = PAD_L + i * slot + (slot - bw) / 2
        y = PAD_T + plot_h * (1 - (v - lo) / (hi - lo))
        top, height = (y, zero_y - y) if v >= 0 else (zero_y, y - zero_y)
        tip = f"{label}: {'no data' if raw is None else _fmt(v)}"
        parts.append(
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(0.5, height):.1f}" fill="{ACCENT}"><title>{escape(tip)}</title></rect>'
        )
        if n <= 16 or i % max(1, n // 12) == 0:
            short = label if len(label) <= 12 else label[:11] + "…"
            cx = x + bw / 2
            parts.append(
                f'<text x="{cx:.1f}" y="{H - PAD_B + 14}" font-size="10" fill="{TEXT}" text-anchor="end" transform="rotate(-35 {cx:.1f} {H - PAD_B + 14})">{escape(short)}</text>'
            )
    return _frame(title, "".join(parts), lo, hi, y_label)


def line_chart(title: str, labels: list[str], values: list[float | None], y_label: str) -> str:
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return bar_chart(title, labels, values, y_label)
    lo, hi = _y_scale(present)
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    n = len(values)
    step = plot_w / max(1, n - 1)
    segments: list[list[tuple[float, float]]] = [[]]
    dots = []
    for i, v in enumerate(values):
        if v is None:  # gap, not zero
            if segments[-1]:
                segments.append([])
            continue
        x = PAD_L + i * step
        y = PAD_T + plot_h * (1 - (v - lo) / (hi - lo))
        segments[-1].append((x, y))
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{ACCENT}"><title>{escape(labels[i])}: {escape(_fmt(v))}</title></circle>'
        )
    paths = [
        '<polyline fill="none" stroke="{c}" stroke-width="2" points="{p}"/>'.format(
            c=ACCENT, p=" ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
        )
        for seg in segments
        if len(seg) > 1
    ]
    xlabels = []
    every = max(1, n // 10)
    for i, label in enumerate(labels):
        if i % every == 0 or i == n - 1:
            x = PAD_L + i * step
            xlabels.append(
                f'<text x="{x:.1f}" y="{H - PAD_B + 14}" font-size="10" fill="{TEXT}" text-anchor="end" transform="rotate(-35 {x:.1f} {H - PAD_B + 14})">{escape(label)}</text>'
            )
    return _frame(title, "".join(paths + dots + xlabels), lo, hi, y_label)
