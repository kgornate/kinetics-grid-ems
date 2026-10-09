Phase 7 Runtime Bundle v0.3

Purpose:
Deploy trained StandardScaler + IsolationForest model to i.MX93 and run CPU inference.

Files:
model/iforest_model_v0_3.joblib
model/standard_scaler_v0_3.joblib
model/ml_model_manifest_v0_3.json
scripts/eai_phase7_offline_infer.py
test_data/phase7_replay_samples_v0_3.csv

Run on i.MX93:

cd /root/kinetics-grid-ems/northbound_ems_gateway/edge_ai_poc/runtime_v0_3/phase7_runtime_bundle_v0_3

python3 scripts/eai_phase7_offline_infer.py \
  --model-dir model \
  --input test_data/phase7_replay_samples_v0_3.csv \
  --output /tmp/phase7_replay_infer_output.csv
