# Bug Report

Audit date: 2026-10-05. No production fixes were made during this QA audit. Findings below are reproducible or directly evidenced by the executed UI/test/code path. Priorities describe recommended triage, not project-defined SLAs.

## QA-01: Negative retrieval limit silently slices results

- **Severity / priority:** Low / P3.
- **Affected area:** BM25 public API; `skillgap/core.py` (`BM25.search`, around line 204); `run_eval.py` accepts integer `--k` without checking it is nonnegative.
- **Reproduction:** With two matching documents, call `BM25(docs).search('SQL', k=-1)`.
- **Expected:** Reject negative k with a clear `ValueError` (zero may validly return no hits); a negative limit must not have implicit list-slice meaning.
- **Actual:** No exception. The expression `[:k]` uses Python negative slicing and silently drops the last result. `pytest --runxfail tests/test_qa_regression.py::test_bm25_negative_k_is_rejected` reproduced `Failed: DID NOT RAISE ValueError`.
- **Impact:** Invalid CLI/library inputs produce surprising retrieval results. Current Streamlit number input has minimum 1, so ordinary UI use does not expose it.
- **Recommendation:** Validate `k >= 0` at the search/API boundary and the CLI boundary; add explicit zero/negative tests.
- **Status:** Open; not fixed per audit-only instruction.

## QA-02: Specific model answer omitted citations and was withheld

- **Severity / priority:** Moderate / P2.
- **Affected area:** Local Ollama answer generation; `skillgap/generation.py`, `app.py`.
- **Reproduction:** In the browser choose Graduate Business/Data Analyst, All levels; ask `Is experience with Tableau required?`; click Analyse.
- **Expected:** A concise answer supported by retrieved ads with exact `[SOURCE doc_id]` citations, or a clear abstention when evidence is insufficient.
- **Actual:** Three ads were retrieved. The model drafted: “In these retrieved ads, experience with Tableau is not explicitly stated as a requirement…” and said a named employer considered Tableau desirable, but included no source tags. The app correctly withheld the draft and warned “The draft contains no source citations and is therefore unsupported.” No final answer was produced.
- **Impact:** The safety gate avoids publishing ungrounded recommendations, but a normal specific-question workflow can fail to provide a usable response. A citation ID check alone would not establish semantic faithfulness even when citations exist.
- **Recommendation:** Keep the fail-closed gate. Evaluate stronger model/prompt or constrained citation generation on a held-out set; include human faithfulness/correctness labels before selecting a model/prompt. Do not relax citation validation to make this example appear successful.
- **Status:** Open; behavior is deterministic only for overview questions, not specific RAG queries.

## QA-03: Unauthenticated Streamlit UI listens on wildcard interface

- **Severity / priority:** Moderate / P2 for any shared/reachable network; low for isolated trusted local use.
- **Affected area:** Runtime deployment configuration, `app.py` has no authentication; current server launch.
- **Reproduction/evidence:** Read-only `Get-NetTCPConnection` showed the Streamlit listener on IPv6 `::` port 8501. Ollama is correctly loopback-only at `127.0.0.1:11434`. The Streamlit server printed LAN/network URLs. No login or authorization code is present.
- **Expected:** A local-only prototype should listen only on loopback; a shared deployment needs a documented access-control boundary.
- **Actual:** The UI is bound to all IPv6 interfaces and does not require a user identity. Remote reachability from another device was deliberately not probed.
- **Impact:** Other hosts on reachable networks may be able to view/use the app and submit queries. The corpus is public, but application access and model/resource consumption are still exposed.
- **Recommendation:** Launch with `--server.address 127.0.0.1` for local use; if network access is intended, require an approved authenticated reverse proxy/firewall configuration. Recheck listener address after deployment.
- **Status:** Open deployment risk. No remote access test performed.

## QA-04: Evaluation trace can mark a rejected draft as Answered/PASS

- **Severity / priority:** Low to moderate / P2.
- **Affected area:** `app.py` around lines 151–152, trace row “4. Answer/refusal decision”.
- **Reproduction/evidence:** Run QA-02. The checks object reports `grounding_pass=False` and the UI says the answer is withheld. The trace expression uses `checks['abstained'] or result` to select “Answered” and the status expression also treats a truthy `result` as PASS, without requiring `checks['grounding_pass']`.
- **Expected:** Trace labels the outcome “Rejected/withheld” and does not show PASS for a draft that was not accepted.
- **Actual:** From the inspected code, the nonempty uncited draft takes the “Answered”/PASS branch even though it is withheld. DataFrame cells are rendered through Streamlit’s grid and not exposed in the page accessibility snapshot; the inconsistent branch is nevertheless deterministic from the observed state and source condition.
- **Impact:** The mentor-facing evaluation trace can mislead reviewers about whether a usable grounded answer was produced.
- **Recommendation:** Base the trace answer/status on `grounding_pass`, `abstained`, and whether an accepted answer was actually displayed; add a regression test for a truthy ungrounded result.
- **Status:** Open; not fixed per audit-only instruction.

## QA-05: Long profile generation can be slow and truncated in helper/evaluation path

- **Severity / priority:** Moderate / P2 for generation-evaluation completeness; UI overview path currently avoids this call.
- **Affected area:** `skillgap/generation.py` around lines 164–171; `run_generation_eval.py` still calls the model for its overview path.
- **Reproduction/evidence:** Directly passed the BA profile plus three representative ads to `answer_with_ollama`. On this host the call took 185.9 seconds and ended at the 512-token cap mid-claim. Earlier run with a smaller cap also truncated. `Ollama ps` showed 100% CPU use, 4K context and around 0.3 GB free system memory at the time. The Streamlit overview now uses deterministic profile formatting and does not incur this LLM call.
- **Expected:** Any generation/evaluation call returns a complete answer within its configured deadline or emits a clear incomplete/timeout result, not a partial claim presented as a normal draft.
- **Actual:** Helper returns the token-limited partial text as if complete; the current app’s overview route bypasses it, but the generation-evaluation script still invokes it for overview questions.
- **Impact:** Long generation evaluations can take minutes per prompt and write truncated outputs; the full generation evaluation was therefore not run.
- **Recommendation:** Make the generation-evaluation runner match the app’s deterministic overview behavior, or budget output tokens according to response shape and detect truncation/finish reason; keep a realistic latency limit.
- **Status:** Open for the helper/evaluation path; not observed on the current app overview path.

## QA-06: Supported Python version is unspecified and configured Python 3.9.7 cannot install Streamlit

- **Severity / priority:** Low / P3, unless Python 3.9.7 is an intended supported runtime.
- **Affected area:** `README.md` installation requirements, `requirements.txt` Streamlit constraint, environment setup.
- **Reproduction:** Attempt to install `streamlit>=1.36,<1.50` with the configured Conda Python 3.9.7. Pip reports no matching version because Streamlit releases in that range exclude Python 3.9.7; newer releases require Python >=3.10. The app was therefore run with Python 3.14.5.
- **Expected:** Declare the supported Python range and ensure documented setup instructions resolve the dependencies on that range.
- **Actual:** README gives a generic venv/install sequence without declaring a Python minimum. The configured interpreter cannot satisfy the declared Streamlit range.
- **Impact:** A user following the generic setup with Python 3.9.7 cannot launch the UI, although tests can run when that Conda environment is activated.
- **Recommendation:** Declare and test an explicit Python minimum (for example, Python >=3.10 if consistent with project intent); add a documented Windows setup command and CI matrix for supported runtimes.
- **Status:** Open; project support target is unresolved.
