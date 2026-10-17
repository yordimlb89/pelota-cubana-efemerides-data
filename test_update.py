import copy
import datetime as dt
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import update
from detector import achievements

class AnniversaryTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'data.json').read_text())

    def test_all_existing_history_valid(self):
        update.validate(self.data)
        self.assertGreaterEqual(len(self.data['events']),1806)

    def test_four_homers_is_only_a_fixture(self):
        self.assertIn('4 jonrones en un juego',achievements(dict(group='batting',atBats=4,hits=4,homeRuns=4)))

    def test_postseason_and_pitching(self):
        self.assertEqual(achievements(dict(homeRuns=2)),[])
        self.assertEqual(achievements(dict(homeRuns=2),True),['2 jonrones en un juego'])
        self.assertEqual(achievements(dict(group='pitching',hits=6,strikeOuts=4)),[])
        self.assertEqual(achievements(dict(group='pitching',hits=0,inningsPitched='1.0')),[])
        self.assertIn('Juego completo de nueve entradas sin hits',achievements(dict(group='pitching',hits=0,inningsPitched='9.0',completeGame=True)))

    def test_cycle_needs_single(self):
        self.assertNotIn('Batea para el ciclo',achievements(dict(hits=3,doubles=1,triples=1,homeRuns=1)))
        self.assertIn('Batea para el ciclo',achievements(dict(hits=4,doubles=1,triples=1,homeRuns=1)))

    def test_preservation_guard(self):
        data=copy.deepcopy(self.data)
        data['events'].pop()
        data['coverage']['events']=len(data['events'])
        with self.assertRaises(AssertionError):update.validate(data,self.data)

    def test_missing_death_does_not_erase_death(self):
        previous=copy.deepcopy(self.data)
        def fake(url):
            if 'schedule?' in url:return {'dates':[],'totalGames':0}
            if 'people?' in url:
                return {'people':[{'id':int(x)} for x in url.split('personIds=')[1].split(',')]}
            if url==update.CUBA:return {'schema':1,'snapshot':{'edition':65,'games':[]},'records':[],'reports':{}}
            raise AssertionError(url)
        result,summary=update.refresh(previous,{},getter=fake)
        self.assertEqual(result,self.data)
        self.assertFalse(summary['changed'])

    def test_failed_fetch_preserves_input(self):
        before=copy.deepcopy(self.data)
        def fail(url):raise OSError('Source unavailable')
        with self.assertRaises(OSError):update.refresh(self.data,{},getter=fail)
        self.assertEqual(self.data,before)

    def test_duplicate_ordered_name_goes_to_review(self):
        event={'key':'new','date':'2026-10-06','name':'BRIDÓN DÍAZ Jonathan','id':None}
        existing={'old':{'key':'old','date':'2026-10-06','name':'Jonathan Bridón Díaz','id':None}}
        self.assertEqual(update.duplicate(event,existing),'old')
        event['name']='BRIDÓN DÍAZ Jonathan Lázaro'
        self.assertEqual(update.duplicate(event,existing),'old')

    def test_nonfinal_cuba_ignored_and_final_repeat_stable(self):
        source={'schema':1,'snapshot':{'edition':65,'games':[{'reportId':None,'score':None}]},'records':[],'reports':{}}
        events={};pending={}
        self.assertEqual(update.cuba_events(source,events,pending,'2026-10-07')[0],0)
        game={'id':'snb65-clasificatoria-99','number':99,'reportId':'r','score':[4,0],'date':'2026-10-06','source':'https://www.beisbolcubano.cu/estadisticas/BoxScore?idJuego=99'}
        record={'id':'r','kind':'Juegos','title':'A vs B','phase':'Clasificatoria','game':{'scores':['4','0'],'date':'2026-10-06'}}
        report={'updatedAt':'2026-10-07','structured':[{'group':'Bateo','label':'A','columns':['Nombre','VB','H','2B','3B','HR','CI'],'rows':[['PRUEBA Ejemplo - D','4','4','0','0','4','4']]}]}
        source['snapshot']['games']=[game];source['records']=[record];source['reports']={'r':report}
        update.cuba_events(source,events,pending,'2026-10-07')
        once=copy.deepcopy(events)
        update.cuba_events(source,events,pending,'2026-10-07')
        self.assertEqual(events,once);self.assertEqual(len(events),1)
        report['structured'][0]['rows'][0][5]='1'
        update.cuba_events(source,events,pending,'2026-10-07')
        self.assertEqual(events,{})

