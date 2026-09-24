import json
p = r'd:\Trae\horse\data\references\_odds_HV_20260923_R456789.json'
with open(p, 'r', encoding='utf-8') as f:
    d = json.load(f)
for r in d:
    r.pop('horseCount', None)
with open(p, 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print('Cleaned horseCount field')
for r in d:
    print(f'R{r["raceNumber"]}: {len(r["horses"])} horses @ {r["updateTime"]}')
