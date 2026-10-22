# Annotation results (AI annotator: Claude, 2026-10-22)

All three sheets were filled by one AI annotator, not by people. No inter-annotator agreement exists.
Treat these as provisional until a team member spot-checks them.

## Generation (dev, Llama 3.2 3B): faithfulness by citation presence

| Prompt | Group | n | Faithful | Correct |
|---|---|---|---|---|
| v2 | cited | 22 | 18 | 20 |
| v2 | uncited (gate would withhold) | 5 | 4 | 5 |
| v3 | cited | 24 | 19 | 20 |
| v3 | uncited (gate would withhold) | 3 | 1 | 2 |

## Retrieval relevance labels (label_audit.csv)

70/72 sampled (question, relevant ad) pairs are correct (97.2%).
Both errors: Power BI tagged from a Microsoft customer-story URL (power-bi) inside the ad text.
In 25 rows the stored evidence sentence does not contain the skill, although the ad does.

## Skill extraction vs. blind labels (skill_labels.csv)

20 ads: precision 0.950, recall 0.884, F1 0.916

- BA_35973636: false positive [], missed ['Communication']
- BA_35974925: false positive [], missed ['Teamwork']
- BA_35975297: false positive ['Communication'], missed []
- BA_35980382: false positive ['Teamwork'], missed ['Attention to Detail']
- BA_35983821: false positive ['Teamwork'], missed []
- BA_35991552: false positive [], missed ['Teamwork']
- DA_35956778: false positive [], missed ['Presentation']
- DA_35967493: false positive [], missed ['Stakeholder Management']
- DA_36001488: false positive [], missed ['Data Cleaning']
- DS_35969591: false positive ['Teamwork'], missed []
- DS_35982327: false positive [], missed ['Data Visualisation']
- DS_35996335: false positive [], missed ['Data Cleaning', 'Presentation']
