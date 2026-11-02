"""Tests for the NBA fit layer (shadow candidate A, EXP-20261021-05)."""
import json, math, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, SCRIPTS)
import nba_fit_layer as fl  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "nba_fit_layer_A_parity.json")


class Parity(unittest.TestCase):
    def test_matches_harness_within_1e9(self):
        model, reason = fl.default_model()
        self.assertIsNotNone(model, reason)
        units = json.load(open(FIXTURE))["units"]
        self.assertGreaterEqual(len(units), 400)
        worst = 0.0
        for u in units:
            p, why = fl.fit_prob_A(u["stat"], u["line"], u["season_stat_total"], u["season_minutes_total"], u["prior10_mean_min"])
            self.assertIsNone(why)
            worst = max(worst, abs(p - u["harness_A"]))
        self.assertLess(worst, 1e-9)
        self.assertEqual({u["stat"] for u in units}, {"PTS", "REB", "AST", "FG3M"})

    def test_survival_function_matches_scipy_when_available(self):
        try:
            from scipy.stats import nbinom, poisson
        except ImportError:
            self.skipTest("scipy not installed")
        for mu in (0.7, 3.2, 12.5, 27.0):
            for n in (1, 2, 5, 10, 20, 30):
                self.assertAlmostEqual(fl._sf(n, mu, 0.0), float(poisson.sf(n - 1, mu)), places=10)
                al = 0.197
                self.assertAlmostEqual(fl._sf(n, mu, al), float(nbinom.sf(n - 1, 1 / al, 1 / (1 + al * mu))), places=10)


class Loader(unittest.TestCase):
    def test_missing_file(self):
        m, why = fl.load_model(os.path.join(tempfile.gettempdir(), "does_not_exist_nba_fit.json"))
        self.assertIsNone(m); self.assertIn("unreadable", why)

    def test_hash_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, fl.MODEL_FILENAME)
            shutil.copy(fl.DEFAULT_MODEL_PATH, p)
            with open(p, "a") as fh:
                fh.write(" ")
            m, why = fl.load_model(p)
            self.assertIsNone(m); self.assertIn("sha256 mismatch", why)
            self.assertIsNone(fl.p_fit_A("PTS", 20, 800, 1000, 30, model=m) if m else None)

    def test_default_file_matches_pinned_hash(self):
        m, why = fl.load_model()
        self.assertIsNotNone(m, why); self.assertEqual(m["model_id"], fl.MODEL_ID)

    def test_malformed_model_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json"); open(p, "w").write("{not json")
            m, why = fl.load_model(p, expected_sha256=None)
            self.assertIsNone(m); self.assertIn("malformed", why)


class Behaviour(unittest.TestCase):
    def test_clip_bounds(self):
        hi = fl.p_fit_A("REB", 1, 5000, 100, 36)          # mu huge -> p ~ 1
        lo = fl.p_fit_A("PTS", 60, 100, 1000, 25)         # mu tiny -> p ~ 0
        self.assertLessEqual(hi, fl.CLIP_HI); self.assertGreaterEqual(lo, fl.CLIP_LO)
        # a model with a steep recalibration slope must hit the final clip exactly
        import copy
        steep = copy.deepcopy(fl.default_model()[0])
        for s in steep["recalibration"].values():
            s["b"] = 50.0
        self.assertEqual(fl.p_fit_A("REB", 1, 5000, 100, 36, model=steep), fl.CLIP_HI)
        self.assertEqual(fl.p_fit_A("PTS", 60, 100, 1000, 25, model=steep), fl.CLIP_LO)

    def test_monotone_in_line(self):
        ps = [fl.p_fit_A("AST", n, 400, 1500, 30) for n in range(1, 12)]
        self.assertTrue(all(a >= b for a, b in zip(ps, ps[1:])))

    def test_invalid_inputs_return_none_with_reason(self):
        for args in (("XYZ", 5, 1, 1, 30), ("PTS", 20.5, 1, 1, 30), ("PTS", 0, 1, 1, 30), ("PTS", 20, 1, 0, 30),
                     ("PTS", 20, 1, 100, 0), ("PTS", 20, float("nan"), 100, 30)):
            p, why = fl.fit_prob_A(*args)
            self.assertIsNone(p); self.assertTrue(why)

    def test_alias(self):
        self.assertEqual(fl.p_fit_A("3PM", 2, 100, 1000, 30), fl.p_fit_A("FG3M", 2, 100, 1000, 30))

    def test_no_scipy_or_numpy_needed(self):
        code = "import sys; sys.path.insert(0, %r); import nba_fit_layer as f; " \
               "assert f.p_fit_A('PTS', 20, 800, 1000, 30) is not None; " \
               "assert 'scipy' not in sys.modules and 'numpy' not in sys.modules" % SCRIPTS
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
