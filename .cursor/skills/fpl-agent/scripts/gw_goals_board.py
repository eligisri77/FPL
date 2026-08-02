#!/usr/bin/env python3
"""GW1–2 goals board from external statistical projections (Prem Projections).

Not the project's internal FPL model.

Writes:
  data/gw_goals_board.json
  viewer/gw_goals_board.html
"""
from __future__ import annotations

import json
import math
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VIEWER = ROOT / "viewer"
SOURCE_URL = "https://premprojections.com/"
SOURCE_FX = "https://premprojections.com/fixtures"
UA = {"User-Agent": "EliFPL/1.0 (personal; +local viewer)"}

# Prem Projections short names → FPL short_name
NAME_MAP = {
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Bournemouth": "BOU",
    "Brentford": "BRE",
    "Brighton": "BHA",
    "Chelsea": "CHE",
    "Coventry": "COV",
    "Coventry City": "COV",
    "Everton": "EVE",
    "Forest": "NFO",
    "Nottingham Forest": "NFO",
    "Fulham": "FUL",
    "Hull": "HUL",
    "Hull City": "HUL",
    "Ipswich": "IPS",
    "Ipswich Town": "IPS",
    "Leeds": "LEE",
    "Leeds United": "LEE",
    "Liverpool": "LIV",
    "Man City": "MCI",
    "Manchester City": "MCI",
    "Man United": "MUN",
    "Manchester United": "MUN",
    "Newcastle": "NEW",
    "Newcastle United": "NEW",
    "Palace": "CRY",
    "Crystal Palace": "CRY",
    "Sunderland": "SUN",
    "Tottenham": "TOT",
    "Spurs": "TOT",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def outcome_probs(lh: float, la: float, max_goals: int = 10) -> tuple[float, float, float]:
    ph = pd = pa = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, lh) * poisson_pmf(j, la)
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
    s = ph + pd + pa or 1.0
    return ph / s, pd / s, pa / s


def recover_xg(
    p_home: float, p_draw: float, p_away: float, seed_h: float = 1.3, seed_a: float = 1.1
) -> tuple[float, float]:
    """Recover Poisson λ_home / λ_away from 1X2 probabilities (grid + refine)."""
    best = (seed_h, seed_a)
    best_err = 1e9
    for lh in [x * 0.05 for x in range(4, 81)]:  # 0.20–4.00
        for la in [x * 0.05 for x in range(4, 81)]:
            ph, pd, pa = outcome_probs(lh, la)
            err = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
            if err < best_err:
                best_err = err
                best = (lh, la)
    # local refine
    lh0, la0 = best
    for _ in range(40):
        improved = False
        for dl, da in (
            (0.02, 0),
            (-0.02, 0),
            (0, 0.02),
            (0, -0.02),
            (0.02, 0.02),
            (-0.02, -0.02),
            (0.02, -0.02),
            (-0.02, 0.02),
        ):
            lh, la = max(0.15, lh0 + dl), max(0.15, la0 + da)
            ph, pd, pa = outcome_probs(lh, la)
            err = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
            if err < best_err:
                best_err = err
                lh0, la0 = lh, la
                improved = True
        if not improved:
            break
    return round(lh0, 2), round(la0, 2)


def parse_gw1_xg(html: str) -> list[dict]:
    """Parse published home–away xG from Prem Projections homepage table."""
    rows = []
    # Aug 21</td><td class="team">Arsenal</td>...<td class="num">2.73 – 0.56</td>
    pat = re.compile(
        r'class="team">([^<]+)</td>\s*<td class="vs">vs</td>\s*'
        r'<td class="team">([^<]+)</td>.*?'
        r'class="num">(\d+\.\d+)\s*[–-]\s*(\d+\.\d+)</td>',
        re.S,
    )
    for m in pat.finditer(html):
        home, away = m.group(1).strip(), m.group(2).strip()
        xgh, xga = float(m.group(3)), float(m.group(4))
        rows.append(
            {
                "home": NAME_MAP.get(home, home),
                "away": NAME_MAP.get(away, away),
                "home_name": home,
                "away_name": away,
                "home_xg": xgh,
                "away_xg": xga,
                "match_xg": round(xgh + xga, 2),
                "xg_source": "published",
            }
        )
    return rows


