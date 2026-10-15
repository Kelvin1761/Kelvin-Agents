"""Safety contracts for the official-time research adapter."""
import copy
import io
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

from au_tas_time_source_20261015 import parse
from au_time_coverage_eval_20261015 import available, bind_rq_lookup


class TimeSourceContracts(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'C': '46267'}, {'C': 'Devonport Tapeta Synthetic'}, {'C': '1'}, {'C': 'G-3'},
            {'A': 'RACE 1'},
            {'B': 'DISTANCE', 'C': 'Winner', 'E': 'IVRTIME', 'H': 'TO 800M', 'K': 'L800'},
        ]
        self.rows += [{'A': str(i+1), 'B': '1650', 'C': name, 'D': '9999',
                      'E': str(103.44+i), 'H': str(56.9+i), 'K': '46.54',
                      'X': '12.66', 'Y': '11.4', 'Z': '11.32', 'AA': '11.16'}
                     for i, name in enumerate(['Azonto', 'Eaglefurther', 'Flossing'])]
        sheet = ET.Element('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}worksheet')
        data = ET.SubElement(sheet, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheetData')
        for i in [2, 3, 6, 7, 13, 15, 16, 17, 18]:
            ET.SubElement(data, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row', r=str(i))
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z:
            z.writestr('xl/worksheets/sheet1.xml', ET.tostring(sheet))
        self.raw = raw.getvalue()
        self.meeting = {'meetDate': '2026-09-02T00:00:00Z', 'meetCode': 'test',
                        'track': {'venueName': 'Devonport'}}
        self.races = {'race': [{'raceNumber': 1, 'raceDistance': 1650, 'nameRaceForm': 'BM68',
                              'raceTiming': {'trackCondition': {'value': 'Synthetic'}}}]}
        self.attachment = {'url': 'https://example.test/official.xlsx',
                           'date': '2026-09-02 10:25:27', 'modified': '2026-09-03 01:00:00'}

    def parse(self):
        with patch('au_tas_time_source_20261015.workbook', return_value=self.rows):
            return parse(self.raw, self.meeting, self.races, self.attachment)

    def test_own_time_not_official_winner_clock(self):
        events, _ = self.parse()
        self.assertEqual([r['time'] for r in events[0]['rows']], [103.44, 104.44, 105.44])
        self.assertEqual(events[0]['track'], 'devonportsynthetic')
        self.assertEqual(events[0]['going'], 'synthetic')
        self.rows[-1].pop('E')
        self.assertEqual(self.parse()[0], [])  # D alone cannot fill missing own time.

    def test_reject_wrong_date_and_geometry(self):
        self.meeting['meetDate'] = '2026-09-03T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'date mismatch'):
            self.parse()
        self.meeting['meetDate'] = '2026-09-02T00:00:00Z'
        self.races['race'][0]['raceDistance'] = 1600
        self.assertEqual(self.parse()[0], [])

    def test_reject_bad_split_and_duplicate_identity(self):
        original = copy.deepcopy(self.rows)
        self.rows[-1]['AA'] = '21.16'
        self.assertEqual(self.parse()[0], [])
        self.rows = original
        self.rows[-1]['C'] = 'Azonto'
        self.assertEqual(self.parse()[0], [])

    def test_reject_unverified_layout_or_header(self):
        self.rows[1]['C'] = 'Devonport Other Track'
        with self.assertRaisesRegex(ValueError, 'venue binding'):
            self.parse()
        self.rows[1]['C'] = 'Devonport Tapeta Synthetic'
        self.rows[5]['E'] = 'WINNINGTIME'
        self.assertEqual(self.parse()[0], [])

    def test_publication_and_modified_asof(self):
        event = self.parse()[0][0]
        self.assertFalse(available(event, '2026-09-03'))
        self.assertTrue(available(event, '2026-09-04'))
        event['published_at_utc'] = '2026-09-04T00:00:00Z'
        self.assertFalse(available(event, '2026-09-04'))

    def test_rq_binding_keeps_surface_and_warwick_farm_distinct(self):
        raw = {(('aquisparkgoldcoast', '2026-09-02', 1, 1200), 'horse'): {'A': 1},
               (('aquisparkgoldcoastpoly', '2026-09-02', 1, 1200), 'horse'): {'A': 2},
               (('picklebetparkwarwick', '2026-09-02', 1, 1200), 'horse'): {'A': 3}}
        got = bind_rq_lookup(raw)
        self.assertEqual(got[(('goldcoast', '2026-09-02', 1, 1200), 'horse')]['A'], 1)
        self.assertEqual(len(got), 5)
        self.assertNotIn((('warwickfarm', '2026-09-02', 1, 1200), 'horse'), got)
        raw[(('goldcoast', '2026-09-02', 1, 1200), 'horse')] = {'A': 9}
        with self.assertRaisesRegex(ValueError, 'ambiguous RQ'):
            bind_rq_lookup(raw)


if __name__ == '__main__':
    unittest.main()
