import sys
import json
import pandas as pd
from openai import OpenAI

MODEL = "gpt-5"  
client = OpenAI(api_key = "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"
)

# ---- LOAD CSV ----
csv_path = sys.argv[1]
df = pd.read_csv(csv_path)

# Convert to structured records
transfers = []
for _, row in df.iterrows():
    transfers.append({
        "source_plate": row["Source Plate Name"],
        "source_well": row["Source Well"],
        "destination_plate": row["Destination Plate Name"],
        "destination_well": row["Destination Well"],
        "volume_ul": float(row["Transfer Volume"]),
        "sample": row["Sample ID"]
    })

context = {
    "num_transfers": len(transfers),
    "transfers": transfers
}

system_prompt = """
You are a laboratory automation compiler.

You receive liquid handling transfer instructions.
Generate a Python protocol script for Opentrons OT-2

Rules:
- Do not change volumes.
- Do not invent transfers.
- Use loops when possible.
- Produce clean executable Python code only.
"""

response = client.responses.create(
    model=MODEL,
    input = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(context, indent=2)
        }
    ]
)

generated_code = response.output_text

# ---- SAVE OUTPUT ----
with open("generated_protocol_from_csv.py", "w") as f:
    f.write(generated_code)

print("Script generated: generated_protocol_fromcsv.py")