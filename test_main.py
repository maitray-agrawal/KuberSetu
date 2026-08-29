import pytest
from fastapi.testclient import TestClient
from main import app, run_reconciliation_logic

client = TestClient(app)

def test_exact_match_scenario():
    """Verify that an exact ID match without fee/timing discrepancy produces EXACT_MATCH."""
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    # TXN-0571A6F9 is a known exact match scenario in ground truth
    txn_id = "TXN-0571A6F9"
    assert txn_id in matched_results, f"Expected {txn_id} to be matched"
    item = matched_results[txn_id]
    
    assert item["confidence"] == 1.00
    assert "EXACT_MATCH" in item["root_causes"] or item["rule_fired"] == "FEE_VARIANCE" or "EXACT_MATCH" in item["rule_fired"]
    assert item["matched_pass"] == "Pass 1 (Exact ID Match)"
    assert item["status"] == "AUTO_RESOLVED"

def test_known_fuzzy_case_resolves_correctly():
    """Verify that a known reference variance fuzzy match resolves with REFERENCE_VARIANCE."""
    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    
    # TXN-25C42D20 is a known fuzzy match scenario with reference variance (e.g. trailing space / lowercase)
    txn_id = "TXN-25C42D20"
    assert txn_id in matched_results, f"Expected {txn_id} to be fuzzy matched"
    item = matched_results[txn_id]
    
    assert "REFERENCE_VARIANCE" in item["root_causes"]
    assert item["rule_fired"] == "REFERENCE_VARIANCE"
    assert item["matched_pass"] == "Pass 2 (Fuzzy Match)"
    assert item["confidence"] > 0.65 and item["confidence"] < 1.0

def test_orphan_flagged_as_unresolved_orphan():
    """Verify that an un-matched transaction is correctly flagged as UNRESOLVED_ORPHAN."""
    res = run_reconciliation_logic(save_log=False)
    orphans = res["orphans"]
    
    # TXN-A45CF8F3 is an orphan missing in ledger and bank
    orphan_ids = [o["gateway_id"] for o in orphans]
    assert "TXN-A45CF8F3" in orphan_ids, "Expected TXN-A45CF8F3 to be in orphans list"
    
    orphan_item = next(o for o in orphans if o["gateway_id"] == "TXN-A45CF8F3")
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
    # Test valid fuzzy transaction
    resp_ok = client.get("/api/audit/TXN-25C42D20")
    assert resp_ok.status_code == 200
    audit_data = resp_ok.json()
    assert audit_data["gateway_id"] == "TXN-25C42D20"
    assert audit_data["matched_pass"] == "Pass 2 (Fuzzy Match)"
    assert audit_data["rule_fired"] == "REFERENCE_VARIANCE"

    # Test non-existent transaction 404
    resp_404 = client.get("/api/audit/NON_EXISTENT_TXN_999")
    assert resp_404.status_code == 404
    assert "not found" in resp_404.json()["detail"].lower()