class MLBFinalSelectionTests(unittest.TestCase):
    def setUp(self):
        now = dt.datetime(2026, 10, 17, 12, tzinfo=dt.timezone.utc)
        clock = patch('update.dt.datetime', wraps=dt.datetime)
        clock.start().now.return_value = now
        self.addCleanup(clock.stop)
        self.data = {
            'people': [{'key': 'fixture-person', 'id': 7, 'name': 'Fixture Player',
                        'origin': 'cuba', 'leagues': ['mlb'], 'dates': {}}],
            'events': [{'key': 'curated-fixture', 'date': '2020-01-01',
                        'name': 'Historical Fixture', 'origin': 'cuba', 'leagues': ['mlb'],
                        'title': 'Preserved history', 'detail': 'Test fixture only.',
                        'source': 'https://example.com/history'}],
            'coverage': {'events': 1},
        }
        self.game = {
            'gamePk': 849817, 'gameType': 'L', 'officialDate': '2026-10-16',
            'status': {'abstractGameState': 'Final', 'codedGameState': 'F',
                       'statusCode': 'F', 'detailedState': 'Final'},
            'teams': {'away': {'team': {'name': 'Tampa Bay Rays'}},
                      'home': {'team': {'name': 'Cleveland Guardians'}}},
        }
        self.box = {'teams': {
            'home': {'players': {}},
            'away': {'players': {'ID7': {'person': {'id': 7},
                     'stats': {'batting': {'atBats': 4, 'hits': 2, 'homeRuns': 2, 'rbi': 4}}}}},
        }}
        self.box_requests = []

    def fake(self, url):
        if 'schedule?' in url:
            games = [self.game] if 'sportId=1&' in url else []
            return {'dates': [{'date': '2026-10-16', 'games': games}], 'totalGames': len(games)}
        if '/boxscore' in url:
            self.box_requests.append(url)
            return self.box
        if 'people?' in url:
            return {'people': [{'id': 7}]}
        if url == update.CUBA:
            return {'schema': 1, 'snapshot': {'edition': 65, 'games': []}, 'records': [], 'reports': {}}
        raise AssertionError(url)

    def test_postponed_future_date_preserves_history_without_fetching_boxscore(self):
        self.game['officialDate'] = '2026-10-18'
        self.game['status'].update(codedGameState='D', statusCode='DR', detailedState='Postponed', reason='Rain')
        existing = dict(self.data['events'][0], key='automatic-mlb-849817-7-batting')
        self.data['events'].append(existing)
        self.data['coverage']['events'] = 2
        before = copy.deepcopy(self.data)
        result, summary = update.refresh(self.data, {}, getter=self.fake)
        self.assertEqual(result, before)
        self.assertEqual(self.data, before)
        self.assertEqual(self.box_requests, [])
        self.assertEqual(summary['mlbMilbGamesChecked'], 0)
        self.assertFalse(summary['changed'])

    def test_nonfinal_and_unknown_codes_are_not_processed(self):
        for code in ('D', 'C', 'I', 'S', 'O', 'Q', 'R', 'unknown', None):
            with self.subTest(code=code):
                self.game['status']['codedGameState'] = code
                result, summary = update.refresh(self.data, {}, getter=self.fake)
                self.assertEqual(result, self.data)
                self.assertEqual(summary['mlbMilbGamesChecked'], 0)
        del self.game['status']['codedGameState']
        result, summary = update.refresh(self.data, {}, getter=self.fake)
        self.assertEqual(result, self.data)
        self.assertEqual(summary['mlbMilbGamesChecked'], 0)
        self.assertEqual(self.box_requests, [])

    def test_genuine_final_and_completed_early_are_processed_and_repeat_stable(self):
        for status, detail in (('F', 'Final'), ('FR', 'Completed Early: Rain')):
            with self.subTest(status=status):
                self.game['status'].update(statusCode=status, detailedState=detail)
                before = copy.deepcopy(self.data)
                result, summary = update.refresh(self.data, {}, getter=self.fake)
                self.assertEqual(self.data, before)
                self.assertEqual(summary['mlbMilbGamesChecked'], 1)
                self.assertEqual(summary['added'], ['automatic-mlb-849817-7-batting'])
                self.assertEqual(summary['removedAfterOfficialCorrection'], [])
                self.assertIn(before['events'][0], result['events'])
                event = next(e for e in result['events'] if e['key'].startswith('automatic-mlb-'))
                self.assertEqual(event['date'], '2026-10-16')
                self.assertEqual(event['title'], '2 jonrones en un juego')
                repeated, second_summary = update.refresh(result, {}, getter=self.fake)
                self.assertEqual(repeated, result)
                self.assertFalse(second_summary['changed'])

    def test_genuine_final_future_date_still_fails_without_changing_input(self):
        self.game['officialDate'] = '2026-10-18'
        before = copy.deepcopy(self.data)
        with self.assertRaisesRegex(AssertionError, 'Future date'):
            update.refresh(self.data, {}, getter=self.fake)
        self.assertEqual(self.data, before)

if __name__=='__main__':unittest.main()
