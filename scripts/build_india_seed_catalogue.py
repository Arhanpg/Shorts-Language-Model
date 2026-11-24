#!/usr/bin/env python3
"""Build an India-focused ShortsLM creator and hashtag discovery catalogue.

Sources are public tabular datasets. Creator rows remain discovery leads, not
proof of current Reels/Shorts activity or permission to retrieve/train on media.
No creator is invented to fill a target. Hashtags generated from language/topic
vocabularies are explicitly marked unverified until native-speaker review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://datasets-server.huggingface.co"
YT_DATASET = "ScrapeExchange/youtube-channel-7m-plus"
YT_CARD = f"https://huggingface.co/datasets/{YT_DATASET}"
DEX_DATASET = "Shikha180224/dexfluence-indian-creator-index"
DEX_CARD = f"https://huggingface.co/datasets/{DEX_DATASET}"
IG_URL = "https://huggingface.co/datasets/arh1p/instagram-top-accounts/resolve/main/latest.csv"
IG_CARD = "https://huggingface.co/datasets/arh1p/instagram-top-accounts"
UA = "ShortsLM-India-Catalogue/1.0 (metadata-only research)"
FIELDS = [
    "account_id", "platform", "account_handle", "account_url", "channel_id",
    "display_name", "entity_type", "country", "region", "language", "category",
    "followers_count", "videos_count", "views_count", "rank", "source_dataset",
    "source_url", "source_license", "source_observed_at", "discovery_status",
    "short_form_status", "rights_status", "last_independent_verification_at",
    "notes",
]
TAG_FIELDS = [
    "hashtag_id", "hashtag", "normalized_hashtag", "language", "language_code",
    "region_scope", "category", "candidate_platform_scope", "generation_rule",
    "verification_state", "frequency_measured_at", "native_speaker_review_status",
    "source_url", "notes",
]

# Language labels and ISO codes are catalogue scopes, not claims about each creator.
LANGUAGES = [
    ("Hindi", "hi", "हिंदी", "North/Central India"),
    ("Marathi", "mr", "मराठी", "Maharashtra"),
    ("Gujarati", "gu", "ગુજરાતી", "Gujarat"),
    ("Kannada", "kn", "ಕನ್ನಡ", "Karnataka"),
    ("Telugu", "te", "తెలుగు", "Andhra Pradesh/Telangana"),
    ("Tamil", "ta", "தமிழ்", "Tamil Nadu/Puducherry"),
    ("Malayalam", "ml", "മലയാളം", "Kerala"),
    ("Bhojpuri", "bho", "भोजपुरी", "Bihar/Eastern Uttar Pradesh"),
    ("Bengali", "bn", "বাংলা", "West Bengal/Tripura"),
    ("Punjabi", "pa", "ਪੰਜਾਬੀ", "Punjab"),
    ("Odia", "or", "ଓଡ଼ିଆ", "Odisha"),
    ("Assamese", "as", "অসমীয়া", "Assam"),
    ("Kashmiri", "ks", "کٲشُر", "Jammu and Kashmir"),
    ("Urdu", "ur", "اردو", "Multi-state"),
    ("Konkani", "kok", "कोंकणी", "Goa/Konkan"),
    ("Manipuri", "mni", "মৈতৈলোন্", "Manipur"),
    ("English-India", "en-IN", "India", "Pan-India"),
]

# Search vocabulary intentionally broad; generated combinations are not popularity claims.
TOPICS = {
    "film_tv": ["cinema", "movie", "film", "actor", "actress", "trailer", "review", "dialogue", "song", "dance"],
    "music_dance": ["music", "singer", "song", "dance", "classicaldance", "folk", "cover", "remix"],
    "sports": ["cricket", "football", "hockey", "badminton", "kabaddi", "wrestling", "athletics", "olympics", "fitness"],
    "education": ["education", "study", "exam", "upsc", "ssc", "neet", "jee", "maths", "science", "coding"],
    "comedy": ["comedy", "funny", "memes", "skit", "standup", "prank"],
    "motivation": ["motivation", "inspiration", "success", "career", "selfhelp", "business"],
    "politics_civic": ["india", "bharat", "politics", "news", "civic", "election", "publicservice"],
    "food": ["food", "recipe", "streetfood", "cooking", "indianfood", "regionalfood"],
    "travel_culture": ["travel", "tourism", "heritage", "culture", "festival", "temple", "history"],
    "fashion_beauty": ["fashion", "beauty", "makeup", "skincare", "style", "womenshealth"],
    "technology": ["technology", "tech", "gadget", "ai", "startup", "innovation"],
    "gaming_animation": ["gaming", "esports", "cartoon", "animation", "kidscontent", "storytelling"],
    "lifestyle": ["lifestyle", "family", "parenting", "fitness", "wellness", "dailyvlog"],
    "agriculture": ["agriculture", "farmer", "farming", "ruralindia", "dairy"],
}
LANG_ROOTS = {
    "hi": ["भारत", "हिंदुस्तान", "हिंदी", "क्रिकेट", "बॉलीवुड", "शिक्षा", "किसान", "खाना", "हास्य", "प्रेरणा"],
    "mr": ["महाराष्ट्र", "मराठी", "मराठीमन", "मराठीचित्रपट", "शेती", "शिक्षण", "विनोद", "किल्ले"],
    "gu": ["ગુજરાત", "ગુજરાતી", "ગુજરાતીવિડિઓ", "ગરબા", "ગુજરાતીફૂડ", "શિક્ષણ", "ખેડૂત"],
    "kn": ["ಕರ್ನಾಟಕ", "ಕನ್ನಡ", "ಕನ್ನಡಿಗ", "ಕನ್ನಡಚಿತ್ರ", "ಕನ್ನಡಹಾಡು", "ಶಿಕ್ಷಣ", "ಕೃಷಿ"],
    "te": ["తెలుగు", "తెలంగాణ", "ఆంధ్రప్రదేశ్", "టాలీవుడ్", "తెలుగుపాటలు", "విద్య", "రైతు"],
    "ta": ["தமிழ்", "தமிழ்நாடு", "கோலிவுட்", "தமிழ்பாடல்", "கல்வி", "விவசாயம்", "நகைச்சுவை"],
    "ml": ["കേരളം", "മലയാളം", "മലയാളസിനിമ", "മലയാളംപാട്ട്", "വിദ്യാഭ്യാസം", "കൃഷി"],
    "bho": ["भोजपुरी", "भोजपुरीगाना", "बिहार", "पूर्वांचल", "भोजपुरीसिनेमा"],
    "bn": ["বাংলা", "পশ্চিমবঙ্গ", "বাংলাসিনেমা", "বাংলাগান", "শিক্ষা", "কৃষি"],
    "pa": ["ਪੰਜਾਬ", "ਪੰਜਾਬੀ", "ਪੰਜਾਬੀਗਾਣੇ", "ਭੰਗੜਾ", "ਖੇਤੀ", "ਸਿੱਖਿਆ"],
    "or": ["ଓଡ଼ିଶା", "ଓଡ଼ିଆ", "ଓଡ଼ିଆଗୀତ", "ଶିକ୍ଷା", "ଚାଷ"],
    "as": ["অসম", "অসমীয়া", "অসমীয়াগীত", "শিক্ষা", "কৃষি"],
    "ks": ["کٲشُر", "کٔشیر", "کٲشِر", "تعلیم"],
    "ur": ["اردو", "ہندوستان", "تعلیم", "شاعری", "مزاح"],
    "kok": ["कोंकणी", "गोवा", "कोंकणीगीत", "कोंकण"],
    "mni": ["মৈতৈ", "মণিপুর", "মণিপুরী", "শিক্ষা"],
    "en-IN": ["india", "indian", "bharat", "desi", "madeinindia", "indianculture"],
}

def request_bytes(url: str, attempts: int = 5) -> bytes:
    last = None
    for attempt in range(attempts):
        headers = {"User-Agent": UA, "Accept": "application/json,text/csv,*/*"}
        token = os.environ.get("HF_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                return response.read()
        except HTTPError as exc:
            last = exc
            if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
            retry = exc.headers.get("Retry-After")
            try:
                delay = float(retry) if retry else min(15 * 2**attempt, 120)
            except ValueError:
                delay = min(15 * 2**attempt, 120)
            if attempt + 1 < attempts:
                print(f"HTTP {exc.code}; respecting retry delay {delay:.0f}s", file=sys.stderr)
                time.sleep(max(1, min(delay, 180)))
        except (URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt + 1 < attempts:
                delay = min(5 * 2**attempt, 60)
                print(f"Transient source error; retrying in {delay}s", file=sys.stderr)
                time.sleep(delay)
    raise RuntimeError(f"Could not fetch {url}: {last}")

def get_json(endpoint: str, params: dict) -> dict:
    url = f"{API}/{endpoint}?{urlencode(params)}"
    return json.loads(request_bytes(url).decode("utf-8"))

def rows_from_response(data: dict) -> list[dict]:
    return [x["row"] for x in data.get("rows", []) if isinstance(x, dict) and isinstance(x.get("row"), dict)]

def fetch_youtube_india(target: int, max_rows: int) -> tuple[list[dict], dict]:
    splits = get_json("splits", {"dataset": YT_DATASET})
    candidates = [x for x in splits.get("splits", []) if x.get("split") == "train"]
    if not candidates:
        raise RuntimeError("No train split found in YouTube source")
    split = next((x for x in candidates if "boinko-youtube-channel" in x.get("config", "")), candidates[0])
    config = split["config"]
    # Filter at source rather than sampling globally and guessing geography from names.
    where = '"country"=\'India\' OR "country"=\'IN\''
    result = get_json("filter", {"dataset": YT_DATASET, "config": config, "split": "train",
                                 "where": where, "offset": 0, "length": 100})
    total = int(result.get("num_rows_total") or 0)
    partial = bool(result.get("partial", False))
    found = rows_from_response(result)
    offset = len(found)
    while len({str(x.get("channel_id") or "").strip() for x in found if str(x.get("channel_id") or "").strip()}) < target and offset < total and len(found) < max_rows:
        time.sleep(1.0)
        page = get_json("filter", {"dataset": YT_DATASET, "config": config, "split": "train",
                                   "where": where, "offset": offset, "length": 100})
        batch = rows_from_response(page)
        if not batch:
            break
        found.extend(batch)
        offset += len(batch)
    # Stable dedup by channel ID; never fill gaps with non-India rows.
    unique = {}
    for row in found:
        cid = str(row.get("channel_id") or "").strip()
        if cid and cid not in unique:
            unique[cid] = row
    records = []
    for row in unique.values():
        cid = str(row.get("channel_id") or "").strip()
        handle = str(row.get("channel_handle") or "").strip().lstrip("@")
        url = str(row.get("url") or row.get("channel_url") or "").strip()
        if not url and cid:
            url = f"https://www.youtube.com/channel/{cid}"
        if not url and handle:
            url = f"https://www.youtube.com/@{handle}"
        records.append({
            "account_id": f"yt:{cid}", "platform": "youtube",
            "account_handle": f"@{handle}" if handle else "", "account_url": url,
            "channel_id": cid, "display_name": row.get("title") or "",
            "entity_type": "unknown_person_or_org", "country": "IN",
            "region": "", "language": "und", "category": row.get("category") or "",
            "followers_count": row.get("subscriber_count") or "",
            "videos_count": row.get("video_count") or "", "views_count": row.get("view_count") or "",
            "rank": "", "source_dataset": YT_DATASET, "source_url": YT_CARD,
            "source_license": "CC BY-SA 4.0 compilation; underlying content rights remain separate",
            "source_observed_at": "source snapshot hydrated through 2026-11-14",
            "discovery_status": "INDIA_COUNTRY_FIELD_MATCH_NEEDS_LIVE_RECHECK",
            "short_form_status": "NOT_VERIFIED_FOR_SHORTS", "rights_status": "NOT_ASSESSED_DISCOVERY_ONLY",
            "last_independent_verification_at": "",
            "notes": "Country field matched India/IN in public channel dataset. Language, creator identity and current Shorts activity are not verified; compilation license does not grant media rights.",
        })
    records.sort(key=lambda x: (-int(x["followers_count"] or 0), x["display_name"].casefold()))
    return records[:target], {
        "dataset": YT_DATASET, "source_url": YT_CARD, "filter": where,
        "matching_rows_reported": total, "partial_index": partial,
        "unique_channel_ids_retrieved": len(records), "target": target,
        "max_rows_scanned": max_rows,
        "limitation": "Dataset Viewer filter can be partial for sources larger than 5 GB; verify coverage and country field semantics.",
    }

def fetch_instagram_india(target: int) -> tuple[list[dict], dict]:
    text = request_bytes(IG_URL).decode("utf-8-sig")
    latest = {}
    for row in csv.DictReader(text.splitlines()):
        handle = (row.get("username") or "").strip().lstrip("@").casefold()
        country = (row.get("country") or "").strip().upper()
        also = {x.strip().upper() for x in (row.get("countries") or "").split(";") if x.strip()}
        if not handle or (country != "IN" and "IN" not in also):
            continue
        if handle not in latest or row.get("date", "") > latest[handle].get("date", ""):
            latest[handle] = row
    ordered = sorted(latest.values(), key=lambda x: (int(x.get("rank") or 10**9), x.get("username", "").casefold()))
    records = []
    for row in ordered[:target]:
        handle = row["username"].strip().lstrip("@").casefold()
        records.append({
            "account_id": f"ig:{handle}", "platform": "instagram",
            "account_handle": f"@{handle}", "account_url": f"https://www.instagram.com/{handle}/",
            "channel_id": "", "display_name": row.get("name") or "",
            "entity_type": "person" if row.get("type") == "person" else "organization" if row.get("type") == "org" else "unknown",
            "country": "IN", "region": "", "language": "und",
            "category": row.get("category") or "", "followers_count": row.get("followers") or "",
            "videos_count": "", "views_count": "", "rank": row.get("rank") or "",
            "source_dataset": "arh1p/instagram-top-accounts", "source_url": IG_CARD,
            "source_license": "CC BY 4.0 compilation; underlying content rights remain separate",
            "source_observed_at": row.get("date") or "",
            "discovery_status": "INDIA_COUNTRY_FIELD_MATCH_NEEDS_LIVE_RECHECK",
            "short_form_status": "NOT_VERIFIED_FOR_REELS", "rights_status": "NOT_ASSESSED_DISCOVERY_ONLY",
            "last_independent_verification_at": "",
            "notes": "Country field matched IN or the account is listed among India-linked countries in the public account snapshot. Category is source category; language, India audience and active Reels status are not verified. No media rights implied.",
        })
    return records, {
        "dataset": "arh1p/instagram-top-accounts", "source_url": IG_CARD,
        "download_url": IG_URL, "country_filter": "country == IN",
        "matching_unique_accounts": len(ordered), "target": target,
        "max_observation_date": max((x.get("date", "") for x in ordered), default=""),
    }


def fetch_dexfluence_india() -> tuple[dict[str, list[dict]], dict]:
    """Read the public India creator index via Dataset Viewer; keep IG/YT only."""
    data = get_json("splits", {"dataset": DEX_DATASET})
    splits = data.get("splits", [])
    if not splits:
        return {"instagram": [], "youtube": []}, {
            "dataset": DEX_DATASET, "source_url": DEX_CARD,
            "status": "NO_DATASET_VIEWER_SPLIT_AVAILABLE",
        }
    chosen = next((x for x in splits if x.get("split") == "train"), splits[0])
    config, split = chosen.get("config", "default"), chosen.get("split", "train")
    first = get_json("first-rows", {"dataset": DEX_DATASET, "config": config, "split": split})
    total = int(first.get("num_rows_total") or 0)
    raw = rows_from_response(first)
    offset = len(raw)
    while offset < total and offset < 10000:
        page = get_json("rows", {"dataset": DEX_DATASET, "config": config,
                                 "split": split, "offset": offset, "length": 100})
        batch = rows_from_response(page)
        if not batch:
            break
        raw.extend(batch)
        offset += len(batch)
        time.sleep(0.25)
    output = {"instagram": [], "youtube": []}
    for row in raw:
        platform = str(row.get("platform") or "").strip().casefold()
        location = str(row.get("location") or row.get("country") or "").strip().upper()
        if platform not in output or location not in {"IN", "INDIA"}:
            continue
        handle = str(row.get("handle") or "").strip().lstrip("@")
        if not handle:
            continue
        if platform == "instagram":
            url = f"https://www.instagram.com/{handle}/"
        else:
            url = f"https://www.youtube.com/@{handle}"
        output[platform].append({
            "account_id": f"{platform[:2]}:dexfluence:{handle.casefold()}",
            "platform": platform, "account_handle": f"@{handle}",
            "account_url": url, "channel_id": "",
            "display_name": str(row.get("name") or ""),
            "entity_type": "unknown_person_or_org", "country": "IN",
            "region": str(row.get("region") or row.get("city") or ""),
            "language": str(row.get("language") or "und"),
            "category": str(row.get("niche") or row.get("category") or ""),
            "followers_count": row.get("followers") or "",
            "videos_count": "", "views_count": "", "rank": "",
            "source_dataset": DEX_DATASET, "source_url": DEX_CARD,
            "source_license": "CC BY 4.0 as stated by dataset card; underlying platform/media rights remain separate",
            "source_observed_at": "dataset snapshot; refresh date to be verified",
            "discovery_status": "DATASET_REPORTED_INDIA_CREATOR_LEAD_NEEDS_LIVE_RECHECK",
            "short_form_status": "NOT_VERIFIED_FOR_REELS_OR_SHORTS",
            "rights_status": "NOT_ASSESSED_DISCOVERY_ONLY",
            "last_independent_verification_at": "",
            "notes": "India creator-index row; dataset-reported verification/authenticity fields are not independently audited by ShortsLM. Recheck identity, account status, region, language and current short-form activity.",
        })
    return output, {
        "dataset": DEX_DATASET, "source_url": DEX_CARD,
        "rows_reported": total, "rows_retrieved": len(raw),
        "instagram_candidates": len(output["instagram"]),
        "youtube_candidates": len(output["youtube"]),
        "license_claim": "CC BY 4.0 (dataset card; recheck at use time)",
    }

def merge_candidates(primary: list[dict], supplemental: list[dict], platform: str, target: int) -> list[dict]:
    merged = {}
    for row in primary + supplemental:
        handle = str(row.get("account_handle") or row.get("account_url") or row.get("channel_id") or row.get("account_id") or "").strip().lstrip("@").casefold()
        if not handle:
            continue
        old = merged.get(handle)
        if old is None:
            merged[handle] = row
        elif old.get("source_dataset") != DEX_DATASET and row.get("source_dataset") == DEX_DATASET:
            # Prefer source-native account facts from the primary country-index source.
            continue
    values = list(merged.values())
    values.sort(key=lambda x: (-int(x.get("followers_count") or 0), x.get("display_name", "").casefold()))
    return values[:target]

def hashtag_rows(target: int) -> list[dict]:
    """Generate balanced candidate tags across all listed language scopes."""
    per_language: dict[str, list[dict]] = {}
    patterns = [
        ("native_root", "{root}"),
        ("native_root_reels", "{root}reels"),
        ("native_root_shorts", "{root}shorts"),
        ("native_root_india", "{root}india"),
        ("roman_topic_reels", "{topic}reels"),
        ("roman_topic_shorts", "{topic}shorts"),
        ("roman_topic_india", "{topic}india"),
        ("roman_topic_creator", "{topic}creator"),
    ]
    topic_items = [(cat, topic) for cat, topics in TOPICS.items() for topic in topics]
    global_seen: set[str] = set()
    for language, code, native, region in LANGUAGES:
        local = []
        for root in LANG_ROOTS.get(code, []):
            for rule, template in patterns[:4]:
                tag = template.format(root=root, topic="")
                norm = re.sub(r"[^\w]", "", tag, flags=re.UNICODE).casefold()
                if norm and norm not in global_seen:
                    global_seen.add(norm)
                    local.append(make_tag(norm, tag, language, code, region, "regional_identity", rule))
        for category, topic in topic_items:
            for rule, template in patterns[4:]:
                tag = template.format(root="", topic=topic)
                if code == "hi":
                    tag = "bharat" + tag
                elif code == "en-IN":
                    tag = "india" + tag
                else:
                    tag = code.replace("-", "") + tag
                norm = re.sub(r"[^\w]", "", tag, flags=re.UNICODE).casefold()
                if norm and norm not in global_seen:
                    global_seen.add(norm)
                    local.append(make_tag(norm, tag, language, code, region, category, rule))
        per_language[code] = local

    # Round-robin so the first 1,500 do not overrepresent the first few languages.
    output = []
    active = list(per_language)
    cursor = 0
    while active and len(output) < target:
        code = active[cursor]
        bucket = per_language[code]
        if bucket:
            output.append(bucket.pop(0))
        if not bucket:
            active.remove(code)
            if not active:
                break
            cursor %= len(active)
        else:
            cursor = (cursor + 1) % len(active)
    if len(output) < target:
        raise RuntimeError(f"Only {len(output)} unique hashtag candidates generated; requested {target}. No fake top-up.")
    return output[:target]

def make_tag(norm: str, tag: str, language: str, code: str, region: str, category: str, rule: str) -> dict:
    return {
        "hashtag_id": f"IN_{code}_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:12]}",
        "hashtag": "#" + tag, "normalized_hashtag": norm,
        "language": language, "language_code": code, "region_scope": region,
        "category": category, "candidate_platform_scope": "instagram;youtube_search_text",
        "generation_rule": rule, "verification_state": "GENERATED_UNVERIFIED_CANDIDATE",
        "frequency_measured_at": "", "native_speaker_review_status": "PENDING",
        "source_url": "",
        "notes": "Compositional India/language/topic discovery candidate; not proof of native usage, popularity or retrieval yield. Native-speaker review and live search validation required.",
    }

def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def write_lines(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(x + "\n" for x in values), encoding="utf-8")

def build(args) -> dict:
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    yt, yt_meta = fetch_youtube_india(args.youtube_limit, args.youtube_scan_limit)
    ig, ig_meta = fetch_instagram_india(args.instagram_limit)
    try:
        dex, dex_meta = fetch_dexfluence_india()
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        dex = {"instagram": [], "youtube": []}
        dex_meta = {"dataset": DEX_DATASET, "source_url": DEX_CARD, "status": "SUPPLEMENTAL_SOURCE_UNAVAILABLE", "error": str(exc)}
    yt = merge_candidates(yt, dex["youtube"], "youtube", args.youtube_limit)
    ig = merge_candidates(ig, dex["instagram"], "instagram", args.instagram_limit)
    tags = hashtag_rows(args.hashtag_target)
    write_csv(out / "youtube_channel_candidates.csv", yt, FIELDS)
    write_csv(out / "instagram_account_candidates.csv", ig, FIELDS)
    write_csv(out / "instagram_person_candidates.csv", [x for x in ig if x["entity_type"] == "person"], FIELDS)
    write_csv(out / "instagram_organization_publisher_candidates.csv", [x for x in ig if x["entity_type"] == "organization"], FIELDS)
    write_csv(out / "hashtags_master_candidates.csv", tags, TAG_FIELDS)
    write_csv(out / "hashtags_generated_candidates.csv", tags, TAG_FIELDS)
    write_lines(out / "instagram_creator_seeds.txt", [x["account_handle"].lstrip("@") for x in ig])
    write_lines(out / "youtube_creator_seeds.txt", [x["account_url"] for x in yt if x["account_url"]])
    write_lines(out / "india_hashtags.txt", [x["hashtag"] for x in tags])
    summary = {
        "release": "ShortsLM India discovery catalogue v1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "instagram_accounts": len(ig),
            "instagram_people": sum(x["entity_type"] == "person" for x in ig),
            "instagram_organizations": sum(x["entity_type"] == "organization" for x in ig),
            "youtube_channels": len(yt),
            "hashtags": len(tags),
        },
        "targets": {"instagram": args.instagram_limit, "youtube": args.youtube_limit, "hashtags": args.hashtag_target},
        "sources": {"instagram": ig_meta, "youtube": yt_meta, "supplemental_india_creator_index": dex_meta},
        "language_scopes": [{"language": x[0], "code": x[1], "region": x[3]} for x in LANGUAGES],
        "category_scopes": list(TOPICS),
        "limitations": [
            "Creator rows are public dataset leads, not live-verified active Shorts/Reels creators.",
            "India country fields do not prove the creator's audience is predominantly Indian.",
            "The YouTube dataset viewer filter may be partial because its source exceeds 5 GB; inspect partial_index and matching_rows_reported.",
            "Language is unknown unless a source explicitly supplies it; no language is inferred from a name.",
            "Hashtags are generated candidates, not verified popular tags; native-speaker review and retrieval-yield measurement are required.",
            "If source-backed Indian creator rows are fewer than the requested target, the output remains below target; the script does not invent or pad creators.",
            "No creator row grants permission to download, retain, analyze or train on media.",
        ],
    }
    (out / "QA_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/seed_catalogue/india_v1"))
    parser.add_argument("--instagram-limit", type=int, default=1500)
    parser.add_argument("--youtube-limit", type=int, default=1500)
    parser.add_argument("--hashtag-target", type=int, default=1500)
    parser.add_argument("--youtube-scan-limit", type=int, default=100000,
                        help="Safety cap on matching YouTube rows fetched; filter endpoint max page length is 100.")
    args = parser.parse_args()
    if min(args.instagram_limit, args.youtube_limit, args.hashtag_target, args.youtube_scan_limit) <= 0:
        parser.error("all limits must be positive")
    try:
        print(json.dumps(build(args), ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, csv.Error, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
