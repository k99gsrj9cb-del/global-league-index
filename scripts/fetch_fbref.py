"""
FBref scraper for 2026 FIFA World Cup player stats.
Outputs: data/players/wc2026_raw.json

Rate limit: 3s between requests (per fbref robots.txt).
Run: python scripts/fetch_fbref.py
"""
from __future__ import annotations
import json, time, re, sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
import gzip, io
from html.parser import HTMLParser

BASE = Path(__file__).parent.parent
OUT  = BASE / "data" / "players"
RAW  = BASE / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

FBREF_ROOT = "https://fbref.com"
COMP_URL   = f"{FBREF_ROOT}/en/comps/1/2026/2026-FIFA-World-Cup-Stats"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

DELAY = 3.2  # seconds between requests


def get(url: str) -> str:
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.info().get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"  HTTP {e.code}: {url}", file=sys.stderr)
        raise
    except URLError as e:
        print(f"  URLError: {e.reason}: {url}", file=sys.stderr)
        raise


# ---------------------------------------------------------------------------
# Minimal HTML table parser – avoids heavy deps (bs4/lxml)
# ---------------------------------------------------------------------------

class TableParser(HTMLParser):
    """Extract all <table id="..."> elements as lists of row-dicts."""

    def __init__(self):
        super().__init__()
        self.tables: dict[str, list[dict]] = {}
        self._cur_id: str | None = None
        self._headers: list[str] = []
        self._header_rows: list[list[str]] = []  # all thead rows; we use the last
        self._row: list[str] = []
        self._cur_header_row: list[str] = []
        self._in_thead = False
        self._in_tbody = False
        self._in_th = False
        self._in_td = False
        self._cell_buf = ""
        self._skip_table = False
        self._depth = 0  # nested table depth

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                tid = attrs.get("id", "")
                if tid:
                    self._cur_id = tid
                    self.tables[tid] = []
                    self._headers = []
                    self._header_rows = []
                    self._skip_table = False
                else:
                    self._skip_table = True
        elif tag == "thead":
            self._in_thead = True
            self._header_rows = []
        elif tag == "tbody":
            self._in_tbody = True
        elif tag == "th" and self._in_thead and not self._skip_table:
            self._in_th = True
            self._cell_buf = ""
        elif tag == "th" and self._in_tbody and not self._skip_table:
            # FBref uses <th scope="row"> for Rk/Player cells in data rows — treat as <td>
            self._in_td = True
            self._cell_buf = ""
        elif tag == "tr":
            self._row = []
            self._cur_header_row = []
        elif tag == "td" and self._in_tbody and not self._skip_table:
            self._in_td = True
            self._cell_buf = ""

    def handle_endtag(self, tag):
        if tag == "table":
            if self._depth == 1:
                self._cur_id = None
                self._skip_table = False
            self._depth -= 1
        elif tag == "thead":
            self._in_thead = False
            # Use only the LAST header row (FBref has group headers in first rows)
            if self._header_rows:
                self._headers = self._header_rows[-1]
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "th" and self._in_th:
            self._in_th = False
            self._cur_header_row.append(self._cell_buf.strip())
        elif tag == "tr" and self._in_thead:
            if self._cur_header_row:
                self._header_rows.append(self._cur_header_row)
            self._cur_header_row = []
        elif tag == "tr" and self._in_tbody and self._cur_id and not self._skip_table:
            if self._row and any(self._row):
                row_dict = {}
                for i, val in enumerate(self._row):
                    key = self._headers[i] if i < len(self._headers) else f"col{i}"
                    if key not in row_dict:  # keep first occurrence (raw count, not per-90)
                        row_dict[key] = val.strip()
                self.tables[self._cur_id].append(row_dict)
            self._row = []
        elif tag in ("td", "th") and self._in_td:
            self._in_td = False
            self._row.append(self._cell_buf.strip())

    def handle_data(self, data):
        if self._in_th or self._in_td:
            self._cell_buf += data


def parse_tables(html: str) -> dict[str, list[dict]]:
    # FBref wraps player-level tables in HTML comments to block scrapers.
    # Uncomment them before parsing so our TableParser can find them.
    html = re.sub(r'<!--\s*(<table)', r'\1', html)
    html = re.sub(r'(</table>)\s*-->', r'\1', html)
    p = TableParser()
    p.feed(html)
    return p.tables


