#!/usr/bin/env python3
"""Top-20 projected goal scorers for the next N gameweeks.

Writes:
  data/goals_watchlist.json
  viewer/goals_watchlist.html

Re-run weekly (after fetch_data.py) to refresh.
"""
from __future__ import annotations

import json
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
    POS,
    is_banned,
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


def team_ratings(bootstrap: dict, teams: dict) -> tuple[dict[int, float], dict[int, float]]:
    """Attack strength + defence weakness (higher weak = leakier)."""
    top_att: dict[int, float] = {}
    for tid in teams:
        pool = []
        for p in bootstrap["elements"]:
            if p["team"] != tid or p["element_type"] not in (2, 3, 4):
                continue
            pool.append(float(p.get("expected_goals") or 0) + float(p.get("expected_assists") or 0))
        pool.sort(reverse=True)
        top_att[tid] = sum(pool[:6])

    att_r: dict[int, float] = {}
    def_weak: dict[int, float] = {}
    for tid, t in teams.items():
        so = ((t.get("strength_overall_home") or 3) + (t.get("strength_overall_away") or 3)) / 2
        att = so * 20 + top_att[tid] * 2
        dstr = so * 20
        if t["short_name"] in PROMOTED:
            att *= 0.55
            dstr *= 0.55
        att_r[tid] = att
        def_weak[tid] = 100 - dstr
    return _norm(att_r), _norm(def_weak)


def fixture_team_xg(
    fixtures: list[dict],
    gw_from: int,
    horizon: int,
    att_n: dict[int, float],
    weak_n: dict[int, float],
) -> dict[int, list[dict]]:
    """Per team: list of {gw, opp, home, team_xg, match_xg} for next horizon."""
    by_team: dict[int, list[dict]] = defaultdict(list)
    raw_rows = []
    for f in fixtures:
        ev = f.get("event")
        if ev is None or ev < gw_from or ev >= gw_from + horizon:
            continue
        h, a = f["team_h"], f["team_a"]
        xgh = 1.35 * (att_n[h] / 50) * (weak_n[a] / 50) * 1.12
        xga = 1.35 * (att_n[a] / 50) * (weak_n[h] / 50) * 0.95
        fdr_h = f.get("team_h_difficulty") or 3
        fdr_a = f.get("team_a_difficulty") or 3
        open_fdr = (6 - fdr_h) + (6 - fdr_a)
        mismatch = abs(att_n[h] - att_n[a])
        score = 0.65 * (xgh + xga) + 0.20 * (open_fdr / 8 * 3.5) + 0.15 * (mismatch / 30 * 1.5)
        raw_rows.append(
            {
                "gw": ev,
                "h": h,
                "a": a,
                "xgh": xgh,
                "xga": xga,
                "raw": score,
                "fdr_h": fdr_h,
                "fdr_a": fdr_a,
            }
        )
    if not raw_rows:
        return by_team
    mu = statistics.mean(r["raw"] for r in raw_rows)
    scale = 2.75 / mu if mu else 1.0
    for r in raw_rows:
        tot = r["raw"] * scale
        split = r["xgh"] + r["xga"] or 1.0
        th = r["xgh"] / split * tot
        ta = r["xga"] / split * tot
        by_team[r["h"]].append(
            {
                "gw": r["gw"],
                "opp_id": r["a"],
                "home": True,
                "team_xg": th,
                "match_xg": tot,
                "fdr": r["fdr_h"],
            }
        )
        by_team[r["a"]].append(
            {
                "gw": r["gw"],
                "opp_id": r["h"],
                "home": False,
                "team_xg": ta,
                "match_xg": tot,
                "fdr": r["fdr_a"],
            }
        )
    return by_team


def player_role(p: dict) -> str:
    """Label for UI: FWD / Wing·AM / Creator / DEF."""
    pos = p["element_type"]
    if pos == 2:
        return "DEF"
    if pos == 4:
        return "FWD"
    xg = float(p.get("expected_goals") or 0)
    goals = p.get("goals_scored") or 0
    threat = float(p.get("threat") or 0)
    creat = float(p.get("creativity") or 0)
    # Attacking mid / winger: finishes or high threat
    if threat >= 280 or xg >= 5 or goals >= 7:
        return "Wing·AM"
    if creat >= 400 and threat < 220:
        return "Creator"
    return "MID"


