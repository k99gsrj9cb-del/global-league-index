"""
Updates data/manifest.json to set current_snapshot to the latest available snapshot.
Run after build_snapshots.py.
"""
import json
from pathlib import Path
from datetime import datetime

BASE     = Path(__file__).parent.parent
MANIFEST = BASE / "data" / "manifest.json"
SNAPS    = BASE / "data" / "snapshots"

with open(MANIFEST) as f:
    manifest = json.load(f)

# Find all group-stage cumulative snapshots that exist
available = set()
for p in SNAPS.glob("*.json"):
    available.add(p.stem)

# Walk snapshots in order; find the latest available non-KO one
# (KO snapshots are cumulative/isolated pairs — handled separately)
latest = None
for s in manifest["snapshots"]:
    if not s["ko"] and s["id"] in available:
        latest = s["id"]
    elif s["ko"]:
        cid = f"{s['id']}_cumulative"
        if cid in available:
            latest = s["id"]

if latest:
    manifest["current_snapshot"] = latest
    manifest["generated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Updated manifest: current_snapshot = {latest}")
else:
    print("No snapshots found — manifest unchanged.")