# ---------------------------------------------------------------------------
# Stat-table fetch helpers
# ---------------------------------------------------------------------------

STAT_PAGES = {
    "standard":     f"{FBREF_ROOT}/en/comps/1/2026/stats/2026-FIFA-World-Cup-Stats",
    "passing":      f"{FBREF_ROOT}/en/comps/1/2026/passing/2026-FIFA-World-Cup-Stats",
    "defense":      f"{FBREF_ROOT}/en/comps/1/2026/defense/2026-FIFA-World-Cup-Stats",
    "misc":         f"{FBREF_ROOT}/en/comps/1/2026/misc/2026-FIFA-World-Cup-Stats",
    "possession":   f"{FBREF_ROOT}/en/comps/1/2026/possession/2026-FIFA-World-Cup-Stats",
    "keepers":      f"{FBREF_ROOT}/en/comps/1/2026/keepers/2026-FIFA-World-Cup-Stats",
}

# FBref column name → our field name mapping per page
FIELD_MAP = {
    "standard": {
        "Player":  "name",
        "Squad":   "nation",   # FBref: Squad = national team (e.g. "tn Tunisia")
        "Club":    "squad",    # FBref: Club  = club side (e.g. "Al Ain")
        "Pos":     "pos",
        "90s":     "nineties",
        "MP":      "mp",
        "Min":     "minutes",
        "Gls":     "goals",
        "Ast":     "assists",
        "G+A":     "ga",
    },
    "passing": {
        "Player":  "name",
        "Squad":   "nation",
        "PrgP":    "prog_passes",
    },
    "possession": {
        "Player":  "name",
        "Squad":   "nation",
        "PrgP":    "prog_passes",   # progressive passes (if not already set)
        "Press":   "pressures",
        "Won":     "duels_won",
        "Att":     "duels_att",
    },
    "defense": {
        "Player":  "name",
        "Squad":   "nation",
        "Tkl":     "tackles",
        "TklW":    "tackles_won",
        "Int":     "interceptions",
    },
    "misc": {
        "Player":  "name",
        "Squad":   "nation",
        "Press":   "pressures",
        "Won":     "duels_won",
        "Int":     "interceptions_misc",
    },
    "keepers": {
        "Player":  "name",
        "Squad":   "nation",
        "GA":      "gk_ga",        # goals against
        "SoTA":    "gk_sota",      # shots on target against
        "Saves":   "gk_saves",     # saves
        "CS":      "gk_cs",        # clean sheets
        "Save%":   "gk_save_pct",  # save percentage
    },
}

# FBref table id prefixes we want (they include the competition id)
TABLE_ID_PATTERNS = {
    "standard":   "stats_standard",
    "passing":    "stats_passing",
    "defense":    "stats_defense",
    "misc":       "stats_misc",
    "possession": "stats_possession",
    "keepers":    "stats_keeper",
}


def find_table(tables: dict, pattern: str) -> list[dict] | None:
    for tid, rows in tables.items():
        if pattern in tid:
            return rows
    return None


