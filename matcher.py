import pandas as pd
from ml_matcher import get_matcher_model, extract_pair_features

def run_matching_pipeline(gw_df: pd.DataFrame, leg_df: pd.DataFrame, bank_df: pd.DataFrame):
    """
    Executes Pass 1 (Exact ID match & duplicate detection) and Pass 2 (ML-based fuzzy match with candidate blocking).
    """
    matched_results = {}
    duplicates = []
    seen_gateway_ids = set()
    exceptions_logged = {
        "TIMING_DRIFT": 0,
        "FEE_VARIANCE": 0,
        "REFERENCE_VARIANCE": 0,
        "DUPLICATE_DETECTED": 0
    }

    # PASS 1: Exact ID Matches & Duplicate Handling
    for _, gw in gw_df.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        leg_matches = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
        bank_matches = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]

        if not leg_matches.empty and not bank_matches.empty:
            leg = leg_matches.iloc[0]
            bank = bank_matches.iloc[0]

            if gw_id in seen_gateway_ids:
                dup_entry = {
                    "gateway_id": gw_id,
                    "original_gateway_id": gw_id,
                    "ledger_id": str(leg['entry_id']),
                    "bank_id": str(bank['settlement_ref']),
                    "matched_pass": "Pass 1 (Duplicate Detected)",
                    "root_causes": ["DUPLICATE_DETECTED"],
                    "rule_fired": "DUPLICATE_DETECTED",
                    "confidence": 1.00,
                    "exposure": float(gw['amount']),
                    "expected_loss": 0.0,
                    "status": "DUPLICATE_DETECTED"
                }
                duplicates.append(dup_entry)
                exceptions_logged["DUPLICATE_DETECTED"] += 1
                continue

            seen_gateway_ids.add(gw_id)
            causes = []
            
            if abs(gw['amount'] - bank['credited_amount']) > 0.01:
                causes.append("FEE_VARIANCE")
                exceptions_logged["FEE_VARIANCE"] += 1
            if (bank['dt'].normalize() - gw['dt'].normalize()).days > 0:
                causes.append("TIMING_DRIFT")
                exceptions_logged["TIMING_DRIFT"] += 1
                
            if not causes:
                causes.append("EXACT_MATCH")
                
            rule_fired = causes[0] if len(causes) == 1 else ", ".join(causes)
            matched_results[gw_id] = {
                "gateway_id": gw_id,
                "ledger_id": str(leg['entry_id']),
                "bank_id": str(bank['settlement_ref']),
                "matched_pass": "Pass 1 (Exact ID Match)",
                "root_causes": causes,
                "rule_fired": rule_fired,
                "confidence": 1.00,
                "exposure": float(gw['amount'])
            }

    # PASS 2: Fuzzy Matches using ML Model with Candidate Blocking
    matcher_model = get_matcher_model()
    matched_and_dup_ids = set(matched_results.keys()).union(seen_gateway_ids)
    gw_unmatched = gw_df[~gw_df['gateway_id'].isin(matched_and_dup_ids)]
    leg_unmatched = leg_df[~leg_df['entry_id'].isin([m['ledger_id'] for m in matched_results.values()])]
    bank_unmatched = bank_df[~bank_df['settlement_ref'].isin([m['bank_id'] for m in matched_results.values()])]

    unblocked_comparisons = len(gw_unmatched) * len(leg_unmatched) * len(bank_unmatched)
    blocked_comparisons = 0

    ambiguous_results = {}
    orphan_results = []

    for _, gw in gw_unmatched.iterrows():
        best_match, best_score = None, 0.0
        highest_cand_pair, highest_cand_score = None, 0.0
        gw_id = str(gw['gateway_id']).strip()
        gw_amt = float(gw['amount'])
        gw_amt_bucket = round(gw_amt, -2)
        gw_date = gw['dt'].floor('D')

        # BLOCKING: Filter ledger candidates in the same amount bucket / range
        leg_candidates = leg_unmatched[
            (leg_unmatched['gross_value'].apply(lambda x: round(x, -2)) == gw_amt_bucket) |
            (abs(gw_amt - leg_unmatched['gross_value']) < 1.0)
        ]

        # BLOCKING: Filter bank candidates in same amount bucket & within 3-day date window
        bank_candidates = bank_unmatched[
            ((bank_unmatched['credited_amount'].apply(lambda x: round(x, -2)) == gw_amt_bucket) |
             (abs(gw_amt - bank_unmatched['credited_amount']) <= (gw_amt * 0.05))) &
            (abs((bank_unmatched['dt'].dt.floor('D') - gw_date).dt.days) <= 3)
        ]

        blocked_comparisons += len(leg_candidates) * len(bank_candidates)
        has_candidates = (len(leg_candidates) > 0) and (len(bank_candidates) > 0)

        if has_candidates:
            for _, leg in leg_candidates.iterrows():
                for _, bank in bank_candidates.iterrows():
                    features = extract_pair_features(gw, leg, bank)
                    match_prob = float(matcher_model.predict_proba(features)[0][1])
                    if match_prob > highest_cand_score:
                        highest_cand_score = match_prob
                        highest_cand_pair = (str(leg['entry_id']), str(bank['settlement_ref']))
                    if match_prob >= 0.50 and match_prob > best_score:
                        best_score = match_prob
                        best_match = (str(leg['entry_id']), str(bank['settlement_ref']))

        if best_match:
            matched_results[gw_id] = {
                "gateway_id": gw_id,
                "ledger_id": str(best_match[0]),
                "bank_id": str(best_match[1]),
                "matched_pass": "Pass 2 (Fuzzy Match)",
                "root_causes": ["REFERENCE_VARIANCE"],
                "rule_fired": "REFERENCE_VARIANCE",
                "confidence": round(best_score, 2),
                "exposure": float(gw['amount'])
            }
            exceptions_logged["REFERENCE_VARIANCE"] += 1
            leg_unmatched = leg_unmatched[leg_unmatched['entry_id'] != best_match[0]]
            bank_unmatched = bank_unmatched[bank_unmatched['settlement_ref'] != best_match[1]]
        elif has_candidates:
            best_cand_dict = {
                "ledger_id": highest_cand_pair[0] if highest_cand_pair else None,
                "bank_id": highest_cand_pair[1] if highest_cand_pair else None,
                "confidence": round(highest_cand_score, 2)
            }
            ambiguous_results[gw_id] = {
                "gateway_id": gw_id,
                "ledger_id": best_cand_dict["ledger_id"],
                "bank_id": best_cand_dict["bank_id"],
                "best_candidate": best_cand_dict,
                "matched_pass": "Pass 2 (Ambiguous)",
                "root_causes": ["BELOW_CONFIDENCE_THRESHOLD"],
                "rule_fired": "BELOW_CONFIDENCE_THRESHOLD",
                "confidence": round(highest_cand_score, 2),
                "exposure": float(gw['amount']),
                "expected_loss": round((1.0 - highest_cand_score) * float(gw['amount']), 2),
                "status": "AMBIGUOUS_UNRESOLVED"
            }
            exceptions_logged["BELOW_CONFIDENCE_THRESHOLD"] = exceptions_logged.get("BELOW_CONFIDENCE_THRESHOLD", 0) + 1
        else:
            if len(leg_candidates) == 0 and len(bank_candidates) == 0:
                rule_fired = "GATEWAY_ONLY_ORPHAN"
            elif len(leg_candidates) == 0:
                rule_fired = "LEDGER_ONLY_ORPHAN"
            else:
                rule_fired = "BANK_ONLY_ORPHAN"

            best_leg_id = str(leg_candidates.iloc[0]['entry_id']) if len(leg_candidates) > 0 else None
            best_bank_id = str(bank_candidates.iloc[0]['settlement_ref']) if len(bank_candidates) > 0 else None

            orphan_results.append({
                "gateway_id": gw_id,
                "ledger_id": best_leg_id,
                "bank_id": best_bank_id,
                "matched_pass": "Unmatched (Orphan)",
                "root_causes": ["MISSING_SOURCES"],
                "rule_fired": rule_fired,
                "confidence": 0.00,
                "exposure": float(gw['amount']),
                "expected_loss": float(gw['amount']),
                "status": "UNRESOLVED_ORPHAN"
            })
            exceptions_logged["MISSING_SOURCES"] = exceptions_logged.get("MISSING_SOURCES", 0) + 1

    reduction_pct = (1.0 - (blocked_comparisons / unblocked_comparisons)) * 100.0 if unblocked_comparisons > 0 else 0.0
    print(f"[Pass 2 Blocking Optimization] Unblocked candidate comparisons: {unblocked_comparisons} | Blocked candidate comparisons: {blocked_comparisons} | Complexity reduction: {reduction_pct:.2f}%")

    return {
        "matched_results": matched_results,
        "ambiguous_results": ambiguous_results,
        "orphan_results": orphan_results,
        "duplicates": duplicates,
        "seen_gateway_ids": seen_gateway_ids,
        "exceptions_logged": exceptions_logged,
        "gw_unmatched": gw_unmatched,
        "leg_unmatched": leg_unmatched,
        "bank_unmatched": bank_unmatched
    }
