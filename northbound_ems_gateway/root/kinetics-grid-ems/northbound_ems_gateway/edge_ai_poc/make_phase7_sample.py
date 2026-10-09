import pandas as pd
from pathlib import Path

bundle = Path("phase7_runtime_bundle_v0_3")
out = bundle / "test_data" / "phase7_replay_samples_v0_3.csv"

normal = pd.read_csv("ml_v0_3/normal_test_sample_v0_3.csv").head(200)
anomaly = pd.read_csv("phase6_2_validation_outputs/phase6_2_top_ml_anomalies.csv").head(200)

combined = pd.concat([normal, anomaly], ignore_index=True)
combined.to_csv(out, index=False)

print("WROTE", out)
print("ROWS", len(combined))
