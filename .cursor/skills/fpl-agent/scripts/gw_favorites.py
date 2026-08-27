#!/usr/bin/env python3
"""Build GW favorites page from UK bookmaker shortest-odds (Bet365).

Writes:
  data/gw_favorites.json
  viewer/gw_favorites.html
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VIEWER = ROOT / "viewer"

# Bet365 decimal odds for current GW (sources: Bet365 via betting.bet,
# refreshed ~2026-08-27). Odds change — check live before using.
BOOKIE = "Bet365"
BOOKIE_HE = "Bet365"
GW = 2

# home, draw, away decimals
ODDS: dict[tuple[str, str], tuple[float, float, float]] = {
    ("CRY", "MCI"): (4.60, 3.90, 1.67),
    ("LIV", "NFO"): (1.53, 4.20, 5.50),
    ("BOU", "EVE"): (2.05, 3.40, 3.40),
    ("COV", "HUL"): (1.85, 3.50, 3.90),
    ("TOT", "NEW"): (2.30, 3.50, 2.90),
    ("CHE", "BHA"): (1.91, 3.70, 3.70),
    ("LEE", "BRE"): (2.50, 3.30, 2.75),
    ("SUN", "FUL"): (2.40, 3.20, 2.90),
    ("MUN", "IPS"): (1.44, 4.50, 6.50),
    ("AVL", "ARS"): (6.00, 4.00, 1.53),
}

HE_TEAM = {
    "ARS": "ארסנל",
    "AVL": "אסטון וילה",
    "BHA": "ברייטון",
    "BOU": "בורנמות׳",
    "BRE": "ברנטפורד",
    "CHE": "צ׳לסי",
    "COV": "קובנטרי",
    "CRY": "קריסטל פאלאס",
    "EVE": "אברטון",
    "FUL": "פולהאם",
    "HUL": "האל",
    "IPS": "איפסוויץ׳",
    "LEE": "לידס",
    "LIV": "ליברפול",
    "MCI": "מנצ׳סטר סיטי",
    "MUN": "מנצ׳סטר יונייטד",
    "NEW": "ניוקאסל",
    "NFO": "נוטינגהאם פורסט",
    "SUN": "סנדרלנד",
    "TOT": "טוטנהאם",
}

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
    "Fulham": "FUL",
    "Hull": "HUL",
    "Hull City": "HUL",
    "Ipswich": "IPS",
    "Ipswich Town": "IPS",
    "Leeds": "LEE",
    "Liverpool": "LIV",
    "Man City": "MCI",
    "Manchester City": "MCI",
    "Man United": "MUN",
    "Manchester United": "MUN",
    "Newcastle": "NEW",
    "Palace": "CRY",
    "Crystal Palace": "CRY",
    "Sunderland": "SUN",
    "Tottenham": "TOT",
    "Spurs": "TOT",
}


def load_likely_scores() -> dict[tuple[str, str], str]:
    home = DATA / "_prem_home.html"
    out: dict[tuple[str, str], str] = {}
    if not home.exists():
        return out
    import re

    html = home.read_text(encoding="utf-8")
    m = re.search(r"var MD=(\{.*?\});</script>", html)
    if not m:
        return out
    md = json.loads(m.group(1))
    for key, val in (md.get("fix") or {}).items():
        if "|" not in key:
            continue
        a, b = key.split("|", 1)
        ha = NAME_MAP.get(a.strip())
        aw = NAME_MAP.get(b.strip())
        ls = (val or {}).get("ls")
        if ha and aw and ls:
            out[(ha, aw)] = ls.replace("–", "-")
    return out


def pick_favorite(h: float, d: float, a: float) -> tuple[str, str, float]:
    """Return (side_code, hebrew_label, odds) for shortest price."""
    options = [
        ("H", "ניצחון בית", h),
        ("D", "תיקו", d),
        ("A", "ניצחון חוץ", a),
    ]
    side, label, odds = min(options, key=lambda x: x[2])
    return side, label, odds


def fmt_kickoff(iso: str | None) -> str:
    if not iso:
        return "—"
    # 2026-08-21T19:00:00Z → local-ish display in Israel (+3 in summer)
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        local = dt.astimezone().strftime("%a %d/%m · %H:%M")
        # Hebrew weekday light touch via English abbrev is ok in data; HTML can show ISO
        return dt.strftime("%d/%m %H:%M UTC")
    except Exception:
        return iso


def build() -> dict:
    boot = json.loads((DATA / "bootstrap.json").read_text(encoding="utf-8"))
    fx = json.loads((DATA / "fixtures.json").read_text(encoding="utf-8"))
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    full = {t["id"]: t["name"] for t in boot["teams"]}
    likely = load_likely_scores()

    rows = []
    for f in sorted(
        [x for x in fx if x.get("event") == GW],
        key=lambda x: x.get("kickoff_time") or "",
    ):
        hs = teams[f["team_h"]]
        aws = teams[f["team_a"]]
        odds = ODDS.get((hs, aws))
        if not odds:
            continue
        oh, od, oa = odds
        side, label, fav = pick_favorite(oh, od, oa)
        if side == "H":
            pick_team = HE_TEAM.get(hs, hs)
            pick_en = full[f["team_h"]]
        elif side == "A":
            pick_team = HE_TEAM.get(aws, aws)
            pick_en = full[f["team_a"]]
        else:
            pick_team = "תיקו"
            pick_en = "Draw"
        stake = 10.0
        ret = round(stake * fav, 2)
        profit = round(ret - stake, 2)
        implied = round(100.0 / fav, 1)
        rows.append(
            {
                "home": hs,
                "away": aws,
                "home_he": HE_TEAM.get(hs, hs),
                "away_he": HE_TEAM.get(aws, aws),
                "home_en": full[f["team_h"]],
                "away_en": full[f["team_a"]],
                "kickoff": f.get("kickoff_time"),
                "kickoff_label": fmt_kickoff(f.get("kickoff_time")),
                "odds_home": oh,
                "odds_draw": od,
                "odds_away": oa,
                "fav_side": side,
                "fav_label": label,
                "fav_team_he": pick_team,
                "fav_team_en": pick_en,
                "fav_odds": fav,
                "implied_pct": implied,
                "stake": stake,
                "return_on_stake": ret,
                "profit_on_stake": profit,
                "likely_score_model": likely.get((hs, aws)),
            }
        )

    payload = {
        "gw": GW,
        "bookie": BOOKIE,
        "bookie_he": BOOKIE_HE,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "note_he": (
            "לכל משחק: התוצאה (1X2) עם היחס הנמוך ביותר אצל Bet365 — "
            "כלומר ההימור שהשוק רואה כהכי סביר, והרווח הכספי עליו הוא הכי קטן. "
            "לא ייעוץ הימורים. יחסים משתנים."
        ),
        "matches": rows,
    }
    return payload


def render(payload: dict) -> str:
    cards = []
    for m in payload["matches"]:
        score = m.get("likely_score_model")
        score_html = (
            f'<div class="score">תוצאה מדויקת סבירה (Prem Projections): <b>{score}</b></div>'
            if score
            else ""
        )
        badge = {"H": "home", "D": "draw", "A": "away"}[m["fav_side"]]
        cards.append(
            f"""
