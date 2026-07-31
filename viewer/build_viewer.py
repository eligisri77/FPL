#!/usr/bin/env python3
"""Rebuild viewer/squad.html + data/squad_view.json from a squad JSON."""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# script at viewer/build_viewer.py -> parents[1]=FPL? 
# Path: D:/Games/FPL/viewer/build_viewer.py -> parents[0]=viewer, parents[1]=FPL
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cursor/skills/fpl-agent/scripts"))


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "EliFPL/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--squad",
        type=Path,
        default=ROOT / "squads" / "eli_draft_legal.json",
    )
    args = ap.parse_args()
    squad = json.loads(args.squad.read_text(encoding="utf-8"))
    boot = get_json("https://fantasy.premierleague.com/api/bootstrap-static/")
    fix = get_json("https://fantasy.premierleague.com/api/fixtures/")
    teams = {t["id"]: t for t in boot["teams"]}
    by_id = {p["id"]: p for p in boot["elements"]}
    gw = squad.get("gw_from") or 1

    def next_fix(team_id: int):
        for f in fix:
            if f.get("event") != gw:
                continue
            if f["team_h"] == team_id:
                return teams[f["team_a"]]["short_name"] + "(H)", f.get("team_h_difficulty", 3)
            if f["team_a"] == team_id:
                return teams[f["team_h"]]["short_name"] + "(A)", f.get("team_a_difficulty", 3)
        return "—", 3

    players = []
    for pid in squad["player_ids"]:
        p = by_id[pid]
        opp, fdr = next_fix(p["team"])
        players.append(
            {
                "id": pid,
                "name": p["web_name"],
                "team": teams[p["team"]]["short_name"],
                "pos": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[p["element_type"]],
                "price": p["now_cost"] / 10,
                "own": float(p["selected_by_percent"] or 0),
                "ep": float(p["ep_next"] or 0),
                "opp": opp,
                "fdr": fdr,
                "captain": pid == squad.get("captain_id"),
                "vice": pid == squad.get("vice_id"),
            }
        )

    view = {
        "meta": {
            "cost": squad.get("cost", sum(x["price"] for x in players)),
            "itb": squad.get("itb", round(100 - sum(x["price"] for x in players), 1)),
            "gw": gw,
            "label": squad.get("label", args.squad.stem),
        },
        "players": players,
    }
    out_json = ROOT / "data" / "squad_view.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = ROOT / "viewer" / "squad.html"
    html = html_path.read_text(encoding="utf-8")
    payload = json.dumps(view, ensure_ascii=False)
    html2, n = re.subn(
        r"const DATA = .*?;",
        f"const DATA = {payload};",
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit("Could not patch DATA blob in squad.html")

    xi_ids = squad.get("xi_ids") or [p["id"] for p in players[:11]]
    xi_payload = json.dumps(xi_ids)
    html2, n2 = re.subn(
        r"const XI_IDS = .*?;",
        f"const XI_IDS = {xi_payload};",
        html2,
        count=1,
        flags=re.S,
    )
    if n2 != 1:
        raise SystemExit("Could not patch XI_IDS in squad.html")

    # Refresh summary note from squad notes / captain
    cap_name = next((p["name"] for p in players if p["captain"]), "?")
    vice_name = next((p["name"] for p in players if p["vice"]), "?")
    note = squad.get("notes") or (
        f"C: {cap_name} · VC: {vice_name} · בלי Salah · עד 3 לקבוצה"
    )
    note_html = (
        f"C: <b>{cap_name}</b> · VC: <b>{vice_name}</b><br/>"
        + note.replace("<", "&lt;").replace(">", "&gt;")
    )
    html2, n3 = re.subn(
        r'(<div class="panel">\s*<h2>סיכום</h2>\s*<p class="note">).*?(</p>)',
        rf"\1{note_html}\2",
        html2,
        count=1,
        flags=re.S,
    )
    if n3 != 1:
        print("warn: could not patch summary note")

    html_path.write_text(html2, encoding="utf-8")
    print(f"Updated {out_json}")
    print(f"Updated {html_path}")


if __name__ == "__main__":
    main()