def player_goal_share(p: dict) -> float:
    """Share of team goals this player is projected to take (0–1-ish).

    Finishing-first: wingers / attacking mids with real goal threat compete
    with strikers (not just FWD position bias).
    """
    pos = p["element_type"]
    mins = p.get("minutes") or 0
    starts = p.get("starts") or 0
    xg = float(p.get("expected_goals") or 0)
    xg90 = float(p.get("expected_goals_per_90") or 0)
    goals = p.get("goals_scored") or 0
    threat = float(p.get("threat") or 0)
    creat = float(p.get("creativity") or 0)
    price = p["now_cost"] / 10

    # Core finishing signal — position-agnostic
    finishing = xg * 1.15 + goals * 0.45 + xg90 * 12 + threat / 70

    # Minutes reliability
    if starts >= 25:
        nail = 1.0
    elif starts >= 15:
        nail = 0.85
    elif starts >= 8:
        nail = 0.65
    elif mins >= 900:
        nail = 0.55
    else:
        nail = 0.35

    # Mild position prior (MIDs close to FWDs — wings score)
    pos_share = {1: 0.01, 2: 0.10, 3: 0.34, 4: 0.40}.get(pos, 0.2)

    # Boost proven goal-threat mids / wingers
    wing_boost = 1.0
    if pos == 3:
        if threat >= 450 or xg >= 8 or goals >= 10:
            wing_boost = 1.45
        elif threat >= 300 or xg >= 5 or goals >= 7:
            wing_boost = 1.28
        elif threat >= 200 or xg >= 3:
            wing_boost = 1.12
        # Pure creators (Bruno-ish assists) — keep some floor via price, damp pure creat
        if creat > threat * 2.2 and xg < 5 and goals < 8:
            wing_boost *= 0.72

    price_boost = 1.0
    if pos == 4 and price >= 14:
        price_boost = 1.45
    elif pos == 4 and price >= 10:
        price_boost = 1.18
    elif pos == 3 and price >= 11:
        price_boost = 1.22
    elif pos == 3 and price >= 8:
        price_boost = 1.12
    elif pos == 3 and price >= 7:
        price_boost = 1.05

    raw = finishing * nail * pos_share * price_boost * wing_boost

    # Soft floors so elite assets aren't zeroed on blank prior cards
    if pos == 4 and price >= 14:
        raw = max(raw, 11.0 * nail)
    if pos == 4 and price >= 7.5 and nail >= 0.65:
        raw = max(raw, 3.5 * nail)
    if pos == 3 and price >= 11 and nail >= 0.65:
        raw = max(raw, 7.5 * nail)
    if pos == 3 and price >= 7.5 and nail >= 0.65 and (threat >= 250 or xg >= 4 or goals >= 6):
        raw = max(raw, 5.5 * nail)
    return raw


def build_watchlist(horizon: int = DEFAULT_HORIZON, top_n: int = TOP_N) -> dict:
    profile = load_profile()
    bootstrap = load_bootstrap()
    fixtures = load_json(DATA / "fixtures.json")
    teams = teams_by_id(bootstrap)
    gw = next_gw(bootstrap)
    att_n, weak_n = team_ratings(bootstrap, teams)
    by_team = fixture_team_xg(fixtures, gw, horizon, att_n, weak_n)

    # Normalize player shares within each club so team_xg is split sensibly
    club_pools: dict[int, list[tuple[dict, float]]] = defaultdict(list)
    for p in bootstrap["elements"]:
        if p.get("status") not in ("a", "d"):
            continue
        if is_banned(p, profile["banned_players"]):
            continue
        if p["element_type"] == 1:
            continue
        share = player_goal_share(p)
        if share <= 0:
            continue
        club_pools[p["team"]].append((p, share))

    ranked = []
    for tid, pool in club_pools.items():
        fixtures_t = by_team.get(tid, [])
        if not fixtures_t:
            continue
        team_xg_sum = sum(x["team_xg"] for x in fixtures_t)
        total_share = sum(s for _, s in pool) or 1.0
        for p, share in pool:
            frac = share / total_share
            # Cap share: elite 9s still top, but wings/AMs can take large cut
            if p["element_type"] == 4:
                frac = min(frac, 0.52)
            elif p["element_type"] == 3:
                frac = min(frac, 0.42)
            else:
                frac = min(frac, 0.22)
            proj = team_xg_sum * frac
            # Availability dampen for doubtful
            if p.get("status") == "d":
                proj *= 0.7
            opp_bits = []
            for fx in sorted(fixtures_t, key=lambda x: x["gw"]):
                opp = teams[fx["opp_id"]]["short_name"]
                ha = "H" if fx["home"] else "A"
                opp_bits.append(f"GW{fx['gw']}:{opp}({ha})")
            ranked.append(
                {
                    "id": p["id"],
                    "name": p["web_name"],
                    "team": teams[tid]["short_name"],
                    "team_id": tid,
                    "pos": POS[p["element_type"]],
                    "role": player_role(p),
                    "price": p["now_cost"] / 10,
                    "own": float(p.get("selected_by_percent") or 0),
                    "status": p.get("status"),
                    "starts": p.get("starts") or 0,
                    "prior_xg": float(p.get("expected_goals") or 0),
                    "prior_goals": p.get("goals_scored") or 0,
                    "proj_goals": round(proj, 2),
                    "team_xg_horizon": round(team_xg_sum, 2),
                    "goal_share": round(frac, 3),
                    "fixtures": opp_bits,
                    "prefer": p["web_name"] in profile.get("prefer_players", []),
                }
            )

    ranked.sort(key=lambda x: (-x["proj_goals"], -x["price"]))
    top = ranked[:top_n]
    for i, row in enumerate(top, 1):
        row["rank"] = i

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gw_from": gw,
        "gw_to": gw + horizon - 1,
        "horizon": horizon,
        "top_n": top_n,
        "method": (
            "Team xG from FDR + prior GI + overall strength; "
            "split by finishing share with wing/AM boost (threat/xG/goals) — "
            "not FWD-only. Salah banned. Updated weekly."
        ),
        "players": top,
        "all_scanned": len(ranked),
    }
    return payload


