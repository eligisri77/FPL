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
    "Xhaka": "שאקה",
    "Kinsky": "קינסקי",
    "O'Nien": "או׳נין",
    "B.Fernandes": "ברנו",
    "Foden": "פודן",
    "Rudoni": "רודוני",
    "Caicedo": "קאיסדו",
    "Sakamoto": "סאקאמוטו",
    "Verbruggen": "ורברוגן",
    "Willock": "ווילוק",
    "Alderete": "אלדרטה",
    "Mitchell": "מיטשל",
    "Eze": "איזה",
    "Rogers": "רוג׳רס",
    "Mateta": "מאטטה",
    "Aina": "איינה",
    "Gvardiol": "גווארדיול",
    "Diop": "דיופ",
    "Gibbs-White": "גיבס-ווייט",
    "Saka": "סאקה",
    "Tonali": "טונאלי",
    "Brobbey": "ברובי",
    "Gyökeres": "ייקרש",
    "Angulo": "אנגולו",
    "Robertson": "רוברטסון",
    "Tzolis": "צוליס",
    "Muharemović": "מוהרמוביץ׳",
    "Justin": "ג׳סטין",
    "Hume": "יום",
    "Palmer": "פאלמר",
    "Sarr": "סאר",
    "Gomez": "גומז",
}


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "EliFPL/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _list_html(items: list | None, cls: str) -> str:
    arr = items if items else ["—"]
    return "<ul class='" + cls + "'>" + "".join(f"<li>{x}</li>" for x in arr) + "</ul>"


def _gw_td(g: dict | None) -> str:
    if not g:
        return "<td>—</td>"
    pts = (
        f'<div class="pts">תחזית ≈ {float(g["pts"]):.1f}</div>'
        if g.get("pts") is not None
        else ""
    )
    return f"""  <td>
    <div class="fix">{g.get("opp")} ({g.get("loc")}) · קבוצה≈{float(g.get("xg") or 0):.2f} · נגד≈{float(g.get("conc") or 0):.2f}</div>
    {pts}
    <div class="split">
      <div><div class="lab plus">יתרונות</div>{_list_html(g.get("pros"), "pros")}</div>
      <div><div class="lab minus">חסרונות</div>{_list_html(g.get("cons"), "cons")}</div>
    </div>
  </td>"""


def write_gw12_table(gw12: list[dict], path: Path, squad: dict) -> None:
    """Keep the standalone mobile table in sync with live.json."""
    if not path.exists() or not gw12:
        return
    html = path.read_text(encoding="utf-8")
    pos_order = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
    rows = sorted(
        gw12,
        key=lambda p: (0 if p.get("xi") else 1, pos_order.get(p["pos"], 9), -p["price"]),
    )
    body = []
    for p in rows:
        mark = " (C)" if p.get("captain") else " (VC)" if p.get("vice") else ""
        slot = "הרכב" if p.get("xi") else "ספסל"
        cls = ' class="bn"' if not p.get("xi") else ""
        alt = p.get("alt")
        if alt:
            you = float((p.get("gw1") or {}).get("pts") or 0) + float(
                (p.get("gw2") or {}).get("pts") or 0
            )
            them = (
                float(alt.get("pts_gw1") or 0) + float(alt.get("pts_gw2") or 0)
                if alt.get("pts_gw1") is not None
                else None
            )
            cmp = (
                f'<span class="pts">אתה {you:.1f} · מחליף {them:.1f} (שני מחזורים)</span>'
                if them is not None
                else ""
            )
            alt_html = (
                f'<div class="alt"><b>{alt.get("name_he") or alt.get("name")}</b> · '
                f'{alt.get("team")} {alt.get("pos")} · £{float(alt.get("price") or 0):.1f}'
                f'<span class="why">{alt.get("why") or ""}</span>{cmp}</div>'
            )
        else:
            alt_html = '<span style="color:#9aab9d">—</span>'
        body.append(
            f'<tr{cls}>\n  <td class="name"><b>{p["name"]}{mark}</b>'
            f'<div class="meta">{p["pos"]} · {p["team"]} · £{float(p["price"]):.1f} · {slot}</div></td>\n'
            f"{_gw_td(p.get('gw1'))}\n{_gw_td(p.get('gw2'))}\n  <td>{alt_html}</td>\n</tr>"
        )
    tbody = "\n".join(body)
    html2, n = re.subn(
        r"(<tbody>\s*).*?(\s*</tbody>)",
        rf"\1\n{tbody}\n\2",
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        print("warn: could not patch squad_gw12_table tbody")
        return
    html2, _ = re.subn(
        r'(<div class="sub">).*?(</div>)',
        r"\1לפי הצילום שלך · מקור שערים: Prem Projections · תחזית נקודות: מודל אלי (לא ep הרשמי) · בלי כפל קפטן · בוסט GW2 · WC GW3\2",
        html2,
        count=1,
        flags=re.S,
    )
    names = " · ".join(
        p.get("name_he") or p.get("name") or "?"
        for p in rows
        if p.get("xi")
    )
    html2, _ = re.subn(
        r'(<div class="warn">).*?(</div>)',
        rf'\1שימו לב: מבאומו וברנו שני קשרים של יונייטד — לפי הכללים אסור שני שחקנים מאותה קבוצה באותה עמדה. סגל: {names}.\2',
        html2,
        count=1,
        flags=re.S,
    )
    path.write_text(html2, encoding="utf-8")
    print(f"Updated {path}")


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
                "alt": p.get("alt"),
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

    live_by_id = {x["id"]: x for x in (squad.get("players") or [])}
    players = []
    for pid in squad["player_ids"]:
        p = by_id[pid]
        opp, fdr = next_fix(p["team"])
        live = live_by_id.get(pid) or {}
        model_ep = (live.get("gw1") or {}).get("pts")
        players.append(
            {
                "id": pid,
                "name": p["web_name"],
                "team": teams[p["team"]]["short_name"],
                "pos": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[p["element_type"]],
                "price": p["now_cost"] / 10,
                "own": float(p["selected_by_percent"] or 0),
                "ep": float(model_ep if model_ep is not None else (p["ep_next"] or 0)),
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
    html2, _ = re.subn(
        r'(<div class="gw12-sub">).*?(</div>)',
        r"\1לפי Prem Projections · תחזית נקודות: מודל אלי (לא ep הרשמי של FPL) · בלי כפל קפטן · מחליף עד אותו מחיר\2",
        html2,
        count=1,
        flags=re.S,
    )

    html_path.write_text(html2, encoding="utf-8")
    write_gw12_table(gw12, ROOT / "viewer" / "squad_gw12_table.html", squad)
    print(f"Updated {out_json}")
    print(f"Updated {html_path} (GW12 rows={len(gw12)})")


if __name__ == "__main__":
    main()
