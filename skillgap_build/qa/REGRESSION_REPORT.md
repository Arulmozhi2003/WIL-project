# Regression Report

Audit date: 2026-10-05  
Production application code was not changed during this audit. The only code addition is an isolated pytest module at `tests/test_qa_regression.py`; QA reports and retrieval-evaluation output are under `qa/`.

## Automated Coverage

The project initially contained 25 tests in `tests/test_core.py`. The audit added 5 QA regression tests covering:

- BM25 `k` boundary behavior: k=0, k greater than result count, and the known negative-k defect.
- Dense retrieval/role scoping with a fake encoder; no model download.
- Empty document-directory behavior.
- CSV ingestion in an isolated temporary filesystem: valid import, HTML/entity normalization, duplicate suppression, short-row dropping, missing-field dropping and manifest linkage.

Current combined run: `C:/Python314/python.exe -m pytest -q` -> **29 passed, 1 xfailed**. The xfailed case is intentionally strict and exposes QA-01; running that case with `--runxfail` yields `Failed: DID NOT RAISE ValueError`. No other test failures occurred.

Existing tests continue to cover BM25 ranking/role restriction, stemming/tokenization, exact taxonomy skill extraction and aliases, skill-gap calculations, role overview, experience classification, retrieval metrics/threshold tuning/bootstrap, hybrid ranking, citation ID checks, placeholder rejection, abstention and mocked Ollama payload construction. The request test asserts timeout=600 and `num_predict`=512.

## End-to-End/Integration Evidence

- Live Streamlit app loaded at localhost and displayed the historical-corpus notice, role/experience controls, skills/question fields, settings, result tables and evidence controls.
- Overview happy path was submitted in the browser with BA / All levels. It displayed deterministic skill counts for 58 ads and passed citation/grounding checks.
- Specific Tableau requirement path retrieved three ads and called the real local Ollama model. The generated text had no citations, was withheld, and displayed a no-citation warning. The evidence-support table was absent after the prior rendering fix. The rejected draft could be inspected in its explicitly labelled expander.
- Current evaluation-trace source logic still labels any truthy draft as Answered/PASS, even when grounding fails. This is documented as QA-04; trace cell text was not directly extracted from Streamlit's canvas-rendered dataframe.
- Local Ollama health and a small generated response were verified. The local model-specific path is slow; one direct overview-helper request took 185.9 seconds and hit the configured 512-token cap mid-claim. The main app's overview path bypasses model generation, but the CLI generation-evaluation path still invokes the model.
- `run_eval.py` evaluated 54 labelled questions with saved BM25 settings. A separate output was written to `qa/evidence/retrieval_eval.json` to preserve the existing experiment report/config.

## Remaining Regression Risks

- The supported Python minimum is unspecified. Python 3.9.7 could run tests under Conda activation but cannot install the declared Streamlit range; the app was validated on Python 3.14.5.
- No browser automation suite is committed; browser checks in this report are manually driven via the available VS Code browser tools. Reruns depend on local services and the live workspace.
- Generation correctness/faithfulness is not covered by unit tests and requires independent human annotation. A model response passing citation syntax is not proof of support.
- Dense retrieval with the actual MiniLM model, the full dev/test experiment ladder, all prompt versions, all three roles in browser, every job-level setting, and max-k performance are not verified here.
- No supported browser/viewport policy or accessibility target is defined. Keyboard-only, screen-reader, contrast and responsive checks remain outstanding.
- The UI's wildcard bind and lack of authentication make network deployment inappropriate without explicit access controls.
- Existing historical generation report has no faithful/correct scores; current default prompt v4 has no complete human-rated evaluation.

## Release Recommendation

Keep the app restricted to a trusted local demo. Before external use, document a supported Python version and fix QA-06 if 3.9.7 is intended, fix QA-01 and QA-04, decide on a safe network binding/authentication policy, improve and human-evaluate the specific-answer citation success rate (QA-02), and ensure generation evaluation cannot record truncated output as complete (QA-05). Do not treat the combined 54-question retrieval diagnostic as held-out generalization evidence.
