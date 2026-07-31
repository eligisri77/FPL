# FPL Agent — Reference

## Hard constraints (must enforce)

1. **Budget**: ≤ £100.0m spent; target ITB £0.2m (±0.1 OK if unlocks clear upgrade)
2. **Salah**: never select any player whose web_name/second_name matches Salah (Liverpool)
3. **Club limit**: ≤ 3 players per `team` id
4. **Same club + same position**: forbidden  
   Position codes: 1=GK, 2=DEF, 3=MID, 4=FWD
5. **Squad size**: 2 GK, 5 DEF, 5 MID, 3 FWD
6. **Valid XI**: at least 1 GK, 3–5 DEF, 2–5 MID, 1–3 FWD; exactly 11

## Philosophy notes

Eli prefers a **strong XI** over a balanced bench. Default:
- Playing 11 carry the points
- Bench = cheapest legal coverage (4.0/4.5) unless a £0.5 upgrade clearly prevents blank risk

Suggest a stronger bench only when:
- Multiple rotation risks in XI, or
- Blank/DGW period approaching

## Planning horizon

Default build window = **next 6 gameweeks** from current/next GW.  
Do not optimize for GW10+ unless using Wildcard planning.

## Live data

Official API (no auth for public endpoints):

| Endpoint | Use |
|---|---|
| `/api/bootstrap-static/` | Players, teams, events, prices |
| `/api/fixtures/` | Fixtures / difficulty |
| `/api/entry/{team_id}/` | Manager entry |
| `/api/entry/{team_id}/event/{gw}/picks/` | Current picks |

Scripts cache to `data/bootstrap.json` and `data/fixtures.json`.

## Finding Team ID

1. Open https://fantasy.premierleague.com and log in
2. Go to **Points** or **Pick Team**
3. URL looks like: `https://fantasy.premierleague.com/entry/1234567/event/1`
4. The number `1234567` is the **Team ID**
5. Save it in `config/profile.yaml` → `team_id:`

Not required until a squad is saved online.

## Aggressive OR heuristics

- Captaincy > marginal 5th midfielder upgrades
- Prefer minutes certainty over ceiling for mid-price
- Differentials: ~20–30% of squad max
- Don't chase a one-week haul without forward fixtures
