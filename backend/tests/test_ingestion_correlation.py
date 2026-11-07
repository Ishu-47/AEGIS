"""Regression tests for correlation identifiers in plain-text logs."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.main import parse_logs


def test_order_id_is_extracted_from_bracket_service_logs_across_services():
    raw = """2026-11-07 10:01:01 INFO [order-service] Order request received order_id=ORD-101
2026-11-07 10:01:02 INFO [order-service] Calling payment service order_id=ORD-101
2026-11-07 10:01:03 INFO [payment-service] Payment gateway request initiated order_id=ORD-101
2026-11-07 10:01:08 ERROR [payment-service] Connection timeout while connecting to payment gateway order_id=ORD-101
2026-11-07 10:01:08 ERROR [order-service] Payment processing failed order_id=ORD-101
2026-11-07 10:01:09 ERROR [api-gateway] Returning HTTP 500 order_id=ORD-101"""
    events = parse_logs(raw)
    assert len(events) == 6
    assert {event["correlation_id"] for event in events} == {"ORD-101"}
    assert {event["service"] for event in events} == {
        "order-service", "payment-service", "api-gateway"
    }
    assert [event["severity"] for event in events].count("ERROR") == 3
