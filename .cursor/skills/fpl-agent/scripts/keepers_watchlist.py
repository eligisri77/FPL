#!/usr/bin/env python3
"""Top projected goalkeepers for the next N gameweeks.

Writes:
  data/keepers_watchlist.json
  viewer/keepers_watchlist.html

Re-run weekly (after fetch_data.py) to refresh.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fpl_lib import (  # noqa: E402
    load_bootstrap,
    load_json,
    load_profile,
    next_gw,
    save_json,
    teams_by_id,
)

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
VIEWER = ROOT / "viewer"
DEFAULT_HORIZON = 5
TOP_N = 20
PROMOTED = {"COV", "HUL", "IPS", "SUN"}


def _norm(d: dict[int, float]) -> dict[int, float]:
    vals = list(d.values())
    mu = statistics.mean(vals)
    sd = statistics.pstdev(vals) or 1.0
    return {k: 50.0 + (v - mu) / sd * 15.0 for k, v in d.items()}


def team_defence_strength(bootstrap: dict, teams: dict) -> dict[int, float]:
    """Higher = better defence (more CS likely)."""
    raw: dict[int, float] = {}
    for tid, t in teams.items():
        so = ((t.get("strength_overall_home") or 3) + (t.get("strength_overall_away") or 3)) / 2
        # Prior CS among club GKs
        cs = 0
        mins = 0
        xgc = 0.0
        for p in bootstrap["elements"]:
            if p["team"] != tid or p["element_type"] != 1:
                continue
            cs += p.get("clean_sheets") or 0
            mins += p.get("minutes") or 0
            xgc += float(p.get("expected_goals_conceded") or 0)
        cs_rate = (cs / max(mins / 90, 1)) if mins else 0.25
        score = so * 22 + cs_rate * 40 - xgc * 0.35
        if t["short_name"] in PROMOTED:
            score *= 0.72
        raw[tid] = score
    return _norm(raw)


def fixture_cs_and_saves(
    fixtures: list[dict],
    gw_from: int,
    horizon: int,
    def_n: dict[int, float],
    att_n: dict[int, float],
) -> dict[int, list[dict]]:
    """Per team: projected CS prob + expected saves proxy for each GW."""
    by_team: dict[int, list[dict]] = defaultdict(list)
    for f in fixtures:
        ev = f.get("event")
        if ev is None or ev < gw_from or ev >= gw_from + horizon:
            continue
        h, a = f["team_h"], f["team_a"]
        fdr_h = f.get("team_h_difficulty") or 3
        fdr_a = f.get("team_a_difficulty") or 3

        # CS probability from defence vs opponent attack + FDR
        # Baseline ~28% PL CS rate; scale by relative strength
        for tid, opp, home, fdr in (
            (h, a, True, fdr_h),
            (a, h, False, fdr_a),
        ):
            d = def_n[tid] / 50
            oa = att_n[opp] / 50
            fdr_factor = (6 - fdr) / 3  # easy fixtures → higher
            home_b = 1.08 if home else 0.95
            cs_p = 0.26 * d / max(oa, 0.55) * fdr_factor * home_b
            cs_p = max(0.05, min(0.62, cs_p))
            # Saves rise when facing stronger attack / worse defence
            saves = 2.2 + 1.8 * oa / max(d, 0.6) + (0.4 if not home else 0.0)
            saves = max(1.5, min(6.5, saves))
            # Goals conceded proxy for -1/2
            gc = 1.15 * oa / max(d, 0.55) * (0.92 if home else 1.05)
            gc = max(0.4, min(2.8, gc))
            by_team[tid].append(
                {
                    "gw": ev,
                    "opp_id": opp,
                    "home": home,
                    "fdr": fdr,
                    "cs_p": cs_p,
                    "saves": saves,
                    "gc": gc,
                }
            )
    return by_team


def attack_norm(bootstrap: dict, teams: dict) -> dict[int, float]:
    raw: dict[int, float] = {}
    for tid, t in teams.items():
        so = ((t.get("strength_overall_home") or 3) + (t.get("strength_overall_away") or 3)) / 2
        gi = 0.0
        for p in bootstrap["elements"]:
            if p["team"] != tid or p["element_type"] not in (3, 4):
                continue
            gi += float(p.get("expected_goals") or 0) + float(p.get("expected_assists") or 0)
        score = so * 18 + gi * 0.9
        if t["short_name"] in PROMOTED:
            score *= 0.6
        raw[tid] = score
    return _norm(raw)


def build_watchlist(horizon: int = DEFAULT_HORIZON, top_n: int = TOP_N) -> dict:
    profile = load_profile()
    bootstrap = load_bootstrap()
    fixtures = load_json(DATA / "fixtures.json")
    teams = teams_by_id(bootstrap)
    gw = next_gw(bootstrap)
    def_n = team_defence_strength(bootstrap, teams)
    att_n = attack_norm(bootstrap, teams)
    by_team = fixture_cs_and_saves(fixtures, gw, horizon, def_n, att_n)

    ranked = []
    for p in bootstrap["elements"]:
        if p["element_type"] != 1:
            continue
        if p.get("status") not in ("a", "d"):
            continue
        if not p.get("can_select", True):
            continue
        tid = p["team"]
        fx = by_team.get(tid, [])
        if not fx:
            continue

        starts = p.get("starts") or 0
        mins = p.get("minutes") or 0
        if starts >= 28:
            nail = 1.0
        elif starts >= 18:
            nail = 0.88
        elif starts >= 8:
            nail = 0.65
        elif mins >= 600:
            nail = 0.45
        else:
            nail = 0.25  # backup / unproven

        prior_saves = p.get("saves") or 0
        prior_cs = p.get("clean_sheets") or 0
        prior_ps = p.get("penalties_saved") or 0
        prior_gc = p.get("goals_conceded") or 0
        prior_pts = p.get("total_points") or 0
        prior_games = max(starts, 1)
        saves_per_game = prior_saves / prior_games if starts else 3.0
        # Blend projected saves with prior rate
        save_blend = 0.55

        proj_pts = 0.0
        opp_bits = []
        sum_cs = 0.0
        sum_saves = 0.0
        sum_gc = 0.0
        for row in sorted(fx, key=lambda x: x["gw"]):
            # Appearance 2 pts if nailed
            app = 2.0 * nail
            cs = 4.0 * row["cs_p"] * nail
            sav = row["saves"] * (1 - save_blend) + saves_per_game * save_blend
            sav_pts = (sav / 3.0) * nail
            gc_pen = -(row["gc"] / 2.0) * nail
            # Rare pen save prior (~0.03–0.08 / game for busy GKs)
            pen = (prior_ps / prior_games) * 5.0 * nail if starts else 0.02 * 5
            # Soft bonus proxy
            bonus = 0.18 * nail * (1.15 if row["cs_p"] > 0.35 else 1.0)
            gw_pts = app + cs + sav_pts + gc_pen + pen + bonus
            proj_pts += gw_pts
            sum_cs += row["cs_p"] * nail
            sum_saves += sav * nail
            sum_gc += row["gc"] * nail
            opp = teams[row["opp_id"]]["short_name"]
            ha = "H" if row["home"] else "A"
            opp_bits.append(f"GW{row['gw']}:{opp}({ha})")

        if p.get("status") == "d":
            proj_pts *= 0.7
            nail *= 0.7

        # Tiny prior-season quality nudge so elite CS GKs rank up
        if prior_pts >= 140 and starts >= 30:
            proj_pts *= 1.06
        elif prior_pts >= 120 and starts >= 28:
            proj_pts *= 1.03

        ranked.append(
            {
                "id": p["id"],
                "name": p["web_name"],
                "team": teams[tid]["short_name"],
                "team_id": tid,
                "pos": "GK",
                "price": p["now_cost"] / 10,
                "own": float(p.get("selected_by_percent") or 0),
                "status": p.get("status"),
                "starts": starts,
                "prior_pts": prior_pts,
                "prior_cs": prior_cs,
                "prior_saves": prior_saves,
                "prior_ps": prior_ps,
                "prior_gc": prior_gc,
                "proj_pts": round(proj_pts, 2),
                "proj_cs": round(sum_cs, 2),
                "proj_saves": round(sum_saves, 1),
                "proj_gc": round(sum_gc, 2),
                "nail": round(nail, 2),
                "fixtures": opp_bits,
                "pts_per_m": round(proj_pts / max(p["now_cost"] / 10, 0.1), 2),
                "prefer": p["web_name"] in profile.get("prefer_players", []),
            }
        )

    ranked.sort(key=lambda x: (-x["proj_pts"], x["price"]))
    # Prefer first-choice: if two from same club, keep higher proj / nail
    seen_club: set[str] = set()
    filtered = []
    for row in ranked:
        if row["team"] in seen_club and row["nail"] < 0.6:
            continue
        if row["team"] in seen_club:
            continue
        seen_club.add(row["team"])
        filtered.append(row)
    # If we filtered too hard, fall back
    use = filtered if len(filtered) >= top_n else ranked
    top = use[:top_n]
    for i, row in enumerate(top, 1):
        row["rank"] = i

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gw_from": gw,
        "gw_to": gw + horizon - 1,
        "horizon": horizon,
        "top_n": top_n,
        "method": (
            "Projected FPL pts over horizon: 2 app + 4×CS_prob + saves/3 "
            "− GC/2 + pen-save prior + soft bonus; FDR + team strength. "
            "One GK per club in table."
        ),
        "scoring_rules": {
            "appearance_60": 2,
            "clean_sheet": 4,
            "per_3_saves": 1,
            "penalty_save": 5,
            "per_2_conceded": -1,
        },
        "players": top,
        "all_scanned": len(ranked),
    }


def write_html(payload: dict) -> Path:
    rows = []
    for p in payload["players"]:
        prefer = " ★" if p.get("prefer") else ""
        fix = " · ".join(p["fixtures"])
        flag = " ⚠" if p.get("status") == "d" else ""
        rows.append(
            f"""<tr>
