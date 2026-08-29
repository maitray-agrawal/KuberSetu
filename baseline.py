import pandas as pd
import json
import os

DATA_DIR = "data"

# 1. Load the generated data
try:
    gw_df = pd.read_csv(f"{DATA_DIR}/gateway.csv")
    leg_df = pd.read_csv(f"{DATA_DIR}/ledger.csv")
    bank_df = pd.read_csv(f"{DATA_DIR}/bank.csv")
    with open(f"{DATA_DIR}/ground_truth.json", "r") as f:
        ground_truth = json.load(f)
except FileNotFoundError:
    print("Error: Could not find the CSVs. Make sure you are running this from the directory containing the 'data' folder.")
    exit(1)

# 2. Normalize whitespace (standard data hygiene)
gw_df['gateway_id'] = gw_df['gateway_id'].astype(str).str.strip()
leg_df['entry_id'] = leg_df['entry_id'].astype(str).str.strip()
bank_df['settlement_ref'] = bank_df['settlement_ref'].astype(str).str.strip()

# 3. Naive Deterministic Matching (Exact ID Match)
# We perform inner joins. If the ID is altered or missing, it gets dropped silently.
matched_gw_leg = pd.merge(gw_df, leg_df, left_on='gateway_id', right_on='entry_id', how='inner')
exact_matches = pd.merge(matched_gw_leg, bank_df, left_on='gateway_id', right_on='settlement_ref', how='inner')

# Store our naive system's predictions
predictions = {}
for _, row in exact_matches.iterrows():
    predictions[row['gateway_id']] = {
        "ledger": row['entry_id'],
        "bank": row['settlement_ref']
    }

# 4. Evaluation Engine (The Honest Metrics)
total_expected_matches = 0
true_positives = 0
false_positives = 0
false_match_exposure = 0.0

for cid, truth in ground_truth.items():
    # An expected full match is one that actually exists in all 3 systems
    is_full_match_expected = (truth['expected_ledger'] is not None) and (truth['expected_bank'] is not None)
    if is_full_match_expected:
        total_expected_matches += 1
        
    pred = predictions.get(truth['expected_gateway'])
    
    if pred:
        # The system made a match. Was it exactly right?
        if pred['ledger'] == truth['expected_ledger'] and pred['bank'] == truth['expected_bank']:
            true_positives += 1
        else:
            false_positives += 1
            false_match_exposure += truth['financial_exposure']

# Calculate Metrics
precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
recall = true_positives / total_expected_matches if total_expected_matches > 0 else 0

print("==================================================")
print("       BASELINE DETERMINISTIC MATCHER (V1)        ")
print("==================================================")
print(f"Total Ground Truth Records: {len(ground_truth)}")
print(f"Valid 3-Way Matches Possible: {total_expected_matches}")
print(f"System Matches Made:        {len(predictions)}")
print("--------------------------------------------------")
print(f"True Positives:             {true_positives}")
print(f"False Positives:            {false_positives}")
print(f"Precision:                  {precision:.2%}")
print(f"Recall:                     {recall:.2%}")
print(f"False Match Risk Exposure:  ₹{false_match_exposure:,.2f}")
print("==================================================")