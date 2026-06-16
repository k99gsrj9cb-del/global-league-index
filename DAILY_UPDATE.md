# GLI Daily Update Checklist

Do this once per day, ideally in the morning after overnight matches.

---

## Step 1 — Save the 5 FBref pages

For each URL below:
1. Open the link in Chrome
2. Wait for the page to fully load (you'll see a table of player names)
3. Press **Cmd+Option+I** → click **Console** tab
4. Click in the console, paste this and press Enter:
   ```
   copy(document.documentElement.outerHTML)
   ```
5. Open **TextEdit** → Cmd+N → Cmd+V to paste
6. Go to **Format → Make Plain Text**
7. Save into `Documents/GLOBAL LEAGUE INDEX/CODE/data/raw/` with the filename shown

| # | URL | Save as |
|---|-----|---------|
| 1 | https://fbref.com/en/comps/1/2026/stats/2026-FIFA-World-Cup-Stats | `fbref_standard.html` |
| 2 | https://fbref.com/en/comps/1/2026/passing/2026-FIFA-World-Cup-Stats | `fbref_passing.html` |
| 3 | https://fbref.com/en/comps/1/2026/defense/2026-FIFA-World-Cup-Stats | `fbref_defense.html` |
| 4 | https://fbref.com/en/comps/1/2026/misc/2026-FIFA-World-Cup-Stats | `fbref_misc.html` |
| 5 | https://fbref.com/en/comps/1/2026/possession/2026-FIFA-World-Cup-Stats | `fbref_possession.html` |
| 6 | https://fbref.com/en/comps/1/2026/keepers/2026-FIFA-World-Cup-Stats | `fbref_keepers.html` |

When TextEdit asks if you want to replace the existing file, click **Replace**.

---

## Step 2 — Run the pipeline

Open Terminal and run these three commands (one at a time, wait for each to finish):

```
cd "/Users/timmillar/Documents/GLOBAL LEAGUE INDEX/CODE"
```
```
python3 scripts/fetch_fbref.py
```
```
python3 scripts/build_snapshots.py
```
```
python3 scripts/update_manifest.py
```

You should see "Updated manifest: current_snapshot = group_dX" at the end.

---

## Step 3 — Check for new clubs

After fetching, run:
```
python3 scripts/check_clubs.py
```

If it says **"Missing from lookup: 0"** you're done.

If there are missing clubs, add them to `data/club_league_lookup.json` then re-run `build_snapshots.py` and `update_manifest.py`.

---

## Step 4 — Preview locally (optional)

```
python3 -m http.server 8000
```

Then open `http://localhost:8000` to check everything looks right. Press Ctrl+C when done.

---

## Step 5 — Push to GitHub (once repo is set up)

```
git add data/
git commit -m "data: update group_dX"
git push
```

Your live site will update automatically within a minute.