<td class="rank">{p['rank']}</td>
<td class="name">{p['name']}{prefer}{flag}</td>
<td>{p['team']}</td>
<td>£{p['price']:.1f}</td>
<td class="proj">{p['proj_pts']:.1f}</td>
<td>{p['proj_cs']:.2f}</td>
<td>{p['proj_saves']:.0f}</td>
<td>{p['prior_pts']}</td>
<td>{p['prior_cs']}</td>
<td>{p['prior_saves']}</td>
<td>{p['prior_ps']}</td>
<td>{p['own']:.0f}%</td>
<td class="fix">{fix}</td>
</tr>"""
        )
    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Top {payload['top_n']} שוערים — GW{payload['gw_from']}–{payload['gw_to']}</title>
<style>
:root {{ --bg:#0f1410; --panel:#182018; --ink:#f2f5f0; --muted:#9aab9d; --accent:#c8f06c; --line:#2a3a2c; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: Segoe UI, Tahoma, sans-serif; background:var(--bg); color:var(--ink); }}
.wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
h1 {{ margin: 0 0 6px; }}
.sub {{ color: var(--muted); margin-bottom: 18px; font-size: .92rem; }}
.badge {{ display:inline-block; background:#243024; color:var(--accent); padding:4px 10px; border-radius:999px; font-weight:700; margin-left:8px; }}
.rules {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 14px; margin-bottom:16px; font-size:.82rem; color:var(--muted); line-height:1.55; }}
.rules b {{ color:var(--accent); }}
table {{ width:100%; border-collapse: collapse; background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
th, td {{ padding: 10px 8px; text-align: right; border-bottom: 1px solid var(--line); font-size: .85rem; }}
th {{ color: var(--muted); font-weight: 600; background: #141c14; position: sticky; top: 0; }}
tr:hover td {{ background: #1e2a1e; }}
.rank {{ color: var(--accent); font-weight: 800; width: 40px; }}
.name {{ font-weight: 700; }}
.proj {{ color: var(--accent); font-weight: 800; font-size: 1rem; }}
.fix {{ color: var(--muted); font-size: .7rem; max-width: 320px; }}
.note {{ color: var(--muted); font-size: .8rem; margin-top: 14px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Top {payload['top_n']} שוערים צפויים
    <span class="badge">GW{payload['gw_from']}–{payload['gw_to']}</span>
  </h1>
  <div class="sub">עודכן: {payload['generated_at'][:19].replace('T',' ')} UTC · אופק {payload['horizon']} מחזורים · ⚠ = ספק כשירות</div>
  <div class="rules">
    <b>ניקוד שוער:</b>
    60+ דק׳ = 2 · שער נקי = +4 · כל 3 עצירות = +1 · עצירת פנדל = +5 ·
    כל 2 ספיגות = −1 · בונוס BPS = +1–3
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>שוער</th><th>קבוצה</th><th>מחיר</th>
        <th>≈נק׳</th><th>≈CS</th><th>≈עצירות</th>
        <th>נק׳*</th><th>CS*</th><th>עצירות*</th><th>פנד׳*</th>
        <th>בעלות</th><th>פיקסצ׳רים</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <p class="note">* = עונה קודמת. ≈נק׳ / ≈CS / ≈עצירות = הקרנה ל־{payload['horizon']} מחזורים (מודל FDR+חוזק הגנה+קצב עצירות).
  להרצה מחדש: <code>python .cursor/skills/fpl-agent/scripts/fetch_data.py</code>
  ואז <code>python .cursor/skills/fpl-agent/scripts/keepers_watchlist.py</code></p>
</div>
</body>
</html>
"""
    out = VIEWER / "keepers_watchlist.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Top projected goalkeepers watchlist")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--top", type=int, default=TOP_N)
    args = ap.parse_args()

    payload = build_watchlist(horizon=args.horizon, top_n=args.top)
    out_json = DATA / "keepers_watchlist.json"
    save_json(out_json, payload)
    out_html = write_html(payload)

    print(f"GW{payload['gw_from']}–{payload['gw_to']} | top {payload['top_n']}")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_html}")
    print()
    for p in payload["players"]:
        print(
            f"{p['rank']:2}. {p['name']:16} {p['team']:3} £{p['price']:.1f}  "
            f"≈{p['proj_pts']:.1f}pts  CS≈{p['proj_cs']:.2f}  "
            f"sav≈{p['proj_saves']:.0f}  own={p['own']:.0f}%"
        )


if __name__ == "__main__":
    main()
