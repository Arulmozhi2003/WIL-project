# SkillGap — Test-Driven RAG prototype

**WIL Project 84.** Prototype roles: Graduate Data Analyst, Graduate Data Scientist, Graduate Business/Data Analyst. Core retrieval and skill-gap logic is role-agnostic.

## Data

**Source:** JobsPikr (2018). *30000 job postings from SEEK Australia* [Data set]. Zenodo. https://doi.org/10.5281/zenodo.1220874 — licensed **CC BY 4.0**. Every document keeps its original SEEK URL and post date. The underlying ad text was written by the advertisers; use it for non-commercial study only and attribute the dataset as above.

**Rebuild from scratch (deterministic):**

```bash
python scripts/build_seek_dataset.py   # download + MD5 check -> select -> clean -> dedupe -> data/documents/
python scripts/build_questions.py      # labelled questions + audit sheets (seed 42)
```

| Step | Rule | Result |
|---|---|---|
| Source | All postings, 10–17 April 2018 | 30,000 |
| Role by job title | Data Scientist: `data scien`, `machine learning`, `statistician`, `quantitative analyst` (excluding developer/full-stack/front-end). Data Analyst: data/reporting/insights/BI/analytics … analyst. Business/Data Analyst: business (systems/data/process) analyst **and** the ad names at least one data skill | 8,916 excluded as senior titles; 142 BA ads with no data skill excluded |
| Seniority | Titles containing senior, lead, principal, manager, head, director, architect, consultant, specialist… are excluded (graduate focus) | 181 selected |
| Cleaning | Strip HTML, repair UTF-8 decoded as cp1252, drop text < 300 characters | 1 dropped |
| Deduplication | Exact text duplicates; reposts with the same title and ≥ 80% 5-word-shingle Jaccard (`data/provenance/NEAR_DUPLICATES.csv`) | 15 + 6 dropped |
| **Knowledge base** | | **159 ads: 80 Data Analyst, 58 Business/Data Analyst, 21 Data Scientist** |

`data/provenance/MANIFEST.csv` maps every document to its raw-file row.

**Limitations:** the ads are from one week in April 2018, so tools such as Power BI are under-represented compared with today. "Graduate" is the target audience, not a guarantee that every source ad is graduate-level. Experience filtering is based only on explicit numerical requirements and graduate/junior/entry wording; missing experience information is kept as unknown rather than treated as zero experience. The Data Scientist collection is small (21 ads).

**Questions:** `data/evaluation/questions.json` holds 54 questions (33 dev / 21 test, 12 unanswerable) in three types with rule-based labels (see `scripts/build_questions.py`). Two sheets for human verification:
- `data/evaluation/label_audit.csv`: 72 (question, relevant document, evidence sentence) pairs. Mark each 1/0 and report the agreement.
- `data/annotation/skill_labels.csv`: 20 random ads. Fill `manual_skills` (`;`-separated, or `NONE`) **before** looking at `auto_skills`. `run_experiments.py` then reports extraction precision, recall and F1.

## Architecture

```
raw ads ──ingest.py──> data/documents/*.json (+ data/provenance/)
                         │  skills: manual labels, or exact taxonomy match (skillgap/core.py SKILL_TAXONOMY)
                         ▼
question + role + experience scope ──> retriever (BM25 | dense MiniLM | hybrid RRF), scoped before ranking, top-k
                         │  tuned threshold is used only for the original full corpus; filtered subsets are marked unvalidated
                         ▼
                    Ollama (prompt v1/v2) ──> answer with [SOURCE id] citations ──> automatic citation checks
role + user skills ──> deterministic skill-gap table over ALL role documents (not the LLM, not the query)
```

Design decisions:
- **Skill gaps are deterministic** and computed over every document for the chosen role, so the list does not change with the wording of the question and the LLM cannot invent it. Each gap shows "named in N of M documents".
- **Abstention is a retrieval decision.** On the original full corpus, a question whose best match is weaker than the dev-tuned threshold gets no answer instead of a guess. The saved threshold must **not** be assumed valid after filtering the corpus by experience level, because BM25 IDF and score distributions change; the app therefore disables the saved tuned configuration for filtered subsets and labels them as not separately validated.
- **Hybrid retrieval** fuses BM25 and dense rankings with Reciprocal Rank Fusion (k=60); each side applies its own threshold first.

## Data document schema (one JSON file per source)

```json
{
  "doc_id": "DA001",
  "role": "Graduate Data Analyst",
  "title": "Actual source title",
  "text": "Verbatim or appropriately licensed extracted requirements...",
  "skills": ["SQL", "Excel"],
  "skills_source": "manual | auto_taxonomy",
  "source_url": "https://actual-source.example/page",
  "source_type": "PUBLIC_JOB_AD",
  "collected_date": "YYYY-MM-DD"
}
```

`skills` must be a list. Skills must be defensible from the cited source; do not guess them.


### Experience-level filtering

