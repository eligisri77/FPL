#!/usr/bin/env python3
"""Horizon Ease Board — original GW3–8 fixture run ranking for Eli FPL.

Not Opta, not a raw FPL FDR dump. Composite Ease Index (0–100, higher = easier):
  - Opponent table form so far (points + position) → threat
  - Official fixture difficulty for *our* side (API team_*_difficulty) → threat
  - Team strength band (1–5 home/away) → threat
  - Home/away adjustment
  Invert blend to ease, average across GW3–8.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VIEWER = ROOT / "viewer"
GW_FROM, GW_TO = 3, 8

boot = json.loads((DATA / "bootstrap.json").read_text(encoding="utf-8"))
fx = json.loads((DATA / "fixtures.json").read_text(encoding="utf-8"))
teams = {t["id"]: t for t in boot["teams"]}

# Max points possible after 2 GWs is 6; scale gently for early season
MAX_PTS = max((t["points"] or 0) for t in teams.values()) or 6


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def opponent_threat(opp: dict, venue_for_us: str) -> float:
    """0–100 threat of facing this opponent at this venue."""
    pts = float(opp.get("points") or 0)
    pos = int(opp.get("position") or 20)
    # Form threat: high points + high table = harder
    form_threat = (pts / MAX_PTS) * 55.0 + ((21 - pos) / 20.0) * 25.0
    # Strength band 1–5 (home or away overall)
    if venue_for_us == "H":
        band = float(opp.get("strength_overall_away") or opp.get("strength") or 3)
    else:
        band = float(opp.get("strength_overall_home") or opp.get("strength") or 3)
    band_threat = (band / 5.0) * 45.0
    return 0.55 * form_threat + 0.45 * band_threat


def fixture_ease(team_id: int, f: dict) -> tuple[float, str, str, int, int]:
    if f["team_h"] == team_id:
        opp = teams[f["team_a"]]
        loc = "H"
        # Difficulty of the fixture from our perspective
        fdr = int(f.get("team_h_difficulty") or 3)
    else:
        opp = teams[f["team_h"]]
        loc = "A"
        fdr = int(f.get("team_a_difficulty") or 3)

    threat = opponent_threat(opp, loc)
    fdr_threat = (fdr / 5.0) * 100.0
    # Unique blend — not equal to FDR alone
    blended = 0.42 * threat + 0.58 * fdr_threat
    ease = 100.0 - blended
    if loc == "H":
        ease += 3.5
    else:
        ease -= 1.5
    ease = clamp(ease)
    return round(ease, 1), opp["short_name"], loc, int(f["event"]), fdr


def ease_band(ease: float) -> str:
    if ease >= 62:
        return "soft"
    if ease >= 48:
        return "mid"
    return "hard"


rows = []
for tid, t in teams.items():
    matches = []
    for f in sorted(
        [x for x in fx if x.get("event") is not None and GW_FROM <= x["event"] <= GW_TO],
        key=lambda x: (x["event"], x.get("kickoff_time") or ""),
    ):
        if f["team_h"] != tid and f["team_a"] != tid:
            continue
        ease, opp, loc, gw, fdr = fixture_ease(tid, f)
        matches.append(
            {
                "gw": gw,
                "opp": opp,
                "loc": loc,
                "label": f"{opp} ({loc})",
                "ease": ease,
                "fdr": fdr,
                "band": ease_band(ease),
            }
        )
    avg = round(sum(m["ease"] for m in matches) / max(len(matches), 1), 1)
    soft = sum(1 for m in matches if m["band"] == "soft")
    hard = sum(1 for m in matches if m["band"] == "hard")
    rows.append(
        {
            "id": tid,
            "name": t["name"],
            "short": t["short_name"],
            "table_pos": t["position"],
            "table_pts": t["points"],
            "avg_ease": avg,
            "soft_count": soft,
            "hard_count": hard,
            "matches": matches,
        }
    )

rows.sort(key=lambda r: (-r["avg_ease"], -r["soft_count"], r["hard_count"], r["short"]))

payload = {
    "title": "Horizon Ease Board",
    "subtitle": f"GW{GW_FROM}–{GW_TO} · original in-house ease (not Opta)",
    "method_en": (
        "Ease Index 0–100 (higher = easier): blend of opponent early-season form "
        "(points + table place), opponent strength band, and official FPL fixture "
        "difficulty for your side, then home/away nudge. Soft ≥62, mid 48–61, hard <48."
    ),
    "gw_from": GW_FROM,
    "gw_to": GW_TO,
    "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "teams": rows,
}

(DATA / "fixture_ease_gw3_8.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

# HTML — original layout: ranked runway strips, not Opta clone
def cell_style(band: str, ease: float) -> str:
    # Green = easy (best games), stone = mid, rust = hard — our palette
    if band == "soft":
        return f"background:#c8e6a0;color:#142010;--e:{ease}"
    if band == "mid":
        return f"background:#d9d2c5;color:#1a1814;--e:{ease}"
    return f"background:#c47a5a;color:#1a0e0a;--e:{ease}"


cards = []
for i, r in enumerate(rows, 1):
    cells = []
    for m in r["matches"]:
        cells.append(
            f'<div class="cell" style="{cell_style(m["band"], m["ease"])}">'
            f'<span class="gw">GW{m["gw"]}</span>'
            f'<span class="opp">{m["label"]}</span>'
            f'<span class="sc">{m["ease"]:.0f}</span></div>'
        )
    medal = "best" if i <= 5 else ("tough" if i > 15 else "")
    cards.append(
        f'<article class="row {medal}">'
        f'<div class="rank">{i}</div>'
        f'<div class="club"><b>{r["short"]}</b><span>{r["name"]}</span></div>'
        f'<div class="strip">{"".join(cells)}</div>'
        f'<div class="avg"><b>{r["avg_ease"]:.1f}</b><span>ease</span></div>'
        f"</article>"
    )

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>
<title>Horizon Ease Board · GW{GW_FROM}–{GW_TO}</title>
<style>
:root {{
  --bg:#12140f; --panel:#1a1e16; --ink:#eef2e8; --muted:#8f9a86;
  --line:#2c3328; --accent:#b7d96a; --paper:#e8e2d6;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"Segoe UI",Tahoma,sans-serif;
  background:var(--bg); color:var(--ink);
}}
.wrap {{ max-width:1100px; margin:0 auto; padding:22px 14px 56px; }}
a.back {{ color:var(--accent); text-decoration:none; font-size:.85rem; }}
.hero {{
  display:grid; grid-template-columns:1.4fr .8fr; gap:18px;
  margin:14px 0 22px; align-items:end;
}}
@media (max-width:800px) {{ .hero {{ grid-template-columns:1fr; }} }}
h1 {{
  margin:0; font-size:clamp(1.6rem,3vw,2.2rem); letter-spacing:-.02em;
  font-weight:800; line-height:1.1;
}}
.tag {{
  display:inline-block; margin-top:8px; padding:3px 10px; border:1px solid var(--line);
  color:var(--accent); font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
}}
.blurb {{ color:var(--muted); font-size:.88rem; line-height:1.5; margin:0; }}
.legend {{
  display:flex; flex-wrap:wrap; gap:8px; margin:0 0 14px;
}}
.legend span {{
  font-size:.72rem; font-weight:700; padding:4px 8px; border-radius:4px;
}}
.legend .soft {{ background:#c8e6a0; color:#142010; }}
.legend .mid {{ background:#d9d2c5; color:#1a1814; }}
.legend .hard {{ background:#c47a5a; color:#1a0e0a; }}
.board {{ display:flex; flex-direction:column; gap:8px; }}
.row {{
  display:grid; grid-template-columns:36px 110px 1fr 64px; gap:10px;
  align-items:center; background:var(--panel); border:1px solid var(--line);
  padding:8px 10px; border-radius:8px;
}}
.row.best {{ border-color:#4a6a28; }}
.row.tough {{ opacity:.92; }}
@media (max-width:720px) {{
  .row {{ grid-template-columns:28px 72px 1fr; }}
  .avg {{ display:none; }}
}}
.rank {{ font-weight:800; color:var(--muted); text-align:center; }}
.row.best .rank {{ color:var(--accent); }}
.club b {{ display:block; font-size:1rem; }}
.club span {{ display:block; color:var(--muted); font-size:.65rem; line-height:1.2; }}
.strip {{ display:grid; grid-template-columns:repeat(6,1fr); gap:5px; }}
.cell {{
  border-radius:5px; padding:6px 4px; text-align:center; min-height:54px;
  display:flex; flex-direction:column; justify-content:center; gap:1px;
}}
.cell .gw {{ font-size:.58rem; font-weight:700; opacity:.7; }}
.cell .opp {{ font-size:.72rem; font-weight:800; line-height:1.15; }}
.cell .sc {{ font-size:.62rem; font-weight:700; opacity:.8; }}
.avg {{ text-align:center; }}
.avg b {{ display:block; font-size:1.15rem; color:var(--accent); }}
.avg span {{ font-size:.65rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }}
.foot {{ margin-top:18px; color:var(--muted); font-size:.75rem; line-height:1.45; }}
.tops {{
  background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px;
}}
.tops h2 {{ margin:0 0 8px; font-size:.95rem; }}
.tops ol {{ margin:0; padding-inline-start:18px; color:var(--ink); font-size:.85rem; line-height:1.55; }}
.tops li b {{ color:var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="index.html">← Eli FPL</a>
  <div class="hero">
    <div>
      <h1>Horizon Ease Board</h1>
      <div class="tag">GW{GW_FROM}–{GW_TO} · Wildcard window</div>
    </div>
    <p class="blurb">{payload['method_en']}</p>
  </div>
  <div class="legend">
    <span class="soft">Soft run (best)</span>
    <span class="mid">Mixed</span>
    <span class="hard">Hard stretch</span>
  </div>
  <div class="tops">
    <h2>Best 5 club runs (target assets)</h2>
    <ol>
      {"".join(f"<li><b>{r['short']}</b> · avg ease {r['avg_ease']:.1f} · soft fixtures {r['soft_count']}/6</li>" for r in rows[:5])}
    </ol>
  </div>
  <div style="height:14px"></div>
  <div class="board">
    {"".join(cards)}
  </div>
  <p class="foot">Source: FPL API strengths + live table after GW2 + per-fixture difficulty · built for Eli FPL · updated {payload['updated']}. Higher average ease = better schedule for attacking that club’s players.</p>
</div>
</body>
</html>
"""
out_html = VIEWER / "fixture_ease_gw3_8.html"
out_html.write_text(html, encoding="utf-8")
print(f"Wrote {out_html}")
for i, r in enumerate(rows, 1):
    strip = " | ".join(f"{m['label']} {m['ease']:.0f}" for m in r["matches"])
    print(f"{i:2}. {r['short']:3} avg={r['avg_ease']:5.1f} soft={r['soft_count']}  {strip}")
