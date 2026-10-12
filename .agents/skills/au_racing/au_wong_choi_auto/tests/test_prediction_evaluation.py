from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest
from dataclasses import replace
import json
import os
import subprocess
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_prediction_evaluation import evaluate_family, metric_row
from au_prediction_intake import content_hash, PredictionValidationError


class ArtifactEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.base_profile = {"fitted": False, "name": "base"}
        self.profiles = {"arm": {"fitted": False, "name": "fixed candidate"}}
        self.manifest = {"schema": "au-paired-predictions/v1", "provenance_audit": "PASS", "evaluation_races": []}
        self.baseline, self.candidates = [], {"arm": []}
        for offset in range(12):
            day = (date(2026, 8, 5) + timedelta(days=offset)).isoformat()
            labels = {str(n): n for n in range(1, 7)}
            race = {"race_id": day + "/track/1", "date": day, "prediction_at": day + "T12:00:00+10:00",
                    "input": {"runner_ids": list(labels), "sources": [{"audit": "PASS", "available_at": day + "T09:00:00+10:00"}]},
                    "labels": labels, "labels_hash": content_hash(labels), "cohorts": {"venue": "A", "going": "Good"}}
            self.manifest["evaluation_races"].append(race)
            def record(order, profile):
                return {"race_id": race["race_id"], "date": day, "prediction_at": race["prediction_at"],
                        "input_hash": content_hash(race["input"]), "profile_hash": content_hash(profile),
                        "ranking": order, "ability": {n: 70-i for i, n in enumerate(order)}, "status": "candidate"}
            self.baseline.append(record(["4", "5", "6", "1", "2", "3"], self.base_profile))
            self.candidates["arm"].append(record(list(labels), self.profiles["arm"]))
        ranking = ["top3_capture_at5", "ndcg_at5", "top5_pairwise_auc", "mean_top3_model_rank", "competitive_recall_at5"]
        self.power = {"prepared_at": "2026-10-11T00:00:00+00:00", "arms": {"arm": {
            m: {"component_budget": 1., "mde": .1} for m in ranking}}}
        self.registration = {"schema": "au-evaluation-family/v1", "holm_unit": "arm_metric",
                             "manifest_hash": content_hash(self.manifest), "baseline_profile_hash": content_hash(self.base_profile),
                             "power_hash": content_hash(self.power), "registered_at": "2026-10-11T00:01:00+00:00",
                             "evaluation_started_at": "2026-10-11T00:02:00+00:00", "ranking_metrics": ranking,
                             "arms": {"arm": {"profile_hash": content_hash(self.profiles["arm"])}},
                             "cohorts": [{"name": "small", "key": "field_size", "values": [4,5,6,7,8], "min_races": 6, "min_days": 6}]}

    def evaluate(self):
        return evaluate_family(self.manifest, self.baseline, self.candidates,
                               baseline_profile=self.base_profile, candidate_profiles=self.profiles,
                               registration=self.registration, power_record=self.power)

    def test_known_supported_effect_requires_forward(self):
        report = self.evaluate()
        self.assertEqual(report["arms"]["arm"]["decision"]["verdict"], "PRIMARY_WIN")
        self.assertEqual(report["arms"]["arm"]["forward_status"], "PENDING_FORWARD")
        self.assertFalse(report["release_authorized"])
        self.assertEqual(len(report["holm_adjusted_p"]), 7)

    def test_aa_rejected_even_with_zero_power(self):
        self.candidates["arm"] = deepcopy(self.baseline)
        for row in self.candidates["arm"]:
            row["profile_hash"] = content_hash(self.profiles["arm"])
        for item in self.power["arms"]["arm"].values():
            item["component_budget"] = 0
        self.registration["power_hash"] = content_hash(self.power)
        self.assertEqual(self.evaluate()["arms"]["arm"]["decision"]["reason"], "identical_predictions")

    def test_final_order_used_instead_of_score_sort(self):
        race = self.manifest["evaluation_races"][0]
        record = deepcopy(self.candidates["arm"][0])
        record["ranking"] = ["4", "5", "1", "2", "3", "6"]
        self.assertFalse(metric_row(race, record)["good_positional"])
        self.assertFalse(metric_row(race, record)["gold"])

    def test_missing_placing_cannot_be_assumed_unplaced(self):
        race = self.manifest["evaluation_races"][0]
        race["labels"]["3"] = None
        race["labels_hash"] = content_hash(race["labels"])
        self.registration["manifest_hash"] = content_hash(self.manifest)
        with self.assertRaisesRegex(PredictionValidationError, "invalid_finish_labels"):
            self.evaluate()

    def test_family_cannot_drop_an_arm(self):
        self.registration["arms"]["missing"] = {"profile_hash": "x"}
        with self.assertRaisesRegex(PredictionValidationError, "registered_arm_set_changed"):
            self.evaluate()

    def test_registration_must_precede_evaluation(self):
        self.registration["registered_at"] = "2026-10-12T00:00:00+00:00"
        with self.assertRaisesRegex(PredictionValidationError, "registered_after_evaluation"):
            self.evaluate()

    def test_sparse_cohort_cannot_be_called_safe(self):
        self.registration["cohorts"][0]["min_days"] = 20
        decision = self.evaluate()["arms"]["arm"]["decision"]
        self.assertEqual(decision["verdict"], "UNRESOLVABLE")

    def test_market_cohort_is_out_of_scope(self):
        self.registration["cohorts"][0]["key"] = "sp"
        with self.assertRaisesRegex(PredictionValidationError, "market_or_unknown_cohort"):
            self.evaluate()

    def test_provenance_flag_blocks_a_statistically_strong_signal(self):
        self.manifest["evaluation_races"][0]["input"]["sources"][0]["audit"] = "FLAG"
        self.registration["manifest_hash"] = content_hash(self.manifest)
        with self.assertRaisesRegex(PredictionValidationError, "source_provenance_flag"):
            self.evaluate()

    def test_noninformative_ranking_does_not_block_primary_win(self):
        for item in self.power["arms"]["arm"].values():
            item["component_budget"] = 0
        self.registration["power_hash"] = content_hash(self.power)
        report = self.evaluate()
        self.assertEqual(report["arms"]["arm"]["decision"]["verdict"], "PRIMARY_WIN")
        self.assertTrue(all(p == 1 for key,p in report["holm_raw_p"].items() if key.split('::')[1] in self.registration['ranking_metrics']))

    def test_label_hash_change_is_rejected(self):
        self.manifest["evaluation_races"][0]["labels"]["1"] = 2
        self.registration["manifest_hash"] = content_hash(self.manifest)
        with self.assertRaisesRegex(PredictionValidationError, "finish_labels_hash_changed"):
            self.evaluate()

    def test_harmful_venue_rejects_pooled_primary_gain(self):
        races, bases, candidates = [], [], []
        for race, base, cand in zip(self.manifest['evaluation_races'], self.baseline, self.candidates['arm']):
            for number in range(3):
                r,b,c=deepcopy(race),deepcopy(base),deepcopy(cand)
                r['race_id'] += '/' + str(number)
                b['race_id']=c['race_id']=r['race_id']
                if number==2:
                    r['cohorts']['venue']='B'
                    b['ranking'],c['ranking']=c['ranking'],b['ranking']
                    b['ability'],c['ability']=c['ability'],b['ability']
                races.append(r);bases.append(b);candidates.append(c)
        self.manifest['evaluation_races']=races
        self.baseline,self.candidates['arm']=bases,candidates
        self.registration['manifest_hash']=content_hash(self.manifest)
        self.registration['cohorts'].append({'name':'venue B','key':'venue','values':['B'],'min_races':6,'min_days':6})
        report=self.evaluate()['arms']['arm']
        self.assertEqual(report['decision']['reason'],'cohort_regression')
        self.assertEqual(report['cohorts']['venue B']['status'],'HARM')

    def test_family_holm_can_reject_a_raw_winner(self):
        import au_prediction_evaluation as module
        original = module._evidence
        def controlled(*args):
            return replace(original(*args), p_value=.02)
        with patch.object(module, '_evidence', side_effect=controlled):
            report = self.evaluate()
        self.assertEqual(report['arms']['arm']['raw_decision']['verdict'], 'PRIMARY_WIN')
        self.assertEqual(report['arms']['arm']['decision']['reason'], 'family_holm_not_significant')
        self.assertAlmostEqual(report['holm_adjusted_p']['arm::gold'], .14)

    def test_all_noninformative_ranking_is_unresolvable_without_primary_gain(self):
        for base in self.baseline:
            order=['1','2','4','3','5','6']
            base['ranking']=order
            base['ability']={n:70-i for i,n in enumerate(order)}
        for item in self.power['arms']['arm'].values():
            item['component_budget']=0
        self.registration['power_hash']=content_hash(self.power)
        decision=self.evaluate()['arms']['arm']['decision']
        self.assertEqual(decision['verdict'],'UNRESOLVABLE')
        self.assertEqual(decision['reason'],'all_registered_ranking_metrics_noninformative')

    def test_low_power_cannot_rescue_primary_regression(self):
        for base,cand in zip(self.baseline,self.candidates['arm']):
            base['ranking'],cand['ranking']=cand['ranking'],base['ranking']
            base['ability'],cand['ability']=cand['ability'],base['ability']
        for item in self.power['arms']['arm'].values():
            item['component_budget']=0
        self.registration['power_hash']=content_hash(self.power)
        decision=self.evaluate()['arms']['arm']['decision']
        self.assertEqual(decision['verdict'],'REJECT')
        self.assertEqual(decision['reason'],'cohort_regression')

    def test_dead_heat_placings_use_canonical_capture_at_four(self):
        race=deepcopy(self.manifest['evaluation_races'][0])
        race['labels']['4']=3
        race['labels_hash']=content_hash(race['labels'])
        result=metric_row(race,self.candidates['arm'][0])
        self.assertEqual(result['actual_top3_count'],4)
        self.assertTrue(result['gold'])

    def test_cli_evaluates_artifacts_and_persists_rejection(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'au_eval.py'
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            values={'manifest':self.manifest, 'predictions':{'baseline':self.baseline,'candidates':self.candidates,
                    'baseline_profile':self.base_profile,'candidate_profiles':self.profiles},
                    'registration':self.registration,'power':self.power}
            for name,value in values.items():
                (folder/(name+'.json')).write_text(json.dumps(value))
            command=[sys.executable,str(script),'--prediction-manifest',str(folder/'manifest.json'),
                     '--family-predictions',str(folder/'predictions.json'),'--family-registration',str(folder/'registration.json'),
                     '--power-record',str(folder/'power.json'),'--output-json',str(folder/'result.json')]
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','WC_DISABLE_POST_SUCCESS_DEPLOY':'1','WC_SB_CACHE_ONLY':'1'}
            result=subprocess.run(command,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads((folder/'result.json').read_text())['arms']['arm']['decision']['verdict'],'PRIMARY_WIN')
            values['predictions']['candidates']['arm'][0]['race_id']='wrong-race'
            (folder/'predictions.json').write_text(json.dumps(values['predictions']))
            result=subprocess.run(command,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertEqual(json.loads((folder/'result.json').read_text())['reason'],'race_identity_changed')


if __name__ == "__main__":
    unittest.main()
