#!/usr/bin/env python3
"""Eli FPL expected-points model for GW1–2 (not official FPL ep_next).

Uses Prem Projections team xG / xGC already stored on each player, official
scoring, Poisson CS, role shares, and DEFCON hit rates.
Points are **per player, not captained**.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))

GOAL_PTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
CS_PTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
YELLOW = {"GK": -0.04, "DEF": -0.14, "MID": -0.12, "FWD": -0.08}

# xG share of team attack, xA share of team attack, role
ROLE: dict[int, tuple[float, float, str]] = {
    411: (0.48, 0.08, "st"),  # Haaland
    379: (0.34, 0.10, "st"),  # Isak
    165: (0.30, 0.12, "st"),  # João Pedro
    106: (0.32, 0.08, "st"),  # Thiago BRE
    367: (0.16, 0.12, "w"),  # Gakpo
    469: (0.04, 0.12, "fb"),  # N.Williams
    491: (0.28, 0.08, "st"),  # Igor Jesus
    25: (0.36, 0.08, "st"),  # Gyökeres
    552: (0.32, 0.06, "st"),  # Brobbey
    426: (0.14, 0.22, "am"),  # Bruno
    154: (0.18, 0.20, "am"),  # Palmer
    427: (0.20, 0.12, "cf"),  # Mbeumo
    480: (0.12, 0.16, "am"),  # Gibbs-White
    557: (0.12, 0.14, "w"),  # Tzolis
    208: (0.14, 0.10, "w"),  # Sarr
    455: (0.04, 0.08, "dm"),  # Tonali
    159: (0.03, 0.06, "dm"),  # Caicedo
    551: (0.08, 0.08, "cm"),  # Angulo
    127: (0.08, 0.10, "cm"),  # Gomez
    4: (0.03, 0.04, "cb"),  # Gabriel
    8: (0.05, 0.10, "fb"),  # Calafiori
    175: (0.04, 0.10, "fb"),  # van Ewijk
    473: (0.04, 0.12, "fb"),  # Aina
    502: (0.03, 0.12, "fb"),  # Robertson
    391: (0.04, 0.06, "cb"),  # Gvardiol
    334: (0.02, 0.03, "cb"),
    332: (0.03, 0.08, "fb"),  # Justin
    534: (0.03, 0.10, "fb"),  # Hume
    418: (0.02, 0.03, "cb"),  # Maguire
    539: (0.02, 0.03, "cb"),
    87: (0.02, 0.03, "cb"),
    259: (0.02, 0.03, "cb"),
    1: (0.002, 0.002, "gk"),  # Raya
    412: (0.002, 0.002, "gk"),
    57: (0.002, 0.002, "gk"),
    109: (0.002, 0.002, "gk"),
}

DEFCON = {
    "gk": 0.0,
    "cb": 0.48,
    "fb": 0.22,
    "dm": 0.40,
    "cm": 0.28,
    "am": 0.08,
    "w": 0.08,
    "cf": 0.06,
    "st": 0.04,
}


def default_role(pos: str, price: float, name: str) -> tuple[float, float, str]:
    n = (name or "").lower()
    if pos == "GK":
        return 0.002, 0.002, "gk"
    if pos == "FWD":
        if price >= 14:
            return 0.48, 0.08, "st"
        if price >= 8.5:
            return 0.34, 0.10, "st"
        if price >= 6.5:
            return 0.30, 0.08, "st"
        return 0.26, 0.06, "st"
    if pos == "MID":
        if price >= 11:
            return 0.16, 0.22, "am"
        if price >= 7.5:
            return 0.14, 0.14, "am"
        if price >= 6.0:
            return 0.11, 0.12, "w"
        if any(x in n for x in ("caicedo", "tonali", "rice", "palhinha")):
            return 0.04, 0.07, "dm"
        return 0.05, 0.07, "dm"
    # DEF
    if any(x in n for x in ("calafiori", "aina", "robertson", "ewijk", "gvardiol")):
        return 0.04, 0.10, "fb"
    if price >= 5.5:
        return 0.04, 0.08, "fb"
    return 0.02, 0.03, "cb"


def xpts(
    *,
    pos: str,
    price: float,
    name: str,
    team_xg: float,
    conc: float,
    pid: int | None = None,
) -> float:
    got = ROLE.get(pid) if pid is not None else None
    if got is None:
        xg_s, xa_s, role = default_role(pos, price, name)
    else:
        xg_s, xa_s, role = got
    p_xg = team_xg * xg_s
    p_xa = team_xg * xa_s
    appear = 2.0
    goals = p_xg * GOAL_PTS[pos]
    assists = p_xa * 3.0
    p_cs = math.exp(-max(0.05, conc))
    mins60 = 0.94
    cs = mins60 * p_cs * CS_PTS[pos]
    gc = -0.5 * conc if pos in ("GK", "DEF") else 0.0
    saves = (2.3 + 0.9 * conc) / 3.0 if pos == "GK" else 0.0
    dc = 2.0 * DEFCON.get(role, 0.08)
    bonus = min(1.15, 0.11 * (goals + assists + cs + (saves if pos == "GK" else 0)))
    cards = YELLOW[pos]
    total = appear + goals + assists + cs + gc + saves + dc + bonus + cards
    return round(max(0.4, total), 1)


def team_xg_index(players: list[dict]) -> dict[tuple[str, int], tuple[float, float]]:
    idx: dict[tuple[str, int], tuple[float, float]] = {}
    for p in players:
        for gw, key in ((1, "gw1"), (2, "gw2")):
            g = p.get(key) or {}
            if "xg" in g and "conc" in g:
                idx[(p["team"], gw)] = (float(g["xg"]), float(g["conc"]))
    return idx


def fill_alt_index(
    idx: dict[tuple[str, int], tuple[float, float]],
) -> dict[tuple[str, int], tuple[float, float]]:
    """Add missing clubs from Prem Projections parser / recovered 1X2."""
    try:
        from gw_goals_board import (  # type: ignore
            NAME_MAP,
            parse_gw1_xg,
            parse_gw_probs,
        )
    except Exception:
        return idx
    home = ROOT / "data" / "_prem_home.html"
    fx = ROOT / "data" / "_prem_fx.html"
    extra: dict[tuple[str, int], tuple[float, float]] = {}
    if home.exists():
        for m in parse_gw1_xg(home.read_text(encoding="utf-8")):
            extra[(m["home"], 1)] = (m["home_xg"], m["away_xg"])
            extra[(m["away"], 1)] = (m["away_xg"], m["home_xg"])
    if fx.exists():
        for m in parse_gw_probs(fx.read_text(encoding="utf-8"), 2):
            extra[(m["home"], 2)] = (m["home_xg"], m["away_xg"])
            extra[(m["away"], 2)] = (m["away_xg"], m["home_xg"])
    extra.update(idx)  # squad numbers win (already aligned)
    return extra


def apply_squad(path: Path) -> dict:
    squad = json.loads(path.read_text(encoding="utf-8"))
    idx = fill_alt_index(team_xg_index(squad.get("players") or []))
    rows = []
    for p in squad.get("players") or []:
        pid = p["id"]
        for key in ("gw1", "gw2"):
            g = p.get(key)
            if not g:
                continue
            g["pts"] = xpts(
                pos=p["pos"],
                price=float(p["price"]),
                name=p.get("name") or "",
                team_xg=float(g["xg"]),
                conc=float(g["conc"]),
                pid=pid,
            )
        alt = p.get("alt")
        if alt:
            aid = alt.get("id")
            team = alt["team"]
            pos = alt["pos"]
            price = float(alt["price"])
            name = alt.get("name") or ""
            for gw, field in ((1, "pts_gw1"), (2, "pts_gw2")):
                pair = idx.get((team, gw))
                if not pair:
                    continue
                txg, conc = pair
                alt[field] = xpts(
                    pos=pos,
                    price=price,
                    name=name,
                    team_xg=txg,
                    conc=conc,
                    pid=aid,
                )
        you = (p.get("gw1") or {}).get("pts", 0) + (p.get("gw2") or {}).get("pts", 0)
        rows.append((p.get("name_he") or p["name"], p["pos"], p["gw1"]["pts"], p["gw2"]["pts"], you))
    path.write_text(json.dumps(squad, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("id/name                 pos  GW1  GW2  tot")
    for name, pos, a, b, t in rows:
        print(f"{name:22} {pos:3} {a:4.1f} {b:4.1f} {t:4.1f}")
    return squad


def main() -> None:
    apply_squad(ROOT / "squads" / "live.json")


if __name__ == "__main__":
    main()
