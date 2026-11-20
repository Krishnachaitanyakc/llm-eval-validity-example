"""Assert that the example reproduces the published numbers exactly.

Run from the supplement folder:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, "results")
sys.path.insert(0, ROOT)

from pipeline_example import __version__, checks, run_example  # noqa: E402

TEXT_FILES = ("run_output.txt", "stage_effects.csv", "depth_profile.csv",
              "format_scores.csv", "corrected_outcomes.csv",
              "faulty_log_plain.csv", "audit_sample.csv", "checks.json",
              "summary.json", "chapter_table.md")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class GCoefficientTest(unittest.TestCase):
    """Equation (5) by expected mean squares on small hand checked designs."""

    def test_no_interaction_no_rerun_noise(self):
        cells = {"c1": {"A": [0.2, 0.2], "B": [0.6, 0.6]},
                 "c2": {"A": [0.2, 0.2], "B": [0.6, 0.6]}}
        g = checks.g_coefficient(cells, ("A", "B"), ("c1", "c2"))
        self.assertAlmostEqual(g["var_m"], 0.08)
        self.assertEqual(g["var_mc"], 0.0)
        self.assertEqual(g["var_e"], 0.0)
        self.assertAlmostEqual(g["rho2"], 1.0)

    def test_hand_computed(self):
        # Cell means A: 0.2, 0.4; B: 0.6, 0.6; reruns at +-0.05 of the mean.
        cells = {"c1": {"A": [0.15, 0.25], "B": [0.55, 0.65]},
                 "c2": {"A": [0.35, 0.45], "B": [0.55, 0.65]}}
        g = checks.g_coefficient(cells, ("A", "B"), ("c1", "c2"))
        # By hand: MS_m = 0.18, MS_mc = 0.02, MS_e = 0.005.
        self.assertAlmostEqual(g["ms_m"], 0.18)
        self.assertAlmostEqual(g["ms_mc"], 0.02)
        self.assertAlmostEqual(g["ms_e"], 0.005)
        self.assertAlmostEqual(g["var_e"], 0.005)
        self.assertAlmostEqual(g["var_mc"], 0.0075)
        self.assertAlmostEqual(g["var_m"], 0.04)
        self.assertAlmostEqual(g["rho2"], 0.04 / (0.04 + 0.0075 / 2 + 0.005 / 4))

    def test_decision_study_for_one_condition(self):
        cells = {"c1": {"A": [0.15, 0.25], "B": [0.55, 0.65]},
                 "c2": {"A": [0.35, 0.45], "B": [0.55, 0.65]}}
        g = checks.g_coefficient(cells, ("A", "B"), ("c1", "c2"),
                                 d_conditions=1, d_reruns=2)
        self.assertEqual((g["n_c"], g["R"]), (1, 2))
        self.assertAlmostEqual(g["rho2"], 0.04 / (0.04 + 0.0075 + 0.005 / 2))
        self.assertAlmostEqual(g["rho2_all_conditions"],
                               0.04 / (0.04 + 0.0075 / 2 + 0.005 / 4))

    def test_negative_estimates_truncated(self):
        cells = {"c1": {"A": [0.0, 1.0], "B": [1.0, 0.0]},
                 "c2": {"A": [1.0, 0.0], "B": [0.0, 1.0]}}
        g = checks.g_coefficient(cells, ("A", "B"), ("c1", "c2"))
        self.assertEqual(g["var_m"], 0.0)
        self.assertEqual(g["var_mc"], 0.0)
        self.assertEqual(g["rho2"], 0.0)


class ReproducibleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cls.res = run_example.main(["--out", cls.tmp.name, "--no-figure"])
        cls.stdout = buf.getvalue()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_printed_output_matches(self):
        self.assertEqual(self.stdout, read(os.path.join(RESULTS, "run_output.txt")))

    def test_result_files_match(self):
        for name in TEXT_FILES:
            with self.subTest(file=name):
                self.assertEqual(read(os.path.join(self.tmp.name, name)),
                                 read(os.path.join(RESULTS, name)))

    def test_key_numbers(self):
        r = self.res
        self.assertEqual({k: round(v, 3) for k, v in r["truth"].items()},
                         {"Alpha": 0.636, "Beta": 0.675, "Gamma": 0.557})
        self.assertEqual({k: round(v, 3) for k, v in r["headline"].items()},
                         {"Alpha": 0.523, "Beta": 0.263, "Gamma": 0.579})
        self.assertEqual(r["rank_tau_faulty_vs_truth"], -1.0)

    def test_verdicts(self):
        c = self.res["checks"]
        self.assertEqual(c["item5"]["verdict"], "FAIL")
        self.assertEqual(c["item5"]["verdict_corrected"], "PASS")
        self.assertEqual(c["item4"]["verdict"], "FAIL")
        self.assertEqual(c["item4"]["extractors"]["strict"]["verdict"], "PASS")
        self.assertEqual(c["item6"]["verdict"], "FAIL")
        self.assertEqual(c["item6"]["name"],
                         "Rescoring with an independent strict extractor")
        self.assertEqual(c["item1_faulty"]["verdict"], "FAIL")
        self.assertEqual(c["item1_corrected"]["verdict"], "PASS")
        self.assertEqual(c["item14"]["verdict_faulty_report"], "FAIL")
        self.assertEqual(c["item14"]["verdict_corrected_report"], "PASS")
        self.assertEqual(c["item10"]["verdict"], "FAIL")
        self.assertEqual(c["item10"]["verdict_strict"], "PASS")
        self.assertEqual(c["item15"]["verdict"], "FAIL")
        dominance = [t for _, _, t in c["item14"]["dominance"]]
        self.assertEqual(dominance, ["Beta > Alpha",
                                     "not ordered, bounds overlap",
                                     "not ordered, bounds overlap"])

    def test_item_values(self):
        c = self.res["checks"]
        self.assertEqual(round(c["item1_faulty"]["value"], 3), 0.561)
        self.assertEqual(round(c["item1_corrected"]["value"], 3), 0.955)
        self.assertEqual(c["item1_faulty"]["g_study"]["n_c"], 1)
        self.assertEqual(c["item1_faulty"]["g_study"]["R"], 5)
        self.assertEqual(round(c["item1_faulty"]["value_all_formats"], 3), 0.837)
        self.assertEqual(round(c["item1_corrected"]["value_all_formats"], 3), 0.988)
        self.assertEqual(round(c["item1_faulty"]["min_tau"], 3), 0.333)
        self.assertEqual(round(c["item5"]["value"], 3), 0.226)
        self.assertEqual(round(c["item5"]["value_corrected"], 3), 0.027)
        perm = c["item4"]["extractors"]["permissive"]["per_system"]
        self.assertEqual({n: (v["correct"], v["n"]) for n, v in perm.items()},
                         {"Alpha": (33, 40), "Beta": (12, 40),
                          "Gamma": (28, 40)})
        lost = c["item14"]["faulty_lost_share"]
        self.assertEqual(round(lost["Gamma"], 3), 0.229)
        ba = c["item14"]["bootstrap"]["pairs"][0]
        self.assertEqual(ba["margin"], "lower(Beta) - upper(Alpha)")
        self.assertEqual((round(ba["low"], 3), round(ba["high"], 3)),
                         (-0.027, 0.042))
        self.assertFalse(ba["resolved"])

    def test_tau_takes_only_coarse_values(self):
        values = {round(v, 6) for k in ("item1_faulty", "item1_corrected")
                  for v in self.res["checks"][k]["taus"].values()}
        self.assertTrue(values <= {-1.0, -0.333333, 0.333333, 1.0})

    def test_chapter_table_shape(self):
        lines = read(os.path.join(RESULTS, "chapter_table.md")).splitlines()
        self.assertEqual(lines[0], "| Fault (stage) | Effect on headline | "
                         "Check (item) | Statistic | Threshold | Verdict |")
        items = [row.split(" | ")[2].rsplit("(", 1)[1].rstrip(")")
                 for row in lines[2:9]]
        self.assertEqual(items, ["5", "4", "1", "10", "14", "15", "6"])
        self.assertEqual(lines[9], "")
        self.assertTrue(lines[10].startswith("Table 3."))

    def test_truth_inside_corrected_bounds(self):
        counts = self.res["checks"]["item14"]["counts"]
        for name, truth in self.res["truth"].items():
            self.assertLessEqual(counts[name]["lower"], truth)
            self.assertLessEqual(truth, counts[name]["upper"])

    def test_version(self):
        self.assertEqual(__version__, "1.0.1")
        self.assertEqual(read(os.path.join(ROOT, "VERSION")).strip(), __version__)
        self.assertIn(f"version: {__version__}",
                      read(os.path.join(ROOT, "CITATION.cff")))

    def test_second_run_is_byte_identical(self):
        """A second run in the same process writes identical files."""
        with tempfile.TemporaryDirectory() as out:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_example.main(["--out", out, "--no-figure"])
            self.assertEqual(buf.getvalue(), self.stdout)
            for name in TEXT_FILES:
                with self.subTest(file=name):
                    with open(os.path.join(out, name), "rb") as fa, \
                            open(os.path.join(self.tmp.name, name), "rb") as fb:
                        self.assertEqual(fa.read(), fb.read())

    def test_independent_of_hash_seed(self):
        """A fresh interpreter with another hash seed prints the same text."""
        env = dict(os.environ, PYTHONHASHSEED="12345")
        with tempfile.TemporaryDirectory() as out:
            proc = subprocess.run(
                [sys.executable, "-m", "pipeline_example.run_example",
                 "--out", out, "--no-figure"],
                cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout, self.stdout)


if __name__ == "__main__":
    unittest.main()
