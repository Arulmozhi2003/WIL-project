# SkillGap retrieval experiments

Run 2026-09-29T13:27:23+00:00 · dataset `1e2b07563c84` · 159 documents · 33 dev / 21 test questions · k=3

**Chosen system: BT** (BM25 fully tuned (grid: k1, b, stemming, normalisation, threshold)) with `{"k1": 2.0, "b": 0.75, "stopwords": true, "stemming": true, "normalise": true, "min_score": 0.12763649999999999}`. max dev selection_score = mean(nDCG@k over answerable, decision accuracy over all); thresholds at the midpoint of the best dev plateau; ties -> simpler config.

## Development (used for tuning)

| ID | Configuration | Hit@k | MRR | nDCG@k | Dec. acc. | Abstain (unans.) | False abstain | Selection |
|---|---|---|---|---|---|---|---|---|
| B0 | BM25 starter baseline (k1=1.5, b=0.75, no threshold) | 0.963 | 0.920 | 0.861 | 0.818 | 0.000 | 0.000 | 0.839 |
| B1 | + stopword removal | 0.963 | 0.901 | 0.861 | 0.818 | 0.000 | 0.000 | 0.839 |
| B2 | + light stemming | 1.000 | 0.963 | 0.920 | 0.818 | 0.000 | 0.000 | 0.869 |
| B3 | + abstention threshold on raw score | 1.000 | 0.963 | 0.920 | 0.848 | 0.167 | 0.000 | 0.884 |
| B4 | + threshold on normalised score | 1.000 | 0.963 | 0.900 | 0.970 | 0.833 | 0.000 | 0.935 |
| BT | BM25 fully tuned (grid: k1, b, stemming, normalisation, threshold) | 1.000 | 0.963 | 0.920 | 0.970 | 0.833 | 0.000 | 0.945 |
| D0 | Dense MiniLM, no threshold | 1.000 | 0.932 | 0.815 | 0.818 | 0.000 | 0.000 | 0.817 |
| D1 | Dense MiniLM + tuned threshold | 0.963 | 0.920 | 0.806 | 0.939 | 0.667 | 0.000 | 0.873 |
| H1 | Hybrid RRF (BT + D1) | 1.000 | 0.957 | 0.899 | 0.909 | 0.500 | 0.000 | 0.904 |

## Held-out test (reported once, never tuned on)

| ID | Configuration | Hit@k | MRR | nDCG@k | Dec. acc. | Abstain (unans.) | False abstain | Selection |
|---|---|---|---|---|---|---|---|---|
| B0 | BM25 starter baseline (k1=1.5, b=0.75, no threshold) | 0.867 | 0.867 | 0.820 | 0.714 | 0.000 | 0.000 | 0.767 |
| B1 | + stopword removal | 1.000 | 0.911 | 0.851 | 0.714 | 0.000 | 0.000 | 0.783 |
| B2 | + light stemming | 0.933 | 0.933 | 0.882 | 0.714 | 0.000 | 0.000 | 0.798 |
| B3 | + abstention threshold on raw score | 0.933 | 0.933 | 0.882 | 0.762 | 0.167 | 0.000 | 0.822 |
| B4 | + threshold on normalised score | 0.933 | 0.933 | 0.867 | 0.905 | 0.667 | 0.000 | 0.886 |
| BT | BM25 fully tuned (grid: k1, b, stemming, normalisation, threshold) | 0.933 | 0.933 | 0.867 | 0.857 | 0.500 | 0.000 | 0.862 |
| D0 | Dense MiniLM, no threshold | 0.867 | 0.822 | 0.643 | 0.714 | 0.000 | 0.000 | 0.679 |
| D1 | Dense MiniLM + tuned threshold | 0.800 | 0.756 | 0.612 | 0.905 | 0.833 | 0.067 | 0.758 |
| H1 | Hybrid RRF (BT + D1) | 0.867 | 0.867 | 0.765 | 0.810 | 0.333 | 0.000 | 0.787 |

95% bootstrap CIs for the chosen system on test:

- selection_score: 0.752 – 0.953
- mean_ndcg_at_k: 0.720 – 0.983
- decision_accuracy: 0.714 – 1.000
