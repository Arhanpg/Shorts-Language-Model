# India-focused creator and hashtag catalogue v1.0

**Status:** source-backed discovery candidate builder. Run it locally to materialize the lists.  
**Output directory:** data/seed_catalogue/india_v1/  
**Scope:** India country-linked creator accounts plus Indian-language/topic hashtag candidates.

## Targets

- Up to 1,500 Instagram accounts.
- Up to 1,500 YouTube channels.
- 1,500 India/language/topic hashtag candidates.

The builder does not fabricate accounts to meet a numeric target. If a source returns fewer eligible records, the QA report records the actual count. The list is a discovery seed, not a verified registry of active Reels/Shorts creators.

## Source inputs

1. **Instagram top accounts:** https://huggingface.co/datasets/arh1p/instagram-top-accounts. The builder filters country == IN and accounts whose countries field includes IN. Its schema distinguishes people and organizations. The dataset card describes this as a follower-ranked snapshot sourced from Wikidata usernames and a hand-maintained list. It is not a full census of Indian creators.
2. **YouTube channel inventory:** https://huggingface.co/datasets/ScrapeExchange/youtube-channel-7m-plus. The builder uses the Hugging Face Dataset Viewer /filter endpoint for country == India OR country == IN, avoiding a download of the 10.6 GB Parquet. The viewer warns that filters on datasets over 5 GB may be partial; the report records partial_index.
3. **Supplemental India creator index:** https://huggingface.co/datasets/Shikha180224/dexfluence-indian-creator-index. The script reads the public Dataset Viewer rows and includes only Instagram/YouTube rows with a country field of IN/India. Its reported verification/authenticity fields are not independently verified by ShortsLM.
4. **Hashtag vocabulary:** curated topic families and regional-language roots in the script. Tags are compositional search candidates, not claims of measured popularity or native usage.

Source documentation: https://huggingface.co/docs/dataset-viewer/en/filter. Its filter endpoint supports country predicates and paged results; the documentation explicitly notes that large-dataset filtering may be partial.

## Diversity scope

The hashtag generator round-robins across 17 language/community scopes so that the first 1,500 do not come only from Hindi/English. It includes Hindi, Marathi, Gujarati, Kannada, Telugu, Tamil, Malayalam, Bhojpuri, Bengali, Punjabi, Odia, Assamese, Kashmiri, Urdu, Konkani, Manipuri and English-India discovery terms.

Topic families include:
- Film, television, actors, actresses, cinema and music
- Cricket, football, hockey, badminton, kabaddi, wrestling, athletics, women's sports and fitness
- Women-focused creator topics, women in business/technology/education and empowerment
- Miss World, Miss Universe, pageants, modelling and beauty
- Education, school, competitive exams, UPSC, NEET, JEE, mathematics, science and coding
- Comedy, memes, skits and stand-up
- Motivation, careers, business and entrepreneurship
- Politics, public figures, politicians, news, elections, governance and civic information
- Regional television, serials, folklore and regional cinema
- Food, cooking, street food and regional cuisine
- Travel, tourism, heritage, festivals and culture
- Fashion, beauty, makeup and lifestyle
- Technology, gadgets, AI and startups
- Gaming, esports, cartoons, animation and storytelling
- Agriculture, farming and rural life

Creator datasets have much less language and regional metadata than the hashtag taxonomy. The builder does **not** infer a creator's language from their name or country. Unknown language stays und; categories are source-provided where available. A future live verification pass should annotate primary language, state/region, content category, active short-form status and audience evidence.

## Build

From the repository root in PowerShell:

~~~powershell
python scripts/build_india_seed_catalogue.py `
  --instagram-limit 1500 `
  --youtube-limit 1500 `
  --hashtag-target 1500
~~~

No Hugging Face account/token is required for public sources. If anonymous Dataset Viewer limits cause 429 responses, the script respects Retry-After and retries; you can optionally set a read-only HF_TOKEN environment variable. Do not put tokens in command history or commit them.

Output files:

| File | Contents |
|---|---|
| instagram_account_candidates.csv | India-linked Instagram accounts, person/org type retained |
| instagram_person_candidates.csv | Person-only Instagram rows |
| instagram_organization_publisher_candidates.csv | Organization/publisher rows |
| youtube_channel_candidates.csv | India-country-matched YouTube channels |
| hashtags_master_candidates.csv | Balanced Indian language/topic hashtag candidates |
| hashtags_generated_candidates.csv | Same generated candidate list for compatibility with existing catalogue tooling |
| instagram_creator_seeds.txt | Instagram handles |
| youtube_creator_seeds.txt | YouTube channel URLs |
| india_hashtags.txt | Hashtags |
| QA_SUMMARY.json | Exact counts, source metadata, partial-index flag and limitations |

If creator counts are below 1,000, do not pad with non-Indian or invented accounts. Review QA_SUMMARY.json; the next step is a source-backed regional creator research pass, not synthetic names.

## Collect URLs only

The existing URL collector accepts this catalogue schema and keeps its metadata-only behavior. It writes to a separate India output directory and database so the global URL inventories are not mixed.

### YouTube Shorts

~~~powershell
shorts-lm urls collect `
  --catalogue-dir data/seed_catalogue/india_v1 `
  --database .shortslm/india-url-discovery.sqlite3 `
  --output-dir data/discovered_urls/india `
  --report-dir outputs/url-collection/india `
  --platforms youtube
~~~

### Instagram Reels

Sign in once using the existing dedicated ShortsLM browser profile, if not already signed in:

~~~powershell
shorts-lm discover instagram-browser-login
~~~

Then run:

~~~powershell
shorts-lm urls collect `
  --catalogue-dir data/seed_catalogue/india_v1 `
  --database .shortslm/india-url-discovery.sqlite3 `
  --output-dir data/discovered_urls/india `
  --report-dir outputs/url-collection/india `
  --platforms instagram
~~~

### Both platforms in one run

~~~powershell
shorts-lm urls collect `
  --catalogue-dir data/seed_catalogue/india_v1 `
  --database .shortslm/india-url-discovery.sqlite3 `
  --output-dir data/discovered_urls/india `
  --report-dir outputs/url-collection/india `
  --platforms all
~~~

Outputs:
- data/discovered_urls/india/instagram_reels.txt
- data/discovered_urls/india/youtube_shorts.txt

The YouTube collector uses yt-dlp flat metadata extraction; Instagram uses the visible Playwright browser workflow. These commands discover URLs only. They do not download media or run ASR/OCR/feature extraction. If a platform returns a login challenge, CAPTCHA, 403/429 or rate limit, stop and resume only when normal access is available. Do not bypass restrictions or rotate accounts/proxies.

## Review and limitations

- Country is a source metadata field, not proof of Indian audience share.
- Dataset-level verification claims are not independently confirmed.
- Current Reels/Shorts activity is not guaranteed; live recheck is needed.
- Follower count is not a quality or virality label.
- Hashtag frequency and retrieval yield are unmeasured.
- A public account listing does not grant media retrieval, retention, analysis or model-training rights.
- The YouTube source is a large compilation and the Dataset Viewer may expose a partial index; inspect the QA report.
- Keep source attribution and license information with derived lists. Recheck licenses and terms at use time.
