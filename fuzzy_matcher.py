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

# Convert dates to standard formats for comparison
gw_df['dt'] = pd.to_datetime(gw_df['timestamp'], format='%d-%m-%Y %H:%M')
leg_df['dt'] = pd.to_datetime(leg_df['entry_date'], format='%d.%m.%Y')
bank_df['dt'] = pd.to_datetime(bank_df['settled_on'], format='%Y-%m-%d')

# 2. Trackers
matched_results = {}
exceptions_logged = {"TIMING_DRIFT": 0, "FEE_VARIANCE": 0, "REFERENCE_VARIANCE": 0}

def similarity(a, b):
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

# 3. PASS 1: Exact ID Matches (But we verify the details)
for _, gw in gw_df.iterrows():
    gw_id = str(gw['gateway_id']).strip()
    
    # Find matching ledger and bank rows
    leg_match = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
    bank_match = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
    
    if not leg_match.empty and not bank_match.empty:
        leg = leg_match.iloc[0]
        bank = bank_match.iloc[0]
        
        root_cause = "EXACT_MATCH"
        
        # Exception Tagging
        if abs(gw['amount'] - bank['credited_amount']) > 0 and abs(gw['amount'] - bank['credited_amount']) <= (gw['amount'] * 0.05):
            root_cause = "FEE_VARIANCE"
            exceptions_logged["FEE_VARIANCE"] += 1
        elif (bank['dt'] - gw['dt']).days > 0:
            root_cause = "TIMING_DRIFT"
            exceptions_logged["TIMING_DRIFT"] += 1
            
        matched_results[gw_id] = {
            "ledger": leg['entry_id'],
            "bank": bank['settlement_ref'],
            "root_cause": root_cause,
            "confidence": 1.00
        }

# 4. PASS 2: Fuzzy Matching for the Leftovers
# Get records not matched in Pass 1
gw_unmatched = gw_df[~gw_df['gateway_id'].isin(matched_results.keys())]
leg_unmatched = leg_df[~leg_df['entry_id'].isin([m['ledger'] for m in matched_results.values()])]
bank_unmatched = bank_df[~bank_df['settlement_ref'].isin([m['bank'] for m in matched_results.values()])]

for _, gw in gw_unmatched.iterrows():
    best_match = None
    best_score = 0.0
    
    gw_id = str(gw['gateway_id']).strip()
    
    # Scan unmatched ledger records
    for _, leg in leg_unmatched.iterrows():
        # Scan unmatched bank records
        for _, bank in bank_unmatched.iterrows():
            # If the amounts are highly similar (allowing for fees)
            if abs(gw['amount'] - leg['gross_value']) < 1 and abs(gw['amount'] - bank['credited_amount']) <= (gw['amount'] * 0.05):
                
                # Check reference string similarity
                sim_leg = similarity(gw_id, leg['entry_id'])
                sim_bank = similarity(gw_id, bank['settlement_ref'])
                avg_sim = (sim_leg + sim_bank) / 2
                
                if avg_sim > 0.65 and avg_sim > best_score:
                    best_score = avg_sim
                    best_match = (leg['entry_id'], bank['settlement_ref'])

    if best_match:
        matched_results[gw_id] = {
            "ledger": best_match[0],
            "bank": best_match[1],
            "root_cause": "REFERENCE_VARIANCE",
            "confidence": round(best_score, 2)
        }
        exceptions_logged["REFERENCE_VARIANCE"] += 1
        
        # Remove from unmatched pools to prevent duplicate consumption
        leg_unmatched = leg_unmatched[leg_unmatched['entry_id'] != best_match[0]]
        bank_unmatched = bank_unmatched[bank_unmatched['settlement_ref'] != best_match[1]]

# 5. Evaluation Engine
total_expected_matches = sum(1 for t in ground_truth.values() if t['expected_ledger'] and t['expected_bank'])
true_positives = 0
false_positives = 0
false_match_exposure = 0.0

for gw_id, result in matched_results.items():
    # Find the actual ground truth canonical ID for this gateway_id
    true_canonical = None
    for cid, truth in ground_truth.items():
        if truth['expected_gateway'] == gw_id:
            true_canonical = cid
            break
            
    if true_canonical:
        expected = ground_truth[true_canonical]
        if result['ledger'] == expected['expected_ledger'] and result['bank'] == expected['expected_bank']:
            true_positives += 1
        else:
            false_positives += 1
            false_match_exposure += expected['financial_exposure']

precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
recall = true_positives / total_expected_matches if total_expected_matches > 0 else 0

print("==================================================")
print("     SETTLESENSE: FUZZY MATCHER & EXCEPTIONS      ")
print("==================================================")
print(f"Total Ground Truth Records: {len(ground_truth)}")
print(f"Valid 3-Way Matches Possible: {total_expected_matches}")
print(f"System Matches Made:        {len(matched_results)}")
print("--------------------------------------------------")
print(f"True Positives:             {true_positives}")
print(f"False Positives:            {false_positives}")
print(f"Precision:                  {precision:.2%}")
print(f"Recall:                     {recall:.2%}")
print(f"False Match Risk Exposure:  ₹{false_match_exposure:,.2f}")
print("--------------------------------------------------")
print("Exceptions Successfully Root-Caused:")
print(f"- Timing Drift:         {exceptions_logged['TIMING_DRIFT']}")
print(f"- Fee Variance:         {exceptions_logged['FEE_VARIANCE']}")
print(f"- Reference Variance:   {exceptions_logged['REFERENCE_VARIANCE']}")
print("==================================================")