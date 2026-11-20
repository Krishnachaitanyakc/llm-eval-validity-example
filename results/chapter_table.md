| Fault (stage) | Effect on headline | Check (item) | Statistic | Threshold | Verdict |
| --- | --- | --- | --- | --- | --- |
| Prompt loses question (1) | Alpha 0.636 to 0.512 | Unparseable outputs (5) | Largest share 0.226 (0.027) | At most 0.05 | FAIL (PASS) |
| Last number fallback (3) | Beta 0.553 to 0.222 | Extractor audit (4) | Lowest bound 0.181 (0.912); error gap 0.525 (0.000) | At least 0.9; gap under half the smallest gap | FAIL (PASS) |
| Same fault, four formats (3) | Ranking varies by format | Format invariance (1) | Eρ² 0.561 (0.955), one format | At least 0.8 | FAIL (PASS) |
| Same fault, echo agent (3) | Echo agent scores 0.125 | Null agent (10) | Score 0.125 (0.000) | At most floor 0 plus 0.01 | FAIL (PASS) |
| Final event lost, runs dropped (6, 7) | Gamma 0.427 to 0.549 | Undecided outcomes (14) | U not reported; lost share Gamma 0.229, others 0.03 | P, F, U, E and bounds reported | FAIL (PASS) |
| Best of 5 runs (7) | Rise 0.028 to 0.039 | Selection (15) | Best minus mean 0.039 | Every run reported | FAIL |
| All faults (1 to 7) | Beta 0.263, true 0.675 | Rescoring, strict extractor (6) | Largest distance 0.274 (Beta) | At most 0.01 | FAIL |

Table 3. Worked example with three simulated systems, 240 items and 5 runs per item. The true ranking is Beta > Alpha > Gamma; the faulty pipeline reports Gamma > Alpha > Beta. Each row gives an injected fault and its stage, its effect on the headline, the check of Table 2 that tests it, the statistic, the threshold and the verdict on the faulty pipeline; values and verdicts in parentheses are for the corrected pipeline or the strict extractor. All thresholds were fixed before the run. The audit labels 40 outputs per system. Bounds are over runs (1,200 per system), with grader errors rerun at most once. In the corrected report Beta's lower bound exceeds Alpha's upper bound by 0.008, but the paired bootstrap 95% interval over items for this margin, [−0.027, 0.042], includes zero, so the order holds for these runs only.
