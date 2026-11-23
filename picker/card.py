"""Draws reports/card.svg from reports/latest.json: top 5 plus expectation vs reality.

Pure standard library, so the nightly job needs nothing extra. The SVG has its own
dark background, so it reads the same on GitHub light and dark themes.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from . import config as C

W = 900
BG, PANEL, INK, MUTED, LINE = "#0f0f1e", "#181830", "#f4f4f8", "#9a9ab5", "#2a2a48"
ACCENT, UP, DOWN = "#7c6cf0", "#2ecc8f", "#ff6b6b"


def _t(x, y, s, size=14, fill=INK, anchor="start", weight="normal"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{escape(str(s))}</text>')


def _pct(v, digits=2):
    return "-" if v is None else f"{v:+.{digits}f}%"


def _num(v):
    return "-" if v is None else f"{v:,.2f}"


def build_svg(data: dict) -> str:
    picks = data.get("picks") or []
    hist = data.get("history") or []
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} H_PLACEHOLDER" '
         f'width="{W}" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
         f'<rect width="{W}" height="H_PLACEHOLDER" rx="14" fill="{BG}"/>']

    target = data.get("target_date") or "-"
    asof = data.get("asof_date") or "-"
    gen = (data.get("generated_at") or "")[:16].replace("T", " ")
    o.append(_t(28, 40, "NSE LLM Picker", 22, INK, weight="bold"))
    o.append(_t(28, 62, f"Top 5 for session {target}  |  based on close of {asof}  |  updated {gen} IST",
                12.5, MUTED))
    o.append(_t(W - 28, 40, "experiment, not investment advice", 11, MUTED, "end"))

    # ---- top 5 table
    y = 86
    cols = [(28, "#", "start"), (60, "Symbol", "start"), (250, "Ref close", "end"),
            (335, "Expected", "end"), (425, "Target", "end"), (515, "Stop", "end"),
            (580, "P(up)", "end"), (625, "Combined", "start")]
    o.append(f'<rect x="16" y="{y}" width="{W - 32}" height="{34 + 38 * max(len(picks), 1)}" rx="10" fill="{PANEL}"/>')
    for x, label, anc in cols:
        o.append(_t(x, y + 24, label, 11.5, MUTED, anc, "bold"))
    ry = y + 34
    for p in picks[:5]:
        o.append(f'<line x1="28" x2="{W - 28}" y1="{ry}" y2="{ry}" stroke="{LINE}"/>')
        base = ry + 25
        o.append(_t(28, base, p["rank"], 14, ACCENT, weight="bold"))
        o.append(_t(60, base, p["symbol"], 14, INK, weight="bold"))
        o.append(_t(250, base, _num(p.get("ref_close")), 13, INK, "end"))
        e = p.get("exp_ret_pct")
        o.append(_t(335, base, _pct(e), 13, UP if (e or 0) >= 0 else DOWN, "end", "bold"))
        o.append(_t(425, base, _num(p.get("target_price")), 13, INK, "end"))
        o.append(_t(515, base, _num(p.get("stop_price")), 13, INK, "end"))
        pu = p.get("p_up")
        o.append(_t(580, base, "-" if pu is None else f"{pu * 100:.0f}%", 13, INK, "end"))
        comb = p.get("combined") or 0
        frac = max(0.0, min(1.0, abs(comb)))
        col = UP if comb >= 0 else DOWN
        o.append(f'<rect x="625" y="{base - 11}" width="170" height="10" rx="5" fill="{LINE}"/>')
        o.append(f'<rect x="625" y="{base - 11}" width="{170 * frac:.0f}" height="10" rx="5" fill="{col}"/>')
        o.append(_t(806, base - 2, f"{comb:+.2f}", 12.5, INK))
        ry += 38
    if not picks:
        o.append(_t(W / 2, y + 62, "No picks yet. The first run happens after a market close.", 13, MUTED, "middle"))
    y = ry + 28 if picks else y + 34 + 38 + 28

    # ---- expectation vs reality: all five picks of the latest scored session
    o.append(_t(28, y, "Expectation vs reality", 17, INK, weight="bold"))
    y += 14
    last = hist[0]["target_date"] if hist else None
    rows = sorted([h for h in hist if h.get("target_date") == last], key=lambda r: r.get("rank") or 99)[:5]
    if not rows:
        o.append(f'<rect x="16" y="{y}" width="{W - 32}" height="64" rx="10" fill="{PANEL}"/>')
        o.append(_t(32, y + 26, f"No session has been scored yet. The first result appears after the {target} close.",
                    13, INK))
        o.append(_t(32, y + 47, "Each pick is logged before the open, then compared with the real close.", 12, MUTED))
        y += 64
    else:
        def avg(key):
            v = [r[key] for r in rows if r.get(key) is not None]
            return sum(v) / len(v) if v else None
        hits = sum(1 for r in rows if r.get("dir_hit"))
        errs = [abs(r["error_pp"]) for r in rows if r.get("error_pp") is not None]
        err = sum(errs) / len(errs) if errs else None
        tiles = [("Session scored", str(last)),
                 ("Direction right", f"{hits} of {len(rows)}"),
                 ("Avg expected", _pct(avg("exp_ret_pct"))),
                 ("Avg actual", _pct(avg("act_ret_pct"))),
                 ("Avg error", "-" if err is None else f"{err:.2f} pp")]
        tw = (W - 32 - 4 * 10) / 5
        for i, (lab, val) in enumerate(tiles):
            x = 16 + i * (tw + 10)
            o.append(f'<rect x="{x:.0f}" y="{y}" width="{tw:.0f}" height="62" rx="10" fill="{PANEL}"/>')
            o.append(_t(x + 14, y + 22, lab, 11.5, MUTED))
            o.append(_t(x + 14, y + 49, val, 18 if i == 0 else 20, INK, weight="bold"))
        y += 62

        y += 18
        o.append(_t(28, y, f"Latest scored picks ({last}): expected (grey) vs actual (colour), % move", 12.5, MUTED))
        y += 10
        hi = max([abs(r.get("exp_ret_pct") or 0) for r in rows] +
                 [abs(r.get("act_ret_pct") or 0) for r in rows] + [1.0])
        o.append(f'<rect x="16" y="{y}" width="{W - 32}" height="{14 + 44 * len(rows)}" rx="10" fill="{PANEL}"/>')
        mid, scale = 430, 130 / hi
        by = y + 10
        for r in rows:
            ex, ac = r.get("exp_ret_pct") or 0, r.get("act_ret_pct")
            o.append(_t(32, by + 24, f"#{r.get('rank')}  {r['symbol']}", 13, INK, weight="bold"))
            o.append(f'<line x1="{mid}" x2="{mid}" y1="{by + 2}" y2="{by + 38}" stroke="{LINE}"/>')
            o.append(f'<rect x="{mid if ex >= 0 else mid + ex * scale:.0f}" y="{by + 6}" '
                     f'width="{abs(ex) * scale:.0f}" height="11" rx="3" fill="#6b6b8a"/>')
            if ac is not None:
                o.append(f'<rect x="{mid if ac >= 0 else mid + ac * scale:.0f}" y="{by + 21}" '
                         f'width="{abs(ac) * scale:.0f}" height="11" rx="3" fill="{UP if ac >= 0 else DOWN}"/>')
            hit = r.get("dir_hit")
            tag = "" if hit is None else ("direction right" if hit else "direction wrong")
            o.append(_t(W - 32, by + 24, f"{_pct(ex)} vs {_pct(ac)}  {tag}", 12.5,
                        MUTED if hit is None else (UP if hit else DOWN), "end"))
            by += 44
        y = by + 4

    h = int(y + 30)
    o.append(_t(28, h - 12, "github.com/NANDAN-CREATOR/nse-llm-picker  |  rebuilt after every nightly run", 11, MUTED))
    o.append("</svg>")
    return "\n".join(o).replace("H_PLACEHOLDER", str(h))


def write_card(src: Path | None = None, out: Path | None = None) -> Path:
    src = Path(src or C.REPORT_DIR / "latest.json")
    out = Path(out or C.REPORT_DIR / "card.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_svg(json.loads(src.read_text())), encoding="utf-8")
    return out
