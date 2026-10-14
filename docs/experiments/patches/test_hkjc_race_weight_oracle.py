"""Soundness tests for oracle feasibility, baseline identity and quarantine."""
import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import hkjc_race_weight_oracle as oracle


class OracleTests(unittest.TestCase):
    def test_gold_and_good_are_different(self):
        scores=np.arange(6,0,-1,dtype=float)
        m=oracle.metrics(scores,np.array([1,4,2,3,5,6]),np.arange(1,7))
        self.assertTrue(m['gold']); self.assertFalse(m['good'])

    def test_nonnegative_cannot_reverse_dominance(self):
        x=np.zeros((6,len(oracle.BASE))); x[:,0]=[1,2,3,8,9,10]
        pos=np.arange(1,7)
        self.assertIsNone(oracle.joint(x,np.zeros(6),pos,'positive'))
        w=oracle.joint(x,np.zeros(6),pos,'signed')
        self.assertIsNotNone(w); self.assertLess(w[0],0)
        m=oracle.metrics(x@w,pos,np.arange(1,7))
        self.assertTrue(m['gold'] and m['good'])

    def test_joint_finds_minimum_zero_distance_when_baseline_passes(self):
        x=np.zeros((6,len(oracle.BASE))); x[:,0]=[10,9,8,3,2,1]
        w=oracle.joint(x,np.zeros(6),np.arange(1,7),'local')
        np.testing.assert_allclose(w,oracle.BASE,atol=1e-8)

    def test_constant_wrong_residual_is_not_rescuable(self):
        x=np.zeros((6,len(oracle.BASE)))
        for tier in ('local','positive','signed'):
            self.assertIsNone(oracle.joint(x,np.arange(6),np.arange(1,7),tier))

    def test_replica_and_debut_lock(self):
        data={'matrix_'+d:[60.,80.] for d in oracle.DIMS}
        data.update(is_debut=[0,1],current_live_recomputed_ability=[54.21,82.17])
        x,r,s=oracle.arrays(pd.DataFrame(data))
        np.testing.assert_allclose(x@oracle.BASE+r,s)
        self.assertTrue((x[1]==0).all())
        self.assertEqual(float((x@np.roll(oracle.BASE,1)+r)[1]),s[1])

    def test_quarantine_excludes_labels_before_validation(self):
        f=pd.DataFrame({'date':['2026-09-06','2026-09-09','2026-10-11'],
                        'finish_pos':[1,'poison',None]})
        d=oracle.dev_frame(f,'2026-09-09')
        self.assertEqual(d.finish_pos.tolist(),[1])

    def test_single_target_witness_is_verified(self):
        x=np.zeros((6,len(oracle.BASE)));x[:,0]=[10,9,8,3,2,1]
        for target in ('gold','good'):
            w=oracle.joint(x,np.zeros(6),np.arange(1,7),'local',target)
            self.assertTrue(oracle.metrics(x@w,np.arange(1,7),np.arange(1,7))[target])

    def test_local_constraints(self):
        for v,(lo,hi) in zip(oracle.BASE,oracle.bounds('local')):
            self.assertLessEqual(lo,v);self.assertGreaterEqual(hi,v)

if __name__=='__main__': unittest.main()