<article class="card">
  <div class="when">{m['kickoff_label']}</div>
  <div class="fixture"><b>{m['home_he']}</b> מול <b>{m['away_he']}</b></div>
  <div class="meta">{m['home']}–{m['away']} · {m['home_en']} v {m['away_en']}</div>
  <div class="board">
    <div class="cell"><span>בית</span><b>{m['odds_home']:.2f}</b></div>
    <div class="cell"><span>תיקו</span><b>{m['odds_draw']:.2f}</b></div>
    <div class="cell"><span>חוץ</span><b>{m['odds_away']:.2f}</b></div>
  </div>
  <div class="fav {badge}">
    <div class="lab">הימור עם היחס הנמוך ביותר</div>
    <div class="big">{m['fav_label']} · {m['fav_team_he']}</div>
    <div class="odds">יחס {m['fav_odds']:.2f} · הסתברות משוערת ≈{m['implied_pct']}%</div>
    <div class="money">£10 → החזר £{m['return_on_stake']:.2f} (רווח £{m['profit_on_stake']:.2f})</div>
  </div>
  {score_html}
</article>"""
        )

    body = "\n".join(cards)
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>
<title>תוצאה מועדפת — מחזור {payload['gw']} · {payload['bookie_he']}</title>
<style>
:root {{
  --bg:#0f1410; --panel:#182018; --ink:#f2f5f0; --muted:#9aab9d;
  --accent:#c8f06c; --line:#2a3a2c; --home:#3d6b4a; --away:#4a5a7a; --draw:#6a5a3a;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Segoe UI, Tahoma, sans-serif; background:var(--bg); color:var(--ink); }}
.wrap {{ max-width:720px; margin:0 auto; padding:20px 14px 48px; }}
a.back {{ color:var(--accent); text-decoration:none; font-size:.85rem; }}
h1 {{ margin:10px 0 6px; font-size:1.35rem; }}
.sub {{ color:var(--muted); font-size:.9rem; line-height:1.45; margin-bottom:14px; }}
.pill {{
  display:inline-block; background:#243024; color:var(--accent);
  padding:4px 10px; border-radius:999px; font-size:.75rem; font-weight:700; margin-left:6px;
}}
.warn {{
  background:#2a2018; border:1px solid #6a4a30; color:#e8a87c;
  padding:10px 12px; border-radius:10px; margin-bottom:16px; font-size:.85rem; line-height:1.4;
}}
.card {{
  background:var(--panel); border:1px solid var(--line);
  border-radius:14px; padding:14px 14px 12px; margin-bottom:12px;
}}
.when {{ color:var(--muted); font-size:.78rem; margin-bottom:4px; }}
.fixture {{ font-size:1.1rem; margin-bottom:2px; }}
.meta {{ color:var(--muted); font-size:.75rem; margin-bottom:10px; }}
.board {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:10px; }}
.cell {{
  background:#141c14; border:1px solid var(--line); border-radius:10px;
  padding:8px; text-align:center;
}}
.cell span {{ display:block; color:var(--muted); font-size:.72rem; margin-bottom:4px; }}
.cell b {{ font-size:1.05rem; }}
.fav {{ border-radius:12px; padding:12px; border:1px solid #3a5a3c; }}
.fav.home {{ background:linear-gradient(135deg,#1c3324,#182018); }}
.fav.away {{ background:linear-gradient(135deg,#1c2438,#182018); }}
.fav.draw {{ background:linear-gradient(135deg,#33281c,#182018); }}
.fav .lab {{ color:var(--muted); font-size:.75rem; margin-bottom:4px; }}
.fav .big {{ font-size:1.15rem; font-weight:800; color:var(--accent); margin-bottom:4px; }}
.fav .odds, .fav .money {{ color:#cfe9c8; font-size:.88rem; line-height:1.4; }}
.score {{ margin-top:10px; color:var(--muted); font-size:.8rem; }}
.score b {{ color:var(--ink); }}
.foot {{ margin-top:18px; color:var(--muted); font-size:.75rem; line-height:1.45; }}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="index.html">← חזרה</a>
  <h1>תוצאה מועדפת — מחזור {payload['gw']}
    <span class="pill">{payload['bookie_he']}</span>
  </h1>
  <div class="sub">{payload['note_he']}<br/>עודכן: {payload['updated']}</div>
  <div class="warn">18+ · הימורים ממכרים · זה לוח מידע ל־FPL בלבד, לא המלצה להמר. בדקו יחסים עדכניים באפליקציה לפני כל פעולה.</div>
  {body}
  <p class="foot">מקור יחסי 1X2: {payload['bookie']} (מחזור {payload['gw']}, אוג׳ 2026). תוצאה מדויקת משלימה מ־Prem Projections — לא יחס הימורים.</p>
</div>
</body>
</html>
"""


def main() -> None:
    payload = build()
    DATA.mkdir(parents=True, exist_ok=True)
    out_json = DATA / "gw_favorites.json"
    out_html = VIEWER / "gw_favorites.html"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_html.write_text(render(payload), encoding="utf-8")
    print(f"Wrote {out_json} ({len(payload['matches'])} matches)")
    print(f"Wrote {out_html}")
    for m in payload["matches"]:
        print(
            f"{m['home']}-{m['away']}: {m['fav_label']} {m['fav_team_he']} @ {m['fav_odds']:.2f}"
        )


if __name__ == "__main__":
    main()
