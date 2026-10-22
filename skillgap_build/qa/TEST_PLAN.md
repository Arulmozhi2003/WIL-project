# Test Plan

Audit date: 2026-10-05  
Project: SkillGap prototype (`skillgap_build`)  
Constraint: audit-only; do not modify production application code. Isolated regression tests and QA documentation are permitted. No live external or destructive security testing.

## Scope and Approach

Test the actual local Python/Streamlit application, its deterministic core logic, local JSON corpus, ingestion command, evaluation command and Ollama integration. The primary test levels are:

- Existing unit/regression suite: retrieval, tokenization, skill rules, role overview, experience parsing, evaluation metrics, grounding and mocked Ollama request.
- Added isolated pytest coverage: k boundaries, dense retriever role scope with a fake encoder (no model download), empty corpus, and ingestion normalization/deduplication/row filtering in temporary directories.
- CLI evaluation: run the saved BM25 configuration against labelled questions and save output in `qa/evidence/`, not over prior experiment results.
- Browser E2E: use the running local Streamlit app for a real role-overview interaction; exercise a specific question and observe whether citations are accepted or withheld.
- Local API integration: verify Ollama availability/model and bounded generation behavior. Do not stop Ollama or mutate project corpus/results.
- Static/security review: inspect endpoints, authentication/data persistence, input flow and listener addresses. Non-destructive only.

## Environment and Test Data

- Windows host, Python 3.14.5 for the live app and final audit tests. Direct Conda Python 3.9.7 invocation had an `_ssl` DLL error; activation via `conda run` allowed tests to execute, but the declared Streamlit range could not be installed there. The project has no explicit supported Python minimum.
- Project root: `skillgap_build/`. Pytest: `C:/Python314/python.exe -m pytest -q`.
- Streamlit: `http://localhost:8501`. Ollama API: `http://127.0.0.1:11434`; model `llama3.2:3b`.
- Dataset: 159 source ads; `data/evaluation/questions.json`: 54 labelled questions (33 dev/21 test). No credentials/test accounts needed or present.
- Ingestion smoke test creates raw rows under pytest `tmp_path` and writes documents/provenance only under that isolated temporary folder.
- Retrieval-evaluation output is isolated at `qa/evidence/retrieval_eval.json`.

## Execution and Safety

Use the selected Python interpreter to run pytest. Use `run_eval.py --config results/best_config.json --output qa/evidence/retrieval_eval.json` for read-only retrieval scoring. Browser inputs do not change the corpus. Avoid `scripts/build_seek_dataset.py` because it rebuilds/deletes dataset files, avoid `ingest.py` with default paths, and do not run the full experiment ladder because it overwrites saved results and may download dense assets. Full `run_generation_eval.py` needs many slow model calls and leaves faithfulness/correctness blank pending human annotation; the whole generation evaluation is not claimed complete. Do not probe outside localhost or test another user's machine.

## Test Categories

- Functional positive/negative: role/experience scope, overview, specific Q&A, skill gap and source evidence.
- Boundary/input validation: empty/invalid document data, skill list types, retrieval `k`, threshold and free-text risks.
- Integration: corpus-to-retriever, retriever-to-Ollama prompt, citations-to-evidence output, ingestion-to-provenance, and evaluation CLI.
- Security/privacy: authentication/RBAC absence (not applicable to prototype), loopback Ollama, Streamlit listener exposure, prompt injection defenses, HTML/input handling and data persistence.
- Performance/reliability: observed generation latency, request timeout/output limits, no-evidence abstention, unavailable API behavior and large evidence settings.
- Accessibility/browser/responsive: inspect controls/labels in the browser; broad browser, keyboard, screen-reader and viewport matrix remains unrun because no dedicated E2E/accessibility framework is configured.

## Exit and Reporting Rules

Each test case records expected behavior from README/code contracts. `PASS` means executed and observed as expected. `FAIL` means executed behavior violates a documented or conservative API boundary. `XFAIL` is an intentionally expected pytest failure used to preserve a reproduced known defect; it is not counted as a pass. `BLOCKED` means a required service/resource was unavailable. `NOT RUN` means no execution evidence exists. `N/A` means the feature is absent from this architecture. Prior experiment output is historical evidence, not a fresh run.