def write_html(payload: dict) -> Path:
    rows = []
    for p in payload["players"]:
        prefer = " ★" if p.get("prefer") else ""
        fix = " · ".join(p["fixtures"])
        role = p.get("role") or p["pos"]
        rows.append(
            f"""<tr>
<td class="rank">{p['rank']}</td>
<td class="name">{p['name']}{prefer}</td>
<td>{p['team']}</td>
<td>{p['pos']}</td>
<td>{role}</td>
<td>£{p['price']:.1f}</td>
<td class="proj">{p['proj_goals']:.2f}</td>
<td>{p['own']:.0f}%</td>
<td>{p['prior_goals']}</td>
<td class="fix">{fix}</td>
</tr>"""
        )
    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Top {payload['top_n']} כובשים — GW{payload['gw_from']}–{payload['gw_to']}</title>
<style>
:root {{ --bg:#0f1410; --panel:#182018; --ink:#f2f5f0; --muted:#9aab9d; --accent:#c8f06c; --line:#2a3a2c; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: Segoe UI, Tahoma, sans-serif; background:var(--bg); color:var(--ink); }}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
h1 {{ margin: 0 0 6px; }}
.sub {{ color: var(--muted); margin-bottom: 18px; font-size: .92rem; }}
.badge {{ display:inline-block; background:#243024; color:var(--accent); padding:4px 10px; border-radius:999px; font-weight:700; margin-left:8px; }}
table {{ width:100%; border-collapse: collapse; background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
th, td {{ padding: 10px 8px; text-align: right; border-bottom: 1px solid var(--line); font-size: .88rem; }}
th {{ color: var(--muted); font-weight: 600; background: #141c14; position: sticky; top: 0; }}
tr:hover td {{ background: #1e2a1e; }}
.rank {{ color: var(--accent); font-weight: 800; width: 40px; }}
.name {{ font-weight: 700; }}
.proj {{ color: var(--accent); font-weight: 800; font-size: 1rem; }}
.fix {{ color: var(--muted); font-size: .72rem; max-width: 340px; }}
.note {{ color: var(--muted); font-size: .8rem; margin-top: 14px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Top {payload['top_n']} כובשים צפויים
    <span class="badge">GW{payload['gw_from']}–{payload['gw_to']}</span>
  </h1>
  <div class="sub">עודכן: {payload['generated_at'][:19].replace('T',' ')} UTC · אופק {payload['horizon']} מחזורים · ★ = prefer בפרופיל</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>שחקן</th><th>קבוצה</th><th>עמדה</th><th>תפקיד</th><th>מחיר</th>
        <th>≈גולים</th><th>בעלות</th><th>שערים*</th><th>פיקסצ׳רים</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <p class="note">*שערים = עונה קודמת/סה״כ בכרטיס. המדד ≈גולים הוא הקרנה ל־{payload['horizon']} מחזורים (לא הבטחה).
  להרצה מחדש: <code>python .cursor/skills/fpl-agent/scripts/fetch_data.py</code>
  ואז <code>python .cursor/skills/fpl-agent/scripts/goals_watchlist.py</code></p>
</div>
</body>
</html>
"""
    out = VIEWER / "goals_watchlist.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Top projected goal scorers watchlist")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--top", type=int, default=TOP_N)
    args = ap.parse_args()

    payload = build_watchlist(horizon=args.horizon, top_n=args.top)
    out_json = DATA / "goals_watchlist.json"
    save_json(out_json, payload)
    out_html = write_html(payload)

    print(f"GW{payload['gw_from']}–{payload['gw_to']} | top {payload['top_n']}")
    print(f"Wrote {out_json}")
    print(f"Wrote {out_html}")
    print()
    for p in payload["players"]:
        star = "★" if p.get("prefer") else " "
        role = p.get("role", p["pos"])
        print(
            f"{p['rank']:2}. {star} {p['name']:15} {p['team']:3} {p['pos']:3} "
            f"{role:8} £{p['price']:.1f}  ≈{p['proj_goals']:.2f}  own={p['own']:.0f}%"
        )


if __name__ == "__main__":
    main()
