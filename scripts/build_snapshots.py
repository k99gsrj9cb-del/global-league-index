from __future__ import annotations  # noqa: E402
"""
GLI Snapshot Pipeline — 2026 World Cup
Reads:  data/players/wc2026_raw.json
        data/club_league_lookup.json
        data/tournament_schedule.json   (optional — auto-generates if missing)
Writes: data/snapshots/<snapshot_id>.json

Run:    python scripts/build_snapshots.py
        python scripts/build_snapshots.py --snapshot group_d3   (single snapshot)
        python scripts/build_snapshots.py --validate            (validate only)
"""
import json, sys, argparse
from pathlib import Path
from datetime import date, datetime

BASE     = Path(__file__).parent.parent
PLAYERS  = BASE / "data" / "players" / "wc2026_raw.json"
LOOKUP   = BASE / "data" / "club_league_lookup.json"
SCHEDULE = BASE / "data" / "tournament_schedule.json"
SNAPS    = BASE / "data" / "snapshots"
SNAPS.mkdir(parents=True, exist_ok=True)

MIN_MINUTES = 60  # eligibility threshold

# ---------------------------------------------------------------------------
# League definitions — 18 leagues for 2026
# ---------------------------------------------------------------------------

LEAGUES = [
    {"id": "epl",       "name": "Premier League",        "short": "EPL",  "country": "England",      "color": "#5910DC"},
    {"id": "laliga",    "name": "La Liga",                "short": "LL",   "country": "Spain",        "color": "#C4291C"},
    {"id": "bundesl",   "name": "Bundesliga",             "short": "BL",   "country": "Germany",      "color": "#EB5027"},
    {"id": "seriea",    "name": "Serie A",                "short": "SA",   "country": "Italy",        "color": "#2A398D"},
    {"id": "ligue1",    "name": "Ligue 1",                "short": "L1",   "country": "France",       "color": "#394CF3"},
    {"id": "bras",      "name": "Brasileirão",            "short": "BR",   "country": "Brazil",       "color": "#3CAC3B"},
    {"id": "ligamx",    "name": "Liga MX",                "short": "MX",   "country": "Mexico",       "color": "#224F41"},
    {"id": "mls",       "name": "MLS",                    "short": "MLS",  "country": "USA/Canada",   "color": "#60C3D7"},
    {"id": "saudi",     "name": "Saudi Pro League",       "short": "SPL",  "country": "Saudi Arabia", "color": "#F5A623"},
    {"id": "champ",     "name": "Championship",           "short": "EFL",  "country": "England",      "color": "#AA8BF8"},
    {"id": "priml",     "name": "Primeira Liga",          "short": "PL",   "country": "Portugal",     "color": "#6A1C19"},
    {"id": "argent",    "name": "Liga Profesional",       "short": "LPA",  "country": "Argentina",    "color": "#90F8DA"},
    {"id": "turkey",    "name": "Süper Lig",              "short": "SL",   "country": "Türkiye",      "color": "#BBEA4A"},
    {"id": "erediv",    "name": "Eredivisie",             "short": "ERE",  "country": "Netherlands",  "color": "#FF6B00"},
    {"id": "belgian",   "name": "Pro League",             "short": "BEL",  "country": "Belgium",      "color": "#EF0C23"},
    {"id": "scottish",  "name": "Scottish Prem",          "short": "SPF",  "country": "Scotland",     "color": "#003F87"},
    {"id": "jleague",   "name": "J-League",               "short": "JPN",  "country": "Japan",        "color": "#0033A0"},
    {"id": "other",     "name": "Other Leagues",          "short": "OTH",  "country": "Various",      "color": "#9ea3b0"},
]

LEAGUE_IDS = {l["id"] for l in LEAGUES}


# ---------------------------------------------------------------------------
# Composite score formula (from spec)
# ---------------------------------------------------------------------------

def composite(p90: dict) -> float:
    return round(
        p90["goals"]        * 28.0
        + p90["assists"]    * 20.0
        + p90["prog_passes"]* 2.2
        + p90["duels_won"]  * 1.8
        + p90["tackles"]    * 2.5
        + p90["pressures"]  * 1.2
        + p90["interceptions"] * 2.0,
        2
    )


