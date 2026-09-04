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
    "Raya": "ראיה",
    "Gabriel": "גבריאל",
    "João Pedro": "ז׳ואאו פדרו",
    "Thiago": "תיאגו",
    "Gakpo": "גקפו",
    "N.Williams": "נ. ויליאמס",
    "Maguire": "מאגווייר",
    "Palmer": "פאלמר",
    "Sarr": "סאר",
    "Gomez": "גומז",
    "Saliba": "סאליבה",
    "Semenyo": "סמניו",
    "Ndiaye": "נדיאייה",
    "Wirtz": "וירץ",
    "Cherki": "שרקי",
    "Suzuki": "סוזוקי",
    "Hall": "הול",
    "M.Sangaré": "מ. סנגרה",
    "Szoboszlai": "סובוסלאי",
    "Wissa": "ויסה",
}


def horizon_gws(squad: dict) -> list[int]:
    g0 = int(squad.get("gw_from") or 3)
    h = int(squad.get("horizon") or 6)
    return list(range(g0, g0 + h))


def _alt_horizon_html(p: dict, gws: list[int]) -> str:
    alt = p.get("alt")
    if not alt:
        return '<span style="color:#9aab9d">—</span>'
    you = sum(float((p.get(f"gw{g}") or {}).get("pts") or 0) for g in gws)
    them = sum(float(alt.get(f"pts_gw{g}") or 0) for g in gws)
    delta = (
        f" (+£{float(alt['delta']):.1f})"
        if alt.get("delta") is not None
        else ""
    )
    return (
        f'<div class="alt"><b>{alt.get("name_he") or alt.get("name")}</b> · '
        f'{alt.get("team")} {alt.get("pos")} · £{float(alt.get("price") or 0):.1f}{delta}'
        f'<span class="why">{alt.get("why") or ""}</span>'
        f'<span class="pts">6 מח׳: אתה {you:.1f} · מחליף {them:.1f}</span></div>'
    )


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


def write_gw12_table(horizon: list[dict], path: Path, squad: dict, gws: list[int]) -> None:
    """Keep the standalone horizon table in sync with live.json."""
    if not path.exists() or not horizon:
        return
    html = path.read_text(encoding="utf-8")
    pos_order = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
    rows = sorted(
        horizon,
        key=lambda p: (0 if p.get("xi") else 1, pos_order.get(p["pos"], 9), -p["price"]),
    )
    gw_hdr = "".join(f"<th>מחזור {g}</th>" for g in gws)
    body = []
    for p in rows:
        mark = " (C)" if p.get("captain") else " (VC)" if p.get("vice") else ""
        slot = "הרכב" if p.get("xi") else "ספסל"
        cls = ' class="bn"' if not p.get("xi") else ""
        gw_cells = "".join(_gw_td(p.get(f"gw{g}")) for g in gws)
        tot = sum(float((p.get(f"gw{g}") or {}).get("pts") or 0) for g in gws)
        body.append(
            f'<tr{cls}>\n  <td class="name"><b>{p["name"]}{mark}</b>'
            f'<div class="meta">{p["pos"]} · {p["team"]} · £{float(p["price"]):.1f} · {slot}</div></td>\n'
            f"{gw_cells}\n  <td><div class=\"pts\">{tot:.1f}</div></td>\n</tr>"
        )
    tbody = "\n".join(body)
    html2, n = re.subn(
        r"(<thead>\s*<tr>).*?(</tr>\s*</thead>)",
        rf"\1<th>שחקן</th>{gw_hdr}<th>סה״כ 6</th>\2",
        html,
        count=1,
        flags=re.S,
    )
    if n != 1:
        print("warn: could not patch horizon table thead")
    html2, n2 = re.subn(
        r"(<tbody>\s*).*?(\s*</tbody>)",
        rf"\1\n{tbody}\n\2",
        html2,
        count=1,
        flags=re.S,
    )
    if n2 != 1:
        print("warn: could not patch horizon table tbody")
        return
    g0, g1 = gws[0], gws[-1]
    html2, _ = re.subn(
        r'(<div class="sub">).*?(</div>)',
        rf"\1סגל WC · מחזורים {g0}–{g1} · תחזית: מודל אלי (לא ep הרשמי) · בלי כפל קפטן\2",
        html2,
        count=1,
        flags=re.S,
    )
    path.write_text(html2, encoding="utf-8")
    print(f"Updated {path}")


