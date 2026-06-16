"""
Diagnostic: check for outliers in tackles and interceptions by league.
Run: python3 scripts/diagnose_metrics.py
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
raw = json.loads((BASE / "data/players/wc2026_raw.json").read_text())
lookup = json.loads((BASE / "data/club_league_lookup.json").read_text())

players = raw["players"]

# Attach league to each player
for p in players:
    p["league"] = lookup.get(p["squad"])

MIN_MINUTES = 60

def p90(val, mins):
    return round(val / mins * 90, 2) if mins >= MIN_MINUTES else None

print("=" * 60)
print("TOP 15 PLAYERS — TACKLES WON PER 90")
print("=" * 60)
eligible = [p for p in players if p["minutes"] >= MIN_MINUTES and p["tackles"] > 0]
eligible.sort(key=lambda p: p["tackles"] / p["minutes"], reverse=True)
for p in eligible[:15]:
    league = p["league"] or "null"
    tkl_p90 = p90(p["tackles"], p["minutes"])
    print(f"  {p['name']:<25} {p['squad']:<22} [{league:<10}]  {p['tackles']} tkl  {p['minutes']}m  → {tkl_p90}/90")

print()
print("=" * 60)
print("MLS — ALL ELIGIBLE PLAYERS BY TACKLES WON")
print("=" * 60)
mls = [p for p in players if p["league"] == "mls" and p["minutes"] >= MIN_MINUTES]
mls.sort(key=lambda p: p["tackles"] / p["minutes"], reverse=True)
for p in mls:
    print(f"  {p['name']:<25} {p['squad']:<22} {p['tackles']} tkl  {p['minutes']}m  → {p90(p['tackles'], p['minutes'])}/90")

print()
print("=" * 60)
print("TOP 15 PLAYERS — INTERCEPTIONS PER 90")
print("=" * 60)
elig_int = [p for p in players if p["minutes"] >= MIN_MINUTES and p["interceptions"] > 0]
elig_int.sort(key=lambda p: p["interceptions"] / p["minutes"], reverse=True)
for p in elig_int[:15]:
    league = p["league"] or "null"
    int_p90 = p90(p["interceptions"], p["minutes"])
    print(f"  {p['name']:<25} {p['squad']:<22} [{league:<10}]  {p['interceptions']} int  {p['minutes']}m  → {int_p90}/90")

print()
print("=" * 60)
print("LEAGUE AVERAGES — TACKLES WON PER 90 (eligible players)")
print("=" * 60)
from collections import defaultdict
league_tkl = defaultdict(list)
league_int = defaultdict(list)
for p in players:
    if p["minutes"] < MIN_MINUTES or not p["league"]:
        continue
    league_tkl[p["league"]].append(p["tackles"] / p["minutes"] * 90)
    league_int[p["league"]].append(p["interceptions"] / p["minutes"] * 90)

tkl_avgs = sorted(league_tkl.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)
for league, vals in tkl_avgs:
    avg = sum(vals)/len(vals)
    print(f"  {league:<12}  avg={avg:.2f}/90  n={len(vals)}")

print()
print("=" * 60)
print("LEAGUE AVERAGES — INTERCEPTIONS PER 90 (eligible players)")
print("=" * 60)
int_avgs = sorted(league_int.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)
for league, vals in int_avgs:
    avg = sum(vals)/len(vals)
    print(f"  {league:<12}  avg={avg:.2f}/90  n={len(vals)}")