`experience_level()` uses explicit evidence only. Numerical requirements in the description override title wording, and experience ranges use the **upper bound** (`1–2 years` -> 2+, `1–4 years` -> 2+). Ads with no explicit numerical requirement remain `Experience not stated`. A title containing graduate/junior/entry wording is labelled `Graduate/entry wording`; this is a title signal, **not proof of zero prior experience**.

Run the reproducible audit with:

```bash
python scripts/audit_experience_levels.py
```

The audit writes `results/experience_level_audit.json` and lists the candidate early-career ads for manual review.

### Importing another dataset

```bash
python ingest.py raw/ads.csv --text-col description --title-col job_title --url-col link \
    --date-col date_collected --role-col role
```

HTML is stripped, exact duplicates and very short (truncated) ads are dropped, and every kept row is recorded in `data/provenance/MANIFEST.csv` with its raw file and row number. Pass `--skills-col` if skills were annotated by hand.

**Validating skill extraction:** hand-label the skills of at least ~20 documents and set `"skills_source": "manual"`. `run_experiments.py` then reports the extractor's precision, recall and F1 against those labels, plus every disagreement.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull llama3.2:3b     # https://ollama.com
streamlit run app.py
```

## Evaluation protocol

### 1. Label questions (`data/evaluation/questions.json`)

```json
{"id": "Q01", "split": "dev", "role": "Graduate Data Analyst",
 "question": "Is Power BI required?", "relevant_doc_ids": ["DA003", "DA007"]}
```

- Aim for **≥ 40 questions**, about **20% unanswerable** (`"relevant_doc_ids": []`, e.g. salary, visa sponsorship, future demand), spread across the three roles.
- Split **before** running anything: roughly 60% `dev`, 40% `test`. Write questions the way a student would ask them, not by copying words from the ad (copying favours BM25).
- Label `relevant_doc_ids` against the whole role collection, not just what the system retrieves.

### 2. Retrieval experiments

```bash
pytest -q
python run_experiments.py            # add --no-dense if sentence-transformers is not installed
```

Runs a sequence of controlled changes on **dev**, picks the final system on dev only, then scores every configuration **once** on test:

| ID | Change |
|---|---|
| B0 | Starter baseline: BM25, k1=1.5, b=0.75, no stopwords, no threshold |
| B1 | + stopword removal |
| B2 | + light stemming |
| B3 | + abstention threshold on raw score |
| B4 | + threshold on normalised score |
| BT | Grid search over k1 {0.9,1.2,1.5,2.0} × b {0.3,0.5,0.75,0.9} × stemming × normalisation, with a threshold for each combination |
| D0/D1 | Dense MiniLM without / with a tuned threshold |
| H1 | Hybrid RRF of BT + D1 |

Metrics: Hit@k, MRR, nDCG@k and Recall@k over answerable questions. **Decision accuracy** is the share of all questions where the system correctly chose to answer or abstain; the table also shows the abstain rate on unanswerable questions and the false-abstain rate on answerable ones. **Selection score** = mean(nDCG@k, decision accuracy). Thresholds are placed at the midpoint of the widest range that scores best on dev, not at its edge, to reduce overfitting. The chosen system's test scores come with 95% bootstrap confidence intervals.

Outputs in `results/`: `summary.md`, `tables.tex` (booktabs tables ready for `\input{}`), `figures/threshold_sweep.pdf`, `failures_dev.md` (dev failure cases for the next iteration), `experiments.json` (everything), `best_config.json` (used by the app and the generation eval), `run_log.csv` (one row per run, the iteration history).

Rules: never tune on test; once you have looked at test results, a later change needs a new test set or has to be reported as post-hoc.

### 3. Generation (end-to-end RAG) evaluation

```bash
python run_generation_eval.py --split dev --prompts v1 v2      # needs Ollama running
# two people independently fill `faithful` and `correct` (1/0) in results/generation_dev.csv
python run_generation_eval.py --score results/generation_dev.csv
```

Automatic checks: abstained, citation present, all citations point to retrieved documents. Human judgements: faithful (every claim is supported by the cited source) and correct (answers the question). The output compares prompt versions; freeze the prompt on dev, then run `--split test` once.

## Limitations to state in the report

- The knowledge base is a small curated sample, not a census of the Australian job market; skill shares describe *these documents*.
- Taxonomy extraction only finds skills named in `SKILL_TAXONOMY`; its recall should be measured on manual labels.
- Small test sets give wide confidence intervals; report n next to every metric.
- Business value should be framed as *demonstrated answer quality on tested questions*, not improved employment outcomes.

## Research baseline

Walert: https://github.com/rmit-ir/walert and https://doi.org/10.1145/3627508.3638309 . The team's earlier Walert retrieval reproduction is separate from SkillGap's own required evaluation.

### Output proof in the app
For every non-abstained generated answer, the app displays an **Evidence supporting this answer** table. Each cited answer claim is mapped to the cited document, a source excerpt selected from that document, and the original source URL. The skill-gap table also has an expandable source-proof view showing source excerpts for the ads that triggered each skill tag. These panels provide visible traceability for the output; they do not replace human semantic faithfulness/correctness evaluation.
