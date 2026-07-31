# Fantasy Premier League — Eli's Agent

פרויקט אסטרטגיה וסוכן FPL לעונת 2026/27.

## מה יש כאן

| נתיב | תפקיד |
|---|---|
| `config/profile.yaml` | ההעדפות שלך (מקור האמת) |
| `.cursor/rules/fpl-core.mdc` | חוקים קבועים לסוכן Cursor |
| `.cursor/skills/fpl-agent/` | סקיל + סקריפטים |
| `data/` | קאש מ־API (bootstrap, fixtures) |
| `squads/` | טיוטות סגל |

## איך מריצים

מתוך `D:\Games\FPL`:

```powershell
python .cursor/skills/fpl-agent/scripts/fetch_data.py
python .cursor/skills/fpl-agent/scripts/suggest_squad.py
python .cursor/skills/fpl-agent/scripts/validate_squad.py squads/gw1_draft.json
```

## איפה מוצאים Team ID

1. היכנס ל־[fantasy.premierleague.com](https://fantasy.premierleague.com)
2. אחרי שיש סגל, לך ל־**Points** / **Pick Team**
3. בכתובת תופיע משהו כמו:  
   `https://fantasy.premierleague.com/entry/1234567/event/1`
4. המספר (`1234567`) הוא ה־**Team ID**
5. שמור ב־`config/profile.yaml` תחת `team_id:`

עדיין אין סגל? לא צריך Team ID עכשיו.

## החוקים שלך (תמצית)

- מטרה: דירוג כללי גבוה | סגנון: אגרסיבי | ~שעה בשבוע
- אופק תכנון: 6 מחזורים
- בלי Salah
- עד 3 מאותה קבוצה, **לא באותו תפקיד**
- כסף בצד: ~£0.2m
- עדיפות ל־11 חזקים, ספסל זול

## צפייה בטלפון

אחרי העלאה ל־GitHub Pages:

| דף | קישור |
|---|---|
| בית | `https://eligisri77.github.io/FPL/` |
| כל הסגלים | `https://eligisri77.github.io/FPL/viewer/alternatives.html` |
| סגל ראשי | `https://eligisri77.github.io/FPL/viewer/squad.html` |
| כובשים | `https://eligisri77.github.io/FPL/viewer/goals_watchlist.html` |

בטלפון: פתח את הקישור → אפשר גם «הוסף למסך הבית».

## שימוש ב־Cursor

פתח את התיקייה `D:\Games\FPL` כ־workspace (או הוסף אותה), ואז שאל למשל:

- "תבנה סגל ל־GW1–6"
- "בדוק את הטיוטה ב־squads/"
- "טרנספרים למחזור הבא"
