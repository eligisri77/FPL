#!/usr/bin/env python3
"""Fetch live FPL bootstrap + fixtures into data/."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "data"
BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"


def get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "EliFPLAgent/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    print("Fetching bootstrap-static...")
    bootstrap = get_json(BOOTSTRAP_URL)
    out_b = DATA / "bootstrap.json"
    out_b.write_text(json.dumps(bootstrap, ensure_ascii=False), encoding="utf-8")
    print(f"  players={len(bootstrap['elements'])} -> {out_b}")

    print("Fetching fixtures...")
    fixtures = get_json(FIXTURES_URL)
    out_f = DATA / "fixtures.json"
    out_f.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
    print(f"  fixtures={len(fixtures)} -> {out_f}")

    nxt = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    cur = next((e for e in bootstrap["events"] if e.get("is_current")), None)
    print(f"current_gw={cur['id'] if cur else None} next_gw={nxt['id'] if nxt else None}")
    if nxt:
        print(f"deadline={nxt.get('deadline_time')}")
    print("Done.")


if __name__ == "__main__":
    main()
