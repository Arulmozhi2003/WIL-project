import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from skillgap.core import BM25, DenseRetriever, load_documents

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bm25_k_boundaries():
    docs = [
        {"doc_id": "a", "title": "SQL analyst", "role": "analyst", "text": "SQL", "skills": []},
        {"doc_id": "b", "title": "SQL analyst", "role": "analyst", "text": "SQL", "skills": []},
    ]
    retriever = BM25(docs)

    assert len(retriever.search("SQL", k=1)) == 1
    assert len(retriever.search("SQL", k=0)) == 0
    assert len(retriever.search("SQL", k=10)) == 2


@pytest.mark.xfail(strict=True, reason="QA-01: negative k silently applies Python negative slicing instead of rejecting the invalid limit")
def test_bm25_negative_k_is_rejected():
    docs = [
        {"doc_id": "a", "title": "SQL analyst", "role": "analyst", "text": "SQL", "skills": []},
        {"doc_id": "b", "title": "SQL analyst", "role": "analyst", "text": "SQL", "skills": []},
    ]
    with pytest.raises(ValueError, match="k"):
        BM25(docs).search("SQL", k=-1)


def test_dense_retrieval_uses_encoder_and_role_scope():
    docs = [
        {"doc_id": "a", "title": "SQL analyst", "role": "analyst", "text": "SQL", "skills": []},
        {"doc_id": "b", "title": "Python scientist", "role": "scientist", "text": "Python", "skills": []},
    ]

    class Encoder:
        def encode(self, texts, normalize_embeddings, convert_to_numpy):
            vectors = []
            for text in texts:
                vectors.append([1.0, 0.0] if "SQL" in text else [0.0, 1.0])
            return np.asarray(vectors, dtype="float32")

    retriever = DenseRetriever(docs, encoder=Encoder())

    assert [hit.doc["doc_id"] for hit in retriever.search("SQL", role="analyst")] == ["a"]
    assert retriever.search("SQL", role="missing") == []


def test_load_documents_empty_directory_is_valid(tmp_path):
    assert load_documents(tmp_path) == []


def test_ingest_cli_cleans_deduplicates_and_keeps_output_isolated(tmp_path):
    raw_path = tmp_path / "ads.csv"
    output_dir = tmp_path / "documents"
    provenance_dir = tmp_path / "provenance"
    long_text = "<p>SQL &amp; Excel reporting requirements.</p> " + ("Relevant job description. " * 12)
    rows = [
        {"title": "Graduate Analyst", "text": long_text, "source_url": "https://example.test/1", "collected_date": "2026-01-01"},
        {"title": "Graduate Analyst", "text": long_text, "source_url": "https://example.test/2", "collected_date": "2026-01-01"},
        {"title": "Short", "text": "Too short", "source_url": "https://example.test/3", "collected_date": "2026-01-01"},
        {"title": "Missing URL", "text": long_text, "source_url": "", "collected_date": "2026-01-01"},
    ]
    with raw_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["title", "text", "source_url", "collected_date"])
        writer.writeheader()
        writer.writerows(rows)

    result = subprocess.run(
        [
            sys.executable,
            "ingest.py",
            str(raw_path),
            "--out",
            str(output_dir),
            "--provenance",
            str(provenance_dir),
            "--role",
            "Graduate Data Analyst",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    documents = sorted(output_dir.glob("*.json"))
    assert len(documents) == 1
    imported = json.loads(documents[0].read_text(encoding="utf-8"))
    assert imported["skills"] == ["Excel", "SQL"]
    assert "<p>" not in imported["text"]
    assert "& Excel" in imported["text"]
    assert "Imported 1 documents" in result.stderr
    assert "'duplicate': 1" in result.stderr
    assert "'too_short': 1" in result.stderr
    assert "'missing_field': 1" in result.stderr
    manifest_rows = list(csv.DictReader((provenance_dir / "MANIFEST.csv").open(encoding="utf-8")))
    assert len(manifest_rows) == 1
    assert manifest_rows[0]["doc_id"] == imported["doc_id"]
