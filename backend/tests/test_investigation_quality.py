"""Regression tests for evidence-grounded incident attribution and reports."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.investigation import (
    analyze_patterns_node,
    validate_evidence_node,
    _ground_final_report,
)


def _event(event_id, timestamp, severity, service, message, correlation_id="req-1"):
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "severity": severity,
        "service": service,
        "message": message,
        "correlation_id": correlation_id,
    }


def test_correlated_multiservice_failure_identifies_only_later_error_services():
    events = [
        _event(1, "2026-11-07T10:00:00+00:00", "INFO", "order-service", "request received"),
        _event(2, "2026-11-07T10:00:01+00:00", "INFO", "payment-service", "payment started"),
        _event(3, "2026-11-07T10:00:05+00:00", "ERROR", "payment-service", "gateway timeout"),
        _event(4, "2026-11-07T10:00:06+00:00", "ERROR", "order-service", "payment failed"),
        _event(5, "2026-11-07T10:00:07+00:00", "ERROR", "api-gateway", "HTTP 500"),
    ]
    state = {
        "events": events,
        "services": {name: {} for name in ("order-service", "payment-service", "api-gateway")},
        "correlation_chains": {"req-1": events},
        "investigation_log": [],
    }
    patterns = analyze_patterns_node(state)["patterns"]
    assert patterns["first_failure_service"] == "payment-service"
    assert patterns["downstream_services"] == ["order-service", "api-gateway"]
    assert patterns["is_cascading"] is True


def test_single_gateway_503_is_not_mislabelled_as_downstream_or_root_cause():
    event = _event(44, "2026-11-07T15:15:29.135263+00:00", "ERROR", "api-gateway", "HTTP 503 returned", None)
    state = {
        "events": [event],
        "patterns": {
            "first_failure_service": "api-gateway",
            "downstream_services": [],
        },
        "confidence_factors": {},
        "sufficient_evidence": False,
    }
    report = _ground_final_report(
        {
            "affected_service": "unknown",
            "downstream_services": ["api-gateway"],
            "timeline_summary": [],
            "probable_root_cause": "Downstream service exhaustion caused the HTTP 503.",
            "supporting_evidence": ["invented evidence"],
            "confidence": 0.9,
        },
        state,
    )
    assert report["affected_service"] == "api-gateway"
    assert report["downstream_services"] == []
    assert len(report["timeline_summary"]) == 1
    assert report["timeline_summary"][0]["event_id"] == 44
    assert report["probable_root_cause"].startswith("Insufficient evidence")
    assert report["confidence"] <= 0.30
    assert report["supporting_evidence"][0]["event_id"] == 44


def test_duplicate_citations_do_not_count_as_multiple_independent_events():
    events = [
        _event(1, "2026-11-07T10:00:00+00:00", "ERROR", "api", "503", None),
        _event(2, "2026-11-07T10:00:01+00:00", "INFO", "api", "request", None),
    ]
    state = {
        "events": events,
        "hypotheses": [
            {"rank": 1, "hypothesis": "API unavailable", "supporting_event_ids": [1, 1, 1]},
        ],
        "stack_traces": [],
        "correlation_chains": {},
        "knowledge_context": [],
        "historical_context": [{"title": "old incident"}],
        "investigation_log": [],
    }
    result = validate_evidence_node(state)
    assert result["confidence_factors"]["events_cited"] == 1
    assert result["sufficient_evidence"] is False


def test_sufficient_logs_report_observed_failure_without_asserting_unverified_external_outage():
    events = [
        _event(51, "2026-11-07T10:01:03+00:00", "INFO", "payment-service", "Gateway request initiated"),
        _event(52, "2026-11-07T10:01:08+00:00", "ERROR", "payment-service", "Connection timeout to payment gateway"),
        _event(53, "2026-11-07T10:01:09+00:00", "ERROR", "order-service", "Payment failed"),
    ]
    state = {
        "events": events,
        "patterns": {
            "first_failure_service": "payment-service",
            "downstream_services": ["order-service"],
        },
        "confidence_factors": {},
        "sufficient_evidence": True,
        "historical_context": [{
            "title": "Previous payment timeout",
            "service": "payment-service",
            "status": "resolved",
            "match_reason": "same primary service in the same application",
            "root_cause": "Provider maintenance window",
        }],
    }
    report = _ground_final_report({
        "probable_root_cause": "External payment gateway outage and throttling caused the failure.",
        "confidence": 0.95,
        "alternative_hypotheses": [],
    }, state)
    assert report["probable_root_cause"].startswith("Confirmed observation:")
    assert "proven upstream cause" in report["probable_root_cause"]
    assert report["alternative_hypotheses"] == []
    assert report["historical_context_summary"][0]["is_direct_evidence"] is False
    assert report["historical_context_summary"][0]["match_reason"] == "same primary service in the same application"


def test_incident_summary_describes_correlated_sequence_without_claiming_proven_causation():
    events = [
        _event(61, "2026-11-07T10:00:00+00:00", "ERROR", "payment", "Gateway timeout"),
        _event(62, "2026-11-07T10:00:01+00:00", "ERROR", "orders", "Payment failed"),
    ]
    state = {
        "events": events,
        "patterns": {"first_failure_service": "payment", "downstream_services": ["orders"]},
        "confidence_factors": {},
        "sufficient_evidence": True,
    }
    report = _ground_final_report({"incident_summary": "A cascade definitely caused the failure."}, state)
    assert "does not by itself prove causation" in report["incident_summary"]
    assert "first observed" not in report["incident_summary"].lower() or "earliest recorded error" in report["incident_summary"].lower()
