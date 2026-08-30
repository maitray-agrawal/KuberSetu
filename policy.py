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
    ambiguous_results = matching_output.get("ambiguous_results", {})
    orphan_results = matching_output.get("orphan_results", [])
    duplicates = matching_output["duplicates"]
    seen_gateway_ids = matching_output["seen_gateway_ids"]
    exceptions_logged = matching_output["exceptions_logged"]

    auto_resolved = []
    human_review = []
    orphans = list(orphan_results)
    ambiguous_unresolved = list(ambiguous_results.values())

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

    # Route near-miss ambiguous records to human_review queue for reviewer visibility
    for amb in ambiguous_unresolved:
        human_review.append(amb)

    total_processed = len(gw_df)
    auto_cnt = len(auto_resolved)
    auto_val = sum(i['exposure'] for i in auto_resolved)
    human_cnt = len(human_review)
    human_val = sum(i['exposure'] for i in human_review)
    orphan_cnt = len(orphans)
    orphan_val = sum(i['exposure'] for i in orphans)
    dup_cnt = len(duplicates)
    dup_val = sum(i['exposure'] for i in duplicates)
    amb_cnt = len(ambiguous_unresolved)
    amb_val = sum(i['exposure'] for i in ambiguous_unresolved)

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
        "ambiguous_unresolved_count": amb_cnt,
        "ambiguous_unresolved_value": round(amb_val, 2),
        "automation_rate": round(auto_cnt / total_processed, 3) if total_processed > 0 else 0.0
    }

    return {
        "metrics": metrics,
        "auto_resolved": auto_resolved,
        "human_review": human_review,
        "duplicates": duplicates,
        "orphans": orphans,
        "ambiguous_unresolved": ambiguous_unresolved,
        "matched_results": matched_results,
        "exceptions_logged": exceptions_logged
    }
