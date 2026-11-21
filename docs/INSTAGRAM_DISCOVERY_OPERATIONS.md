# Instagram Discovery Operations

**Status:** Experimental browser-based discovery; live Instagram behavior must be validated on the user's own account and machine.

## Why the previous run showed 1,469 candidates and zero eligible

The prior collector mixed two different observations:
- a Reel permalink rendered in a profile grid; and
- a Reel record containing an explicit numeric play/view metric.

A permalink proves that a Reel link was visible. It does not prove its metric. The 1,469 observed records in the November 2026 run must not be described as 1,469 verified million-play Reels. Zero newly eligible means no *new* candidate passed the metric and format checks in that run. Previously eligible inventory is not counted as new.

The report now separates metric-unknown, metric-observed, above-threshold, new-inventory and newly-eligible counts. It also records source surface and per-profile/per-hashtag detail-enrichment outcomes.

## Discovery surfaces

The Instagram provider supports:
1. Creator Reels tabs: `https://www.instagram.com/<handle>/reels/`
2. Public hashtag pages: `https://www.instagram.com/explore/tags/<hashtag>/`
3. Public Reel detail pages: `https://www.instagram.com/reel/<shortcode>/`

All pages are navigated normally in one persistent, visible Chrome context per run. The user signs in manually. The collector closes each page but keeps the context alive across creator and hashtag visits. It observes ordinary browser responses and rendered Reel links. It does not build private GraphQL requests, replay captured requests, solve challenges, rotate proxies or bypass rate limits.

## Seed files

- Creator list: `data/instagram_creator_seeds.txt`
- Hashtag list: `data/instagram_hashtags.txt`

One creator or hashtag per line. Lines beginning with comments are ignored. Repeated CLI values are merged and deduplicated.

## Recommended validation sequence

### 1. Parser and offline test suite

```powershell
python -m ruff check src tests
python -m pytest -q
```

### 2. Hashtag-only browser smoke test

This avoids harvesting the default creator list. It tests two hashtags and at most five detail pages per tag.

```powershell
shorts-lm discover graph-run `
  --platform instagram `
  --instagram-seeds-file .shortslm/no-seeds.txt `
  --instagram-hashtag getreadywithme `
  --instagram-hashtag viratkohli `
  --instagram-max-hashtags 2 `
  --max-creators 0 `
  --target-new 20 `
  --max-runtime-seconds 240 `
  --instagram-max-scrolls 6 `
  --instagram-hashtag-max-reel-details 5
```

### 3. Creator-only validation

```powershell
shorts-lm discover graph-run `
  --platform instagram `
  --instagram-seeds-file .shortslm/no-seeds.txt `
  --instagram-creator taneja.gaurav `
  --instagram-creator souravjoshivlogs `
  --instagram-max-hashtags 0 `
  --max-creators 2 `
  --target-new 50 `
  --max-runtime-seconds 240 `
  --instagram-max-scrolls 8 `
  --instagram-max-reel-details 5 `
  --force
```

### 4. Broad run after the smoke tests

```powershell
shorts-lm discover graph-run `
  --platform instagram `
  --target-new 100 `
  --min-metric 1000000 `
  --max-creators 80 `
  --max-runtime-seconds 900 `
  --instagram-max-hashtags 8 `
  --instagram-max-scrolls 8 `
  --instagram-max-reel-details 3 `
  --instagram-hashtag-max-reel-details 8 `
  --force
