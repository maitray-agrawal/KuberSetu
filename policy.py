import os
import pandas as pd

RISK_TOLERANCE_INR = float(os.getenv("RISK_TOLERANCE_INR", "500.00"))

def get_tiered_risk_tolerance(exposure: float, base_tolerance: float = RISK_TOLERANCE_INR) -> float:
    """
    Scales risk tolerance by exposure tiers:
    - High Exposure (> ₹50,000): Tightened risk tolerance (e.g., max ₹250.00)
    - Standard Exposure (<= ₹50,000): Base risk tolerance (default ₹500.00)
    """
    if exposure > 50000.0:
        return min(base_tolerance, 250.00)
    return base_tolerance

def apply_risk_policy(gw_df: pd.DataFrame, leg_df: pd.DataFrame, bank_df: pd.DataFrame, matching_output: dict, risk_tolerance_inr: float = RISK_TOLERANCE_INR):
    """
    Applies the risk policy engine to matched and unmatched records.
    Calculates expected_loss = (1 - confidence) * exposure.
    Routes transactions to AUTO_RESOLVED or HUMAN_REVIEW based on exposure-tiered tolerance.
    Identifies orphan transactions and computes summary metrics.
    """
    matched_results = matching_output["matched_results"]
    duplicates = matching_output["duplicates"]
    seen_gateway_ids = matching_output["seen_gateway_ids"]
    exceptions_logged = matching_output["exceptions_logged"]

    auto_resolved = []
    human_review = []
    orphans = []

    for gw_id, res in matched_results.items():
        prob_wrong = 1.0 - res['confidence']
        expected_loss = prob_wrong * res['exposure']
        res['expected_loss'] = round(expected_loss, 2)

        tiered_tolerance = get_tiered_risk_tolerance(res['exposure'], base_tolerance=risk_tolerance_inr)

        if expected_loss <= tiered_tolerance and res['confidence'] >= 0.70:
            res['status'] = "AUTO_RESOLVED"
            auto_resolved.append(res)
        else:
            res['status'] = "HUMAN_REVIEW"
            human_review.append(res)

    # Orphan classification (Gateway-only, Ledger-only, Bank-only)
    matched_leg_ids = {m['ledger_id'] for m in matched_results.values()}
    matched_bank_ids = {m['bank_id'] for m in matched_results.values()}

    for _, gw in gw_df.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        if gw_id not in matched_results and gw_id not in seen_gateway_ids:
            orphans.append({
                "gateway_id": gw_id,
                "ledger_id": None,
                "bank_id": None,
                "matched_pass": "Unmatched (Orphan)",
                "root_causes": ["MISSING_SOURCES"],
                "rule_fired": "GATEWAY_ONLY_ORPHAN",
                "confidence": 0.00,
                "exposure": float(gw['amount']),
                "expected_loss": float(gw['amount']),
                "status": "UNRESOLVED_ORPHAN"
            })
            exceptions_logged["MISSING_SOURCES"] = exceptions_logged.get("MISSING_SOURCES", 0) + 1

    for _, leg in leg_df.iterrows():
        leg_id = str(leg['entry_id']).strip()
        if leg_id not in matched_leg_ids and leg_id not in seen_gateway_ids:
            orphans.append({
                "gateway_id": f"LEDGER-{leg_id}",
                "ledger_id": leg_id,
                "bank_id": None,
                "matched_pass": "Unmatched (Orphan)",
                "root_causes": ["MISSING_SOURCES"],
                "rule_fired": "LEDGER_ONLY_ORPHAN",
                "confidence": 0.00,
                "exposure": float(leg['gross_value']),
                "expected_loss": float(leg['gross_value']),
                "status": "UNRESOLVED_ORPHAN"
            })
            exceptions_logged["MISSING_SOURCES"] = exceptions_logged.get("MISSING_SOURCES", 0) + 1

    for _, bank in bank_df.iterrows():
        bank_id = str(bank['settlement_ref']).strip()
        if bank_id not in matched_bank_ids and bank_id not in seen_gateway_ids:
            orphans.append({
                "gateway_id": f"BANK-{bank_id}",
                "ledger_id": None,
                "bank_id": bank_id,
                "matched_pass": "Unmatched (Orphan)",
                "root_causes": ["MISSING_SOURCES"],
                "rule_fired": "BANK_ONLY_ORPHAN",
                "confidence": 0.00,
                "exposure": float(bank['credited_amount']),
                "expected_loss": float(bank['credited_amount']),
                "status": "UNRESOLVED_ORPHAN"
            })
            exceptions_logged["MISSING_SOURCES"] = exceptions_logged.get("MISSING_SOURCES", 0) + 1

    total_processed = len(gw_df)
    auto_cnt = len(auto_resolved)
    auto_val = sum(i['exposure'] for i in auto_resolved)
    human_cnt = len(human_review)
    human_val = sum(i['exposure'] for i in human_review)
    orphan_cnt = len(orphans)
    orphan_val = sum(i['exposure'] for i in orphans)
    dup_cnt = len(duplicates)
    dup_val = sum(i['exposure'] for i in duplicates)

    metrics = {
        "total_processed": total_processed,
        "auto_resolved_count": auto_cnt,
        "auto_resolved_value": round(auto_val, 2),
        "human_review_count": human_cnt,
        "human_review_value": round(human_val, 2),
        "orphan_count": orphan_cnt,
        "orphan_value": round(orphan_val, 2),
        "duplicate_count": dup_cnt,
        "duplicate_value": round(dup_val, 2),
        "automation_rate": round(auto_cnt / total_processed, 3) if total_processed > 0 else 0.0
    }

    return {
        "metrics": metrics,
        "auto_resolved": auto_resolved,
        "human_review": human_review,
        "duplicates": duplicates,
        "orphans": orphans,
        "matched_results": matched_results,
        "exceptions_logged": exceptions_logged
    }
