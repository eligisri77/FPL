---
name: fpl-agent
description: >-
  Builds and manages Fantasy Premier League (FPL) squads for Eli using project
  rules, live API data, and local scripts. Use when the user asks about FPL,
  Fantasy Premier League, squad selection, transfers, chips, captaincy,
  fixtures, or anything under D:/Games/FPL.
---

# FPL Agent

## Always do first

1. Read `config/profile.yaml`
2. Ensure fresh data: `python .cursor/skills/fpl-agent/scripts/fetch_data.py`
3. Obey hard constraints in the profile (Salah ban, club/position rules, ITB)

## Core strategy (Eli)

| Setting | Value |
|---|---|
| Goal | High overall rank |
| Style | Aggressive |
| Time | 60 min/week |
| Horizon | GW1–2 strong 15, then Wildcard GW3 |
| Bench | Strong / usable for GW1–2 (not 4.0 fodder) |
| ITB target | £0.2m |

### Hit rule
Take **-4** only if improving ≥2 of: captain / tough fixture / asset trajectory.
In GW1–2: avoid hits unless injury — rebuild on WC GW3.

### Chips
- **WC: GW3** (after early info: minutes, injuries, form)
- FH: blanks only
- TC/BB: doubles or elite fixture; BB optional GW2 if bench is live

## Weekly 60-minute loop

1. Injuries / price drops / flags (10m)
2. Fixtures this GW + next 2 (15m)
3. Transfers — max 2 concrete options (20m)
4. Captain — choose between 2 candidates (10m)
5. Set XI + bench order (5m)

## Squad build workflow

```
Task Progress:
- [ ] Load profile + bootstrap data
- [ ] Apply bans / locks / prefer list
- [ ] Draft strong XI for next 6 GWs
- [ ] Fill cheap legal bench
- [ ] Validate (budget, 3/club, no same club+position, formation)
- [ ] Leave ~£0.2m ITB
- [ ] Write squads/gwN_draft.json
- [ ] Present XI, captain, rationale in Hebrew
```

### Commands

```bash
python .cursor/skills/fpl-agent/scripts/fetch_data.py
python .cursor/skills/fpl-agent/scripts/suggest_squad.py
python .cursor/skills/fpl-agent/scripts/validate_squad.py squads/gw1_draft.json
python .cursor/skills/fpl-agent/scripts/goals_watchlist.py   # top 20 scorers, next 5 GWs
python .cursor/skills/fpl-agent/scripts/keepers_watchlist.py # top 20 GKs, next 5 GWs
python .cursor/skills/fpl-agent/scripts/gw_goals_board.py     # GW1–2 high/low goal matches
```

## Weekly goals watchlist

Every week (or when user asks), refresh the projected top scorers:

1. `python .cursor/skills/fpl-agent/scripts/fetch_data.py`
2. `python .cursor/skills/fpl-agent/scripts/goals_watchlist.py`
3. Open `viewer/goals_watchlist.html` or summarize `data/goals_watchlist.json` in Hebrew

Default: **top 20**, horizon **next 5 GWs**, Salah excluded.

## Weekly keepers watchlist

Same loop with `keepers_watchlist.py` → `viewer/keepers_watchlist.html` (projected FPL pts: CS / saves / pens).

## Output template

```markdown
## סגל מוצע (GWX–Y)
**ITB:** £X.Xm | **מבנה:** X-Y-Z

### XI
...
### ספסל
...
### קפטן / סגן
...
### למה ככה
- ...
### סיכונים
- ...
```

## Additional resources

- Constraints & FPL API notes: [reference.md](reference.md)
- Team ID help: [../../../README.md](../../../README.md)