```

## CLI controls

| Option | Default | Meaning |
|---|---:|---|
| `--instagram-hashtag` | none | Repeatable explicit hashtag |
| `--instagram-hashtags-file` | `data/instagram_hashtags.txt` | Hashtag seed file |
| `--instagram-max-hashtags` | 8 | Maximum hashtag pages per run |
| `--instagram-max-scrolls` | 8 | Maximum scroll rounds per surface |
| `--instagram-max-reel-details` | 3 | Unknown-metric detail pages per creator |
| `--instagram-hashtag-max-reel-details` | 8 | Unknown-metric detail pages per hashtag |
| `--max-creators` | 80 | Creator profiles; zero permits hashtag-only mode |
| `--max-runtime-seconds` | 600 | Whole-run wall-clock budget, capped at 900 seconds |
| `--force` | off | Requeue supplied creator seeds; does not clear candidate history |

## Metric and eligibility semantics

- Instagram play counts and view counts remain distinct fields and are reported with their source.
- Exact numeric response fields and exact numeric JSON-LD `WatchAction` / `ViewAction` counters can be retained.
- Likes are not treated as plays or views.
- Display strings such as `1.2M` are not converted into exact integers.
- A Reel link without an explicit numeric metric is stored as metric-unknown and cannot pass the threshold.
- A candidate only becomes newly eligible when it is a confirmed Reel and its platform-native numeric metric reaches the configured threshold.
- A duplicate already eligible in the database does not count as new eligible yield.

## Interpreting a run

The most useful checks are:
1. Did hashtag and creator pages load without login/checkpoint redirects?
2. How many rendered Reel links were found?
3. How many candidates had explicit numeric metrics before and after detail enrichment?
4. How many metrics were plays versus views?
5. How many were at least the threshold?
6. How many were newly eligible rather than already in the database?
7. Which surfaces produced the best metric coverage per detail-page visit?

If links are found but metric coverage remains zero after detail enrichment, the next task is to inspect the public response/JSON-LD shape captured by the browser and improve the parser with a fixture. Do not claim successful high-view discovery based on links alone.

## YouTube validation remains separate

The YouTube graph provider has a separate smoke test and should be run after the Instagram focused test:

```powershell
shorts-lm discover graph-run `
  --platform youtube `
  --target-new 20 `
  --min-metric 1000000 `
  --max-seed-queries 3 `
  --max-hashtag-queries 3 `
  --max-creators 10 `
  --max-expansions 10 `
  --max-runtime-seconds 240
```

Inspect `outputs/discovery/graph-latest.json` and verify numeric YouTube views, Shorts format evidence, creator/channel IDs, related-sequence results, and candidate persistence. Do not infer YouTube success from Instagram tests or vice versa.

## Security and rights

Public visibility does not itself grant rights to download, retain, analyze or train on a Reel. Discovery is separate from acquisition. The existing item-specific rights manifest remains mandatory for downloading and training. Never commit browser profiles, cookies, sessions, SQLite databases, downloaded videos or private reports.


## Windows browser lifecycle troubleshooting (November 2026)

The browser collector now treats Chrome shutdown as a recoverable lifecycle event:
- It checks the underlying browser connection before reusing a cached persistent context; a disconnected Chrome session is closed and relaunched once with the same profile.
- Provider shutdown is idempotent; context or Proactor pipe cleanup errors cannot replace the original collection result.
- A page-creation failure caused by an already-closed target triggers one fresh context attempt with the same profile.
- If Chrome's persistent profile is locked, an actionable message asks you to close every window using that profile and check for leftover `chrome.exe` processes. Never delete the profile or session files.
- YouTube reports include `discovery_stage_counts` to separate seed-search results, detail-enriched candidates, creator-tab candidates and related-Shorts candidates.


### Seed target vs. graph expansion

The seed bootstrap can itself meet `--target-new`. By default, this preserves the fast-stop behavior and skips the subsequent creator/related-video frontier loop. The report and terminal output now make this explicit. To keep exploring the creator graph after enough new eligible videos have been found, pass:

```powershell
shorts-lm discover graph-run --platform youtube --target-new 20 --max-creators 10 --max-expansions 10 --continue-graph-after-target
```

The run remains bounded by `--max-runtime-seconds`, `--max-creators`, and `--max-expansions`; target overshoot is expected when this option is enabled.
