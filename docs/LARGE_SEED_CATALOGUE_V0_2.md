# Large creator and hashtag discovery seed catalogue v0.2

Prepared 23 November 2026. This release builds large, auditable discovery candidate lists for Phase 4/5. It does not create training examples.

## Build the creator/account lists

You can run this builder directly from the repository root; it uses the committed v0.2 compositional hashtag catalogue. The builder automatically merges the compact 291-handle Gemini/other-AI creator lead CSV checked into `data/research_catalogue/` and the checked-in 100-handle Instagram starter file. To additionally merge the full 300-record creator catalogue with its complete notes, install the full research catalogue v0.1 first using the installer from PR #31:

    python scripts/build_large_seed_catalogue.py --research-dir data/research_catalogue/v0.1 --output-dir data/generated_seed_catalogue/v0.2 --youtube-limit 10000 --instagram-limit 10000 --hashtag-target 10650

The YouTube builder reads evenly spaced pages from the Hugging Face dataset viewer and does not download the full multi-GB Parquet. The Instagram builder downloads the latest.csv snapshot. It emits separate YouTube channels, all Instagram account candidates, person-only Instagram candidates, organization/publisher candidates, plain-text seed lists, and QA_SUMMARY.json.

## Automatic GitHub Actions build

Opening this PR runs `.github/workflows/large-seed-catalogue.yml`. The workflow builds 10,000 YouTube channel candidates and 10,000 Instagram account candidates from the public datasets, then uploads the generated CSVs and QA summary as the `shorts-lm-large-seed-catalogue-v0.2` workflow artifact. The Instagram `person` subset is reported separately and is never padded with organization accounts if fewer than 10,000 people are present.

## Rate limits and optional Hugging Face token

The builder spaces requests by 2.5 seconds, honours the server's `Retry-After` header, and applies bounded exponential backoff to transient failures. Hugging Face recommends passing an `HF_TOKEN` and spreading requests over time when using its Hub endpoints. To improve the anonymous quota in GitHub Actions, create a read-only Hugging Face access token and add it to the repository as an Actions secret named `HF_TOKEN`. The workflow passes it only as an environment variable; it is never written to a file or CSV. The builder still works without it, subject to the public anonymous rate limit.

## Sources

- YouTube: ScrapeExchange/youtube-channel-7m-plus, 7,264,739 channel rows, CC BY-SA 4.0 compilation; underlying creator/platform material remains subject to its own terms and rights. https://huggingface.co/datasets/ScrapeExchange/youtube-channel-7m-plus
- Instagram: arh1p/instagram-top-accounts, ranked account snapshot with person/org type, CC BY 4.0. https://huggingface.co/datasets/arh1p/instagram-top-accounts
- AI/repository leads: the submitted Gemini and other-AI catalogue outputs, retained as leads pending independent recheck.

## Count and identity semantics

A 10,000-row platform file means 10,000 account/channel records after platform-level deduplication, not 10,000 verified individual humans. YouTube source entity type is unknown. Instagram person and organization rows are separated. No cross-platform accounts are merged into unique human identities without explicit identity-link evidence. Report account counts, person counts, organization counts and unique-human counts separately.

## Hashtag semantics

data/research_catalogue/hashtags_generated_compositional_v0.2.csv contains 10,650 unique candidates from 71 language/community scopes x 30 domain labels x five deterministic forms. All are marked GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE; frequency is unmeasured and native-speaker review is pending. The category portion is English taxonomy text appended to a language slug, not a translation or evidence of native usage.

## Rights and Phase 4/5 constraints

Neither public visibility nor the dataset compilation license authorizes video downloads, storage, OCR/ASR, derived-artifact retention or model training. Account rows remain NOT_ASSESSED_DISCOVERY_ONLY and Shorts/Reels activity is NOT_VERIFIED. Each video requires item-specific rights evidence. Ten thousand account leads do not guarantee ten million eligible unique videos; actual yield depends on active publishing, accessible inventory, duplicate rates, rights, platform access and processing quality.
