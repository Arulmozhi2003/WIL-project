# Changelog: issues found and how they were addressed

Appendix evidence of the iterative process. Changes on 2026-09-29 were made with AI assistance (Claude Code, Anthropic). Declare this in the Condition 3 Bounded Use of AI Declaration.

## 2026-09-29 — Review of the starter prototype

| # | Issue found | Evidence | Fix |
|---|---|---|---|
| 1 | Unanswerable questions were always answered | "What salary will this job pay in 2030?" retrieved all 3 documents through the words "this" and "job"; abstain rate on unanswerable questions = 0.0 | Stopword removal + an abstention threshold tuned on dev (`BM25.min_score`) |
| 2 | Dense retriever could never abstain | It always returned the top-k documents, however low their similarity | `DenseRetriever.min_score`, tuned on dev |
| 3 | Skill gaps changed with the question's wording | Gaps were computed only from the top-k documents retrieved for the question | `gaps_for_role` counts skills over all documents for the role and shows "N of M" |
| 4 | A string `skills` field was silently split into characters | `"SQL, Excel"` became `['S','Q','L',...]` | `load_documents` now rejects anything that is not a list of strings |
| 5 | C++ and C# were lost in tokenisation | `C++ and C#` became `['c','c']` | New token pattern |
| 6 | Hyphenated skill names were not normalised | `power-bi` did not map to Power BI, and "Power-BI" in ad text was not detected | Alias keys now normalise hyphens and underscores; the taxonomy has 47 canonical skills |
| 7 | The app rebuilt the retriever on every click | Dense mode reloaded the model each time | `st.cache_resource` / `st.cache_data` |
| 8 | Passage slider crashed with one document | `st.slider(1, 1, 1)` | Replaced with a number input capped at the role's document count |
| 9 | The LLM never saw the target role | The role was not in the prompt | Role is passed to the prompt; prompt v2 adds stricter citation and abstention rules |
| 10 | No check that citations were real | Citations were not checked against the retrieved documents | `check_answer` flags missing and invalid citations; the app warns about them |

## 2026-09-29 — Tuning pipeline, first iteration and a failure