def safe_float(val: str) -> float:
    try:
        return float(val.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def safe_int(val: str) -> int:
    try:
        return int(float(val.replace(",", "")))
    except (ValueError, AttributeError):
        return 0


def extract(rows: list[dict], field_map: dict) -> dict[tuple, dict]:
    """Return {(name, nation_raw): {field: value}} for non-header rows."""
    out = {}
    for row in rows:
        name = row.get("Player", "").strip()
        nation_raw = row.get("Squad", "").strip()  # Squad = national team on WC pages
        if not name or name == "Player":  # skip repeated headers
            continue
        key = (name, nation_raw)
        mapped = {}
        for col, field in field_map.items():
            if col in row:
                mapped[field] = row[col]
        out[key] = mapped
    return out


# ---------------------------------------------------------------------------
# Main scrape
# ---------------------------------------------------------------------------

def scrape_all() -> list[dict]:
    print("Fetching FBref 2026 World Cup stats...")
    all_data: dict[tuple, dict] = {}

    for page_name, url in STAT_PAGES.items():
        # Use local file if it exists (avoids 403 from FBref bot detection)
        local_file = RAW / f"fbref_{page_name}.html"
        if local_file.exists():
            print(f"  [{page_name}] Reading local file: {local_file.name}")
            html = local_file.read_text(encoding="utf-8", errors="replace")
        else:
            print(f"  [{page_name}] {url}")
            try:
                html = get(url)
            except Exception:
                print(f"  Skipping {page_name} due to error.")
                time.sleep(DELAY)
                continue
            time.sleep(DELAY)

        tables = parse_tables(html)
        pattern = TABLE_ID_PATTERNS[page_name]
        rows = find_table(tables, pattern)

        if not rows:
            print(f"  Warning: no table matching '{pattern}' found on {page_name} page.")
            for tid in list(tables.keys())[:5]:
                print(f"    Available table id: {tid} ({len(tables[tid])} rows)")
        else:
            fmap = FIELD_MAP[page_name]
            extracted = extract(rows, fmap)
            print(f"    Found {len(extracted)} player rows.")
            if rows:
                print(f"    Columns: {list(rows[0].keys())[:15]}")
            if extracted:
                sample_key = next(iter(extracted))
                print(f"    Sample row: {extracted[sample_key]}")
            for key, fields in extracted.items():
                if key not in all_data:
                    all_data[key] = {"name": key[0], "nation_raw": key[1]}
                all_data[key].update(fields)

    # Normalise to list and compute per-90 fields
    players = []
    for (name, nation_raw), p in all_data.items():
        minutes = safe_int(p.get("minutes", "0"))
        if minutes == 0:
            continue

        # FBref "Pos" is like "FW,MF" — simplify
        raw_pos = p.get("pos", "")
        pos = _norm_pos(raw_pos)

        # Nation: FBref gives "xx CountryName" e.g. "tn Tunisia" → "TUN"
        nation_str = p.get("nation", nation_raw).strip()
        if " " in nation_str:
            nation = nation_str.split()[-1].upper()   # "Tunisia" → "TUNISIA" (we'll keep full name)
            nation = nation_str.split(None, 1)[-1]    # keep "Tunisia" as readable name
        else:
            nation = nation_str

        # Club: from "Club" column on standard page.
        # FBref prefixes with rank+country e.g. "1.fr Nice" → strip to "Nice"
        club_raw = p.get("squad", "").strip()
        club = re.sub(r'^\d+\.[a-z]{2,3}\s+', '', club_raw).strip() or club_raw

        players.append({
            "name":         name,
            "squad":        club,
            "nation":       nation,
            "pos":          pos,
            "pos_raw":      raw_pos,
            "minutes":      minutes,
            "goals":        safe_int(p.get("goals", "0")),
            "assists":      safe_int(p.get("assists", "0")),
            "prog_passes":  safe_int(p.get("prog_passes", "0")),
            "tackles":      safe_int(p.get("tackles_won", p.get("tackles", "0"))),
            "pressures":    safe_int(p.get("pressures", "0")),
            "interceptions":safe_int(p.get("interceptions", "0")),
            "duels_won":    safe_int(p.get("duels_won", "0")),
            "mp":           safe_int(p.get("mp", "0")),
            # GK-specific fields (zero for outfield players)
            "gk_saves":     safe_int(p.get("gk_saves", "0")),
            "gk_ga":        safe_int(p.get("gk_ga", "0")),
            "gk_sota":      safe_int(p.get("gk_sota", "0")),
            "gk_cs":        safe_int(p.get("gk_cs", "0")),
            "gk_save_pct":  safe_float(p.get("gk_save_pct", "0")),
        })

    players.sort(key=lambda p: p["minutes"], reverse=True)
    print(f"\nTotal players with minutes > 0: {len(players)}")
    return players


def _norm_pos(raw: str) -> str:
    raw = raw.upper()
    if "GK" in raw:
        return "GK"
    if "FW" in raw:
        return "ATT"
    if "MF" in raw:
        return "MID"
    if "DF" in raw:
        return "DEF"
    return "MID"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    players = scrape_all()

    out_path = OUT / "wc2026_raw.json"
    with open(out_path, "w") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "player_count": len(players),
                   "players": players}, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(players)} players → {out_path}")
    print("\nSample (top 5 by minutes):")
    for p in players[:5]:
        print(f"  {p['name']} ({p['squad']}) {p['minutes']}' G:{p['goals']} A:{p['assists']}")
