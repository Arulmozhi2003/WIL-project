# Test Execution Report

Audit date: 2026-10-05  
Application: SkillGap prototype  
Execution constraint: no production code changed during this audit. New tests and QA artifacts are isolated from project corpus/results.

## Summary

| Metric | Result |
|---|---:|
| Test cases identified | 72 |
| Executed | 55 |
| Passed | 49 |
| Failed | 6 behaviors (5 `FAIL` cases plus 1 `XFAIL` defect reproduction) |
| Blocked | 1 |
| Not run | 13 |
| Not applicable | 3 |
| Verified pass rate | 89.1% (49 / 55 executed cases) |

The test runner reports **29 passed, 1 xfailed**. `XFAIL` is a test deliberately marked expected-failure for a reproduced defect, not a passing behavior; it is counted among the 6 failed behaviors above. The five ordinary failing cases are `ENV-03`, `GEN-10`, `PERF-02`, `SEC-04`, and `UI-10`. Counts come from the 72 rows in `TEST_CASES.md`; three `N/A` cases are excluded from the executed denominator.

## Commands and Evidence

- `C:/Python314/python.exe -m pytest --collect-only -q`: 30 automated tests collected after adding `tests/test_qa_regression.py`.
- `C:/Python314/python.exe -m pytest -q`: 29 passed, 1 xfailed, in 1.08 seconds.
- `C:/Python314/python.exe -m pytest -q tests/test_qa_regression.py`: 4 passed, 1 xfailed. It exercised BM25 positive/zero/oversized limits, dense role scoping with a fake encoder, empty corpus, and isolated ingestion.
- `C:/Python314/python.exe -m pytest -q --runxfail tests/test_qa_regression.py::test_bm25_negative_k_is_rejected`: failed as expected because the call did not raise `ValueError`; confirms QA-01.
- Dependency resolution for `streamlit>=1.36,<1.50` under Conda Python 3.9.7: no matching versions; releases in this range exclude 3.9.7. This is an observed compatibility problem with the configured interpreter and an undocumented project Python minimum (QA-06).
- `C:/Python314/python.exe run_eval.py --config results/best_config.json --output qa/evidence/retrieval_eval.json`: completed over 159 docs and 54 questions. Output is isolated at `qa/evidence/retrieval_eval.json`.
- Corpus integrity check: 159 loaded documents, 159 unique IDs, valid `list[str]` skills, all 159 HTTP(S) source URLs; role totals 80/58/21; experience totals 104 not stated, 49 2+ years, 4 graduate/entry wording, 2 explicit 0–1 year.
- Evaluation question file: 54 total, 33 dev, 21 test; 42 answerable, 12 unanswerable.
- Browser E2E: live app opened; role BA, All levels, overview question returned deterministic frequency data for 58 ads. Specific question `Is experience with Tableau required?` retrieved three documents; model response lacked citations, the grounding gate withheld it, and the new UI did not render the evidence-support table. The rejected draft remained available in its explicitly named expander. The evaluation-trace status branch is inconsistent (QA-04).
- Local Ollama smoke test: prior bounded `llama3.2:3b` API call returned `Ollama ready` in 17.8 seconds. The current browser specific question did complete, but generated no citations.
- Live HTTP checks returned 200 for Streamlit `:8501` and Ollama `:11434`.
- Windows listener inspection: Streamlit listens on `::`:8501; Ollama listens on `127.0.0.1`:11434.

## Fresh Retrieval-Evaluation Output

This command ran the saved configuration across the entire 54-question set (dev and test together). These combined figures are diagnostic only and **must not** be presented as held-out test performance or used to select/tune a model:

| Metric | Observed |
|---|---:|
| Hit rate at k | 0.976 |
| MRR | 0.952 |
| nDCG@k | 0.901 |
| Recall@k | 0.547 |
| Answer/abstain decision accuracy | 0.926 |
| Unanswerable abstain rate | 0.667 (8/12) |
| False-abstain rate on answerable questions | 0.000 (0/42) |
| Selection score | 0.913 |

This is a retrieval-only diagnostic. It says nothing about whether Ollama's generated text is correct, faithful or properly cited.

## Feature Coverage

- **Verified in execution:** corpus load and schema, document/source integrity, core BM25/dense-with-fake-encoder/hybrid paths, input skill parsing, deterministic gap and overview calculations, experience rules, citation/abstention/placeholder checks, isolated ingestion, saved-config retrieval scoring, browser page load/overview/specific-question fail-closed path, local model/API health.
- **Observed failures:** configured Python 3.9.7 cannot satisfy the declared Streamlit dependency; negative BM25 k is not validated; long generation via the helper can truncate at its token cap; a real specific query produced no citation and was withheld; Streamlit is bound to a network wildcard without app authentication; the evaluation trace appears to mark a rejected draft as `Answered/PASS`.
- **Blocked:** full generation-quality evaluation needs many slow Ollama calls plus human `faithful`/`correct` labels (two independent annotators per project protocol). Historical `generation_dev.summary.md` has no human scores.
- **Not run:** all 3 roles in browser, all settings/method combinations and k upper boundary, browser back/refresh, dense MiniLM first-use download/live ranking, full experiment ladder, destructive corpus rebuild, source injection/XSS and keyboard/screen-reader/responsive matrix.
- **Not applicable:** login/authorization, database CRUD, separate application REST endpoints; these features are not implemented.

## Readiness Conclusion

The deterministic retrieval/profile/gap core and the fail-closed citation guard show useful verified behavior, and the app is operational locally. **Not release-ready for general users or network exposure** based on this audit: normal LLM answers can be withheld for missing citations, the trace can misreport a withheld response, one public retriever boundary is invalid, the configured Python support is unclear, and the unauthenticated UI listens on all interfaces. There is no measured current end-to-end answer-quality score or accessibility/browser matrix. Keep use restricted to a trusted local demo until issues are addressed and generation is evaluated with human labels.
