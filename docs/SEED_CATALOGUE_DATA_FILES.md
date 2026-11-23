# Git-tracked seed catalogue CSVs — v0.2

This directory is populated by the materializer script and its GitHub Actions workflow.

## Included files

| File | Contents |
|---|---|
| youtube_channel_candidates.csv | 10K+ YouTube channel/account discovery candidates |
| instagram_account_candidates.csv | Instagram account candidates of all entity types |
| instagram_person_candidates.csv | Person-typed Instagram accounts |
| instagram_organization_publisher_candidates.csv | Organization/publisher Instagram accounts |
| instagram_unknown_entity_leads.csv | AI/research leads with unknown person/organization type |
| creators_ai_research_leads_v0.1.csv | Submitted Gemini/other-AI creator handle leads and source claims |
| hashtags_generated_candidates.csv | 10,650 generated language × category hashtag candidates |
| hashtags_ai_research_candidates.csv | Original submitted AI hashtag candidates and source evidence |
| hashtags_master_candidates.csv | Deduplicated union with common schema and source provenance |
| QA_SUMMARY.json | Exact counts, source run, per-CSV SHA-256, datasets and limitations |
| SOURCE_BUILD_QA_SUMMARY.json | Original upstream build summary retained unchanged |

## Provenance

The materialization workflow downloads the successful GitHub Actions artifact shorts-lm-large-seed-catalogue-v0.2 from run 45203258030 (source commit aed68d9377a26d83bedf263207c55a83a33e92e2). It copies the generated CSVs, adds the AI-sourced creator and hashtag CSVs already stored in data/research_catalogue/, derives the unknown-entity Instagram subset, and creates a combined hashtag master.

## Interpretation limits

These are discovery candidates, not independently verified creator identities or proof of current Shorts/Reels activity. Instagram person and organization records are kept separate; YouTube channel identity type is not known. AI-supplied verification statuses remain source-reported claims. Generated hashtag candidates have no measured popularity or retrieval-yield evidence until validated. Public profile visibility and dataset compilation licences do not authorize video download, storage, OCR/ASR artifact retention or model training; item-level rights evidence is still required.
