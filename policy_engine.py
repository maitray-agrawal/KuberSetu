import pandas as pd
import json
import difflib

DATA_DIR = "data"

# 1. Load Data
gw_df = pd.read_csv(f"{DATA_DIR}/gateway.csv")
leg_df = pd.read_csv(f"{DATA_DIR}/ledger.csv")
bank_df = pd.read_csv(f"{DATA_DIR}/bank.csv")
with open(f"{DATA_DIR}/ground_truth.json", "r") as f:
    ground_truth = json.load(f)

gw_df['dt'] = pd.to_datetime(gw_df['timestamp'], format='%d-%m-%Y %H:%M')
leg_df['dt'] = pd.to_datetime(leg_df['entry_date'], format='%d.%m.%Y')
bank_df['dt'] = pd.to_datetime(bank_df['settled_on'], format='%Y-%m-%d')

matched_results = {}
# Using a list for root causes to catch overlapping issues (Fixing the previous bug)
exceptions_logged = {"TIMING_DRIFT": 0, "FEE_VARIANCE": 0, "REFERENCE_VARIANCE": 0}

def similarity(a, b):
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

# --- PASS 1: Exact ID Matches ---
for _, gw in gw_df.iterrows():
    gw_id = str(gw['gateway_id']).strip()
    leg_match = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
    bank_match = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
    
    if not leg_match.empty and not bank_match.empty:
        leg, bank = leg_match.iloc[0], bank_match.iloc[0]
        causes = []
        
        if abs(gw['amount'] - bank['credited_amount']) > 0:
            causes.append("FEE_VARIANCE")
            exceptions_logged["FEE_VARIANCE"] += 1
        if (bank['dt'] - gw['dt']).days > 0:
            causes.append("TIMING_DRIFT")
            exceptions_logged["TIMING_DRIFT"] += 1
            
        if not causes:
            causes.append("EXACT_MATCH")
            
        matched_results[gw_id] = {
            "ledger": leg['entry_id'],
            "bank": bank['settlement_ref'],
            "root_causes": causes,
            "confidence": 1.00,
            "exposure": gw['amount']
        }

# --- PASS 2: Fuzzy Matches ---
gw_unmatched = gw_df[~gw_df['gateway_id'].isin(matched_results.keys())]
leg_unmatched = leg_df[~leg_df['entry_id'].isin([m['ledger'] for m in matched_results.values()])]
bank_unmatched = bank_df[~bank_df['settlement_ref'].isin([m['bank'] for m in matched_results.values()])]

for _, gw in gw_unmatched.iterrows():
    best_match, best_score = None, 0.0
    gw_id = str(gw['gateway_id']).strip()
    
    for _, leg in leg_unmatched.iterrows():
        for _, bank in bank_unmatched.iterrows():
            if abs(gw['amount'] - leg['gross_value']) < 1 and abs(gw['amount'] - bank['credited_amount']) <= (gw['amount'] * 0.05):
                avg_sim = (similarity(gw_id, leg['entry_id']) + similarity(gw_id, bank['settlement_ref'])) / 2
                if avg_sim > 0.65 and avg_sim > best_score:
                    best_score = avg_sim
                    best_match = (leg['entry_id'], bank['settlement_ref'])

    if best_match:
        matched_results[gw_id] = {
            "ledger": best_match[0],
            "bank": best_match[1],
            "root_causes": ["REFERENCE_VARIANCE"],
            "confidence": round(best_score, 2),
            "exposure": gw['amount']
        }
        exceptions_logged["REFERENCE_VARIANCE"] += 1
        leg_unmatched = leg_unmatched[leg_unmatched['entry_id'] != best_match[0]]
        bank_unmatched = bank_unmatched[bank_unmatched['settlement_ref'] != best_match[1]]


# --- PASS 3: RISK POLICY ENGINE ---
# This is what you actually pitch to Razorpay.
# Expected Loss = Probability of being wrong * Financial Exposure
# We abstain (send to human review) if Expected Loss > RISK_TOLERANCE

RISK_TOLERANCE_INR = 500.00  # Max acceptable statistical loss per transaction

operations_queue = {
    "AUTO_RESOLVED": 0,
    "HUMAN_REVIEW": 0,
    "UNRESOLVED_ORPHAN": len(gw_df) - len(matched_results)
}
value_routed = {"AUTO_RESOLVED": 0.0, "HUMAN_REVIEW": 0.0, "UNRESOLVED_ORPHAN": 0.0}

for gw_id, result in matched_results.items():
    prob_wrong = 1.0 - result['confidence']
    expected_loss = prob_wrong * result['exposure']
    
    # Policy Decision
    if expected_loss <= RISK_TOLERANCE_INR and result['confidence'] >= 0.70:
        decision = "AUTO_RESOLVED"
    else:
        decision = "HUMAN_REVIEW"
        
    operations_queue[decision] += 1
    value_routed[decision] += result['exposure']

# Add orphans to value routed
for _, gw in gw_unmatched.iterrows():
    if str(gw['gateway_id']).strip() not in matched_results:
        value_routed["UNRESOLVED_ORPHAN"] += gw['amount']

print("==================================================")
print("     SETTLESENSE: RISK POLICY & TRIAGE ENGINE     ")
print("==================================================")
print(f"Total Transactions Processed: {len(gw_df)}")
print(f"Risk Tolerance (Max Expected Loss): ₹{RISK_TOLERANCE_INR:,.2f}")
print("--------------------------------------------------")
print(f"🟢 AUTO-RESOLVED: {operations_queue['AUTO_RESOLVED']} txns | ₹{value_routed['AUTO_RESOLVED']:,.2f}")
print(f"🟡 HUMAN REVIEW:  {operations_queue['HUMAN_REVIEW']} txns | ₹{value_routed['HUMAN_REVIEW']:,.2f}")
print(f"🔴 ORPHANS/DROP:  {operations_queue['UNRESOLVED_ORPHAN']} txns | ₹{value_routed['UNRESOLVED_ORPHAN']:,.2f}")
print("==================================================")
print(f"Human effort reduced by: {(operations_queue['AUTO_RESOLVED'] / len(gw_df)):.1%}")
print("==================================================")