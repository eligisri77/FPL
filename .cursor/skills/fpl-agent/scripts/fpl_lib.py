"""Shared FPL helpers for Eli's agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]  # D:/Games/FPL
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "profile.yaml"

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_LIMITS = {1: 2, 2: 5, 3: 5, 4: 3}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_profile() -> dict[str, Any]:
    # Minimal YAML subset parser (no PyYAML dependency)
    text = CONFIG.read_text(encoding="utf-8")
    profile: dict[str, Any] = {
        "banned_players": [],
        "locked_players": [],
        "avoid_players": [],
        "prefer_players": [],
        "target_itb": 0.2,
        "budget_total": 100.0,
        "planning_horizon_gws": 6,
        "team_id": None,
    }
    current_list = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.strip().startswith("- "):
            if current_list is not None:
                val = line.strip()[2:].strip().strip("\"'")
                if val and val != "[]":
                    profile[current_list].append(val)
            continue
        current_list = None
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip("\"'")
        if key == "target_itb":
            profile["target_itb"] = float(val) if val else 0.2
        elif key == "total" and "budget" in text:
            try:
                profile["budget_total"] = float(val)
            except ValueError:
                pass
        elif key == "planning_horizon_gws":
            profile["planning_horizon_gws"] = int(val)
        elif key == "team_id":
            profile["team_id"] = None if val in ("null", "", "None") else val
        elif key == "banned_players":
            current_list = "banned_players"
            if val and val != "[]":
                profile["banned_players"].append(val)
        elif key == "locked_players":
            current_list = "locked_players"
        elif key == "avoid_players":
            current_list = "avoid_players"
        elif key == "prefer_players":
            current_list = "prefer_players"
    return profile


def load_bootstrap() -> dict[str, Any]:
    path = DATA / "bootstrap.json"
    if not path.exists():
        raise FileNotFoundError("Missing data/bootstrap.json — run fetch_data.py first")
    return load_json(path)


def teams_by_id(bootstrap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {t["id"]: t for t in bootstrap["teams"]}


def player_label(p: dict[str, Any], teams: dict[int, dict[str, Any]]) -> str:
    team = teams[p["team"]]["short_name"]
    return f"{p['web_name']} ({team}, £{p['now_cost']/10:.1f}m)"


def is_banned(p: dict[str, Any], banned: list[str]) -> bool:
    blob = f"{p.get('web_name','')} {p.get('first_name','')} {p.get('second_name','')}".lower()
    return any(b.lower() in blob for b in banned)


def next_gw(bootstrap: dict[str, Any]) -> int:
    for e in bootstrap["events"]:
        if e.get("is_next"):
            return int(e["id"])
    for e in bootstrap["events"]:
        if e.get("is_current"):
            return int(e["id"])
    return 1


def fixture_attack_score(
    fixtures: list[dict[str, Any]],
    team_id: int,
    gw_from: int,
    horizon: int,
) -> float:
    """Higher = easier attack fixtures. Uses official difficulty (lower FDR better)."""
    score = 0.0
    count = 0
    for f in fixtures:
        ev = f.get("event")
        if ev is None or ev < gw_from or ev >= gw_from + horizon:
            continue
        if f["team_h"] == team_id:
            # attack vs away defence difficulty
            diff = f.get("team_h_difficulty") or 3
            home_bonus = 0.25
            score += (6 - diff) + home_bonus
            count += 1
        elif f["team_a"] == team_id:
            diff = f.get("team_a_difficulty") or 3
            score += 6 - diff
            count += 1
    return score / count if count else 0.0


def fixture_def_score(
    fixtures: list[dict[str, Any]],
    team_id: int,
    gw_from: int,
    horizon: int,
) -> float:
    score = 0.0
    count = 0
    for f in fixtures:
        ev = f.get("event")
        if ev is None or ev < gw_from or ev >= gw_from + horizon:
            continue
        if f["team_h"] == team_id:
            diff = f.get("team_h_difficulty") or 3
            score += (6 - diff) + 0.25
            count += 1
        elif f["team_a"] == team_id:
            diff = f.get("team_a_difficulty") or 3
            score += 6 - diff
            count += 1
    return score / count if count else 0.0
