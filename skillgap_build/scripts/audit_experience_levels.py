from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from skillgap.core import load_documents, EARLY_CAREER

DOCS = ROOT / 'data' / 'documents'
OUT = ROOT / 'results' / 'experience_level_audit.json'

docs = load_documents(DOCS)
level_counts = Counter(d['experience_level'] for d in docs)
role_counts = defaultdict(Counter)
for d in docs:
    role_counts[d['role']][d['experience_level']] += 1

candidates = [
    {
        'doc_id': d['doc_id'],
        'role': d['role'],
        'title': d['title'],
        'experience_level': d['experience_level'],
        'source_url': d['source_url'],
    }
    for d in docs if d['experience_level'] in EARLY_CAREER
]

result = {
    'document_count': len(docs),
    'level_counts': dict(level_counts),
    'role_by_level': {role: dict(counts) for role, counts in role_counts.items()},
    'early_career_candidate_count': len(candidates),
    'early_career_candidates': candidates,
    'interpretation': (
        'Graduate/entry wording is a title signal, not proof of zero experience. '
        'Experience not stated is unknown and excluded from the strict early-career subset. '
        'Numerical ranges are classified using their upper bound.'
    ),
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
