#!/usr/bin/env python3
"""Enrich squad JSON with GW horizon (default 3–8): fixtures, pros/cons, xPts, unique alts."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".cursor/skills/fpl-agent/scripts"))

from fpl_lib import load_bootstrap, teams_by_id  # noqa: E402
from goals_watchlist import fixture_team_xg, team_ratings  # noqa: E402
from xpts_model import xpts  # noqa: E402

GW_FROM = 3
GW_TO = 8
HE = {
    "Suzuki": "סוזוקי",
    "Hall": "הול",
    "Hume": "יום",
    "Guéhi": "גווהי",
    "Rogers": "רוג׳רס",
    "M.Sangaré": "מ. סנגרה",
    "B.Fernandes": "ברנו",
    "Cherki": "שרקי",
    "Szoboszlai": "סובוסלאי",
    "João Pedro": "ז׳ואאו פדרו",
    "Isak": "איסאק",
    "Raya": "ראיה",
    "Wissa": "ויסה",
    "Calafiori": "קאלאפיורי",
    "N.Williams": "נ. ויליאמס",
    "Haaland": "האלאנד",
    "Semenyo": "סמניו",
    "Palmer": "פאלמר",
    "Gabriel": "גבריאל",
    "Gakpo": "גקפו",
    "Foden": "פודן",
    "Pickford": "פיקפורד",
    "Trafford": "טראפורד",
    "Donnarumma": "דונארומה",
    "Gvardiol": "גווארדיול",
    "Aina": "איינה",
    "Mitchell": "מיטשל",
    "Tonali": "טונאלי",
    "Elanga": "אילאנגה",
    "Watkins": "ווטקינס",
    "Mateta": "מאטטה",
}

PREFER = set(HE.keys()) | {"Semenyo", "Gabriel", "Guéhi", "Rogers", "Haaland"}


def load_fixtures() -> list[dict]:
    return json.loads((ROOT / "data" / "fixtures.json").read_text(encoding="utf-8"))


def fixture_xg_index(fixtures: list[dict], gw_from: int, gw_to: int) -> dict[tuple[str, int], tuple[float, float]]:
    """team short -> (team_xg, conc) per GW."""
    boot = load_bootstrap()
    att, weak = team_ratings(boot, teams_by_id(boot))
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    by_team = fixture_team_xg(fixtures, gw_from, gw_to + 1, att, weak)
    idx: dict[tuple[str, int], tuple[float, float]] = {}
    for tid, rows in by_team.items():
        short = teams[tid]
        for r in rows:
            conc = round(max(0.35, r["match_xg"] - r["team_xg"]), 2)
            idx[(short, r["gw"])] = (round(r["team_xg"], 2), conc)
    return idx


def pros_cons(
    *,
    pos: str,
    name: str,
    opp: str,
    loc: str,
    xg: float,
    conc: float,
    fdr: int,
) -> tuple[list[str], list[str]]:
    tot = xg + conc
    pros: list[str] = []
    cons: list[str] = []
    if conc <= 0.95:
        pros.append(f"סופגים מעט (≈{conc:.2f} נגד) — פוטנציאל שער נקי")
    elif conc >= 1.35:
        cons.append(f"סיכון לספוג (≈{conc:.2f} נגד)")
    if xg >= 1.55:
        pros.append(f"התקפת הקבוצה חזקה (≈{xg:.2f})")
    elif xg < 1.05 and pos in ("MID", "FWD"):
        cons.append(f"התקפה חלשה יחסית (≈{xg:.2f})")
    if tot >= 2.85:
        pros.append(f"משחק פתוח (≈{tot:.2f}) — יותר אקשן")
    elif tot <= 2.25:
        pros.append(f"משחק סגור (≈{tot:.2f}) — עוזר לשער נקי")
        if pos in ("MID", "FWD"):
            cons.append("פחות שערים/בישולים צפויים")
    if loc == "בית":
        pros.append("משחק בית")
    else:
        cons.append("משחק חוץ")
    if fdr <= 2:
        pros.append(f"יריב קל (FDR {fdr})")
    elif fdr >= 4:
        cons.append(f"יריב קשה (FDR {fdr})")
    if name == "Cherki" and opp in ("COV", "IPS", "SUN"):
        pros.append("שרקי מול יריבה נוחה")
    if name == "B.Fernandes" and loc == "בית":
        pros.append("ברנו בית — קפטנות אופציה")
    if not pros:
        pros.append("אין יתרון בולט מהמודל")
    if not cons:
        cons.append("אין חיסרון בולט מהמודל")
    return pros[:4], cons[:3]


def can_swap(out_id: int, in_p: dict, squad_ids: list[int], by_id: dict) -> bool:
    if in_p["id"] in squad_ids or in_p.get("status") not in ("a", "d"):
        return False
    if "salah" in in_p["web_name"].lower():
        return False
    rest = [by_id[i] for i in squad_ids if i != out_id]
    clubs = Counter(x["team"] for x in rest)
    if clubs[in_p["team"]] >= 3:
        return False
    if any(
        x["team"] == in_p["team"] and x["element_type"] == in_p["element_type"]
        for x in rest
    ):
        return False
    return True


def alt_candidates(
    out_id: int,
    squad_ids: list[int],
    by_id: dict,
    teams: dict,
    idx: dict[tuple[str, int], tuple[float, float]],
    gw_from: int,
    gw_to: int,
) -> list[tuple[float, float, dict]]:
    out = by_id[out_id]
    lo, hi = out["now_cost"] - 5, out["now_cost"] + 5
    pos = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    cands = []
    for p in by_id.values():
        if p["element_type"] != out["element_type"] or p["id"] == out_id:
            continue
        if not (lo <= p["now_cost"] <= hi):
            continue
        if not can_swap(out_id, p, squad_ids, by_id):
            continue
        delta = (p["now_cost"] - out["now_cost"]) / 10
        short = teams[p["team"]]["short_name"]
        horizon_pts = 0.0
        for gw in range(gw_from, gw_to + 1):
            pair = idx.get((short, gw))
            if not pair:
                continue
            txg, conc = pair
            horizon_pts += xpts(
                pos=pos[p["element_type"]],
                price=p["now_cost"] / 10,
                name=p["web_name"],
                team_xg=txg,
                conc=conc,
                pid=p["id"],
            )
        score = horizon_pts
        score += float(p.get("form") or 0) * 0.35
        score += float(p.get("selected_by_percent") or 0) * 0.02
        if p["web_name"] in PREFER:
            score += 2.0
        cands.append((score, delta, p))
    cands.sort(key=lambda x: -x[0])
    return cands


def enrich_squad(squad: dict, gw_from: int = GW_FROM, gw_to: int = GW_TO) -> dict:
    boot = load_bootstrap()
    teams = teams_by_id(boot)
    by_id = {p["id"]: p for p in boot["elements"]}
    fixtures = load_fixtures()
    idx = fixture_xg_index(fixtures, gw_from, gw_to)
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    squad_ids = squad["player_ids"]
    xi = set(squad.get("xi_ids") or [])
    cap = squad.get("captain_id")
    vice = squad.get("vice_id")

    players = []
    for pid in squad_ids:
        p = by_id[pid]
        short = teams[p["team"]]["short_name"]
        row = {
            "id": pid,
            "name": p["web_name"],
            "name_he": HE.get(p["web_name"], p["web_name"]),
            "team": short,
            "pos": pos_map[p["element_type"]],
            "price": p["now_cost"] / 10,
            "xi": pid in xi,
            "captain": pid == cap,
            "vice": pid == vice,
        }
        for gw in range(gw_from, gw_to + 1):
            pair = idx.get((short, gw))
            if not pair:
                continue
            txg, conc = pair
            # opponent from fixtures
            opp = "?"
            loc = "?"
            fdr = 3
            for f in fixtures:
                if f.get("event") != gw:
                    continue
                if f["team_h"] == p["team"]:
                    opp = teams[f["team_a"]]["short_name"]
                    loc = "בית"
                    fdr = int(f.get("team_h_difficulty") or 3)
                    break
                if f["team_a"] == p["team"]:
                    opp = teams[f["team_h"]]["short_name"]
                    loc = "חוץ"
                    fdr = int(f.get("team_a_difficulty") or 3)
                    break
            pros, cons = pros_cons(
                pos=row["pos"],
                name=p["web_name"],
                opp=opp,
                loc=loc,
                xg=txg,
                conc=conc,
                fdr=fdr,
            )
            pts = xpts(
                pos=row["pos"],
                price=row["price"],
                name=p["web_name"],
                team_xg=txg,
                conc=conc,
                pid=pid,
            )
            row[f"gw{gw}"] = {
                "opp": opp,
                "loc": loc,
                "xg": txg,
                "conc": conc,
                "tot": round(txg + conc, 2),
                "fdr": fdr,
                "pros": pros,
                "cons": cons,
                "pts": pts,
            }
        players.append(row)

    # unique alts — XI first
    order = sorted(players, key=lambda r: (0 if r.get("xi") else 1, -r["price"], r["pos"]))
    used: set[int] = set()
    for row in order:
        cands = alt_candidates(row["id"], squad_ids, by_id, teams, idx, gw_from, gw_to)
        picked = None
        for score, delta, p in cands:
            if p["id"] in used:
                continue
            picked = (delta, p)
            break
        if not picked:
            row["alt"] = None
            continue
        delta, p = picked
        used.add(p["id"])
        sign = (
            f"+£{delta:.1f}"
            if delta > 0
            else (f"£{delta:.1f}" if delta < 0 else "אותו מחיר")
        )
        alt = {
            "id": p["id"],
            "name": p["web_name"],
            "name_he": HE.get(p["web_name"], p["web_name"]),
            "team": teams[p["team"]]["short_name"],
            "pos": pos_map[p["element_type"]],
            "price": p["now_cost"] / 10,
            "delta": delta,
            "why": f"מחליף בטווח ±£0.5 · {sign} · ייחודי · GW{gw_from}–{gw_to}",
            "kind": "pm05",
        }
        for gw in range(gw_from, gw_to + 1):
            pair = idx.get((alt["team"], gw))
            if not pair:
                continue
            txg, conc = pair
            alt[f"pts_gw{gw}"] = xpts(
                pos=alt["pos"],
                price=alt["price"],
                name=alt["name"],
                team_xg=txg,
                conc=conc,
                pid=p["id"],
            )
        row["alt"] = alt

    squad["players"] = players
    squad["gw_from"] = gw_from
    squad["horizon"] = gw_to - gw_from + 1
    cost = sum(by_id[i]["now_cost"] for i in squad_ids) / 10
    squad["cost"] = round(cost, 1)
    squad["itb"] = round(100.0 - cost, 1)
    return squad


def main() -> None:
    path = ROOT / "squads" / "live.json"
    squad = json.loads(path.read_text(encoding="utf-8"))
    squad = enrich_squad(squad)
    path.write_text(json.dumps(squad, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched {path}")
    tot = 0.0
    for p in squad["players"]:
        s = sum((p.get(f"gw{g}") or {}).get("pts", 0) for g in range(GW_FROM, GW_TO + 1))
        tot += s
        print(f"  {p['name_he']:14} horizon≈{s:5.1f}")


if __name__ == "__main__":
    main()
