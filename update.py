"""Independent, fail-closed anniversary updater. No AI, credentials or SNB writes."""
import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
import urllib.request
from zoneinfo import ZoneInfo
from detector import achievements

ROOT = Path(__file__).resolve().parent
API = 'https://statsapi.mlb.com/api/v1/'
CUBA = 'https://raw.githubusercontent.com/yordimlb89/pelota-cubana-serie65-data/main/data.json'

def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'PelotaCubanaStats-Efemerides/1.0'})
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def norm(name):
    plain = ''.join(c for c in unicodedata.normalize('NFD', name.lower()) if not unicodedata.combining(c))
    return ' '.join(sorted(re.findall(r'[a-z0-9]+', plain)))

def duplicate(event, events):
    for other in events.values():
        if other['key'] == event['key'] or other['date'] != event['date']:
            continue
        a, b = set(norm(other['name']).split()), set(norm(event['name']).split())
        name_match = len(a & b) >= 2 and (a <= b or b <= a)
        same = (event.get('id') and other.get('id') == event['id']) or name_match
        # A reviewed entry remains authoritative. Ambiguous same-day matches go to review.
        if same and not other['key'].startswith('automatic-mlb-') and not other['key'].startswith('automatic-live-cuba-'):
            return other['key']
    return None

def pending_match(event, existing_key, pending):
    item = {'key': 'review-' + event['key'], 'reason': 'Posible duplicado del mismo jugador y fecha',
            'existingKey': existing_key, 'candidate': event}
    pending[item['key']] = item

def check_date(value, today):
    assert dt.date.fromisoformat(value).isoformat() == value, 'Invalid date'
    assert value <= today, 'Future date'

def validate(data, previous=None, removable=()):
    assert all(isinstance(data.get(k), list) and data[k] for k in ('people', 'events'))
    today = dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    for section in ('people', 'events'):
        assert len({x['key'] for x in data[section]}) == len(data[section]), 'Duplicate identity'
        for item in data[section]:
            assert item['name'] and item['origin'] in ('cuba', 'heritage', 'mlb')
            assert isinstance(item['leagues'], list) and item['leagues']
            if section == 'events':
                check_date(item['date'], today)
                assert item['title'] and item['detail'] and item['source'].startswith(('https://', '/'))
            else:
                for date in item['dates'].values():
                    check_date(date['date'], today)
                    assert date['source'].startswith(('https://', '/'))
                if item['dates'].get('birth') and item['dates'].get('death'):
                    assert item['dates']['birth']['date'] <= item['dates']['death']['date']
    if previous:
        assert {p['key'] for p in previous['people']} <= {p['key'] for p in data['people']}, 'Lost people'
        old = {e['key']: e for e in previous['events']}
        new = {e['key']: e for e in data['events']}
        assert set(old) - set(new) <= set(removable), 'Lost history'
        for key, event in old.items():
            if key not in removable:
                assert new[key] == event, 'Unexpected historical edit'
    assert data['coverage']['events'] == len(data['events'])