- Added `run_experiments.py`: a sequence of controlled changes, tuning on dev only, a single test run, and bootstrap CIs.
- **Failure observed** (synthetic smoke data): the first version set the threshold at the lower edge of the best dev range. On the test split this rejected an answerable question (test nDCG 0.0 for the tuned system vs 1.0 for the untuned one). That is overfitting to 4 dev questions.
- **Controlled changes in response** (decided from dev behaviour and general principle, then re-run):
  1. The threshold is now the midpoint of the widest best-scoring range, which leaves the most room on both sides.
  2. Normalised BM25 scores (share of the question's attainable score), so one threshold is comparable across questions.
  3. Light stemming (requested/requests, modelling/modeled).
- Remaining limitation: on 3 synthetic documents and 4 dev questions, dev cannot tell configurations apart (many settings tie at a perfect dev score), so the tuned system still missed one synthetic test question. This is expected at that size, and it is why the protocol requires ≥ 40 real questions. The tie-break rule was not tuned further against test results.

## 2026-09-29 — Real dataset and first real evaluation

- **Data:** replaced the synthetic fixtures with 159 real SEEK Australia ads (JobsPikr 2018, CC BY 4.0, DOI 10.5281/zenodo.1220874). The first dataset considered, NextGig's multi-ATS snapshot (CC BY 4.0), was rejected: it has only ~5 relevant Australian ads, its descriptions are LLM-written summaries, and it has no source URLs.
- **Issues found while building it:** 15 exact duplicates; 6 reposts of the same ad in different cities (added near-duplicate detection); UTF-8 text decoded as cp1252 ("â€“", "Â"), repaired in `ingest.py`; a byte-order mark in the CSV header. Checked the ambiguous skill matches (R, Excel, Spark) by reading the matched contexts: all were genuine tool mentions.
- **Questions:** 54 rule-labelled questions (skill / specific ad / unanswerable), stratified 60/40 dev/test. One unanswerable question ("visa sponsorship") was dropped for the Business/Data Analyst role because 3 ads mention sponsorship.
- **Results** (`results/summary.md`, k=3, test n=21): the starter BM25 never declined an unanswerable question (0/6). The dev-selected system (BT: stopwords, stemming, normalised score, threshold 0.128, k1=2.0, b=0.75) declines 3/6 on test with no false abstentions. Test selection score 0.767 → 0.862 (95% CI 0.752–0.953); nDCG@3 0.820 → 0.867. Dense MiniLM ranked worse than BM25 on both dev and test (test nDCG 0.643). Hybrid RRF did not beat BM25 on dev, so it was not selected.
- **Honest notes:**
  - On test, B4 (0.886) scored slightly above the dev-selected BT (0.862). BT stays the reported system because it was chosen on dev.
  - Hybrid RRF answers whenever *either* retriever passes its threshold, which weakens abstention (dev 0.50 vs 0.83). An AND-gated hybrid is a candidate next iteration, but it would need a fresh test set.
- **Dev failure cases** (`results/failures_dev.md`):
  - "Is SQL knowledge expected for business analysts?" ranks first an ad that never mentions SQL but repeats "knowledge", "expected" and "business analyst".
  - "Is the R language asked for?" matches an ad about staff speaking 70 "languages".
  - "Is a forklift licence required?" matches an ad about regulatory "licence" compliance.
- **Rejected idea:** boosting ads whose skill list contains the queried skill would fix the first two failures. It was rejected because the relevance labels come from the same skill lists, so the boost would inflate the metrics circularly.

## 2026-09-30 — Role-level questions, refusal detection and prompt v3

- **Issue (found in the app):** the default question "What skills are requested for this role?" was refused. After stopword removal it is only "skill request role"; "skill" and "role" occur in almost every ad (near-zero IDF) and few ads say "requested", so no ad cleared the 0.128 threshold. None of the 54 evaluation questions was a role-level question, so tuning never saw this case.
- **Fix:** `is_overview_question` detects questions made only of generic words (skills, role, required, job…). They are answered from `role_overview`: skill counts over **all** ads of the role, given to the model as `[SOURCE SKILL_PROFILE]`, plus the 3 ads that name the most of the role's common skills. None of the 54 evaluation questions and none of the should-refuse demo questions take this route, so the retrieval results are unchanged.
- **Issue:** the refusal detector counted any answer containing the refusal sentence as a refusal, including an answer that answered the question and then refused a salary sub-question. It now only counts answers that open with the refusal.
- **Demo check** (49 questions, full RAG, prompt v2): 49/49 behave as expected (39 answered, 10 refused). "Will this job sponsor my visa?" is answerable: one ad states "visa sponsorship is not available for this position". 11 answers named the company instead of using a `[SOURCE id]` tag.
- **Prompt v3 experiment** (citation format shown by example): dev valid citations 22/27 → 24/27, but on the demo list it wrongly refused 2 answerable questions and citations did not improve (29/38 vs 29/40). **Kept v2 as the default**; missing citations remain a known limitation of the 3B model and are flagged in the app.

## 2026-09-30 — Entry-level focus: experience levels and a job-level filter

- **Question from the team:** SkillGap is for students, so how entry-level is the data? Measured: of the 159 ads only 7 have a graduate/junior title, 10 ask for 1–2 years, 104 state no years and 38 ask for 3+ years. In the whole 30,000-ad SEEK file only 9 graduate/junior ads name two or more data skills, so the source cannot supply a graduate-only knowledge base.
- **Decision (team):** keep all 159 ads and add a filter, rather than removing ads. The evaluation therefore stays valid and unchanged (dev 0.945, test 0.862).
- **Change:** `experience_level` tags every ad from explicit wording only: a graduate/junior/entry/trainee/intern title, otherwise the most years of experience asked for. Years count only next to "experience" or "working with/in/as", so company ages ("for over 40 years") and contract lengths ("2 years fixed term") are ignored. The rule was checked on sampled matches and on all "not stated" ads that mention years; the first version missed "3 years+", "(3 Years+)", "5 years working with…" and "(2 years minimum)" and was widened.
- **App:** a Job level filter (All levels / Student-friendly = graduate, 1–2 years or not stated, 121 ads / Graduate-junior titles only, 7 ads) applies to the answer's evidence, role-level answers and the skill-gap table; each retrieved ad shows its level.

## 2026-10-01 reliability patch
- Reworked experience classification so explicit years override "graduate/junior" title wording.
- Split experience into `Graduate/entry title`, `0–1 year`, `Experience not stated`, and `2+ years`.
- Removed "experience not stated" from strict early-career evidence.
- Retrieval is now built over the selected experience subset, not the full corpus followed only by display filtering.
- Added a visible Streamlit evaluation trace (scope, retrieval, answer/refusal, citation presence, citation-ID validity, placeholder check).
- Added a grounding gate: unsupported/invalid-citation/placeholder answers are withheld from the final recommendation and shown only as rejected drafts.
- Added prompt v4 and made it default; v4 forbids unresolved `N of the retrieved documents` placeholders and requires actual counts.
- Added a historical-data warning using the knowledge-base collection dates.
- Added automatic evaluation fields `placeholder_count` and `grounding_pass`.
- Updated tests for conflicting junior-title/experienced-description cases and grounding checks.

## 2026-10-01 — second reliability audit
- Found and fixed a range-parsing bug: `1–2 years` and `1–4 years` were previously classified from the lower bound only. The classifier now uses the upper bound, so these are not treated as strict 0–1 year evidence.
- Renamed title-only eligibility from `Graduate/entry title` to `Graduate/entry wording` to avoid implying that a title proves zero prior experience.
- Re-audited all 159 ads after the fix: 104 `Experience not stated`, 49 `2+ years`, 4 `Graduate/entry wording`, and 2 explicit `0–1 year`. The early-career candidate subset is therefore only 6 ads and still requires human review.
- The saved BM25 threshold in `results/best_config.json` was tuned on the full 159-ad corpus. Because filtering changes BM25 IDF/score distributions, the app now exposes the saved `tuned` configuration only for `All levels`; filtered subsets are explicitly labelled `NOT VALIDATED`.
- Added tests for real failure patterns (`1 to 2 years of Finance experience`, `Experience (typically 1-4 years)`, and title/description conflicts).
- Added `scripts/audit_experience_levels.py` so the classification counts and candidate records can be regenerated.

## Output-evidence audit fix
- Added a visible **Evidence supporting this answer** table that maps each generated claim to its cited source ID, an exact evidence excerpt, and the original source URL.
- Added a **Show source proof for skill-gap table** expander with supporting ad excerpts and source links for each displayed skill gap.
- The evidence mapping is explicitly described as traceability, not an automatic semantic-faithfulness verdict; human faithfulness/correctness review remains required.
- Added automated tests for claim-to-source evidence mapping and uncited-claim detection.

## 2026-10-22 — Annotation of answers, labels and skill tags (AI annotator)

All three annotation sheets were filled by one AI annotator (Claude Code, Anthropic), following written criteria, with the reason for every negative judgement in the sheet. There is no second annotator and no agreement score; a team member should re-judge a sample. Declare this in the Condition 3 Bounded Use of AI Declaration. Summary: `results/annotation_summary.md`.

- **Generated answers** (`results/generation_dev.csv`, then `run_generation_eval.py --score`): prompt v2 faithful 22/27, correct 25/27; v3 faithful 20/27, correct 22/27. v3's extra citations came with less accurate answers, which supports keeping v2.
- **Finding:** citation presence does not predict faithfulness (v2: cited 18/22 faithful, uncited 4/5). The grounding gate is a format check, not a truth check; a claim-level support check is the next step.
- **Retrieval labels** (`data/evaluation/label_audit.csv`): 70/72 correct. Both errors are ads tagged Power BI only because a Microsoft customer-story URL in the text contains `power-bi`. In 25 rows the stored evidence sentence does not contain the skill (the ad does elsewhere).
- **Skill tagging** (`data/annotation/skill_labels.csv`, labelled blind to `auto_skills`): precision 0.950, recall 0.884, F1 0.916 on 20 ads. Errors are soft skills: missed variants ("attention to details", "cleansing") and "collaboration" in company blurbs counted as Teamwork.
- Not yet fixed (would change the tuned results and needs a new test set): strip URLs before tagging; better evidence-sentence selection for the audit sheet.

## 2026-10-23 — Held-out generation run, v4 evaluation and two QA fixes

- **Held-out test, prompt v2** (selected on dev; run once, `results/generation_test.csv`): 15/15 answerable questions answered with valid citations, 6/6 unanswerable refused, grounding gate passed 14/15. The one failure (Q03) is the placeholder "N of the retrieved documents", the problem prompt v4 targets.
- **Prompt v4 on dev** (`results/generation_dev_v4.csv`): 0 placeholders and 6/6 refusals, but citations in 20/27 answers versus 22/27 for v2. Removing placeholders lowered the citation rate; v4 stays the default for counts, and citation formatting is the next change to test on a fresh test set.
- Faithfulness/correctness for these two runs are not judged yet (columns left empty).
- **QA-01 fixed:** `BM25`, `DenseRetriever` and `HybridRetriever` reject a negative `k`; `run_eval.py --k -1` exits with an error. The strict-xfail test is now a normal passing test.
- **QA-04 fixed:** `answer_decision()` in `skillgap/generation.py` drives the app's trace row; a withheld draft is reported as "Withheld (failed grounding check)" / FAIL, never Answered/PASS. New regression test.
- `pytest -q`: 31 passed.