def build_horizon_from_live(squad: dict, gws: list[int]) -> list[dict]:
    """Build horizon rows from squad players gw* blocks."""
    out = []
    xi = set(squad.get("xi_ids") or [])
    for p in squad.get("players") or []:
        if not any(f"gw{g}" in p for g in gws):
            continue
        row = {
            "id": p["id"],
            "name": p.get("name_he") or HE.get(p["name"], p["name"]),
            "name_en": p["name"],
            "team": p["team"],
            "pos": p["pos"],
            "price": p["price"],
            "xi": p["id"] in xi if xi else p.get("xi", True),
            "captain": p.get("captain", False),
            "vice": p.get("vice", False),
            "alt": p.get("alt"),
            "alts": p.get("alts"),
        }
        total = 0.0
        for g in gws:
            row[f"gw{g}"] = p.get(f"gw{g}")
            total += float((p.get(f"gw{g}") or {}).get("pts") or 0)
        row["horizon_total"] = round(total, 1)
        out.append(row)
    return out


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
    gw = squad.get("gw_from") or 3
    gws = horizon_gws(squad)

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
        model_ep = 0.0
        for g in gws:
            model_ep += float((live.get(f"gw{g}") or {}).get("pts") or 0)
        if not model_ep:
            model_ep = float(p.get("ep_next") or 0)
        else:
            model_ep = round(model_ep / len(gws), 1)
        players.append(
            {
                "id": pid,
                "name": live.get("name_he") or HE.get(p["web_name"], p["web_name"]),
                "name_en": p["web_name"],
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
    gw_horizon = build_horizon_from_live(squad, gws)
    gws_payload = json.dumps(gws)
    gw_horizon_payload = json.dumps(gw_horizon, ensure_ascii=False)

    out_json = ROOT / "data" / "squad_view.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")

    html_path = ROOT / "viewer" / "squad.html"
    html = html_path.read_text(encoding="utf-8")
    payload = json.dumps(view, ensure_ascii=False)
    xi_ids = squad.get("xi_ids") or [p["id"] for p in players[:11]]
    xi_payload = json.dumps(xi_ids)
    gw12_payload = gw_horizon_payload

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
    if "const HORIZON_GWS =" not in html2:
        html2 = html2.replace(
            "const GW12 =",
            "const HORIZON_GWS = [];\n    const GW12 =",
            1,
        )
    html2 = patch_const(html2, "HORIZON_GWS", gws_payload)
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

    g0, g1 = gws[0], gws[-1]
    html2, _ = re.subn(
        r'(<h1>Eli\'s Team <span class="pill">).*?(</span></h1>)',
        rf"\1GW{g0}–{g1}\2",
        html2,
        count=1,
        flags=re.S,
    )
    html2, _ = re.subn(
        r'(<div class="sub">).*?(</div>)',
        rf"\1סגל WC · מחזורים {g0}–{g1} · שרקי (C) · איסאק (VC) · בלי Salah\2",
        html2,
        count=1,
        flags=re.S,
    )
    html2, _ = re.subn(
        r'(<section class="gw12-wrap[^"]*"[^>]*>\s*<h2>).*?(</h2>)',
        rf"\1יתרונות / חסרונות — מחזורים {g0}–{g1}\2",
        html2,
        count=1,
        flags=re.S,
    )
    html2, _ = re.subn(
        r'(<div class="gw12-sub">).*?(</div>)',
        r"\1תחזית נקודות: מודל אלי · בלי כפל קפטן · גלילה אופקית בטבלה · מחליפים בטבלה נפרדת למטה\2",
        html2,
        count=1,
        flags=re.S,
    )

    html_path.write_text(html2, encoding="utf-8")
    write_gw12_table(gw_horizon, ROOT / "viewer" / "squad_gw12_table.html", squad, gws)
    print(f"Updated {out_json}")
    print(f"Updated {html_path} (horizon rows={len(gw_horizon)}, GW{g0}–{g1})")


if __name__ == "__main__":
    main()
