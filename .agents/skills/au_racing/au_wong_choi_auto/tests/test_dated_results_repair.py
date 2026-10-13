import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
from au_dated_results_repair import repair_rows

class RepairTests(unittest.TestCase):
 def setUp(self):
  self.row={'Date':'2026-09-01','Track':'Sandown Hillside','Race':'1','Horse':'Example (AUS)','Pos':'1','Barrier':'','Weight':'','Jockey':'','Trainer':'','Time':'','Margin':'—'}
  self.src=dict(self.row,Barrier='12',Weight='58',Jockey='J Smith',Trainer='Future Trainer',Time='72.5',WinningTime='71.9',Margin='0',SP='99')
  self.link={'key':['2026-09-01','Sandown Hillside','1','example'],'dated_run_date':'2026-09-01','dated_run_race':'1','dated_run_track':'Sandown Hillside','source_sha256':'a'*64,'source_path':'frozen.html'}
 def run_repair(self,row=None,src=None,link=None):
  return repair_rows([row or self.row],[src or self.src],[link or self.link])
 def test_fill_dated_fields_and_preserve_semantics(self):
  rows,audit=self.run_repair()
  self.assertEqual(rows[0]['Barrier'],'12') # Original draw never densified.
  self.assertEqual(rows[0]['Margin'],'0L') # Corpus convention: unit suffix, like load_sb_csv.
  self.assertEqual(rows[0]['Trainer'],'');self.assertEqual(rows[0]['Time'],'')
  self.assertNotIn('SP',rows[0]);self.assertNotIn('WinningTime',rows[0])
  self.assertEqual(self.row['Barrier'],'');self.assertEqual(len(audit['filled']),4)
 def test_margin_written_with_unit_and_compared_without(self):
  rows,_=self.run_repair(row=dict(self.row,Pos='3'),src=dict(self.src,Pos='3',Margin='5.22'))
  self.assertEqual(rows[0]['Margin'],'5.22L')
  rows,audit=self.run_repair(row=dict(self.row,Pos='3',Margin='5.22L'),src=dict(self.src,Pos='3',Margin='5.22'))
  self.assertEqual(rows[0]['Margin'],'5.22L');self.assertEqual(audit['conflicts'],[])
 def test_course_layout_does_not_cross_join(self):
  rows,audit=self.run_repair(link=dict(self.link,dated_run_track='Sandown Lakeside'))
  self.assertEqual(rows,[self.row]);self.assertEqual(audit['quarantined_sources'][0]['reason'],'track_alias_unverified')
 def test_existing_values_preserved_conflicts_visible(self):
  rows,audit=self.run_repair(row=dict(self.row,Barrier='2',Weight='58.0'))
  self.assertEqual(rows[0]['Barrier'],'2');self.assertEqual(rows[0]['Weight'],'58.0')
  self.assertEqual([r['column'] for r in audit['conflicts']],['Barrier'])
 def test_position_mismatch_quarantines_whole_row(self):
  rows,audit=self.run_repair(src=dict(self.src,Pos='2'))
  self.assertEqual(rows,[self.row]);self.assertEqual(audit['filled'],[])
 def test_duplicate_sources_all_quarantined(self):
  rows,audit=repair_rows([self.row],[self.src,self.src],[self.link])
  self.assertEqual(rows,[self.row]);self.assertEqual(len(audit['quarantined_sources']),2)
 def test_duplicate_canonical_fail(self):
  with self.assertRaisesRegex(ValueError,'duplicate canonical'):
   repair_rows([self.row,self.row],[self.src],[self.link])
 def test_nonfinite_metadata_not_written(self):
  rows,audit=self.run_repair(src=dict(self.src,Weight='nan',Barrier='-1'))
  self.assertEqual(rows[0]['Weight'],'');self.assertEqual(rows[0]['Barrier'],'')
  self.assertEqual(len(audit['conflicts']),2)
 def test_same_horse_date_race_other_track_not_joined(self):
  rows,audit=self.run_repair(src=dict(self.src,Track='Flemington'),link=dict(self.link,key=['2026-09-01','Flemington','1','example'],dated_run_track='Flemington'))
  self.assertEqual(rows,[self.row]);self.assertEqual(audit['filled'],[])
 def test_order_independent_identity_join(self):
  other=dict(self.src,Horse='Other',Barrier='3')
  link=dict(self.link,key=['2026-09-01','Sandown Hillside','1','other'])
  rows,audit=repair_rows([self.row,dict(self.row,Horse='Other')],[other,self.src],[self.link,link])
  self.assertEqual([r['Barrier'] for r in rows],['12','3'])
 def test_unmatched_lineage_fail(self):
  with self.assertRaisesRegex(ValueError,'lineage identity set'):
   self.run_repair(link=dict(self.link,key=['2026-09-01','Flemington','1','example']))
 def test_lineage_date_and_hash_required(self):
  for link in [dict(self.link,dated_run_date='2026-09-02'),dict(self.link,source_sha256='')]:
   rows,audit=self.run_repair(link=link);self.assertEqual(rows,[self.row]);self.assertEqual(len(audit['quarantined_sources']),1)

if __name__=='__main__':unittest.main()