def cuba_events(source, events, pending, today):
    assert source['schema'] == 1 and source['snapshot']['edition'] == 65
    reports = source['reports']
    records = {r['id']: r for r in source['records']}
    checked = 0
    removable = set()
    for game in source['snapshot']['games']:
        rid = game.get('reportId')
        if not rid or game.get('score') is None:
            continue
        record, report = records[rid], reports[rid]
        assert record['kind'] == 'Juegos'
        assert list(map(str, game['score'])) == record['game']['scores']
        assert game['date'] == record['game']['date']
        check_date(game['date'], today)
        prefix = 'automatic-live-cuba-65-' + str(game['number']) + '-'
        removable.update(k for k in events if k.startswith(prefix))
        for key in list(events):
            if key.startswith(prefix):
                del events[key]
        checked += 1
        for table in report['structured']:
            group = table['group']
            if group not in ('Bateo', 'Pitcheo'):
                continue
            columns = table['columns']
            assert 'Nombre' in columns and ('HR' in columns if group == 'Bateo' else 'SO' in columns)
            for row in table['rows']:
                assert len(row) == len(columns)
                raw = dict(zip(columns, row))
                name = raw['Nombre'].split(' - ', 1)[0].strip()
                if not name or name.upper() in ('TOTAL', 'TOTALES'):
                    continue
                stats = {v: raw.get(k) for k, v in {'VB':'atBats','H':'hits','2B':'doubles','3B':'triples','HR':'homeRuns','CI':'rbi','SO':'strikeOuts'}.items()}
                stats['group'] = 'batting' if group == 'Bateo' else 'pitching'
                if group == 'Pitcheo':
                    stats = {'group':'pitching', 'strikeOuts': raw.get('SO')}
                post = record.get('phase') in ('Play Off', 'Playoff', 'Postemporada')
                marks = achievements(stats, post)
                if not marks:
                    continue
                identity = hashlib.sha256((norm(name)+'|'+group+'|'+table['label']).encode()).hexdigest()[:24]
                key = prefix + identity
                line = (f"Bateó de {raw['VB']}-{raw['H']}, con {raw['HR']} HR y {raw['CI']} CI." if group == 'Bateo'
                        else f"Ponchó a {raw['SO']} bateadores.")
                phase = 'postemporada' if post else 'temporada regular'
                event = {'key':key,'date':game['date'],'name':name,'id':None,'origin':'cuba','leagues':['cuba-history'],
                         'title':' · '.join(marks),'detail':f"{line} {table['label']} · {record['title']} · Serie Nacional 65, {phase}.",
                         'source':game['source'],'href':'/beisbol-cubano','gameId':game['id'],'phase':phase,
                         'method':'official-final-cuba-boxscore','upstreamUpdatedAt':report['updatedAt']}
                existing = duplicate(event, events)
                if existing:
                    pending_match(event, existing, pending)
                else:
                    events[key] = event
    return checked, removable