def per90(player: dict) -> dict:
    m = player["minutes"]
    if m == 0:
        return {k: 0.0 for k in ["goals","assists","prog_passes","duels_won","tackles","pressures","interceptions"]}
    f = 90.0 / m
    return {
        "goals":          round(player["goals"]         * f, 3),
        "assists":        round(player["assists"]        * f, 3),
        "prog_passes":    round(player["prog_passes"]    * f, 2),
        "duels_won":      round(player["duels_won"]      * f, 2),
        "tackles":        round(player["tackles"]        * f, 2),
        "pressures":      round(player["pressures"]      * f, 2),
        "interceptions":  round(player["interceptions"]  * f, 2),
    }


def gk_composite(player: dict) -> float:
    """GK-specific rating based on saves, clean sheets and goals conceded per 90."""
    m = player["minutes"]
    if m == 0:
        return 0.0
    f = 90.0 / m
    saves_p90  = player["gk_saves"] * f
    ga_p90     = player["gk_ga"]    * f
    cs_rate    = player["gk_cs"]    / (m / 90)   # clean sheets per 90
    return round(
        saves_p90  * 15.0
        + cs_rate  * 25.0
        - ga_p90   * 8.0,
        2
    )


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_players() -> list[dict]:
    if not PLAYERS.exists():
        sys.exit(f"ERROR: {PLAYERS} not found. Run fetch_fbref.py first.")
    with open(PLAYERS) as f:
        return json.load(f)["players"]


def load_lookup() -> dict[str, str | None]:
    if not LOOKUP.exists():
        sys.exit(f"ERROR: {LOOKUP} not found. Run scripts/build_lookup.py first.")
    with open(LOOKUP) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 2026 World Cup tournament schedule
# Groups: 48 teams, 3 matches each → 72 group-stage matches over 12 days
# Group stage: Jun 12 – Jun 26, 2026 (days 1–15, with a rest day pattern)
# ---------------------------------------------------------------------------

DEFAULT_SCHEDULE = {
    "tournament": "2026 FIFA World Cup",
    "group_stage_days": [
        {"snapshot_id": "group_d1",  "label": "Day 1",  "date": "2026-06-11", "phase": "Group stage"},
        {"snapshot_id": "group_d2",  "label": "Day 2",  "date": "2026-06-12", "phase": "Group stage"},
        {"snapshot_id": "group_d3",  "label": "Day 3",  "date": "2026-06-13", "phase": "Group stage"},
        {"snapshot_id": "group_d4",  "label": "Day 4",  "date": "2026-06-14", "phase": "Group stage"},
        {"snapshot_id": "group_d5",  "label": "Day 5",  "date": "2026-06-15", "phase": "Group stage"},
        {"snapshot_id": "group_d6",  "label": "Day 6",  "date": "2026-06-16", "phase": "Group stage"},
        {"snapshot_id": "group_d7",  "label": "Day 7",  "date": "2026-06-17", "phase": "Group stage"},
        {"snapshot_id": "group_d8",  "label": "Day 8",  "date": "2026-06-18", "phase": "Group stage"},
        {"snapshot_id": "group_d9",  "label": "Day 9",  "date": "2026-06-19", "phase": "Group stage"},
        {"snapshot_id": "group_d10", "label": "Day 10", "date": "2026-06-20", "phase": "Group stage"},
        {"snapshot_id": "group_d11", "label": "Day 11", "date": "2026-06-21", "phase": "Group stage"},
        {"snapshot_id": "group_d12", "label": "Day 12", "date": "2026-06-22", "phase": "Group stage"},
        {"snapshot_id": "group_d13", "label": "Day 13", "date": "2026-06-23", "phase": "Group stage"},
        {"snapshot_id": "group_d14", "label": "Day 14", "date": "2026-06-24", "phase": "Group stage"},
        {"snapshot_id": "group_d15", "label": "Day 15", "date": "2026-06-25", "phase": "Group stage"},
        {"snapshot_id": "group_d16", "label": "Day 16", "date": "2026-06-26", "phase": "Group stage"},
    ],
    "knockout_rounds": [
        {"snapshot_id": "r32_cumulative",  "label": "R32",  "date_range": "Jun 27–Jul 3",  "phase": "Round of 32",   "view": "cumulative"},
        {"snapshot_id": "r32_isolated",    "label": "R32",  "date_range": "Jun 27–Jul 3",  "phase": "Round of 32",   "view": "isolated"},
        {"snapshot_id": "r16_cumulative",  "label": "R16",  "date_range": "Jul 4–7",        "phase": "Round of 16",   "view": "cumulative"},
        {"snapshot_id": "r16_isolated",    "label": "R16",  "date_range": "Jul 4–7",        "phase": "Round of 16",   "view": "isolated"},
        {"snapshot_id": "qf_cumulative",   "label": "QF",   "date_range": "Jul 9–12",       "phase": "Quarter-finals","view": "cumulative"},
        {"snapshot_id": "qf_isolated",     "label": "QF",   "date_range": "Jul 9–12",       "phase": "Quarter-finals","view": "isolated"},
        {"snapshot_id": "sf_cumulative",   "label": "SF",   "date_range": "Jul 14–15",      "phase": "Semi-finals",   "view": "cumulative"},
        {"snapshot_id": "sf_isolated",     "label": "SF",   "date_range": "Jul 14–15",      "phase": "Semi-finals",   "view": "isolated"},
        {"snapshot_id": "final_cumulative","label": "FIN",  "date_range": "Jul 19",         "phase": "Final",         "view": "cumulative"},
        {"snapshot_id": "final_isolated",  "label": "FIN",  "date_range": "Jul 19",         "phase": "Final",         "view": "isolated"},
    ]
}


