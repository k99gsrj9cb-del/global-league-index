"""
Prints any clubs in wc2026_raw.json that are missing from club_league_lookup.json.
Run after fetch_fbref.py to find gaps before building snapshots.
"""
import json
from pathlib import Path

BASE   = Path(__file__).parent.parent
RAW    = BASE / "data" / "players" / "wc2026_raw.json"
LOOKUP = BASE / "data" / "club_league_lookup.json"

if not RAW.exists():
    print("Run fetch_fbref.py first.")
    raise SystemExit

with open(RAW) as f:
    players = json.load(f)["players"]
with open(LOOKUP) as f:
    lookup = json.load(f)

# Remove _meta key
lookup.pop("_meta", None)

clubs_in_data = {}
for p in players:
    club = p.get("club") or p.get("squad", "")
    if club:
        clubs_in_data.setdefault(club, 0)
        clubs_in_data[club] += 1

missing = {c: n for c, n in clubs_in_data.items() if c not in lookup}
covered = {c: n for c, n in clubs_in_data.items() if c in lookup}

print(f"Clubs in FBref data:  {len(clubs_in_data)}")
print(f"Clubs in lookup:      {len(covered)}")
print(f"Missing from lookup:  {len(missing)}")

if missing:
    print("\nAdd these to data/club_league_lookup.json:")
    for club, n in sorted(missing.items(), key=lambda x: -x[1]):
        print(f'  {club!r}: null,   // {n} player(s)')
else:
    print("\nAll clubs mapped! ✓")

# Summary of league distribution
league_counts = {}
for c, league in lookup.items():
    if c == "_meta":
        continue
    if league:
        league_counts[league] = league_counts.get(league, 0) + clubs_in_data.get(c, 0)

print("\nPlayers per tracked league (from lookup):")
for league, n in sorted(league_counts.items(), key=lambda x: -x[1]):
    print(f"  {league:12s}: {n} players")
