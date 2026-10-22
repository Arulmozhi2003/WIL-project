# SkillGap: A Test-Driven RAG Career Navigator for International Data and IT Students
## WIL Project 84

### Project Aim
To develop and evaluate a Test-Driven RAG assistant that helps international data and IT students understand Australian graduate job requirements and identify evidence-based skill gaps for their target roles.

### Team Members
| Student ID | Name | Role (Milestone 1) |
|---|---|---|
| s4138509 | Arulmozhi Ezhilarasi Arunachalam | RAG evaluation & project coordination |
| s4118043 | Dharani Suresh | Data collection & knowledge base |
| s4184049 | Lingkesh Natanasabapathy | Retrieval & RAG development |
| s4135999 | Prakash Sudarsanraj | Testing & evaluation |
| s4136157 | Sakthisree Gaddam | Documentation, ethics & user experience |

Mentor: Kaixin Ji

### Links
- Trello board: https://trello.com/b/1GEPr6pe/wil-project
- Overleaf report: https://www.overleaf.com/project/69eae9c8f437cd161947a172

### Repository layout
| Path | Contents |
|---|---|
| `skillgap_build/` | The SkillGap prototype: data pipeline, retrievers, generation, Streamlit app, evaluation, tests, results and QA audit. See [`skillgap_build/README.md`](skillgap_build/README.md). |
| `skillgap_build/CHANGELOG.md` | Every issue found and how it was addressed, by date (the iteration history). |
| `skillgap_build/results/` | Retrieval ablation (`summary.md`), run log, generation and annotation results. |
| `skillgap_build/qa/` | QA audit: test plan, test cases, execution, regression and bug reports. |
| `report/` | Overleaf sources of the written report (course template). |
| `docs/` | Milestone 1 document and the Condition 3 AI declaration source. |

### Headline results (held-out test, 21 questions)
- Tuned BM25 declined 3 of 6 unanswerable questions (starter: 0 of 6) with no wrongly declined answerable questions.
- Selection score 0.767 → 0.862 (95% CI 0.752–0.953); BM25 beat dense MiniLM retrieval.
- Generated answers (prompt v2, dev): 22/27 faithful, 25/27 correct (AI-annotated, pending human spot-check).

### Run it
```bash
cd skillgap_build
pip install -r requirements.txt
ollama pull llama3.2:3b
pytest -q
streamlit run app.py
```

### Use of generative AI
Parts of the code, the QA audit, the annotation and the report drafting were done with AI assistance (Claude Code, Anthropic), as recorded in `skillgap_build/CHANGELOG.md` and declared in the Condition 3 form.
