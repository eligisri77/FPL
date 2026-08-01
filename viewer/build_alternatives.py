#!/usr/bin/env python3
"""Rebuild viewer/alternatives.html from squad JSON files."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (title he, squad path, note override optional)
ALTS: list[tuple[str, Path]] = [
    ("0) הדאפט הנוכחי (ראשי)", ROOT / "squads" / "gw1_top1k.json"),
    ("1) גמישות (פחות זולים)", ROOT / "squads" / "gw1_flex.json"),
    ("2) שיא נקודות עונה שעברה", ROOT / "squads" / "last_season_points.json"),
    ("3) BB GW2 — תוכנית צד", ROOT / "squads" / "gw1_bb_gw2_plan.json"),
    ("4) LTFPL Value", ROOT / "squads" / "gw1_ltfpl_value.json"),
    ("5) FPL Mate מותאם", ROOT / "squads" / "alt_fplmate.json"),
    ("6) עקביות", ROOT / "squads" / "alt_consistency.json"),
    ("7) כוכבים מאוזנים", ROOT / "squads" / "alt_stars_balanced.json"),
    ("8) ממוצע עולמי", ROOT / "squads" / "alt_global_template.json"),
]


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "EliFPL/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def next_opp(team_id: int, gw: int, fixtures: list, teams: dict) -> str:
    for f in fixtures:
        if f.get("event") != gw:
            continue
        if f["team_h"] == team_id:
            return teams[f["team_a"]]["short_name"] + "(H)"
        if f["team_a"] == team_id:
            return teams[f["team_h"]]["short_name"] + "(A)"
    return "—"


def enrich(squad: dict, boot: dict, fixtures: list) -> dict:
    teams = {t["id"]: t for t in boot["teams"]}
    by_id = {p["id"]: p for p in boot["elements"]}
    pos = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    gw = squad.get("gw_from") or 1
    xi = set(squad.get("xi_ids") or [])
    cap = squad.get("captain_id")
    vice = squad.get("vice_id")

    players = []
    for pid in squad["player_ids"]:
        p = by_id[pid]
        players.append(
            {
                "id": pid,
                "name": p["web_name"],
                "team": teams[p["team"]]["short_name"],
                "pos": pos[p["element_type"]],
                "price": p["now_cost"] / 10,
                "own": float(p["selected_by_percent"] or 0),
                "opp": next_opp(p["team"], gw, fixtures, teams),
                "xi": pid in xi if xi else True,
                "captain": pid == cap,
                "vice": pid == vice,
            }
        )

    cost = squad.get("cost")
    if cost is None:
        cost = round(sum(x["price"] for x in players), 1)
    itb = squad.get("itb")
    if itb is None:
        itb = round(100.0 - cost, 1)

    return {
        "title": squad.get("label", "squad"),
        "cost": cost,
        "itb": itb,
        "notes": squad.get("notes", ""),
        "players": players,
        "avg_own": round(sum(x["own"] for x in players) / max(len(players), 1), 1),
    }


def card(p: dict, bench: bool = False) -> str:
    cls = ["player"]
    if bench:
        cls.append("bench")
    if p.get("captain"):
        cls.append("captain")
    if p.get("vice"):
        cls.append("vice")
    badge = ""
    if p.get("captain"):
        badge = '<div class="badge">C</div>'
    elif p.get("vice"):
        badge = '<div class="badge vc">V</div>'
    return (
        f'<div class="{" ".join(cls)}">{badge}'
        f'<div class="meta">{p["team"]} · {p["pos"]}</div>'
        f'<div class="name">{p["name"]}</div>'
        f'<div class="price">£{p["price"]:.1f}m</div>'
        f'<div class="opp">{p["opp"]}</div>'
        f'<div class="meta">{p["own"]:.0f}%</div></div>'
    )


def pitch_html(players: list[dict]) -> str:
    xi = [p for p in players if p.get("xi")]
    bench = [p for p in players if not p.get("xi")]
    if not xi:
        # fallback: first of each role by price
        xi, bench = players[:11], players[11:]

    def row(pos: str) -> str:
        group = [p for p in xi if p["pos"] == pos]
        if not group:
            return ""
        return '<div class="row">' + "".join(card(p) for p in group) + "</div>"

    html = row("GK") + row("DEF") + row("MID") + row("FWD")
    html += '<div class="bench-title">Bench</div>'
    html += '<div class="row">' + "".join(card(p, True) for p in bench) + "</div>"
    return html


def section_html(title: str, data: dict, full: bool = False) -> str:
    full_cls = " full" if full else ""
    stat = f"£{data['cost']:.1f}m · ITB £{data['itb']:.1f}m"
    if "ממוצע" in title or "global" in data["title"].lower():
        stat += f" · בעלות ממוצעת {data['avg_own']:.1f}%"
    note = data["notes"].replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<section class="panel{full_cls}"><h2>{title}</h2>'
        f'<div class="stat">{stat}</div>'
        f'<div class="pitch">{pitch_html(data["players"])}</div>'
        f'<p class="note">{note}</p></section>'
    )


CSS = """
:root{--bg:#0f1410;--panel:#182018;--pitch:#1f6b3a;--line:rgba(255,255,255,.18);--ink:#f2f5f0;--muted:#9aab9d;--card:#f4f7f2;--card-ink:#122016;--accent:#c8f06c}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Tahoma,sans-serif;background:var(--bg);color:var(--ink)}
.wrap{max-width:1400px;margin:0 auto;padding:24px 16px}h1{margin:0 0 8px}.sub{color:var(--muted);margin-bottom:18px}
.grid{display:grid;grid-template-columns:1fr;gap:20px}
.panel{background:var(--panel);border:1px solid #2a3a2c;border-radius:14px;padding:14px}.full{grid-column:1/-1}
.stat{color:var(--accent);font-weight:700;margin-bottom:10px}
.pitch{background:repeating-linear-gradient(0deg,var(--pitch) 0 12.5%,#1a5f34 12.5% 25%);border-radius:14px;border:2px solid var(--line);padding:12px 8px;min-height:480px}
.row{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin:10px 0}
.player{width:90px;background:var(--card);color:var(--card-ink);border-radius:10px;padding:6px;text-align:center;position:relative;border:2px solid transparent}
.player.captain{border-color:#d4a017}.player.vice{border-color:#7a8fa3}.player.bench{background:#e8ece6}
.badge{position:absolute;top:-7px;left:-7px;background:#d4a017;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:.65rem;font-weight:800}
.badge.vc{background:#8ea0b0}.name{font-weight:700;font-size:.74rem}.meta{font-size:.6rem;color:#4d5c52}.price{font-weight:800;font-size:.76rem}
.opp{display:inline-block;margin-top:2px;padding:1px 5px;border-radius:999px;background:#dfe8df;font-size:.58rem;font-weight:700}
.bench-title{text-align:center;color:rgba(255,255,255,.75);font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;margin-top:12px}
.note{color:var(--muted);font-size:.82rem;margin-top:10px;line-height:1.45}
"""


def main() -> None:
    boot = json.loads((ROOT / "data" / "bootstrap.json").read_text(encoding="utf-8"))
    fix_path = ROOT / "data" / "fixtures.json"
    if fix_path.exists():
        fixtures = json.loads(fix_path.read_text(encoding="utf-8"))
    else:
        fixtures = get_json("https://fantasy.premierleague.com/api/fixtures/")

    sections = []
    for title, path in ALTS:
        if not path.exists():
            print(f"skip missing {path}", file=sys.stderr)
            continue
        squad = json.loads(path.read_text(encoding="utf-8"))
        data = enrich(squad, boot, fixtures)
        sections.append(section_html(title, data, full=True))

    html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Eli FPL — Alternatives</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>סגלים</h1>
<div class="sub">מתעדכן מ־squads/*.json · LTFPL Value + אלטרנטיבות קודמות</div>
<div class="grid">
{"".join(sections)}
</div></div></body></html>
"""
    out = ROOT / "viewer" / "alternatives.html"
    out.write_text(html, encoding="utf-8")
    print(f"Updated {out} ({len(sections)} squads)")


if __name__ == "__main__":
    main()
