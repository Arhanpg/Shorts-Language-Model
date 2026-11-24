#!/usr/bin/env python3
"""Build a separate India-scoped ShortsLM creator and hashtag discovery catalogue.

The builder filters existing public account-candidate snapshots; it never fabricates
creator identities or fills shortages with non-Indian accounts. Hashtags are
compositional discovery hypotheses, not measured/popular tags.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ACCOUNT_FIELDS = [
    "account_id", "platform", "account_handle", "account_url", "display_name",
    "entity_type", "country", "region", "language", "category", "followers_count",
    "videos_count", "views_count", "rank", "joined_date", "source_dataset",
    "source_url", "source_license", "source_observed_at", "discovery_status",
    "short_form_status", "rights_status", "last_independent_verification_at", "notes",
]
TAG_FIELDS = [
    "hashtag_id", "hashtag", "normalized_hashtag", "language", "language_code",
    "category", "candidate_platform_scope", "generation_rule", "verification_state",
    "frequency_measured_at", "native_speaker_review_status", "source_url", "notes",
]

INDIA_NAMES = {"india", "bharat", "भारत", "in", "ind"}
LANGUAGES = [
    ("Hindi", "hi"), ("Tamil", "ta"), ("Telugu", "te"), ("Malayalam", "ml"),
    ("Kannada", "kn"), ("Marathi", "mr"), ("Gujarati", "gu"), ("Bengali", "bn"),
    ("Punjabi", "pa"), ("Bhojpuri", "bho"), ("Haryanvi", "bgc"),
    ("Odia", "or"), ("Assamese", "as"), ("Rajasthani", "raj"), ("Urdu", "ur"),
]
CATEGORIES = [
    "sports", "cricket", "football", "badminton", "kabaddi", "fitness",
    "womencreators", "beauty", "fashion", "cinema", "actors", "actresses",
    "music", "dance", "comedy", "education", "upsc", "technology", "gaming",
    "cooking", "travel", "politics", "news", "motivation", "spirituality",
    "cartoons", "kids", "agriculture", "finance", "regionalculture",
]
TAG_FORMS = [
    ("language_category", "{language}{category}"),
    ("language_category_reels", "{language}{category}reels"),
    ("category_language_shorts", "{category}{language}shorts"),
    ("language_category_india", "{language}{category}india"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_india(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", (value or "").strip().casefold())
    return normalized in INDIA_NAMES


def is_indian_row(row: dict[str, str]) -> bool:
    # Country is the only inclusion criterion. Region/language/name are not
    # treated as proof of nationality or audience geography.
    return is_india(row.get("country", ""))


def account_key(row: dict[str, str]) -> str:
    return (row.get("account_handle") or row.get("account_url") or row.get("account_id") or "").strip().casefold().lstrip("@")


def bucket_key(row: dict[str, str]) -> tuple[str, str]:
    language = (row.get("language") or "und").strip().casefold() or "und"
    category = (row.get("category") or "uncategorized").strip().casefold() or "uncategorized"
    return language, category


def round_robin(rows: Iterable[dict[str, str]], limit: int) -> list[dict[str, str]]:
    buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        key = account_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        buckets[bucket_key(row)].append(row)
    keys = sorted(buckets)
    selected: list[dict[str, str]] = []
    while keys and len(selected) < limit:
        remaining = []
        for key in keys:
            if buckets[key] and len(selected) < limit:
                selected.append(buckets[key].pop(0))
            if buckets[key]:
                remaining.append(key)
        keys = remaining
    return selected


def generate_hashtags(target: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for language, code in LANGUAGES:
        language_slug = re.sub(r"[^a-z0-9]", "", language.casefold())
        for category in CATEGORIES:
            for index, (rule, template) in enumerate(TAG_FORMS, 1):
                tag = template.format(language=language_slug, category=category)
                if tag in seen or len(tag) > 64:
                    continue
                seen.add(tag)
                rows.append({
                    "hashtag_id": f"IN_{code}_{category}_{index}",
                    "hashtag": f"#{tag}",
                    "normalized_hashtag": tag,
                    "language": language,
                    "language_code": code,
                    "category": category,
                    "candidate_platform_scope": "instagram;youtube_search_text",
                    "generation_rule": rule,
                    "verification_state": "INDIA_COMPOSITIONAL_UNVERIFIED_CANDIDATE",
                    "frequency_measured_at": "",
                    "native_speaker_review_status": "PENDING",
                    "source_url": "",
                    "notes": "India/language/category compositional search hypothesis; not evidence of native usage, popularity, trend status or retrieval yield. Review with native speakers and validate on-platform.",
                })
                if len(rows) >= target:
                    return rows
    if len(rows) < target:
        raise ValueError(f"Only {len(rows)} unique Indian hashtag candidates generated; requested {target}. No synthetic padding.")
    return rows


def build(source_dir: Path, output_dir: Path, instagram_limit: int, youtube_limit: int, hashtag_target: int) -> dict:
    ig_source = read_csv(source_dir / "instagram_account_candidates.csv")
    yt_source = read_csv(source_dir / "youtube_channel_candidates.csv")
    if not ig_source or not yt_source:
        raise FileNotFoundError(
            f"Expected instagram_account_candidates.csv and youtube_channel_candidates.csv in {source_dir}. "
            "Build the existing global v0.2 catalogue first."
        )

    ig_india = [row for row in ig_source if is_indian_row(row)]
    yt_india = [row for row in yt_source if is_indian_row(row)]
    ig = round_robin(ig_india, instagram_limit)
    yt = round_robin(yt_india, youtube_limit)

    # Never silently pad with unverified non-India rows or duplicate accounts.
    tags = generate_hashtags(hashtag_target)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "instagram_account_candidates.csv", ig, ACCOUNT_FIELDS)
    write_csv(output_dir / "youtube_channel_candidates.csv", yt, ACCOUNT_FIELDS)
    write_csv(output_dir / "hashtags_master_candidates.csv", tags, TAG_FIELDS)
    write_csv(output_dir / "hashtags_generated_candidates.csv", tags, TAG_FIELDS)

    ig_handles = [row.get("account_handle", "").strip().lstrip("@") for row in ig if row.get("account_handle")]
    yt_refs = [row.get("account_url", "").strip() or row.get("account_handle", "").strip() for row in yt]
    (output_dir / "instagram_creator_seeds.txt").write_text("".join(f"{v}\n" for v in ig_handles), encoding="utf-8")
    (output_dir / "youtube_creator_seeds.txt").write_text("".join(f"{v}\n" for v in yt_refs), encoding="utf-8")
    (output_dir / "indian_hashtags.txt").write_text("".join(f"{row['hashtag']}\n" for row in tags), encoding="utf-8")

    counts_by_language = defaultdict(int)
    counts_by_category = defaultdict(int)
    for row in ig + yt:
        counts_by_language[(row.get("language") or "und").strip() or "und"] += 1
        counts_by_category[(row.get("category") or "uncategorized").strip() or "uncategorized"] += 1

    files = [
        "instagram_account_candidates.csv", "youtube_channel_candidates.csv",
        "hashtags_master_candidates.csv", "hashtags_generated_candidates.csv",
        "instagram_creator_seeds.txt", "youtube_creator_seeds.txt", "indian_hashtags.txt",
    ]
    summary = {
        "schema_version": "shortslm.india-seed-catalogue.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "country field explicitly identifies India; no inferred nationality",
        "requested_limits": {"instagram": instagram_limit, "youtube": youtube_limit, "hashtags": hashtag_target},
        "counts": {
            "instagram_india_source_rows": len(ig_india),
            "youtube_india_source_rows": len(yt_india),
            "instagram_accounts_selected": len(ig),
            "youtube_channels_selected": len(yt),
            "hashtags_generated": len(tags),
            "instagram_target_met": len(ig) >= instagram_limit,
            "youtube_target_met": len(yt) >= youtube_limit,
        },
        "language_and_category_counts_are_source_reported_or_unknown": True,
        "language_counts": dict(sorted(counts_by_language.items())),
        "category_counts": dict(sorted(counts_by_category.items())),
        "source_files": {
            "instagram": "instagram_account_candidates.csv from global v0.2",
            "youtube": "youtube_channel_candidates.csv from global v0.2",
        },
        "sha256": {
            name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
            for name in files
        },
        "limitations": [
            "Creator rows are source dataset candidates, not independently verified active Shorts/Reels publishers.",
            "Only an explicit country field equal to India/Bharat/IN/IND is accepted; region, language, name or inferred ethnicity is not a substitute.",
            "The global source snapshots may contain fewer than the requested Indian accounts. The builder does not fabricate or top up with non-Indian accounts.",
            "Language/category labels are preserved from the source; unknown language is not guessed from creator name.",
            "YouTube source entity type may be unknown; do not claim all channel rows represent individual people.",
            "Hashtags are compositional candidates, not measured popular or trending tags. Native-speaker review and retrieval-yield testing remain required.",
            "Catalogue inclusion does not grant permission to download, retain, analyze or train on any video.",
        ],
    }
    (output_dir / "QA_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/generated_seed_catalogue/v0.2"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/indian_seed_catalogue/v0.1"))
    parser.add_argument("--instagram-limit", type=int, default=1500)
    parser.add_argument("--youtube-limit", type=int, default=1500)
    parser.add_argument("--hashtag-target", type=int, default=1500)
    args = parser.parse_args()
    if not (1 <= args.instagram_limit <= 1500 and 1 <= args.youtube_limit <= 1500 and 1 <= args.hashtag_target <= 1500):
        parser.error("each target must be between 1 and 1500")
    try:
        summary = build(args.source_dir, args.output_dir, args.instagram_limit, args.youtube_limit, args.hashtag_target)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["counts"]["instagram_target_met"] or not summary["counts"]["youtube_target_met"]:
        print("WARNING: one or more creator targets were not met from explicit India-country rows; no fabricated top-up was performed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
