# Project Analysis

Audit date: 2026-10-05  
Scope: `skillgap_build/`; source inspection, current local dataset, local Streamlit/Ollama services, tests and documented evaluation artifacts. This audit does not change production code.

## Architecture

SkillGap is a Python/Streamlit prototype; the project does not declare a supported Python minimum. The live app and final audit ran with Python 3.14.5. The configured Conda Python 3.9.7 could not resolve the declared `streamlit>=1.36,<2` range because available Streamlit releases exclude that patch version or require Python >=3.10. Its test suite could run when Conda was activated, but that interpreter did not provide the app dependency. This setup ambiguity is recorded as QA-06. `app.py` is the single-page interface. There is no separate web frontend/backend service, application REST router, authentication layer, authorization model, user session store, or database. The app loads JSON files from `data/documents/` and an optional saved retrieval configuration from `results/best_config.json`; user inputs and computed answers are held in the Streamlit session and are not persisted as user records.

| Area | Implementation | Responsibilities |
|---|---|---|
| UI and request orchestration | `app.py` | Role and experience scope, skills/question inputs, retriever/model settings, answer/abstention display, citations/evidence tables, evaluation trace and skill-gap table. |
| Corpus and retrieval | `skillgap/core.py` | Document validation, skill taxonomy/extraction, experience classification, BM25, dense MiniLM, hybrid RRF, role-level profiles and skill gaps. |
| Generation and grounding | `skillgap/generation.py` | Ollama `/api/chat` request, prompt variants, abstention/citation/placeholder checks, evidence excerpt mapping. |
| Metrics | `skillgap/evaluation.py` | Question loading, retrieval metrics, tuning, bootstrap intervals and skill-extraction evaluation. |
| Data import | `ingest.py` | CSV/JSON/JSONL ingestion, text cleaning, exact/near-duplicate handling, skill labels and provenance. |
| Evaluation commands | `run_eval.py`, `run_experiments.py`, `run_generation_eval.py` | Retrieval evaluation, dev tuning/test scoring, generation evaluation requiring Ollama and human annotations. |
| Dataset/question utilities | `scripts/build_seek_dataset.py`, `scripts/build_questions.py`, `scripts/audit_experience_levels.py`, `scripts/extras/` | Rebuild source corpus/questions, classify experience, produce reports/workbooks/demos. |
| Test configuration | `pytest.ini`, `tests/` | Pytest configured to collect `tests/`; project has unit and added QA regression tests. |

Dependencies declared in `requirements.txt`: Streamlit, Requests, NumPy, sentence-transformers, Matplotlib and pytest. Other transitive dependencies provide the transformer, tensor and UI runtime. The dense model is `sentence-transformers/all-MiniLM-L6-v2` and may require a first-use download. Generation defaults to local Ollama model `llama3.2:3b` at `http://localhost:11434`.

## Data and Rules Observed

A read-only load validated 159 documents, all with unique IDs, list-of-string skill tags and HTTP(S) source URLs. Role counts: Graduate Data Analyst 80; Graduate Business/Data Analyst 58; Graduate Data Scientist 21. Experience counts: Experience not stated 104; 2+ years 49; Graduate/entry wording 4; 0–1 year 2. All are labelled as public SEEK Australia 2018 job ads. Evaluation questions: 54 total (33 dev, 21 test); 42 answerable and 12 unanswerable according to the labels.

Business rules specified in README/code:

- Only the supplied historical job-ad corpus is evidence; it is not a current labour-market census or employment guarantee.
- Role and experience selections scope retrieval and skill-gap calculations. Unknown experience remains distinct from zero/low experience; explicit years override title wording and ranges use the upper bound.
- Skills come from a fixed exact-match taxonomy or document-supplied manual labels. User-owned skills are removed from gaps. Skill shares count all selected role documents, independently of question wording.
- Retrieval modes are BM25, dense MiniLM cosine similarity, and reciprocal-rank fusion hybrid. Saved tuning applies only to the original full corpus; filtered subsets should be treated as not separately validated.
- No retrieved evidence means abstain. Generated claims must contain valid source IDs and no unresolved count placeholders to pass the automatic grounding gate. This is not a semantic entailment check.
- Role-overview questions are answered deterministically from counts across the full selected role subset. Normal specific questions are sent to Ollama with the target role and retrieved sources.
- In the inspected version, Ollama generation has a 600-second request timeout and 512-token output cap. Each retrieved document context is truncated to 4,000 characters.

## User-Visible Functionality Inventory

1. Select one of the roles present in the loaded corpus.
2. Select one of five experience scopes: early-career candidate evidence, graduate/entry wording, explicit 0–1 year, experience not stated, or all levels; display counts and warn on small subsets.
3. Enter free-form existing skills and a free-form question.
4. Expand Settings; select tuned (only full corpus), BM25, dense or hybrid retrieval; set evidence count; choose Ollama model and prompt; set skill-gap minimum share.
5. Analyse: detect overview vs specific question; retrieve evidence or abstain; use deterministic counts for overview or Ollama generation for specific questions.
6. Display accepted answer or withheld rejected draft, source citations/claim evidence where applicable, evaluation trace, deterministic potential-gap table, source proof for gaps, and retrieved source documents/URLs.
7. CLI data import and evaluation workflows described in README, including human generation annotation/scoring.

## Integrations and Security Boundary

- Ollama is a local HTTP integration. The local API responded during the audit and `llama3.2:3b` was installed. The app does not authenticate users before sending prompts to that API.
- Dense retrieval can fetch model assets from the model host on first use.
- Dataset build utilities can fetch the cited Zenodo source. Stored source URLs are displayed; the app does not fetch ad URLs at request time.
- No SQL/database, account, password, token, or role-based authorization workflow exists to test. Authentication/RBAC test categories are not applicable to the current design, not passing results.
- Observed Windows listener state: Streamlit bound to IPv6 wildcard `::` on port 8501; Ollama bound to `127.0.0.1:11434`. Streamlit has no configured authentication in this project. This is a deployment exposure risk on a reachable network.
- Dataset build/import commands may delete, append, or overwrite output files depending on options/defaults. They were not run against project data during this audit; ingestion smoke coverage used isolated temporary directories.

## Existing Evidence and Limitations

`README.md` and `CHANGELOG.md` define prototype constraints and known prior issues. `results/summary.md` is a prior retrieval experiment report from 2026-09-29, not this audit’s test run. `results/generation_dev.summary.md` reports prompts v2/v3 citation checks but has no human faithfulness/correctness scores. The app defaults to prompt v4, so those historical results do not validate current end-to-end answer quality.

Unresolved requirements: there is no specified supported browser/viewport matrix, performance service-level objective, maximum question/skills text length, required uptime, external deployment/network policy, acceptable model answer-quality threshold, or signed-off manual faithfulness/correctness label set. The documentation has different installation command examples across platforms; Windows setup is not fully formalized. These are not inferred as requirements.
