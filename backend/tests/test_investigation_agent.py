"""Unit tests for AEGIS investigation grounding and fallback behavior."""
import os

# Import-time SQLAlchemy engine configuration only; tests never connect to this DB.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.agent import _fallback, _refine_query, _should_refine, _validate


def sample_state():
    evidence = {
        "application_id": "app-1",
        "services": ["payment-api"],
        "timeline": [
            {"timestamp": "2026-11-07T10:00:00Z", "severity": "ERROR", "service": "payment-api", "message": "Gateway timeout"},
            {"timestamp": "2026-11-07T10:00:01Z", "severity": "INFO", "service": "order-api", "message": "Request failed"},
        ],
    }
    return {
        "evidence": evidence,
        "patterns": {},
        "retrieved": [{"title": "Payment Runbook", "chunk_index": 2, "content": "Check gateway health"}],
        "analysis": {
            "observed_error": "Gateway timeout",
            "affected_service": "payment-api",
            "probable_root_cause": "Gateway unavailable",
            "supporting_evidence": ["[event:0] Gateway timeout", "[source:Payment Runbook#2] Check health", "[event:99] fabricated"],
            "hypotheses": [],
            "remediation_steps": [],
            "stack_trace_locations": [],
            "confidence": 0.9,
            "uncertainty_notes": "",
            "missing_evidence": ["gateway health telemetry"],
        },
    }


def test_validate_keeps_only_real_citations_and_caps_confidence():
    state = sample_state()
    update = _validate(state)
    result = update["analysis"]
    assert len(result["supporting_evidence"]) == 2
    assert result["confidence"] <= 0.35
    assert "invalid citations" in result["uncertainty_notes"]


def test_validate_replaces_unobserved_service():
    state = sample_state()
    state["analysis"]["affected_service"] = "made-up-service"
    result = _validate(state)["analysis"]
    assert result["affected_service"] == "payment-api"


def test_no_valid_citations_prevents_definitive_root_cause():
    state = sample_state()
    state["analysis"]["supporting_evidence"] = ["Gateway definitely failed"]
    result = _validate(state)["analysis"]
    assert result["confidence"] <= 0.25
    assert result["probable_root_cause"].startswith("Insufficient validated evidence")


def test_refinement_is_bounded_to_one_round():
    state = sample_state()
    state["analysis"]["confidence"] = 0.3
    assert _should_refine(state) == "refine"
    state["retrieval_round"] = 1
    assert _should_refine(state) == "finish"
    query = _refine_query(state)["retrieval_query"]
    assert "gateway health telemetry" in query


def test_deterministic_fallback_is_uncertain_and_actionable():
    state = sample_state()
    result = _fallback(state["evidence"], {}, [])
    assert result["confidence"] <= 0.2
    assert result["probable_root_cause"].startswith("Insufficient evidence")
    assert result["remediation_steps"]
    assert "[event:0]" in result["supporting_evidence"][0]