def parse_gw_probs(html: str, gw: int) -> list[dict]:
    """Parse matchweek N from fixtures page: most-likely score + 1X2 %."""
    m = re.search(
        rf'id="gw-{gw}"(.*?)(?:id="gw-{gw+1}"|$)',
        html,
        flags=re.S | re.I,
    )
    if not m:
        m = re.search(
            rf"Matchweek {gw}(.*?)(?:Matchweek {gw+1}|$)",
            html,
            flags=re.S | re.I,
        )
    if not m:
        return []
    chunk = m.group(1)
    # <tr data-t="Palace|Man City">...<td class="home">Palace</td>
    # <td class="mid"><span class="sc">0–1</span></td>
    # <td class="away">Man City</td>
    # <div class="wdl-seg wdl-h" style="width:19.62%">20%</div>...
    row_pat = re.compile(
        r'<tr[^>]*data-t="([^"|]+)\|([^"]+)"[^>]*>.*?'
        r'class="sc">(\d+)\s*[–-]\s*(\d+)</span>.*?'
        r'wdl-h"[^>]*style="width:([0-9.]+)%"[^>]*>.*?'
        r'wdl-d"[^>]*style="width:([0-9.]+)%"[^>]*>.*?'
        r'wdl-a"[^>]*style="width:([0-9.]+)%"',
        re.S,
    )
    out = []
    for rm in row_pat.finditer(chunk):
        home, away = rm.group(1).strip(), rm.group(2).strip()
        sh, sa = int(rm.group(3)), int(rm.group(4))
        p_h = float(rm.group(5)) / 100.0
        p_d = float(rm.group(6)) / 100.0
        p_a = float(rm.group(7)) / 100.0
        xgh, xga = recover_xg(
            p_h, p_d, p_a, seed_h=max(0.4, sh + 0.35), seed_a=max(0.4, sa + 0.35)
        )
        out.append(
            {
                "home": NAME_MAP.get(home, home),
                "away": NAME_MAP.get(away, away),
                "home_name": home,
                "away_name": away,
                "home_xg": xgh,
                "away_xg": xga,
                "match_xg": round(xgh + xga, 2),
                "p_home": round(p_h, 3),
                "p_draw": round(p_d, 3),
                "p_away": round(p_a, 3),
                "likely_score": f"{sh}–{sa}",
                "xg_source": "recovered_from_1x2",
            }
        )
    return out


def team_leaders(matches: list[dict]) -> dict:
    scored: dict[str, float] = {}
    conceded: dict[str, float] = {}
    for m in matches:
        scored[m["home"]] = m["home_xg"]
        scored[m["away"]] = m["away_xg"]
        conceded[m["home"]] = m["away_xg"]
        conceded[m["away"]] = m["home_xg"]

    def pack(d: dict[str, float], reverse: bool, n: int = 3) -> list[dict]:
        items = sorted(d.items(), key=lambda x: (-x[1] if reverse else x[1]))
        return [{"team": t, "value": round(v, 2)} for t, v in items[:n]]

    return {
        "most_goals_teams": pack(scored, reverse=True),
        "fewest_conceded_teams": pack(conceded, reverse=False),
    }


def rank_matches(matches: list[dict], top_n: int = 3) -> tuple[list[dict], list[dict]]:
    high = [
        {**m, "rank": i}
        for i, m in enumerate(sorted(matches, key=lambda x: -x["match_xg"])[:top_n], 1)
    ]
    low = [
        {**m, "rank": i}
        for i, m in enumerate(sorted(matches, key=lambda x: x["match_xg"])[:top_n], 1)
    ]
    return high, low


