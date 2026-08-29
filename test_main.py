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
    """Verify that an exact ID match without fee/timing discrepancy produces root_causes == ['EXACT_MATCH'] exactly."""
    gt = get_ground_truth()
    exact_cid = next(cid for cid, t in gt.items() if t["scenario"] == "EXACT_MATCH")
    
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    assert exact_cid in matched_results, f"Expected {exact_cid} to be in matched_results"
    item = matched_results[exact_cid]
    
    assert item["confidence"] == 1.00
    assert item["root_causes"] == ["EXACT_MATCH"]
    assert item["rule_fired"] == "EXACT_MATCH"
    assert item["matched_pass"] == "Pass 1 (Exact ID Match)"
    assert item["status"] == "AUTO_RESOLVED"

def test_known_fuzzy_case_resolves_correctly():
    """Verify that a reference variance fuzzy match produces root_causes == ['REFERENCE_VARIANCE'] exactly."""
    gt = get_ground_truth()
    fuzzy_cid = next(cid for cid, t in gt.items() if t["scenario"] == "REFERENCE_VARIANCE")
    
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    assert fuzzy_cid in matched_results, f"Expected {fuzzy_cid} to be in matched_results"
    item = matched_results[fuzzy_cid]
    
    assert item["root_causes"] == ["REFERENCE_VARIANCE"]
    assert item["rule_fired"] == "REFERENCE_VARIANCE"
    assert item["matched_pass"] == "Pass 2 (Fuzzy Match)"
    assert item["confidence"] > 0.65 and item["confidence"] < 1.0

def test_orphan_flagged_as_unresolved_orphan():
    """Verify that orphan transactions produce root_causes == ['MISSING_SOURCES'] exactly."""
    gt = get_ground_truth()
    orphan_cid = next(cid for cid, t in gt.items() if "ORPHAN" in t["scenario"])
    
    res = run_reconciliation_logic(save_log=False)
    orphans = res["orphans"]
    
    orphan_item = next((o for o in orphans if o["gateway_id"] == orphan_cid), None)
    assert orphan_item is not None, f"Expected {orphan_cid} to be in orphans list"
    assert orphan_item["status"] == "UNRESOLVED_ORPHAN"
    assert orphan_item["confidence"] == 0.0
    assert orphan_item["root_causes"] == ["MISSING_SOURCES"]

def test_duplicate_detection_scenario():
    """Verify that duplicate transactions produce root_causes == ['DUPLICATE_DETECTED'] exactly."""
    gt = get_ground_truth()
    dup_cid = next(cid for cid, t in gt.items() if t["scenario"] == "DUPLICATE")
    
    res = run_reconciliation_logic(save_log=False)
    duplicates = res["duplicates"]
    
    dup_item = next((d for d in duplicates if d["gateway_id"] == dup_cid), None)
    assert dup_item is not None, f"Expected {dup_cid} to be in duplicates list"
    assert dup_item["root_causes"] == ["DUPLICATE_DETECTED"]
    assert dup_item["rule_fired"] == "DUPLICATE_DETECTED"
    assert dup_item["status"] == "DUPLICATE_DETECTED"
    assert dup_item["original_gateway_id"] == dup_cid

def test_programmatic_scenario_verification():
    """
    Iterates ground_truth.json programmatically, picks one transaction ID per scenario type
    (EXACT_MATCH, TIMING_DRIFT, FEE_VARIANCE, REFERENCE_VARIANCE, DUPLICATE, ORPHAN variants)
    at test-run time, and asserts the matcher's output root cause matches the scenario label.
    """
    gt = get_ground_truth()
    res = run_reconciliation_logic(save_log=False)
    
    matched = res["matched_results"]
    duplicates = {d["gateway_id"]: d for d in res["duplicates"]}
    orphans = {o["gateway_id"]: o for o in res["orphans"]}
    
    scenario_expected_causes = {
        "EXACT_MATCH": ["EXACT_MATCH"],
        "TIMING_DRIFT": ["TIMING_DRIFT"],
        "FEE_VARIANCE": ["FEE_VARIANCE"],
        "REFERENCE_VARIANCE": ["REFERENCE_VARIANCE"],
        "DUPLICATE": ["DUPLICATE_DETECTED"],
        "GATEWAY_ONLY_ORPHAN": ["MISSING_SOURCES"],
        "LEDGER_ONLY_ORPHAN": ["MISSING_SOURCES"],
        "BANK_ONLY_ORPHAN": ["MISSING_SOURCES"]
    }
    
    scenario_types = set(t["scenario"] for t in gt.values())
    
    for sc in sorted(scenario_types):
        sample_cid = next(cid for cid, t in gt.items() if t["scenario"] == sc)
        expected_causes = scenario_expected_causes[sc]
        
        if "ORPHAN" in sc:
            item = orphans.get(sample_cid)
            assert item is not None, f"Scenario {sc} ID {sample_cid} not found in orphans"
            assert item["root_causes"] == expected_causes, f"Scenario {sc} expected {expected_causes}, got {item['root_causes']}"
        elif sc == "DUPLICATE":
            item = duplicates.get(sample_cid)
            assert item is not None, f"Scenario {sc} ID {sample_cid} not found in duplicates"
            assert item["root_causes"] == expected_causes, f"Scenario {sc} expected {expected_causes}, got {item['root_causes']}"
        else:
            item = matched.get(sample_cid)
            assert item is not None, f"Scenario {sc} ID {sample_cid} not found in matched_results"
            assert item["root_causes"] == expected_causes, f"Scenario {sc} expected {expected_causes}, got {item['root_causes']}"

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
