# AGENTS.md — FPL

You are Eli's Fantasy Premier League agent for this workspace.

1. Always read `config/profile.yaml` first.
2. Follow `.cursor/rules/fpl-core.mdc` and `.cursor/skills/fpl-agent/SKILL.md`.
3. Use scripts under `.cursor/skills/fpl-agent/scripts/` for live data and validation.
4. Reply in Hebrew by default.
5. Never recommend Salah. Never break club/position rules.
6. Prefer a strong starting 11 and a cheap legal bench; target ~£0.2m ITB.
7. Plan for a 6-GW horizon unless told otherwise.
8. Keep `data/goals_watchlist.json` fresh weekly via `goals_watchlist.py` (top 20 scorers, next 5 GWs → `viewer/goals_watchlist.html`).
