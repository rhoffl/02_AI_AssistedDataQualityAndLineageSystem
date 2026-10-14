"""End-to-end validation of the governed data-quality correction process."""

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


CSV_WITH_DEFECTS = b"""customer_id,email,order_total,status
1001,ana@example.com,125.50,completed
1002,bob@example.com,89.00,completed
1003,,45.25,pending
1004,invalid-email,-30.00,completed
1005,dee@example.com,15000.00,completed
1006,eli@example.com,76.40,pending
1006,eli@example.com,76.40,pending
1007,fay@example.com,,cancelled
1008,gus@example.com,110.10,completed
1009,hal@example.com,99.99,unknown
1010,ivy@example.com,82.00,completed
1011,jay@example.com,91.50,pending
"""


def test_detection_human_approval_lineage_and_immutable_source():
    """
    Validates the complete business process:

    ingest -> detect -> explain -> propose -> block unauthorized approval ->
    approve -> execute deterministic correction -> preserve source -> audit.
    """
    with TestClient(app) as client:
        dataset_name = f"Customer Orders {uuid4()}"
        created = client.post(
            "/api/datasets",
            headers={"X-User": "test-owner"},
            json={"name": dataset_name, "description": "Governed process test"},
        )
        assert created.status_code == 200
        dataset_id = created.json()["id"]

        rules = [
            {"column_name": "customer_id", "rule_type": "unique", "parameters": {}, "severity": "high"},
            {"column_name": "email", "rule_type": "not_null", "parameters": {}, "severity": "high"},
            {"column_name": "order_total", "rule_type": "min", "parameters": {"value": 0}, "severity": "high"},
            {
                "column_name": "status",
                "rule_type": "allowed",
                "parameters": {"values": ["completed", "pending", "cancelled"]},
                "severity": "medium",
            },
        ]
        for rule in rules:
            response = client.post(f"/api/datasets/{dataset_id}/rules", json=rule)
            assert response.status_code == 200

        upload = client.post(
            f"/api/datasets/{dataset_id}/upload",
            headers={"X-User": "ingestion-service"},
            files={"file": ("customer_orders.csv", CSV_WITH_DEFECTS, "text/csv")},
        )
        assert upload.status_code == 200
        upload_result = upload.json()
        source_version = upload_result["version"]
        source_version_id = source_version["id"]
        assert upload_result["finding_count"] >= 5
        assert source_version["quality_score"] < 100
        assert source_version["status"] == "review_required"

        source_path = Path(source_version["storage_path"])
        source_bytes_before = source_path.read_bytes()
        source_checksum_before = hashlib.sha256(source_bytes_before).hexdigest()
        assert source_checksum_before == source_version["checksum"]

        details = client.get(f"/api/versions/{source_version_id}")
        assert details.status_code == 200
        findings = details.json()["findings"]
        detectors = {finding["detector"] for finding in findings}
        assert {"missing_values", "duplicates", "rule", "isolation_forest"} <= detectors
        assert all(finding["explanation"] for finding in findings)

        proposals = client.get("/api/proposals").json()
        duplicate_proposal = next(
            proposal
            for proposal in proposals
            if proposal["version_id"] == source_version_id
            and proposal["action"] == "drop_exact_duplicates"
        )
        proposal_id = duplicate_proposal["id"]
        assert duplicate_proposal["status"] == "pending_review"
        assert duplicate_proposal["confidence"] == 0.99

        unauthorized = client.post(
            f"/api/proposals/{proposal_id}/decision",
            headers={"X-User": "quality-agent", "X-Role": "submitter"},
            json={"decision": "approved", "comment": "Agent attempted approval"},
        )
        assert unauthorized.status_code == 403
        assert next(p for p in client.get("/api/proposals").json() if p["id"] == proposal_id)["status"] == "pending_review"

        approved = client.post(
            f"/api/proposals/{proposal_id}/decision",
            headers={"X-User": "data-steward", "X-Role": "steward"},
            json={"decision": "approved", "comment": "Duplicate evidence verified"},
        )
        assert approved.status_code == 200
        assert approved.json()["reviewed_by"] == "data-steward"

        executed = client.post(
            f"/api/proposals/{proposal_id}/execute",
            headers={"X-User": "data-steward", "X-Role": "steward"},
        )
        assert executed.status_code == 200
        child_version = executed.json()["new_version"]
        assert child_version["parent_version_id"] == source_version_id
        assert child_version["id"] != source_version_id
        assert child_version["row_count"] == source_version["row_count"] - 1

        # The approved action must create a child version, never rewrite the source.
        assert source_path.read_bytes() == source_bytes_before
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_checksum_before
        assert Path(child_version["storage_path"]).read_bytes() != source_bytes_before

        lineage = client.get("/api/lineage").json()
        assert any(
            edge["source"] == f"version:{source_version_id}"
            and edge["target"] == f"version:{child_version['id']}"
            and edge["edge_type"] == "correction"
            for edge in lineage
        )
        assert any(
            edge["version_id"] == child_version["id"]
            and edge["edge_type"] == "field_lineage"
            for edge in lineage
        )

        audit = client.get("/api/audit").json()
        actions = {event["action"] for event in audit}
        assert {
            "dataset.created",
            "dataset_version.analyzed",
            "proposal.approved",
            "proposal.executed",
        } <= actions

        notifications = client.get("/api/notifications").json()
        channels = {notice["channel"] for notice in notifications}
        assert {"slack", "email"} <= channels