def refresh(previous, pending, days=7, getter=fetch):
    data = copy.deepcopy(previous)
    end = dt.datetime.now(ZoneInfo('America/New_York')).date()
    start = end - dt.timedelta(days=days)
    people = {p['id']:p for p in data['people'] if p.get('id') and p['origin'] in ('cuba','heritage')}
    assert len(people) == sum(bool(p.get('id')) and p['origin'] in ('cuba','heritage') for p in data['people']), 'Conflicting MLB identities'
    events = {e['key']:e for e in data['events']}
    games = {}
    for sport, league in {1:'mlb',11:'aaa',12:'aa',13:'high-a',14:'a',16:'rookie'}.items():
        schedule = getter(API + f'schedule?sportId={sport}&startDate={start}&endDate={end}')
        assert 'dates' in schedule and 'totalGames' in schedule, 'Invalid schedule'
        for day in schedule['dates']:
            for game in day['games']:
                if game['status']['abstractGameState'] == 'Final' and game['gameType'] in ('R','F','D','L','W'):
                    games[game['gamePk']] = (game, league)
    removable = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        boxes = list(pool.map(lambda gid:getter(API + f'game/{gid}/boxscore'), games))
    for (gid, (game, league)), box in zip(games.items(), boxes):
        assert all('players' in box['teams'][side] for side in ('home','away')), 'Invalid boxscore'
        check_date(game['officialDate'], end.isoformat())
        prefix = f'automatic-mlb-{gid}-'
        removable.update(k for k in events if k.startswith(prefix))
        for key in list(events):
            if key.startswith(prefix):
                del events[key]
        for side, other in [('home','away'), ('away','home')]:
            for player in box['teams'][side]['players'].values():
                pid = player['person']['id']
                if pid not in people:
                    continue
                p, post = people[pid], game['gameType'] != 'R'
                for group in ('batting','pitching'):
                    raw = player.get('stats',{}).get(group,{})
                    stats = raw if group == 'batting' else {k:raw.get(k) for k in ('strikeOuts','inningsPitched','hits','completeGames')}
                    marks = achievements({**stats,'group':group,'completeGame':raw.get('completeGames') == 1}, post)
                    if not marks:
                        continue
                    phase = 'postemporada' if post else 'temporada regular'
                    line = (f"Bateó de {raw.get('atBats',0)}-{raw.get('hits',0)}, con {raw.get('homeRuns',0)} HR y {raw.get('rbi',0)} CI." if group == 'batting'
                            else f"Lanzó {raw.get('inningsPitched')} entradas y ponchó a {raw.get('strikeOuts',0)}.")
                    key = prefix + f'{pid}-{group}'
                    event = {'key':key,'playerKey':p['key'],'date':game['officialDate'],'name':p['name'],'id':pid,'origin':p['origin'],
                             'leagues':[league] if league == 'mlb' else ['milb',league], 'title':' · '.join(marks),
                             'detail':f'{line} {game["teams"][side]["team"]["name"]} ante {game["teams"][other]["team"]["name"]} · {phase}.',
                             'source':f'https://www.mlb.com/gameday/{gid}','href':p.get('href'),'gameId':gid,'phase':phase,'method':'official-final-boxscore'}
                    existing = duplicate(event, events)
                    if existing:
                        pending_match(event, existing, pending)
                    else:
                        events[key] = event
    ids = sorted(people)
    for index in range(0,len(ids),50):
        batch = ids[index:index+50]
        bios = getter(API + 'people?personIds=' + ','.join(map(str,batch)))['people']
        assert set(batch) == {b['id'] for b in bios}, 'Incomplete biography response'
        for bio in bios:
            for field, kind in [('birthDate','birth'),('deathDate','death')]:
                value = bio.get(field)
                if value:
                    check_date(value, end.isoformat())
                    old = people[bio['id']]['dates'].get(kind)
                    if not old or old['date'] != value:
                        people[bio['id']]['dates'][kind] = {'date':value,'source':f'https://www.mlb.com/player/{bio["id"]}'}
    checked, cuba_removable = cuba_events(getter(CUBA), events, pending, end.isoformat())
    removable.update(cuba_removable)
    data['events'] = sorted(events.values(), key=lambda e:(e['date'],e['key']))
    data['coverage'].update(directory=len(data['people']),births=sum('birth' in p['dates'] for p in data['people']),
                            deaths=sum('death' in p['dates'] for p in data['people']), events=len(events),
                            missingBirthDates=sum('birth' not in p['dates'] for p in data['people']))
    validate(data, previous, removable)
    old_events = {e['key']:e for e in previous['events']}
    data['retiredAutomaticKeys'] = sorted((set(previous.get('retiredAutomaticKeys',[])) | (set(old_events)-set(events))) - set(events))
    changed = old_events != events or previous['people'] != data['people']
    if changed:
        data['updatedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    else:
        data = previous
    return data, {'mlbMilbGamesChecked':len(games),'cubaGamesChecked':checked,'changed':changed,
                  'added':sorted(set(events)-set(old_events)),'removedAfterOfficialCorrection':sorted(set(old_events)-set(events)),
                  'pending':len(pending)}

def atomic(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    os.replace(temporary,path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days',type=int,default=7)
    parser.add_argument('--validate-only',action='store_true')
    args = parser.parse_args()
    assert 1 <= args.days <= 366
    path = ROOT/'data.json'
    data = json.loads(path.read_text())
    validate(data)
    if args.validate_only:
        print('Validated:',len(data['people']),'people;',len(data['events']),'events')
        return
    backlog_path = ROOT/'automatic-pending.json'
    pending = json.loads(backlog_path.read_text()) if backlog_path.exists() else {}
    # All network and validation operations complete before any published data is written.
    result, summary = refresh(data,pending,args.days)
    if result != data:
        atomic(path,result)
    if pending or backlog_path.exists():
        atomic(backlog_path,pending)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as report:
            report.write('## Efemérides\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n')

if __name__ == '__main__':
    main()
