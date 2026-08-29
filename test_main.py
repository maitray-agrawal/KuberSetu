import pytest
import json
import os
from fastapi.testclient import TestClient
from main import app, run_reconciliation_logic

client = TestClient(app)

DATA_DIR = "data"

def get_ground_truth():
    with open(f"{DATA_DIR}/ground_truth.json", "r") as f:
        return json.load(f)

def test_exact_match_scenario():
    """Verify that an exact ID match without fee/timing discrepancy produces EXACT_MATCH."""
    gt = get_ground_truth()
    exact_cid = next(cid for cid, t in gt.items() if t["scenario"] == "EXACT_MATCH")
    
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    assert exact_cid in matched_results, f"Expected {exact_cid} to be matched"
    item = matched_results[exact_cid]
    
    assert item["confidence"] == 1.00
    assert "EXACT_MATCH" in item["root_causes"]
    assert item["matched_pass"] == "Pass 1 (Exact ID Match)"
    assert item["status"] == "AUTO_RESOLVED"

def test_known_fuzzy_case_resolves_correctly():
    """Verify that a known reference variance fuzzy match resolves with REFERENCE_VARIANCE."""
    gt = get_ground_truth()
    fuzzy_cid = next(cid for cid, t in gt.items() if t["scenario"] == "REFERENCE_VARIANCE")
    
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    assert fuzzy_cid in matched_results, f"Expected {fuzzy_cid} to be fuzzy matched"
    item = matched_results[fuzzy_cid]
    
    assert "REFERENCE_VARIANCE" in item["root_causes"]
    assert item["rule_fired"] == "REFERENCE_VARIANCE"
    assert item["matched_pass"] == "Pass 2 (Fuzzy Match)"
    assert item["confidence"] > 0.65 and item["confidence"] < 1.0

def test_orphan_flagged_as_unresolved_orphan():
    """Verify that orphan transactions are correctly flagged as UNRESOLVED_ORPHAN."""
    gt = get_ground_truth()
    orphan_cid = next(cid for cid, t in gt.items() if "ORPHAN" in t["scenario"])
    
    res = run_reconciliation_logic(save_log=False)
    orphans = res["orphans"]
    
    orphan_ids = [o["gateway_id"] for o in orphans]
    assert orphan_cid in orphan_ids, f"Expected {orphan_cid} to be in orphans list"
    
    orphan_item = next(o for o in orphans if o["gateway_id"] == orphan_cid)
    assert orphan_item["status"] == "UNRESOLVED_ORPHAN"
    assert orphan_item["confidence"] == 0.0
    assert orphan_item["root_causes"] == ["MISSING_SOURCES"]

def test_health_check_endpoint():
    """Test GET /api/health deployment monitoring endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data

def test_audit_endpoint_decision_trail():
    """Test GET /api/audit/{gateway_id} for valid transaction and 404 error handling."""
    gt = get_ground_truth()
    fuzzy_cid = next(cid for cid, t in gt.items() if t["scenario"] == "REFERENCE_VARIANCE")

    resp_ok = client.get(f"/api/audit/{fuzzy_cid}")
    assert resp_ok.status_code == 200
    audit_data = resp_ok.json()
    assert audit_data["gateway_id"] == fuzzy_cid
    assert audit_data["matched_pass"] == "Pass 2 (Fuzzy Match)"
    assert audit_data["rule_fired"] == "REFERENCE_VARIANCE"

    # Test non-existent transaction 404
    resp_404 = client.get("/api/audit/NON_EXISTENT_TXN_999")
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["detail"].lower()

def test_duplicate_detection_scenario():
    """Verify that duplicate gateway rows are detected, isolated into duplicates array, and updated in metrics."""
    res = run_reconciliation_logic(save_log=False)
    duplicates = res["duplicates"]
    metrics = res["metrics"]
    
    assert len(duplicates) > 0, "Expected duplicates to be detected"
    assert metrics["duplicate_count"] == len(duplicates)
    assert metrics["duplicate_value"] > 0
    
    dup_item = duplicates[0]
    assert dup_item["root_causes"] == ["DUPLICATE_DETECTED"]
    assert dup_item["rule_fired"] == "DUPLICATE_DETECTED"
    assert dup_item["status"] == "DUPLICATE_DETECTED"
    assert "original_gateway_id" in dup_item

