#!/usr/bin/env python3
"""Maximize last-season total_points in a legal £100m FPL squad (no Salah)."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fpl_lib import POS, is_banned, load_bootstrap, load_profile, player_label, save_json, teams_by_id

ROOT = Path(__file__).resolve().parents[4]
FORMS = [(3, 4, 3), (3, 5, 2), (4, 4, 2), (4, 3, 3), (5, 3, 2), (5, 4, 1), (4, 5, 1)]


def pts(p):
    return int(p.get("total_points") or 0)


def can_add(p, picked):
    if sum(1 for x in picked if x["team"] == p["team"]) >= 3:
        return False
    if any(x["team"] == p["team"] and x["element_type"] == p["element_type"] for x in picked):
        return False
    return True


def complete(xi, ordered, budget, target_itb):
    """Add bench to XI; upgrade; return squad dict or None."""
    c = defaultdict(int)
    for p in xi:
        c[p["element_type"]] += 1
    if c[1] != 1:
        return None
    need = {1: 2 - c[1], 2: 5 - c[2], 3: 5 - c[3], 4: 3 - c[4]}
    if any(v < 0 for v in need.values()):
        return None

    rem = budget - sum(p["now_cost"] for p in xi)
    squad = list(xi)
    for pos in (1, 2, 3, 4):
        for _ in range(need[pos]):
            picked = None
            # cheapest first to ensure feasibility, then upgrade
            for p in sorted(ordered[pos], key=lambda x: (x["now_cost"], -pts(x))):
                if p["id"] in {x["id"] for x in squad}:
                    continue
                if p["now_cost"] > rem:
                    continue
                if not can_add(p, squad):
                    continue
                picked = p
                break
            if not picked:
                return None
            squad.append(picked)
            rem -= picked["now_cost"]

    lock = {p["id"] for p in xi if pts(p) >= 200}  # protect Haaland/Bruno-tier in upgrades from XI... 
    # Actually protect only the original XI's top scorers we care about — pass locks separately
    return squad, rem


def upgrade(squad, rem, ordered, target_itb, protect):
    rem = rem
    squad = list(squad)
    for _ in range(200):
        improved = False
        for i, cur in enumerate(squad):
            if cur["id"] in protect:
                continue
            for p in ordered[cur["element_type"]]:
                if p["id"] in {x["id"] for x in squad}:
                    continue
                if pts(p) <= pts(cur):
                    continue
                delta = p["now_cost"] - cur["now_cost"]
                if delta > rem - target_itb:
                    continue
                trial = [x for x in squad if x["id"] != cur["id"]]
                if not can_add(p, trial):
                    continue
                squad[i] = p
                rem -= delta
                improved = True
                break
            if improved:
                break
        if not improved:
            break
    return squad, rem


def dfs_build(ordered, budget, target_itb, protect_ids, nd, nm, nf):
    """DFS fill XI by points with backtracking on budget."""
    need = {1: 1, 2: nd, 3: nm, 4: nf}
    best = None

    def bench_min_cost(partial):
        c = defaultdict(int)
        for p in partial:
            c[p["element_type"]] += 1
        # remaining XI slots
        left = {1: 1 - c[1], 2: nd - c[2], 3: nm - c[3], 4: nf - c[4]}
        # after XI, bench needs
        # underestimate: 4.0 each remaining slot (xi+bench)
        xi_left = sum(max(0, v) for v in left.values())
        # total after full XI counts:
        # final need bench = 2-c1 etc after xi complete — use 4.0 * (4 + xi_left) rough
        return xi_left * 40 + 160  # very loose lower bound

    def rec(partial, rem_need):
        nonlocal best
        spent = sum(p["now_cost"] for p in partial)
        if spent + bench_min_cost(partial) > budget:
            return
        if sum(rem_need.values()) == 0:
            res = complete(partial, ordered, budget, target_itb)
            if not res:
                return
            squad, rem = res
            squad, rem = upgrade(squad, rem, ordered, target_itb, protect_ids)
            # rebuild xi from formation among squad maximizing pts but keeping protect in xi
            gks = [p for p in squad if p["element_type"] == 1]
            defs = sorted([p for p in squad if p["element_type"] == 2], key=lambda x: -pts(x))
            mids = sorted([p for p in squad if p["element_type"] == 3], key=lambda x: -pts(x))
            fwds = sorted([p for p in squad if p["element_type"] == 4], key=lambda x: -pts(x))
            xi = []
            # forced protect into XI
            for pid in protect_ids:
                pl = next((p for p in squad if p["id"] == pid), None)
                if pl and pl not in xi:
                    xi.append(pl)
            d_n = nd - sum(1 for p in xi if p["element_type"] == 2)
            m_n = nm - sum(1 for p in xi if p["element_type"] == 3)
            f_n = nf - sum(1 for p in xi if p["element_type"] == 4)
            g_n = 1 - sum(1 for p in xi if p["element_type"] == 1)
            if g_n > 0:
                for g in sorted(gks, key=lambda x: -pts(x)):
                    if g["id"] not in {x["id"] for x in xi}:
                        xi.append(g)
                        break
            for p in defs:
                if d_n <= 0:
                    break
                if p["id"] in {x["id"] for x in xi}:
                    continue
                xi.append(p)
                d_n -= 1
            for p in mids:
                if m_n <= 0:
                    break
                if p["id"] in {x["id"] for x in xi}:
                    continue
                xi.append(p)
                m_n -= 1
            for p in fwds:
                if f_n <= 0:
                    break
                if p["id"] in {x["id"] for x in xi}:
                    continue
                xi.append(p)
                f_n -= 1
            if len(xi) != 11:
                return
            xi_ids = {p["id"] for p in xi}
            bench = [p for p in squad if p["id"] not in xi_ids]
            cost = sum(p["now_cost"] for p in squad)
            cand = {
                "squad": squad,
                "xi": xi,
                "bench": bench,
                "cost": cost / 10,
                "itb": (budget - cost) / 10,
                "total": sum(pts(p) for p in squad),
                "xip": sum(pts(p) for p in xi),
                "formation": f"{nd}-{nm}-{nf}",
            }
            key = (cand["total"], cand["xip"])
            if best is None or key > best["key"]:
                cand["key"] = key
                best = cand
            return

        # pick next position with remaining need — prioritize high-value positions
        order_pos = sorted(
            [pos for pos, n in rem_need.items() if n > 0],
            key=lambda pos: -max((pts(p) for p in ordered[pos][:5]), default=0),
        )
        pos = order_pos[0]
        tried = 0
        for p in ordered[pos][:25]:
            if p["id"] in {x["id"] for x in partial}:
                continue
            if not can_add(p, partial):
                continue
            if spent + p["now_cost"] > budget:
                continue
            # prune if protect required and we're closing without them — handled by seeding
            tried += 1
            if tried > 18:
                break
            rem2 = dict(rem_need)
            rem2[pos] -= 1
            rec(partial + [p], rem2)

    # Seed with protect players if they fit formation
    seed = []
    rem_need = {1: 1, 2: nd, 3: nm, 4: nf}
    protect_players = []
    for pid in protect_ids:
        # find player
        for pos, lst in ordered.items():
            for p in lst:
                if p["id"] == pid:
                    protect_players.append(p)
                    break
    for p in protect_players:
        if rem_need[p["element_type"]] <= 0:
            return None
        if not can_add(p, seed):
            return None
        seed.append(p)
        rem_need[p["element_type"]] -= 1

    rec(seed, rem_need)
    return best


def main():
    profile = load_profile()
    boot = load_bootstrap()
    teams = teams_by_id(boot)
    banned = profile["banned_players"]
    budget = int(round(profile["budget_total"] * 10))
    target_itb = int(round(profile["target_itb"] * 10))

    ordered = defaultdict(list)
    for p in boot["elements"]:
        if not p.get("can_select", True):
            continue
        if p.get("status") not in ("a", "d"):
            continue
        if is_banned(p, banned):
            continue
        ordered[p["element_type"]].append(p)
    for pos in ordered:
        ordered[pos].sort(key=lambda p: (-pts(p), p["now_cost"]))

    flat = sorted([p for ps in ordered.values() for p in ps], key=lambda p: -pts(p))
    print("Top 15 last season (no Salah):")
    for i, p in enumerate(flat[:15], 1):
        print(f"{i:2}. {player_label(p, teams):30} {pts(p):3} £{p['now_cost']/10:.1f}")

    Haaland = next(p for p in ordered[4] if p["web_name"] == "Haaland")
    Bruno = next(p for p in ordered[3] if p["web_name"] == "B.Fernandes")
    Gabriel = next(p for p in ordered[2] if p["web_name"] == "Gabriel")

    best = None
    for protect in (
        [Haaland["id"], Bruno["id"], Gabriel["id"]],
        [Haaland["id"], Bruno["id"]],
        [Haaland["id"], Gabriel["id"]],
        [Haaland["id"]],
        [Bruno["id"], Gabriel["id"]],
        [],
    ):
        for nd, nm, nf in FORMS:
            # skip impossible protect counts
            from collections import Counter

            pc = Counter()
            id_map = {p["id"]: p for ps in ordered.values() for p in ps}
            for pid in protect:
                pc[id_map[pid]["element_type"]] += 1
            if pc[2] > nd or pc[3] > nm or pc[4] > nf or pc[1] > 1:
                continue
            print(f"search protect={[id_map[i]['web_name'] for i in protect]} form={nd}-{nm}-{nf}…")
            res = dfs_build(ordered, budget, target_itb, protect, nd, nm, nf)
            if not res:
                continue
            print(f"  -> squad={res['total']} xi={res['xip']} £{res['cost']}")
            if best is None or res["key"] > best["key"]:
                best = res
                best["protect"] = [id_map[i]["web_name"] for i in protect]

    if not best:
        print("FAILED")
        return 1

    print(f"\n=== WINNER protect={best.get('protect')} {best['formation']} ===")
    print(f"£{best['cost']:.1f} ITB £{best['itb']:.1f} | squad pts {best['total']} | XI {best['xip']}")
    for p in sorted(best["xi"], key=lambda x: (x["element_type"], -pts(x))):
        print(f"  {POS[p['element_type']]:3} {player_label(p, teams):30} {pts(p):3}")
    print("Bench:")
    for p in best["bench"]:
        print(f"  {POS[p['element_type']]:3} {player_label(p, teams):30} {pts(p):3}")

    picked = {p["id"] for p in best["squad"]}
    print("\nTop-20 not in squad:")
    for i, p in enumerate(flat[:20], 1):
        if p["id"] not in picked:
            print(f"  #{i} {p['web_name']} {pts(p)} £{p['now_cost']/10:.1f}")

    cap = max(best["xi"], key=pts)
    vice = max([p for p in best["xi"] if p["id"] != cap["id"]], key=pts)
    out = {
        "label": "last_season_points_max",
        "gw_from": 1,
        "horizon": 6,
        "formation": best["formation"],
        "player_ids": [p["id"] for p in best["squad"]],
        "xi_ids": [p["id"] for p in best["xi"]],
        "bench_ids": [p["id"] for p in best["bench"]],
        "captain_id": cap["id"],
        "vice_id": vice["id"],
        "cost": best["cost"],
        "itb": best["itb"],
        "last_season_points_total": best["total"],
        "last_season_points_xi": best["xip"],
        "notes": (
            f"Maximize last-season total_points under £100m + Eli rules (no Salah, "
            f"≤3/club, no same club+pos). Protect={best.get('protect')}. "
            f"Squad {best['total']} / XI {best['xip']}. Not 26/27 fixture-optimized."
        ),
    }
    save_json(ROOT / "squads" / "last_season_points.json", out)
    print("Wrote squads/last_season_points.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
