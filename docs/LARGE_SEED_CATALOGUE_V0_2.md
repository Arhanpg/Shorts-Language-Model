# Large creator and hashtag discovery seed catalogue v0.2

Prepared 23 November 2026. This release builds large, auditable discovery candidate lists for Phase 4/5. It does not create training examples.

## Build the creator/account lists

Install the full research catalogue v0.1 first using the installer from PR #31, then run from the repository root:

    python scripts/build_large_seed_catalogue.py --research-dir data/research_catalogue/v0.1 --output-dir data/generated_seed_catalogue/v0.2 --youtube-limit 10000 --instagram-limit 10000 --hashtag-target 10650

The YouTube builder reads evenly spaced pages from the Hugging Face dataset viewer and does not download the full multi-GB Parquet. The Instagram builder downloads the latest.csv snapshot. It emits separate YouTube channels, all Instagram account candidates, person-only Instagram candidates, organization/publisher candidates, plain-text seed lists, and QA_SUMMARY.json.

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
