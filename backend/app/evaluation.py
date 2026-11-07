"""
AEGIS Evaluation Framework — Measure investigation quality.

Provides tools to:
  1. Create known-answer test cases from real or synthetic incidents.
  2. Run the investigation pipeline against test cases.
  3. Score the output against expected root causes and services.
  4. Track quality metrics over time.

Scoring dimensions:
  - root_cause_accuracy:  semantic overlap with expected root cause
  - service_identification: did it find all expected services?
  - evidence_coverage:    what fraction of events were cited?
  - no_fabrication:       zero fabricated event references?
  - report_completeness:  are all 11 report sections populated?
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------

def create_evaluation_case(
    db: Session,
    name: str,
    description: str,
    events_json: list[dict],
    expected_root_cause: str,
    expected_services: list[str],
    expected_severity: str,
) -> EvaluationCase:
    """Create a new evaluation test case."""
    case = EvaluationCase(
        name=name,
        description=description,
        events_json=events_json,
        expected_root_cause=expected_root_cause,
        expected_services=expected_services,
        expected_severity=expected_severity,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_evaluation_cases(db: Session) -> list[EvaluationCase]:
    return list(
        db.scalars(
            select(EvaluationCase)
            .order_by(EvaluationCase.created_at.desc())
        ).all()
    )


def get_evaluation_case(db: Session, case_id: int) -> EvaluationCase | None:
    return db.get(EvaluationCase, case_id)


def delete_evaluation_case(db: Session, case: EvaluationCase) -> None:
    db.delete(case)
    db.commit()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_investigation(
    report_data: dict[str, Any],
    expected: EvaluationCase,
    events_analyzed: int,
    events_cited: int,
) -> dict[str, Any]:
    """Score an investigation report against expected answers.

    Returns a dict with individual dimension scores and an aggregate score.
    """
    scores: dict[str, float] = {}

    # 1. Root cause accuracy (keyword overlap)
    scores["root_cause_accuracy"] = _text_similarity(
        report_data.get("probable_root_cause", ""),
        expected.expected_root_cause,
    )

    # 2. Service identification
    expected_svcs = set(
        s.lower() for s in expected.expected_services
    )
    found_svcs = set()

    primary = report_data.get("affected_service", "")
    if primary:
        found_svcs.add(primary.lower())

    for svc in report_data.get("downstream_services", []) or []:
        found_svcs.add(svc.lower())

    if expected_svcs:
        scores["service_identification"] = (
            len(found_svcs & expected_svcs) / len(expected_svcs)
        )
    else:
        scores["service_identification"] = 1.0

    # 3. Evidence coverage
    if events_analyzed > 0:
        scores["evidence_coverage"] = min(
            events_cited / events_analyzed, 1.0,
        )
    else:
        scores["evidence_coverage"] = 0.0

    # 4. No fabrication
    evidence_mapping = report_data.get("evidence_mapping", {})
    valid_ids = set(
        e.get("event_id")
        for e in report_data.get("timeline_summary", [])
        if e.get("event_id")
    )

    fabricated = 0
    total_cited = 0
    for claim, ids in (evidence_mapping or {}).items():
        for eid in ids:
            total_cited += 1
            if eid not in valid_ids:
                fabricated += 1

    scores["no_fabrication"] = (
        1.0 if fabricated == 0
        else max(0.0, 1.0 - fabricated / max(total_cited, 1))
    )

    # 5. Report completeness
    required_fields = [
        "incident_summary",
        "observed_error",
        "affected_service",
        "downstream_services",
        "timeline_summary",
        "probable_root_cause",
        "alternative_hypotheses",
        "supporting_evidence",
        "remediation_steps",
        "verification_steps",
        "confidence",
    ]

    populated = sum(
        1 for f in required_fields
        if report_data.get(f) not in (None, "", [], {})
    )

    scores["report_completeness"] = populated / len(required_fields)

    # Aggregate
    weights = {
        "root_cause_accuracy": 0.30,
        "service_identification": 0.20,
        "evidence_coverage": 0.20,
        "no_fabrication": 0.15,
        "report_completeness": 0.15,
    }

    aggregate = sum(
        scores[k] * weights[k] for k in weights
    )

    return {
        "scores": scores,
        "aggregate_score": round(aggregate, 3),
        "weights": weights,
        "details": {
            "expected_services": list(expected_svcs),
            "found_services": list(found_svcs),
            "events_analyzed": events_analyzed,
            "events_cited": events_cited,
            "fabricated_citations": fabricated,
            "fields_populated": populated,
            "fields_required": len(required_fields),
        },
    }


def _text_similarity(text_a: str, text_b: str) -> float:
    """Simple word-overlap similarity (Jaccard index).

    For production, replace with embedding-based semantic similarity.
    """
    if not text_a or not text_b:
        return 0.0

    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())

    intersection = words_a & words_b
    union = words_a | words_b

    if not union:
        return 0.0

    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

def run_evaluation(
    db: Session,
    case: EvaluationCase,
    report: Any,
) -> dict[str, Any]:
    """Run evaluation for a completed investigation against a test case.

    ``report`` should be an InvestigationReport ORM object.
    """
    report_data = {
        "incident_summary": report.incident_summary,
        "observed_error": report.observed_error,
        "affected_service": report.affected_service,
        "downstream_services": report.downstream_services,
        "timeline_summary": report.timeline_summary,
        "probable_root_cause": report.probable_root_cause,
        "alternative_hypotheses": report.alternative_hypotheses,
        "supporting_evidence": report.supporting_evidence,
        "evidence_mapping": report.evidence_mapping,
        "remediation_steps": report.remediation_steps,
        "verification_steps": report.verification_steps,
        "confidence": report.confidence,
    }

    result = score_investigation(
        report_data=report_data,
        expected=case,
        events_analyzed=report.events_analyzed,
        events_cited=report.events_cited,
    )

    # Persist result on the case
    case.last_score = result["aggregate_score"]
    case.last_result = result
    case.last_run_at = datetime.now(timezone.utc)
    db.commit()

    return result


# Lightweight, deterministic metrics used by offline regression tests.

def citation_precision(report: dict[str, Any], valid_refs: set[str]) -> float:
    """Fraction of evidence statements carrying at least one valid event citation."""
    import re
    items = [str(item) for item in (report.get("supporting_evidence", []) or [])]
    if not items:
        return 0.0
    valid = {str(ref).removeprefix("event:") for ref in valid_refs}
    grounded = 0
    for item in items:
        refs = re.findall(r"\[event:(\d+)\]", item)
        if refs and any(ref in valid for ref in refs):
            grounded += 1
    return grounded / len(items)


def root_cause_match(report: dict[str, Any], expected_terms: list[str]) -> float:
    """Transparent expected-term recall for a generated root-cause statement."""
    if not expected_terms:
        return 1.0
    actual = str(report.get("probable_root_cause", "")).lower()
    terms = [str(term).lower() for term in expected_terms]
    return sum(term in actual for term in terms) / len(terms)


def confidence_calibration_bucket(report: dict[str, Any]) -> str:
    """Coarse confidence bucket; malformed values are treated conservatively."""
    try:
        value = float(report.get("confidence", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    value = min(1.0, max(0.0, value))
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "medium"
    return "high"

