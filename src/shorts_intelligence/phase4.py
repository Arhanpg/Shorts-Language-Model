"""Phase 4: catalogue coverage, human annotation and rights-aware dataset release."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

phase4_app = typer.Typer(name="phase4", help="Phase 4 dataset QA and annotation.", no_args_is_help=True)
console = Console()
CREATOR_FILES = {
    "youtube": ("youtube_channel_candidates.csv",),
    "instagram": ("instagram_account_candidates.csv", "creators_ai_research_leads_v0.1.csv"),
}
TAG_FILES = ("hashtags_master_candidates.csv", "hashtags_ai_research_candidates.csv", "hashtags_generated_candidates.csv")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _value(row: dict[str, str], *keys: str) -> str:
    data = {str(k).casefold(): (v or "").strip() for k, v in row.items()}
    return next((data[k.casefold()] for k in keys if data.get(k.casefold())), "")


def _identity(row: dict[str, str]) -> str | None:
    value = _value(row, "channel_id", "username", "handle", "channel_handle", "custom_url", "profile_url", "channel_url", "url")
    if not value:
        return None
    if "youtube.com" in value.casefold():
        match = re.search(r"youtube\.com/(?:@|user/|channel/|c/)?([^/?#]+)", value, re.I)
        value = match.group(1) if match else value
    elif "instagram.com" in value.casefold():
        match = re.search(r"instagram\.com/([^/?#]+)", value, re.I)
        value = match.group(1) if match else value
    value = value.strip().lstrip("@").rstrip("/").casefold()
    return value if re.fullmatch(r"[a-z0-9._-]{1,64}", value) else None


def _tag(row: dict[str, str]) -> str | None:
    value = _value(row, "hashtag", "tag", "hashtag_text", "normalized_hashtag", "normalized_tag", "keyword")
    value = value.strip().lstrip("#").casefold()
    if not value or len(value) > 64:
        return None
    return value if all(c in "._" or unicodedata.category(c)[0] in {"L", "N", "M"} for c in value) else None


def _write_lines(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(v + "\n" for v in values), encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    temp.replace(path)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    output = []
    with path.expanduser().resolve(strict=True).open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL line {number}: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL line {number} must be an object")
            output.append(row)
    return output


@phase4_app.command("catalogue")
def catalogue(
    catalogue_dir: Path = typer.Option(Path("data/seed_catalogue/v0.2"), "--catalogue-dir", exists=True, file_okay=False),
    output_dir: Path = typer.Option(Path("outputs/phase4/catalogue"), "--output-dir"),
    batch_size: int = typer.Option(100, "--batch-size", min=10, max=500),
) -> None:
    """Materialize all v0.2 creator and hashtag candidates into deduplicated batches."""
    catalogue_dir = catalogue_dir.expanduser().resolve(strict=True)
    output_dir = output_dir.expanduser().resolve()
    creators: dict[str, list[dict[str, str]]] = {"youtube": [], "instagram": []}
    seen: dict[str, set[str]] = {"youtube": set(), "instagram": set()}
    source_counts: dict[str, int] = {}
    invalid = 0
    for platform, filenames in CREATOR_FILES.items():
        for filename in filenames:
            path = catalogue_dir / filename
            if not path.exists():
                continue
            source = _rows(path)
            source_counts[filename] = len(source)
            for row in source:
                target = platform
                declared = _value(row, "platform").casefold()
                if filename.startswith("creators_ai") and declared in creators:
                    target = declared
                identity = _identity(row)
                if not identity:
                    invalid += 1
                    continue
                if identity not in seen[target]:
                    seen[target].add(identity)
                    creators[target].append({"platform": target, "identity": identity, "source": filename,
                                             "display_name": _value(row, "channel_name", "creator_name", "full_name", "name", "title"),
                                             "verification": _value(row, "verification_state", "source_reported_verification_status") or "not_independently_verified"})
    tags: list[dict[str, str]] = []
    tag_seen: set[str] = set()
    for filename in TAG_FILES:
        path = catalogue_dir / filename
        if not path.exists():
            continue
        source = _rows(path)
        source_counts[filename] = len(source)
        for row in source:
            tag = _tag(row)
            if tag and tag not in tag_seen:
                tag_seen.add(tag)
                tags.append({"hashtag": tag, "language": _value(row, "language", "language_code", "language_scope"),
                             "domain": _value(row, "domain", "category", "topic"), "source": filename})
            elif not tag:
                invalid += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    for platform in creators:
        with (output_dir / f"{platform}_creator_candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["platform", "identity", "source", "display_name", "verification"])
            writer.writeheader()
            writer.writerows(creators[platform])
    with (output_dir / "hashtag_candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["hashtag", "language", "domain", "source"])
        writer.writeheader()
        writer.writerows(tags)

    ig_handles = [row["identity"] for row in creators["instagram"]]
    yt_ids = [row["identity"] for row in creators["youtube"] if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", row["identity"])]
    _write_lines(output_dir / "instagram_creator_seeds.txt", ig_handles)
    _write_lines(output_dir / "youtube_channel_id_seeds.txt", yt_ids)
    _write_lines(output_dir / "instagram_hashtags.txt", [row["hashtag"] for row in tags])
    batch_dir = output_dir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batches = []
    for kind, platform, values in (
        ("instagram_creators", "instagram", ig_handles),
        ("youtube_channel_ids", "youtube", yt_ids),
        ("hashtags", "all", [row["hashtag"] for row in tags]),
    ):
        for offset in range(0, len(values), batch_size):
            index = offset // batch_size + 1
            filename = f"{kind}_{index:04d}.txt"
            _write_lines(batch_dir / filename, values[offset:offset + batch_size])
            batches.append({"kind": kind, "platform": platform, "batch": index,
                            "count": len(values[offset:offset + batch_size]), "path": f"batches/{filename}"})
    report = {
        "schema_version": "phase4.catalogue.v1", "created_at": datetime.now(UTC).isoformat(),
        "source_rows": source_counts, "unique_instagram_accounts": len(ig_handles),
        "unique_youtube_channel_candidates": len(creators["youtube"]),
        "youtube_channel_id_seedable": len(yt_ids),
        "youtube_handle_only_or_unresolved": len(creators["youtube"]) - len(yt_ids),
        "unique_normalized_hashtags": len(tags), "invalid_rows": invalid, "batch_size": batch_size,
        "batches": batches,
        "limitations": [
            "Creator candidates are leads, not proof of active Shorts/Reels publishing.",
            "AI verification labels are source claims, not independent verification.",
            "Hashtag candidates have no assumed popularity or measured retrieval yield.",
            "Public visibility and catalogue licences do not grant media or model-training rights.",
            "YouTube channel handles without a stable UC channel ID are exported for review, not crawled as channel IDs.",
        ],
    }
    (output_dir / "catalogue_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    table = Table(title="Phase 4 catalogue")
    table.add_column("Inventory")
    table.add_column("Count", justify="right")
    for name, count in (("Instagram accounts", len(ig_handles)), ("YouTube channel candidates", len(creators["youtube"])),
                        ("YouTube channel IDs", len(yt_ids)), ("Unique hashtags", len(tags)), ("Batches", len(batches))):
        table.add_row(name, str(count))
    console.print(table)
    console.print(f"[green]Catalogue batches written:[/green] {output_dir}")
    console.print("[yellow]Offline only: no accounts were contacted and no media was downloaded.[/yellow]")


@phase4_app.command("annotation-template")
def annotation_template(
    manifest: Path = typer.Option(..., "--manifest", exists=True, readable=True),
    output: Path = typer.Option(Path("outputs/phase4/annotation_queue.csv"), "--output"),
) -> None:
    """Create a blank human annotation queue from a validated selected manifest."""
    rows = _load_jsonl(manifest)
    columns = ["record_id", "reviewer_id", "review_status", "language_primary", "script", "code_switch_languages",
               "content_domain", "content_subcategory", "audience_segment", "summary_grounded", "hook_type",
               "hook_start_seconds", "hook_end_seconds", "narrative_setup", "narrative_escalation",
               "narrative_payoff", "loop_structure", "shot_boundaries_seconds", "editing_events_json",
               "ocr_transcription_correct", "asr_transcription_correct", "audio_events_json", "evidence_notes",
               "disagreement_notes", "annotation_schema_version", "tool_model_prompt_versions"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({"record_id": row.get("record_id", ""), "review_status": "not_started",
                             "annotation_schema_version": "phase4.annotation.v1"})
    console.print(f"[green]Annotation queue:[/green] {output.resolve()} ({len(rows)} records)")


def _training_rights(row: dict[str, Any]) -> bool:
    rights = row.get("rights") or {}
    if rights:
        scopes = ("media_analysis", "temporary_processing", "derived_artifact_retention", "model_training")
        expires, evidence, revoked, source = rights.get("expires_at"), rights.get("evidence_ref"), rights.get("revoked"), rights
    else:
        scopes = ("media_analysis_permitted", "temporary_processing_permitted", "derived_artifact_retention_permitted", "model_training_permitted")
        expires, evidence, revoked, source = row.get("rights_expires_at"), row.get("rights_reference_hash"), False, row
    if revoked or not evidence or not all(source.get(key) is True for key in scopes):
        return False
    if expires:
        try:
            expiry = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry <= datetime.now(UTC):
                return False
        except ValueError:
            return False
    return True


@phase4_app.command("release")
def release(
    manifest: Path = typer.Option(..., "--manifest", exists=True, readable=True),
    annotations: Path = typer.Option(..., "--annotations", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("outputs/phase4/release"), "--output-dir"),
    golden_fraction: float = typer.Option(0.10, "--golden-fraction", min=0.0, max=0.30),
) -> None:
    """Fail-closed release gate and creator/duplicate-disjoint time-forward splits."""
    records = _load_jsonl(manifest)
    with annotations.expanduser().resolve(strict=True).open("r", newline="", encoding="utf-8-sig") as handle:
        annotation_rows = list(csv.DictReader(handle))
    annotation_map = {row.get("record_id", "").strip(): row for row in annotation_rows}
    if len(annotation_map) != len(annotation_rows) or "" in annotation_map:
        raise ValueError("Annotation record_id values must be non-empty and unique")
    issues: list[dict[str, str]] = []
    accepted: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in records:
        rid = str(row.get("record_id") or "")
        if not rid or rid in seen_ids:
            issues.append({"record_id": rid, "issue": "missing_or_duplicate_record_id"})
            continue
        seen_ids.add(rid)
        if not _training_rights(row):
            issues.append({"record_id": rid, "issue": "rights_not_training_eligible"})
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(row.get("media_sha256") or "")):
            issues.append({"record_id": rid, "issue": "invalid_media_sha256"})
            continue
        try:
            if float(row.get("duration_seconds", 0)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            issues.append({"record_id": rid, "issue": "invalid_duration"})
            continue
        ann = annotation_map.get(rid)
        if not ann or ann.get("review_status", "").strip().casefold() not in {"approved", "adjudicated"}:
            issues.append({"record_id": rid, "issue": "annotation_missing_or_unapproved"})
            continue
        for field in ("language_primary", "content_domain", "summary_grounded", "hook_type"):
            if not (ann.get(field) or "").strip():
                issues.append({"record_id": rid, "issue": f"annotation_core_field_missing:{field}"})
        accepted.append({**row, "annotation": ann})
    output_dir.mkdir(parents=True, exist_ok=True)
    if issues:
        (output_dir / "release_blockers.json").write_text(json.dumps({"issues": issues}, indent=2), encoding="utf-8")
        raise ValueError(f"Release blocked by {len(issues)} QA issue(s); inspect {output_dir / 'release_blockers.json'}")

    # Union creator identity and exact SHA-256 duplicates so neither crosses a split.
    parent = list(range(len(accepted)))
    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(a: int, b: int) -> None:
        a, b = root(a), root(b)
        if a != b:
            parent[b] = a
    creator_owner: dict[str, int] = {}
    hash_owner: dict[str, int] = {}
    for i, row in enumerate(accepted):
        creator = str(row.get("creator_id") or row.get("creator_group") or "").strip()
        digest = str(row["media_sha256"]).casefold()
        if creator:
            if creator in creator_owner: join(i, creator_owner[creator])
            else: creator_owner[creator] = i
        if digest in hash_owner: join(i, hash_owner[digest])
        else: hash_owner[digest] = i
    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, row in enumerate(accepted):
        components[root(i)].append(row)
    groups = list(components.values())
    groups.sort(key=lambda group: hashlib.sha256("|".join(sorted(r["record_id"] for r in group)).encode()).hexdigest())
    golden_target = round(len(accepted) * golden_fraction)
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": [], "golden_locked": []}
    for group in groups:
        if len(splits["golden_locked"]) < golden_target and golden_fraction > 0:
            splits["golden_locked"].extend(group)
    remaining = [g for g in groups if not any(r in splits["golden_locked"] for r in g)]
    def group_time(g: list[dict[str, Any]]) -> str:
        dates = [str(r.get("published_at")) for r in g if r.get("published_at")]
        return max(dates) if dates else "9999"
    remaining.sort(key=lambda g: (group_time(g), str(g[0]["record_id"])))
    population = sum(map(len, remaining))
    train_target, validation_target = int(population * .8), int(population * .1)
    for group in remaining:
        target = "train" if len(splits["train"]) < train_target else "validation" if len(splits["validation"]) < validation_target else "test"
        splits[target].extend(group)
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, rows in splits.items():
        safe = [{"record_id": r["record_id"], "platform": r.get("platform"), "language": r.get("language"),
                 "topic": r.get("topic"), "media_sha256": r["media_sha256"], "duration_seconds": r["duration_seconds"],
                 "published_at": r.get("published_at"), "creator_group": r.get("creator_group")} for r in rows]
        _write_jsonl(output_dir / f"{name}.jsonl", safe)
        counts[name] = len(safe)
    report = {"schema_version": "phase4.release.v1", "created_at": datetime.now(UTC).isoformat(),
              "accepted_records": len(accepted), "split_counts": counts, "rights_training_permission_fraction": 1.0,
              "split_policy": "creator and exact-hash groups kept together; remaining groups ordered by publication time; 80/10/10",
              "limitations": ["Perceptual near-duplicate/transcode detection remains a required pre-release review.",
                             "Inter-annotator agreement requires independent double annotation and adjudication.",
                             "The CLI checks local permission attestations; it does not authenticate legal evidence.",
                             "The golden holdout is locked by workflow, not cryptographically access-controlled."]}
    (output_dir / "release_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    console.print(f"[green]Phase 4 release written:[/green] {output_dir.resolve()}")
    for name, count in counts.items(): console.print(f"{name}: {count}")
