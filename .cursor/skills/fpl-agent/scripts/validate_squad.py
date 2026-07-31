#!/usr/bin/env python3
"""Validate a squad JSON against Eli's FPL rules."""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fpl_lib import (  # noqa: E402
    POS,
    POS_LIMITS,
    is_banned,
    load_bootstrap,
    load_json,
    load_profile,
    player_label,
    teams_by_id,
)


def validate(squad_path: Path) -> int:
    profile = load_profile()
    bootstrap = load_bootstrap()
    teams = teams_by_id(bootstrap)
    by_id = {p["id"]: p for p in bootstrap["elements"]}
    squad = load_json(squad_path)
    ids = squad["player_ids"] if isinstance(squad, dict) else squad

    errors: list[str] = []
    warnings: list[str] = []

    if len(ids) != 15:
        errors.append(f"Need 15 players, got {len(ids)}")

    players = []
    for pid in ids:
        if pid not in by_id:
            errors.append(f"Unknown player id {pid}")
            continue
        players.append(by_id[pid])

    # position counts
    pos_counts = Counter(p["element_type"] for p in players)
    for pos, need in POS_LIMITS.items():
        got = pos_counts.get(pos, 0)
        if got != need:
            errors.append(f"{POS[pos]}: need {need}, got {got}")

    # budget
    cost = sum(p["now_cost"] for p in players) / 10
    budget = profile["budget_total"]
    itb = budget - cost
    if cost > budget + 1e-9:
        errors.append(f"Over budget: £{cost:.1f}m / £{budget:.1f}m")
    target = profile["target_itb"]
    if abs(itb - target) > 0.15:
        warnings.append(f"ITB £{itb:.1f}m (target £{target:.1f}m)")

    # bans
    for p in players:
        if is_banned(p, profile["banned_players"]):
            errors.append(f"Banned player: {player_label(p, teams)}")

    # availability soft warning
    for p in players:
        if p.get("status") not in ("a", "d"):
            warnings.append(f"Flagged/unavailable: {player_label(p, teams)} status={p.get('status')}")

    # max 3 per club
    club_counts = Counter(p["team"] for p in players)
    for tid, n in club_counts.items():
        if n > 3:
            errors.append(f"{teams[tid]['short_name']}: {n} players (max 3)")

    # same club + same position forbidden
    club_pos: dict[tuple[int, int], list[str]] = defaultdict(list)
    for p in players:
        club_pos[(p["team"], p["element_type"])].append(p["web_name"])
    for (tid, pos), names in club_pos.items():
        if len(names) > 1:
            errors.append(
                f"Same club+position: {teams[tid]['short_name']} {POS[pos]} -> {', '.join(names)}"
            )

    print(f"Squad: {squad_path}")
    print(f"Cost: £{cost:.1f}m | ITB: £{itb:.1f}m")
    for p in sorted(players, key=lambda x: (x["element_type"], -x["now_cost"])):
        print(f"  {POS[p['element_type']]:3} {player_label(p, teams)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  x {e}")
        return 1

    print("\nOK — squad passes all hard rules.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("squad", type=Path, help="Path to squad JSON")
    args = ap.parse_args()
    raise SystemExit(validate(args.squad))


if __name__ == "__main__":
    main()
