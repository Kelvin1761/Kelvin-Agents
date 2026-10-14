"""Real parser and engine regressions for isolated AWT correctness candidates."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import hkjc_awt_source_trace as trace


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts,cls.fixed,cls.engine=trace.load_candidates()

    def evidence(self,target):
        return (f'今場={target} 63.4分 | 沙田草地 62.0分(有效樣本4.0/原始5) | '
                '跑馬地草地 61.0分(有效樣本2.0/原始3) | 沙田AWT 63.4分(有效樣本0.7/原始1) | 採用來源=local_history')

    def test_awt_reads_awt_sample_not_first_grass_sample(self):
        text=self.evidence('沙田AWT')
        self.assertEqual(trace.metadata(trace.RacingEngine,text)['effective_n'],4.)
        fixed=trace.metadata(self.engine,text)
        self.assertEqual(fixed['effective_n'],.7);self.assertEqual(fixed['score'],63.4)

    def test_happy_valley_reads_its_own_sample(self):
        self.assertEqual(trace.metadata(self.engine,self.evidence('跑馬地草地'))['effective_n'],2.)

    def test_sha_tin_grass_stays_unchanged(self):
        text=self.evidence('沙田草地')
        self.assertEqual(trace.metadata(self.engine,text),trace.metadata(trace.RacingEngine,text))

    def test_missing_target_row_does_not_borrow_foreign_sample(self):
        text='今場=沙田AWT 60.0分 | 沙田草地 61.0分(有效樣本3.0/原始4) | 外地泥/Synthetic 62.0分(有效樣本8.0/原始9)'
        self.assertEqual(trace.metadata(self.engine,text)['effective_n'],0.)

    def test_missing_text_is_neutral(self):
        self.assertFalse(trace.metadata(self.engine,'')['available'])
        self.assertEqual(trace.metadata(self.engine,'')['score'],60.)

    def parse(self,rail):
        text=f'''#### 賽事概覽 (Race Overview)
- 賽事日期 / 場次 / 跑道及場地狀況: 07/06/2026 / 第1場 / 沙田 全天候跑道 1200米
馬號: 1
馬名: 測試馬
檔位: 1
騎師: 測試騎師
負磅: 120
排位體重: 1100
往績紀錄:
  [1] 06/05/2026 | 日數: 17 | 沙田 "{rail}" 1200 好
      檔位: 4 | 馬重: 1100 | 負磅: 120 | 騎師: 測試騎師 | 名次: 2 / 12
      能量: 91 | 分段時間: 23.00, 22.70, 23.89
      短評: 中等步速
'''
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'賽績.md';p.write_text(text)
            old=self.facts.parse_hkjc_formguide(str(p))['horses'][0]['races'][0]
            new=self.fixed.parse_hkjc_formguide(str(p))['horses'][0]['races'][0]
            return old,new

    def test_quoted_awt_survives_parser_before_surface_and_sectional_scoring(self):
        old,new=self.parse('AWT')
        self.assertEqual(old['venue'],'沙田');self.assertEqual(new['venue'],'沙田AWT')
        self.assertEqual(new['rail'],'AWT');self.assertEqual(new['finish'],2)
        self.assertEqual(new['sectionals'],self.fixed.compute_sectional_from_splits(new['splits'],1200,venue='沙田AWT'))
        result=self.fixed.compute_surface_performance_shadow([new],'沙田AWT',1200,'2026-06-07')
        self.assertEqual(result['target_runs'],1)
        self.assertEqual(result['surfaces']['沙田草地']['runs'],0)

    def test_grass_row_unmodified(self):
        old,new=self.parse('A');self.assertEqual(old,new)

    def test_same_day_awt_row_never_enters_surface_score(self):
        _,new=self.parse('AWT')
        result=self.fixed.compute_surface_performance_shadow([new],'沙田AWT',1200,'2026-05-06')
        self.assertEqual(result['target_runs'],0)

    def test_renderer_keeps_awt_for_table_and_finish_time_standards(self):
        _,race=self.parse('AWT')
        horse={'num':1,'name':'測試馬','jockey':'測試騎師','weight':120,'barrier':1,
               'races':[race],'pdf_overseas_races':[]}
        profile={'entries':[{'date':'06/05/2026','finish_time_raw':'1.09.35',
                           'class_grade':'4','placing':2}]}
        fixed=trace.load_render_candidate()
        calls=[]
        with patch.object(fixed,'get_standard_time',side_effect=lambda venue,*args:calls.append(venue) or 69.):
            text=fixed.generate_horse_block(horse,'沙田AWT',1200,'C4',profile_data=profile,race_date='2026-06-07')
        self.assertIn('| 沙田AWT |',text)
        self.assertNotIn('| 沙田AW |',text)
        self.assertTrue(calls)
        self.assertTrue(all(venue=='沙田AWT' for venue in calls),calls)
        old_calls=[]
        with patch.object(self.facts,'get_standard_time',side_effect=lambda venue,*args:old_calls.append(venue) or 69.):
            self.facts.generate_horse_block(horse,'沙田AWT',1200,'C4',profile_data=profile,race_date='2026-06-07')
        self.assertIn('沙田AW',old_calls)

if __name__=='__main__':unittest.main()