def build() -> dict:
    home_html = fetch(SOURCE_URL)
    fx_html = fetch(SOURCE_FX)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "_prem_home.html").write_text(home_html, encoding="utf-8")
    (DATA / "_prem_fx.html").write_text(fx_html, encoding="utf-8")

    gw1 = parse_gw1_xg(home_html)
    if len(gw1) < 8:
        # fallback: recover GW1 from fixtures probs too
        gw1 = parse_gw_probs(fx_html, 1)

    gw2 = parse_gw_probs(fx_html, 2)
    if not gw2:
        raise SystemExit("Failed to parse GW2 from Prem Projections fixtures page")

    blocks = []
    for gw, matches in ((1, gw1), (2, gw2)):
        high, low = rank_matches(matches)
        leaders = team_leaders(matches)
        blocks.append(
            {
                "gw": gw,
                "match_count": len(matches),
                "high_scoring": high,
                "low_scoring": low,
                "most_goals_teams": leaders["most_goals_teams"],
                "fewest_conceded_teams": leaders["fewest_conceded_teams"],
                "all_matches": matches,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gws": [1, 2],
        "top_n": 3,
        "source": {
            "name": "Prem Projections",
            "url": SOURCE_URL,
            "fixtures_url": SOURCE_FX,
            "note_he": (
                "מקור חיצוני סטטיסטי (לא המודל של הפרויקט). "
                "מחזור 1: שערים צפויים כפי שפורסמו באתר. "
                "מחזור 2: שחזור פואסון מסיכויי 1X2 שפורסמו באותו מודל."
            ),
        },
        "gameweeks": blocks,
    }


def _match_rows(matches: list[dict]) -> str:
    rows = []
    for m in matches:
        rows.append(
            f"""<tr>
<td class="rank">{m['rank']}</td>
<td class="fix"><span class="home">{m['home']}</span>
<span class="vs">מול</span>
<span class="away">{m['away']}</span></td>
<td class="xg">{m['home_xg']:.2f}</td>
<td class="xg">{m['away_xg']:.2f}</td>
<td class="proj">{m['match_xg']:.2f}</td>
</tr>"""
        )
    return "".join(rows)


def _team_chips(rows: list[dict], metric_he: str) -> str:
    bits = []
    for i, r in enumerate(rows, 1):
        bits.append(
            f'<div class="chip"><span class="n">{i}</span>'
            f'<b>{r["team"]}</b>'
            f'<span class="v">≈{r["value"]:.2f} {metric_he}</span></div>'
        )
    return "".join(bits)


def write_html(payload: dict) -> Path:
    sections = []
    for block in payload["gameweeks"]:
        src_note = ""
        if block["gw"] == 1:
            src_note = '<p class="mini">מקור: xG מפורסם ב־Prem Projections</p>'
        else:
            src_note = '<p class="mini">מקור: שחזור מסיכויי 1X2 של Prem Projections</p>'
        sections.append(
            f"""
<section class="gw">
  <h2>מחזור {block['gw']}
    <span class="badge">{block['match_count']} משחקים</span>
  </h2>
  {src_note}

  <div class="teams-row">
    <div class="team-box">
      <h3>כובשות הכי הרבה</h3>
      {_team_chips(block['most_goals_teams'], 'שערים')}
    </div>
    <div class="team-box def">
      <h3>סופגות הכי מעט</h3>
      {_team_chips(block['fewest_conceded_teams'], 'נגדן')}
    </div>
  </div>

  <div class="grid">
    <div class="panel">
      <h3 class="hi">3 משחקים עם הכי הרבה שערים</h3>
      <table>
        <thead><tr>
          <th>#</th><th>משחק</th><th>בית ≈</th><th>חוץ ≈</th><th>סה״כ ≈</th>
        </tr></thead>
        <tbody>{_match_rows(block['high_scoring'])}</tbody>
      </table>
    </div>
    <div class="panel">
      <h3 class="lo">3 משחקים עם הכי מעט שערים</h3>
      <table>
        <thead><tr>
          <th>#</th><th>משחק</th><th>בית ≈</th><th>חוץ ≈</th><th>סה״כ ≈</th>
        </tr></thead>
        <tbody>{_match_rows(block['low_scoring'])}</tbody>
      </table>
    </div>
  </div>
</section>
"""
        )

    src = payload["source"]
    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>שערים צפויים (סטטיסטיקה חיצונית) — מחזורים 1–2</title>
<style>
:root {{
  --bg:#0f1410; --panel:#182018; --ink:#f2f5f0; --muted:#9aab9d;
  --accent:#c8f06c; --line:#2a3a2c; --hi:#7dd87d; --lo:#e8a87c;
}}
* {{ box-sizing: border-box; }}
body {{
  margin:0; font-family: Segoe UI, Tahoma, sans-serif;
  background:var(--bg); color:var(--ink);
}}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ margin: 0 0 6px; font-size: 1.35rem; }}
.sub {{ color: var(--muted); margin-bottom: 18px; font-size: .9rem; line-height: 1.5; }}
.badge {{
  display:inline-block; background:#243024; color:var(--accent);
  padding:3px 10px; border-radius:999px; font-weight:700; font-size:.75rem;
  margin-right:8px; vertical-align: middle;
}}
.gw {{ margin-bottom: 36px; }}
.gw h2 {{ margin: 0 0 8px; font-size: 1.25rem; }}
.mini {{ color: var(--muted); font-size: .78rem; margin: 0 0 12px; }}
.teams-row {{
  display:grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;
}}
@media (max-width: 640px) {{
  .teams-row, .grid {{ grid-template-columns: 1fr !important; }}
}}
.team-box {{
  background: var(--panel); border:1px solid var(--line);
  border-radius: 12px; padding: 12px 14px;
}}
.team-box h3 {{ margin: 0 0 10px; font-size: .85rem; color: var(--muted); font-weight: 600; }}
.chip {{
  display:flex; align-items:baseline; gap:8px; margin-bottom:8px;
}}
.chip .n {{ color: var(--accent); font-weight: 800; width: 1.2rem; }}
.chip b {{ font-size: 1.05rem; }}
.chip .v {{ color: var(--muted); font-size: .8rem; margin-right: auto; }}
.grid {{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.panel {{
  background: var(--panel); border:1px solid var(--line);
  border-radius: 12px; padding: 12px; overflow:hidden;
}}
.panel h3 {{ margin: 0 0 10px; font-size: .92rem; }}
.panel h3.hi {{ color: var(--hi); }}
.panel h3.lo {{ color: var(--lo); }}
table {{ width:100%; border-collapse: collapse; }}
th, td {{ padding: 8px 6px; text-align: right; border-bottom: 1px solid var(--line); font-size: .82rem; }}
th {{ color: var(--muted); font-weight: 600; }}
.rank {{ color: var(--accent); font-weight: 800; width: 28px; }}
.fix .vs {{ color: var(--muted); margin: 0 4px; font-size: .75rem; }}
.home {{ font-weight: 700; }}
.away {{ font-weight: 600; color: #c5d4c7; }}
.proj {{ color: var(--accent); font-weight: 800; }}
.xg {{ color: var(--muted); }}
.note {{ color: var(--muted); font-size: .78rem; margin-top: 8px; line-height: 1.5; }}
a.back, a.ext {{ color: var(--accent); text-decoration: none; font-size: .85rem; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="index.html">← חזרה</a>
  <h1>שערים צפויים — מחזורים 1–2</h1>
  <div class="sub">
    מקור חיצוני: <a class="ext" href="{src['url']}" target="_blank" rel="noopener">Prem Projections</a>
    · עודכן: {payload['generated_at'][:19].replace('T',' ')} UTC<br/>
    {src['note_he']}
  </div>
  {''.join(sections)}
  <p class="note">≈ שערים צפויים לפי המודל החיצוני. לא הבטחה.
  לרענון: <code>python .cursor/skills/fpl-agent/scripts/gw_goals_board.py</code></p>
</div>
</body>
</html>
"""
    out = VIEWER / "gw_goals_board.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    payload = build()
    out_json = DATA / "gw_goals_board.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_html = write_html(payload)
    print(f"Wrote {out_json}")
    print(f"Wrote {out_html}")
    for block in payload["gameweeks"]:
        print(f"\n=== GW{block['gw']} ({block['match_count']}) ===")
        print("כובשות:", ", ".join(f"{t['team']}≈{t['value']}" for t in block["most_goals_teams"]))
        print("סופגות מעט:", ", ".join(f"{t['team']}≈{t['value']}" for t in block["fewest_conceded_teams"]))
        print("הרבה:")
        for m in block["high_scoring"]:
            print(f"  {m['rank']}. {m['home']}–{m['away']}  {m['home_xg']}-{m['away_xg']} = {m['match_xg']}")
        print("מעט:")
        for m in block["low_scoring"]:
            print(f"  {m['rank']}. {m['home']}–{m['away']}  {m['home_xg']}-{m['away_xg']} = {m['match_xg']}")


if __name__ == "__main__":
    main()
