from app.rag_text import chunk_text
from app.evaluation import citation_precision, root_cause_match, confidence_calibration_bucket


def test_chunk_text_empty_and_short_content():
    assert chunk_text("  \n ") == []
    assert chunk_text("hello world") == ["hello world"]


def test_chunk_text_respects_overlap_and_reconstructs_content():
    value = "A" * 1400
    chunks = chunk_text(value, chunk_size=500, overlap=100)
    assert len(chunks) >= 3
    assert all(chunks)
    assert chunks[0][-100:] == chunks[1][:100]


def test_citation_precision_rejects_missing_or_fabricated_refs():
    report = {"supporting_evidence": ["[event:0] timeout", "[event:99] invented", "uncited claim"]}
    assert citation_precision(report, {"event:0", "event:1"}) == 1 / 3


def test_root_cause_match_is_transparent_keyword_coverage():
    assert root_cause_match({"probable_root_cause": "Database connection pool exhausted"}, ["database", "pool"]) == 1.0
    assert root_cause_match({"probable_root_cause": "Database unavailable"}, ["database", "pool"]) == 0.5


def test_confidence_bucket_clamps_values():
    assert confidence_calibration_bucket({"confidence": 0.2}) == "low"
    assert confidence_calibration_bucket({"confidence": 0.5}) == "medium"
    assert confidence_calibration_bucket({"confidence": 1.5}) == "high"
    assert confidence_calibration_bucket({"confidence": "invalid"}) == "low"
