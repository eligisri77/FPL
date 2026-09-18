import json, sys
from pathlib import Path
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path('.cursor/skills/fpl-agent/scripts')))
from build_horizon_squad import enrich_squad, HE

b = json.load(open('data/bootstrap.json', encoding='utf-8'))
teams = {t['id']: t['short_name'] for t in b['teams']}
by = {p['id']: p for p in b['elements']}
fix = json.load(open('data/fixtures.json', encoding='utf-8'))

# New squad from image (GW4 XI):
# XI: Raya, Hall, Calafiori, Kayode, Yalcouyé, Palmer, Gakpo, Mbeumo, Haaland, João Pedro, Gonzalo
# Bench: Verbruggen, Armstrong, Castagne, Guéhi
# Transfer done: Cherki -> Gakpo

gakpo = next(p for p in b['elements'] if p['web_name']=='Gakpo')
print('Gakpo', gakpo['id'], teams[gakpo['team']], gakpo['now_cost']/10, 'min', gakpo['minutes'], 'starts', gakpo.get('starts'))

xi_ids = [1, 449, 8, 88, 605, 154, 367, 427, 411, 165, 569]
bench_ids = [109, 244, 258, 388]
# verify Gakpo id
assert gakpo['id'] == 367 or True
xi_ids = [1, 449, 8, 88, 605, 154, gakpo['id'], 427, 411, 165, 569]
player_ids = xi_ids + bench_ids

HE['Gakpo'] = 'גקפו'
HE['Yalcouyé'] = 'יאלקויה'
HE['Kayode'] = 'קאיודה'

path = Path('squads/live.json')
squad = json.loads(path.read_text(encoding='utf-8'))
squad['player_ids'] = player_ids
squad['xi_ids'] = xi_ids
squad['bench_ids'] = bench_ids
squad['captain_id'] = 411
squad['vice_id'] = 154
squad['gw_from'] = 4
squad['horizon'] = 6
squad['label'] = 'eli_gw4_sep07'
squad['notes'] = (
    'סגל GW4 (עדכון 7/9): חילוף 1 — שרקי→גקפו. '
    'XI: ראיה · הול/קאלאפיורי/קאיודה · יאלקויה/פאלמר(VC)/גקפו/מבאומו · האלאנד(C)/ז׳ואאו פדרו/גונסאלו. '
    'ספסל: ורברוגן, ארמסטרונג, קסטן, גווהי. בלי סלאח.'
)
squad['players'] = []
squad = enrich_squad(squad, gw_from=4, gw_to=9)
path.write_text(json.dumps(squad, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('cost', squad['cost'], 'itb', squad['itb'])
print('clubs', dict(Counter(teams[by[i]['team']] for i in player_ids)))

print('\n=== אופק GW4–9 (XI + חלשים) ===')
rows = []
for p in squad['players']:
    tot = sum((p.get(f'gw{g}') or {}).get('pts',0) for g in range(4,10))
    rows.append((0 if p['xi'] else 1, -tot, p))
for _,__,p in sorted(rows):
    tag='XI' if p['xi'] else 'BN'
    print(f"{tag} {p['name_he']:14} {p['team']:3} £{p['price']:.1f} tot={sum((p.get(f'gw{g}') or {}).get('pts',0) for g in range(4,10)):5.1f}")

# GW4 fixtures for squad
print('\n=== GW4 יריבים ===')
for pid in xi_ids:
    p=by[pid]
    tid=p['team']
    for f in fix:
        if f.get('event')!=4: continue
        if f['team_h']==tid:
            print(f"  {p['web_name']:14} vs {teams[f['team_a']]}(H) FDR{f.get('team_h_difficulty')}"); break
        if f['team_a']==tid:
            print(f"  {p['web_name']:14} vs {teams[f['team_h']]}(A) FDR{f.get('team_a_difficulty')}"); break