def load_schedule() -> dict:
    if SCHEDULE.exists():
        with open(SCHEDULE) as f:
            return json.load(f)
    return DEFAULT_SCHEDULE


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------

def assign_league(player: dict, lookup: dict) -> str | None:
    club = player.get("club") or player.get("squad", "")
    return lookup.get(club)  # None = not tracked


def aggregate_leagues(players: list[dict], lookup: dict, eliminated: set[str]) -> list[dict]:
    """
    Group eligible players by league and compute aggregate per-90 stats.
    Returns list of league dicts sorted by composite_score desc.
    """
    # Bucket players into leagues
    buckets: dict[str, list[dict]] = {l["id"]: [] for l in LEAGUES}

    for p in players:
        league_id = assign_league(p, lookup)
        if league_id is None:
            continue
        if league_id not in buckets:
            continue
        buckets[league_id].append(p)

    results = []
    for league_meta in LEAGUES:
        lid = league_meta["id"]
        all_players = buckets[lid]

        if not all_players:
            continue

        eligible = [p for p in all_players if p["minutes"] >= MIN_MINUTES]
        n_elig = len(eligible)

        # Positional split (all players, not just eligible)
        pos_counts = {"ATT": 0, "MID": 0, "DEF": 0, "GK": 0}
        for p in all_players:
            pos_counts[p.get("pos", "MID")] += 1

        total_pl = len(all_players)
        att_n = pos_counts["ATT"]
        mid_n = pos_counts["MID"]
        def_n = pos_counts["DEF"] + pos_counts["GK"]

        att_pct = round(att_n / total_pl * 100) if total_pl else 0
        mid_pct = round(mid_n / total_pl * 100) if total_pl else 0
        def_pct = 100 - att_pct - mid_pct

        # Average per-90 across eligible players
        # GKs use a separate formula — split eligible into outfield and GK
        eligible_out = [p for p in eligible if p.get("pos") != "GK"]
        eligible_gk  = [p for p in eligible if p.get("pos") == "GK"]

        if eligible:
            avg_mins = sum(p["minutes"] for p in eligible) / len(eligible)
        else:
            avg_mins = 0

        # Outfield weighted per-90
        if eligible_out:
            total_mins_out = sum(p["minutes"] for p in eligible_out)
            agg = {k: sum(p[k] for p in eligible_out) for k in
                   ["goals","assists","prog_passes","duels_won","tackles","pressures","interceptions"]}
            lp90 = {k: round(v * 90.0 / total_mins_out, 3) for k, v in agg.items()}
        else:
            lp90 = {k: 0.0 for k in ["goals","assists","prog_passes","duels_won","tackles","pressures","interceptions"]}

        # League composite uses outfield players only — GKs are rated separately
        # in player cards via gk_composite() but excluded from league ranking
        score = composite(lp90)

        # GK league aggregates (per 90 averaged across eligible GKs)
        if eligible_gk:
            total_gk_mins = sum(p["minutes"] for p in eligible_gk)
            gk_saves_p90  = round(sum(p["gk_saves"] for p in eligible_gk) * 90 / total_gk_mins, 2)
            gk_ga_p90     = round(sum(p["gk_ga"]    for p in eligible_gk) * 90 / total_gk_mins, 2)
            gk_cs_rate    = round(sum(p["gk_cs"]    for p in eligible_gk) / (total_gk_mins / 90), 2)
            gk_save_pct   = round(sum(p["gk_save_pct"] for p in eligible_gk) / len(eligible_gk), 1)
        else:
            gk_saves_p90 = gk_ga_p90 = gk_cs_rate = gk_save_pct = None

        # avg_player_rating
        avg_rating = None
        if not eliminated or lid not in eliminated:
            if avg_mins > MIN_MINUTES:
                avg_rating = round(score / (avg_mins / 90), 2)

        # Build player list
        player_list = sorted(all_players, key=lambda p: p["minutes"], reverse=True)
        player_dicts = []
        for p in player_list:
            p90 = per90(p)
            player_dicts.append({
                "name":          p["name"],
                "nationality":   p.get("nation", ""),
                "club":          p.get("squad", ""),
                "league_id":     lid,
                "position":      p.get("pos", "MID"),
                "minutes":       p["minutes"],
                "goals":         p["goals"],
                "assists":       p["assists"],
                "prog_passes":   p["prog_passes"],
                "duels_won":     p["duels_won"],
                "tackles":       p["tackles"],
                "pressures":     p["pressures"],
                "interceptions": p["interceptions"],
                "rating":        gk_composite(p) if p.get("pos") == "GK" else round(composite(p90), 2),
                "gk_saves":      p.get("gk_saves", 0),
                "gk_ga":         p.get("gk_ga", 0),
                "gk_cs":         p.get("gk_cs", 0),
                "gk_save_pct":   p.get("gk_save_pct", 0.0),
            })

        results.append({
            **league_meta,
            "players_total":    total_pl,
            "players_eligible": n_elig,
            "eligible_flag":    n_elig < 5,
            "avg_mins_per_eligible": round(avg_mins, 1),
            "att_n": att_n, "mid_n": mid_n, "def_n": def_n,
            "att_pct": att_pct, "mid_pct": mid_pct, "def_pct": def_pct,
            "goals_p90":         lp90["goals"],
            "assists_p90":       lp90["assists"],
            "prog_pass_p90":     lp90["prog_passes"],
            "duels_won_p90":     lp90["duels_won"],
            "tackles_p90":       lp90["tackles"],
            "pressures_p90":     lp90["pressures"],
            "interceptions_p90": lp90["interceptions"],
            "composite_score":   score,
            "avg_player_rating": avg_rating,
            "gk_saves_p90":      gk_saves_p90,
            "gk_ga_p90":         gk_ga_p90,
            "gk_cs_rate":        gk_cs_rate,
            "gk_save_pct":       gk_save_pct,
            "eliminated":        lid in eliminated,
            "players":           player_dicts,
        })

    results.sort(key=lambda l: l["composite_score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(snap: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    leagues = snap["leagues"]

    if not leagues:
        errors.append("No leagues in snapshot")

    scores = [l["composite_score"] for l in leagues if not l["eliminated"]]
    if scores != sorted(scores, reverse=True):
        errors.append("Leagues not sorted by composite_score desc")

    for l in leagues:
        if l["composite_score"] < 0:
            errors.append(f"{l['id']}: negative composite score")
        if l["players_total"] == 0:
            warnings.append(f"{l['id']}: zero players")
        total_pct = l["att_pct"] + l["mid_pct"] + l["def_pct"]
        if abs(total_pct - 100) > 2:
            warnings.append(f"{l['id']}: positional pct sum = {total_pct}")
        if l["goals_p90"] > 2.0:
            warnings.append(f"{l['id']}: goals/90 = {l['goals_p90']} (high)")
        if l["pressures_p90"] > 40.0:
            warnings.append(f"{l['id']}: pressures/90 = {l['pressures_p90']} (high)")

    return errors, warnings


# ---------------------------------------------------------------------------
# Build one snapshot
# ---------------------------------------------------------------------------

def build_snapshot(snap_id: str, phase: str, date_str: str, view: str,
                   players: list[dict], lookup: dict, eliminated: set[str],
                   previous_id: str | None = None) -> dict:
    leagues = aggregate_leagues(players, lookup, eliminated)
    snap = {
        "snapshot_id":       snap_id,
        "phase":             phase,
        "date":              date_str,
        "view":              view,
        "generated_at":      datetime.utcnow().isoformat() + "Z",
        "previous_snapshot": previous_id,
        "leagues":           leagues,
    }
    return snap


def write_snapshot(snap: dict) -> Path:
    path = SNAPS / f"{snap['snapshot_id']}.json"
    with open(path, "w") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", help="Build only this snapshot_id")
    parser.add_argument("--validate", action="store_true", help="Validate existing snapshots")
    parser.add_argument("--as-of", dest="as_of", help="Treat today as this date (YYYY-MM-DD). Use if running after midnight for previous day's data.")
    args = parser.parse_args()

    players = load_players()
    lookup  = load_lookup()
    schedule = load_schedule()

    print(f"Loaded {len(players)} players, {len(lookup)} club mappings.")

    # Check for unmapped clubs
    unmapped = set()
    for p in players:
        club = p.get("club") or p.get("squad", "")
        if club and club not in lookup:
            unmapped.add(club)
    if unmapped:
        print(f"\nWARNING: {len(unmapped)} clubs not in lookup:")
        for c in sorted(unmapped)[:20]:
            print(f"  {c!r}")
        if len(unmapped) > 20:
            print(f"  ... and {len(unmapped)-20} more. Run scripts/check_clubs.py for full list.")

    if args.as_of:
        today = args.as_of
        print(f"  ⚠ Running with --as-of {today} (manual override)")
    else:
        # Use the date the FBref data was fetched, not today's clock date.
        # This handles the case where FBref updates late and you run the
        # pipeline after midnight — the data still belongs to the previous day.
        raw_path = BASE / "data" / "players" / "wc2026_raw.json"
        try:
            fetched_at = json.loads(raw_path.read_text())["fetched_at"]
            fetch_date = date.fromisoformat(fetched_at[:10])
            # FBref data always reflects the previous day's matches
            today = (fetch_date - __import__('datetime').timedelta(days=1)).isoformat()
            print(f"  Fetch date: {fetch_date} → allocating to previous day: {today}")
        except Exception:
            today = date.today().isoformat()
            print(f"  Could not read fetch date — using today: {today}")
    previous_id = None
    built = 0

    # Group stage — cumulative snapshots
    for day in schedule["group_stage_days"]:
        sid = day["snapshot_id"]
        if args.snapshot and sid != args.snapshot:
            continue
        if day["date"] > today:
            print(f"  Skipping {sid} (future: {day['date']})")
            continue
        out_path = SNAPS / f"{sid}.json"
        if out_path.exists() and not args.snapshot:
            print(f"  Frozen  {sid} (already built — use --snapshot {sid} to rebuild)")
            previous_id = sid
            built += 1
            continue

        snap = build_snapshot(
            snap_id=sid,
            phase=day["phase"],
            date_str=day["date"],
            view="cumulative",
            players=players,
            lookup=lookup,
            eliminated=set(),
            previous_id=previous_id,
        )

        errors, warnings = validate(snap)
        for e in errors:
            print(f"  ERROR [{sid}]: {e}")
        for w in warnings:
            print(f"  WARN  [{sid}]: {w}")

        if not errors:
            path = write_snapshot(snap)
            print(f"  ✓ {sid} → {path.name}  ({len(snap['leagues'])} leagues)")
            built += 1
            previous_id = sid
        else:
            print(f"  ✗ {sid} BLOCKED by {len(errors)} error(s)")

    print(f"\nBuilt {built} snapshots → {SNAPS}")

    if args.validate:
        print("\nValidating all existing snapshots...")
        for p in sorted(SNAPS.glob("*.json")):
            with open(p) as f:
                snap = json.load(f)
            errs, warns = validate(snap)
            status = "OK" if not errs else f"ERRORS: {errs}"
            print(f"  {p.name}: {status}  ({len(warns)} warnings)")


if __name__ == "__main__":
    main()
