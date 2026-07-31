#!/usr/bin/env python3
"""Suggest an opening FPL squad under Eli's rules (strong XI, cheap bench)."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Windows consoles often break on Hebrew — force UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fpl_lib import (  # noqa: E402
    DATA,
    POS,
    ROOT,
    fixture_attack_score,
    fixture_def_score,
    is_banned,
    load_bootstrap,
    load_json,
    load_profile,
    next_gw,
    player_label,
    save_json,
    teams_by_id,
)


def fnum(p: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(p.get(key) or default)
    except (TypeError, ValueError):
        return default


def available(players: list[dict], banned: list[str]) -> list[dict]:
    out = []
    for p in players:
        if not p.get("can_select", True):
            continue
        if p.get("status") not in ("a", "d"):
            continue
        if is_banned(p, banned):
            continue
        out.append(p)
    return out


def score_attacker(p: dict, fix_score: float) -> float:
    return (
        fnum(p, "ep_next") * 3.0
        + fnum(p, "total_points") * 0.04
        + fnum(p, "points_per_game") * 1.2
        + fnum(p, "selected_by_percent") * 0.03
        + fix_score * 0.9
        + (p["now_cost"] / 10) * 0.25
    )


def score_defender(p: dict, fix_score: float) -> float:
    return (
        fnum(p, "ep_next") * 3.0
        + fnum(p, "total_points") * 0.04
        + fnum(p, "points_per_game") * 1.2
        + fnum(p, "selected_by_percent") * 0.04
        + fix_score * 1.1
        + (p["now_cost"] / 10) * 0.15
    )


def can_add(p: dict, picked: list[dict]) -> bool:
    if sum(1 for x in picked if x["team"] == p["team"]) >= 3:
        return False
    if any(x["team"] == p["team"] and x["element_type"] == p["element_type"] for x in picked):
        return False
    return True


def find_by_names(players: list[dict], names: list[str]) -> list[dict]:
    found = []
    for name in names:
        n = name.lower()
        matches = [
            p
            for p in players
            if n in p["web_name"].lower()
            or n in f"{p.get('first_name','')} {p.get('second_name','')}".lower()
        ]
        if not matches:
            continue
        # prefer higher ownership / price (real star, not fodder namesake)
        matches.sort(key=lambda p: (fnum(p, "selected_by_percent"), p["now_cost"]), reverse=True)
        found.append(matches[0])
    return found


def pick_best(
    candidates: list[dict],
    picked: list[dict],
    n: int,
    scorer,
    max_price: float | None = None,
    min_price: float | None = None,
    min_ownership: float = 0.0,
) -> list[dict]:
    chosen = []
    ranked = sorted(candidates, key=scorer, reverse=True)
    for p in ranked:
        if len(chosen) >= n:
            break
        price = p["now_cost"] / 10
        if max_price is not None and price > max_price + 1e-9:
            continue
        if min_price is not None and price < min_price - 1e-9:
            continue
        if fnum(p, "selected_by_percent") < min_ownership and price >= 5.0:
            # allow low-owned differentials only if they have solid pts history
            if fnum(p, "total_points") < 80 and fnum(p, "ep_next") < 3.0:
                continue
        if not can_add(p, picked + chosen):
            continue
        chosen.append(p)
    return chosen


def pick_cheapest(candidates: list[dict], picked: list[dict], n: int) -> list[dict]:
    chosen = []
    ranked = sorted(
        candidates,
        key=lambda p: (p["now_cost"], -fnum(p, "ep_next"), -fnum(p, "selected_by_percent")),
    )
    for p in ranked:
        if len(chosen) >= n:
            break
        if p["now_cost"] > 45:
            continue
        if not can_add(p, picked + chosen):
            continue
        chosen.append(p)
    return chosen


def total_cost(ps: list[dict]) -> float:
    return sum(p["now_cost"] for p in ps) / 10


def upgrade_to_target(
    picked: list[dict],
    by_pos: dict,
    atk: dict,
    dfn: dict,
    spend_target: float,
) -> list[dict]:
    """Spend leftover cash by upgrading XI-quality slots toward target ITB."""
    picked = list(picked)
    for _ in range(60):
        if total_cost(picked) >= spend_target - 0.05:
            break
        slack = spend_target - total_cost(picked)
        # upgrade cheapest "starter-ish" slots first
        candidates_out = sorted(
            [p for p in picked if p["now_cost"] >= 45],
            key=lambda p: p["now_cost"],
        )
        swapped = False
        for victim in candidates_out:
            pos = victim["element_type"]
            others = [x for x in picked if x["id"] != victim["id"]]
            max_new = victim["now_cost"] + int(round(slack * 10))
            upgrades = [
                p
                for p in by_pos[pos]
                if p["id"] not in {x["id"] for x in picked}
                and victim["now_cost"] < p["now_cost"] <= max_new
                and can_add(p, others)
            ]
            if not upgrades:
                continue
            scorer = (
                (lambda p: score_attacker(p, atk[p["team"]]))
                if pos >= 3
                else (lambda p: score_defender(p, dfn[p["team"]]))
            )
            upgrades.sort(key=scorer, reverse=True)
            best = upgrades[0]
            # only upgrade if score improves (or premium template)
            if scorer(best) < scorer(victim) and fnum(best, "selected_by_percent") < 20:
                continue
            picked = [best if x["id"] == victim["id"] else x for x in picked]
            swapped = True
            break
        if not swapped:
            break
    return picked


def build_xi(picked: list[dict], atk: dict, dfn: dict) -> tuple[list[dict], list[dict]]:
    remaining = list(picked)
    xi: list[dict] = []

    gk = max([p for p in remaining if p["element_type"] == 1], key=lambda p: fnum(p, "ep_next"))
    xi.append(gk)

    defs = sorted(
        [p for p in remaining if p["element_type"] == 2],
        key=lambda p: score_defender(p, dfn[p["team"]]),
        reverse=True,
    )
    xi.extend(defs[:3])

    used = {p["id"] for p in xi}
    pool = [p for p in picked if p["id"] not in used and p["element_type"] != 1]
    pool.sort(
        key=lambda p: score_attacker(p, atk[p["team"]])
        if p["element_type"] >= 3
        else score_defender(p, dfn[p["team"]]),
        reverse=True,
    )
    for p in pool:
        if len(xi) >= 11:
            break
        defs_n = sum(1 for x in xi if x["element_type"] == 2)
        mids_n = sum(1 for x in xi if x["element_type"] == 3)
        fwds_n = sum(1 for x in xi if x["element_type"] == 4)
        if p["element_type"] == 2 and defs_n >= 5:
            continue
        if p["element_type"] == 3 and mids_n >= 5:
            continue
        if p["element_type"] == 4 and fwds_n >= 3:
            continue
        xi.append(p)

    def count(pos: int) -> int:
        return sum(1 for x in xi if x["element_type"] == pos)

    def repair(pos: int, need_n: int, min_keep: dict[int, int]) -> None:
        nonlocal xi
        while count(pos) < need_n:
            cand = [
                p
                for p in picked
                if p["element_type"] == pos and p["id"] not in {x["id"] for x in xi}
            ]
            drop_order = [
                x
                for x in xi
                if x["element_type"] != 1 and count(x["element_type"]) > min_keep[x["element_type"]]
            ]
            drop_order.sort(key=lambda p: fnum(p, "ep_next"))
            if not cand or not drop_order:
                break
            xi = [max(cand, key=lambda p: fnum(p, "ep_next")) if x["id"] == drop_order[0]["id"] else x for x in xi]

    repair(3, 2, {2: 3, 3: 2, 4: 1})
    repair(4, 1, {2: 3, 3: 2, 4: 1})
    repair(2, 3, {2: 3, 3: 2, 4: 1})

    bench = [p for p in picked if p["id"] not in {x["id"] for x in xi}]
    bench.sort(key=lambda p: (p["element_type"] != 1, -fnum(p, "ep_next")))
    return xi, bench


def main() -> None:
    profile = load_profile()
    bootstrap = load_bootstrap()
    fixtures = load_json(DATA / "fixtures.json")
    teams = teams_by_id(bootstrap)
    banned = profile["banned_players"]
    horizon = profile["planning_horizon_gws"]
    gw = next_gw(bootstrap)
    target_itb = profile["target_itb"]
    budget = profile["budget_total"]
    spend_target = budget - target_itb

    players = available(bootstrap["elements"], banned)
    by_pos: dict[int, list] = defaultdict(list)
    for p in players:
        by_pos[p["element_type"]].append(p)

    atk = {t: fixture_attack_score(fixtures, t, gw, horizon) for t in teams}
    dfn = {t: fixture_def_score(fixtures, t, gw, horizon) for t in teams}

    picked: list[dict] = []

    # Locked players first
    for p in find_by_names(players, profile.get("locked_players") or []):
        if can_add(p, picked) and p not in picked:
            picked.append(p)

    # GK starter
    need_gk = 1 - sum(1 for p in picked if p["element_type"] == 1)
    if need_gk > 0:
        picked.extend(
            pick_best(
                by_pos[1],
                picked,
                need_gk,
                lambda p: score_defender(p, dfn[p["team"]]),
                max_price=5.5,
                min_ownership=1.0,
            )
        )

    # 3 strong DEF
    need_def = 3 - sum(1 for p in picked if p["element_type"] == 2)
    if need_def > 0:
        picked.extend(
            pick_best(
                by_pos[2],
                picked,
                need_def,
                lambda p: score_defender(p, dfn[p["team"]]),
                min_price=4.5,
                max_price=8.0,
                min_ownership=2.0,
            )
        )

    # 4 strong MID
    need_mid = 4 - sum(1 for p in picked if p["element_type"] == 3)
    if need_mid > 0:
        picked.extend(
            pick_best(
                by_pos[3],
                picked,
                need_mid,
                lambda p: score_attacker(p, atk[p["team"]]),
                min_price=5.0,
                max_price=13.0,
                min_ownership=3.0,
            )
        )

    # 2 strong FWD (Haaland allowed)
    need_fwd = 2 - sum(1 for p in picked if p["element_type"] == 4)
    if need_fwd > 0:
        picked.extend(
            pick_best(
                by_pos[4],
                picked,
                need_fwd,
                lambda p: score_attacker(p, atk[p["team"]]),
                min_price=5.5,
                max_price=15.5,
                min_ownership=3.0,
            )
        )

    # Fill remaining slots cheap
    need = {
        1: 2 - sum(1 for p in picked if p["element_type"] == 1),
        2: 5 - sum(1 for p in picked if p["element_type"] == 2),
        3: 5 - sum(1 for p in picked if p["element_type"] == 3),
        4: 3 - sum(1 for p in picked if p["element_type"] == 4),
    }
    for pos, n in need.items():
        if n <= 0:
            continue
        cheap = pick_cheapest(by_pos[pos], picked, n)
        if len(cheap) < n:
            ranked = sorted(by_pos[pos], key=lambda p: (p["now_cost"], -fnum(p, "ep_next")))
            for p in ranked:
                if len(cheap) >= n:
                    break
                if p["id"] in {x["id"] for x in picked + cheap}:
                    continue
                if can_add(p, picked + cheap):
                    cheap.append(p)
        picked.extend(cheap)

    if len(picked) != 15:
        print(f"ERROR: only picked {len(picked)}/15")
        for p in picked:
            print(" ", player_label(p, teams))
        raise SystemExit(1)

    # If over budget, downgrade
    for _ in range(40):
        if total_cost(picked) <= spend_target + 0.05:
            break
        expensive = sorted(
            [p for p in picked if p["now_cost"] >= 50],
            key=lambda p: p["now_cost"],
            reverse=True,
        )
        swapped = False
        for victim in expensive:
            others = [x for x in picked if x["id"] != victim["id"]]
            replacements = [
                p
                for p in by_pos[victim["element_type"]]
                if p["id"] not in {x["id"] for x in picked}
                and p["now_cost"] < victim["now_cost"]
                and can_add(p, others)
            ]
            if not replacements:
                continue
            replacements.sort(
                key=lambda p: score_attacker(p, atk[p["team"]])
                if victim["element_type"] >= 3
                else score_defender(p, dfn[p["team"]]),
                reverse=True,
            )
            picked = [replacements[0] if x["id"] == victim["id"] else x for x in picked]
            swapped = True
            break
        if not swapped:
            break

    picked = upgrade_to_target(picked, by_pos, atk, dfn, spend_target)

    cost = total_cost(picked)
    itb = budget - cost
    xi, bench = build_xi(picked, atk, dfn)

    capt_pool = [p for p in xi if p["element_type"] >= 3] or xi
    captain = max(capt_pool, key=lambda p: score_attacker(p, atk[p["team"]]))
    vice_opts = [p for p in capt_pool if p["id"] != captain["id"]] or [p for p in xi if p["id"] != captain["id"]]
    vice = max(vice_opts, key=lambda p: score_attacker(p, atk[p["team"]]))

    out = {
        "gw_from": gw,
        "horizon": horizon,
        "player_ids": [p["id"] for p in picked],
        "xi_ids": [p["id"] for p in xi],
        "bench_ids": [p["id"] for p in bench],
        "captain_id": captain["id"],
        "vice_id": vice["id"],
        "cost": round(cost, 1),
        "itb": round(itb, 1),
        "notes": "Auto-suggest: strong XI, cheap bench, no Salah, no same club+position, ~0.2 ITB",
    }
    out_path = ROOT / "squads" / f"gw{gw}_draft.json"
    save_json(out_path, out)

    print(f"## Suggested squad (GW{gw}-{gw + horizon - 1})")
    print(f"ITB: £{itb:.1f}m | Cost: £{cost:.1f}m | Saved: {out_path}")
    print("\n### XI")
    for p in sorted(xi, key=lambda x: x["element_type"]):
        mark = " (C)" if p["id"] == captain["id"] else (" (VC)" if p["id"] == vice["id"] else "")
        print(f"- {POS[p['element_type']]} {player_label(p, teams)}{mark}")
    print("\n### Bench")
    for p in bench:
        print(f"- {POS[p['element_type']]} {player_label(p, teams)}")
    print("\n### Captain / Vice")
    print(f"- C: {player_label(captain, teams)}")
    print(f"- VC: {player_label(vice, teams)}")


if __name__ == "__main__":
    main()
