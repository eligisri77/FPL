#!/usr/bin/env python3
"""Rebuild viewer/squad.html + data/squad_view.json from a squad JSON.

Also embeds GW1–2 pros/cons table (from squad players.gw1/gw2 if present).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cursor/skills/fpl-agent/scripts"))

HE = {
    "Lammens": "למנס",
    "Shaw": "שו",
    "Calafiori": "קאלאפיורי",
    "Mukiele": "מוקיאלה",
    "Mbeumo": "מבאומו",
    "Semenyo": "סמניו",
    "Scott": "סקוט",
    "Wirtz": "וירץ",
    "Igor Jesus": "איגור ז׳זוס",
    "Haaland": "האלאנד",
    "Isak": "איסאק",
    "Petrović": "פטרוביץ׳",
    "Yarmoliuk": "יארמוליוק",
    "Ajer": "אייר",
    "Van Hecke": "ואן הק",
    "van Ewijk": "ואן אווייק",
    "Guéhi": "גווהי",
    "E.Le Fée": "לה פה",
    "Verbruggen": "ורברוגן",
    "Willock": "ווילוק",
    "Alderete": "אלדרטה",
    "Mitchell": "מיטשל",
    "Eze": "איזה",
    "Rogers": "רוג׳רס",
    "Mateta": "מאטטה",
}


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "EliFPL/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def build_gw12_from_live(squad: dict) -> list[dict]:
    """Prefer analysis already on squad players; else empty."""
    out = []
    xi = set(squad.get("xi_ids") or [])
    for p in squad.get("players") or []:
        if "gw1" not in p or "gw2" not in p:
            continue
        out.append(
            {
                "id": p["id"],
                "name": p.get("name_he") or HE.get(p["name"], p["name"]),
                "name_en": p["name"],
                "team": p["team"],
                "pos": p["pos"],
                "price": p["price"],
                "xi": p["id"] in xi if xi else p.get("xi", True),
                "captain": p.get("captain", False),
                "vice": p.get("vice", False),
                "gw1": p["gw1"],
                "gw2": p["gw2"],
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--squad",
        type=Path,
        default=ROOT / "squads" / "live.json",
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
    gw12 = build_gw12_from_live(squad)

    out_json = ROOT / "data" / "squad_view.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = ROOT / "viewer" / "squad.html"
    html = html_path.read_text(encoding="utf-8")
    payload = json.dumps(view, ensure_ascii=False)
    xi_ids = squad.get("xi_ids") or [p["id"] for p in players[:11]]
    xi_payload = json.dumps(xi_ids)
    gw12_payload = json.dumps(gw12, ensure_ascii=False)

    def patch_const(src: str, name: str, value: str) -> str:
        """Replace a whole `const NAME = ...` line (safe with `;` inside JSON strings)."""
        lines = src.splitlines(keepends=True)
        out = []
        found = False
        for line in lines:
            if line.lstrip().startswith(f"const {name} ="):
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f"{indent}const {name} = {value};\n")
                found = True
            else:
                out.append(line)
        if not found:
            raise SystemExit(f"Could not patch {name} blob in squad.html")
        return "".join(out)

    # First repair any previously corrupted GW12/DATA lines that spilled past `;`
    # by collapsing junk until the next real const / blank / non-junk line.
    html = re.sub(
        r"(const GW12 = ).*?(?=\n\s*const XI_IDS =)",
        rf"\1[];",
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r"(const DATA = ).*?(?=\n\s*const GW12 =)",
        rf"\1{{}};",
        html,
        count=1,
        flags=re.S,
    )

    html2 = patch_const(html, "DATA", payload)
    if "const GW12 =" not in html2:
        html2 = html2.replace(
            "const XI_IDS =",
            f"const GW12 = [];\n    const XI_IDS =",
            1,
        )
    html2 = patch_const(html2, "GW12", gw12_payload)
    html2 = patch_const(html2, "XI_IDS", xi_payload)

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

    # subtitle
    html2, _ = re.subn(
        r'(<div class="sub">).*?(</div>)',
        r"\1סגל ראשי · בוסט GW2 · ווילדקארד GW3 · בלי Salah\2",
        html2,
        count=1,
        flags=re.S,
    )

    html_path.write_text(html2, encoding="utf-8")
    print(f"Updated {out_json}")
    print(f"Updated {html_path} (GW12 rows={len(gw12)})")


if __name__ == "__main__":
    main()
