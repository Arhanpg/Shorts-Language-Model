#!/usr/bin/env python3
"""Build 10K+ Shorts-LM creator-account and hashtag discovery seed catalogues."""
from __future__ import annotations
import argparse, csv, json, os, re, sys, time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

YT_DATASET="ScrapeExchange/youtube-channel-7m-plus"
YT_CARD=f"https://huggingface.co/datasets/{YT_DATASET}"
YT_API="https://datasets-server.huggingface.co"
IG_URL="https://huggingface.co/datasets/arh1p/instagram-top-accounts/resolve/main/latest.csv"
IG_CARD="https://huggingface.co/datasets/arh1p/instagram-top-accounts"
UA="Shorts-LM-Seed-Catalogue/0.2 (research discovery)"
ACCOUNT_FIELDS=["account_id","platform","account_handle","account_url","display_name","entity_type","country","region","language","category","followers_count","videos_count","views_count","rank","joined_date","source_dataset","source_url","source_license","source_observed_at","discovery_status","short_form_status","rights_status","last_independent_verification_at","notes"]
TAG_FIELDS=["hashtag_id","hashtag","normalized_hashtag","language","language_code","category","candidate_platform_scope","generation_rule","verification_state","frequency_measured_at","native_speaker_review_status","source_url","notes"]

def http_bytes(url: str, tries: int = 7) -> bytes:
    """Fetch a public source respectfully, honouring Retry-After on 429/5xx."""
    error = None
    for attempt in range(tries):
        try:
            headers = {"User-Agent": UA, "Accept": "application/json,text/csv,*/*"}
            hf_token = os.environ.get("HF_TOKEN", "").strip()
            if hf_token:
                headers["Authorization"] = f"Bearer {hf_token}"
            req = Request(url, headers=headers)
            with urlopen(req, timeout=45) as response:
                return response.read()
        except HTTPError as exc:
            error = exc
            if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"Non-retryable HTTP {exc.code} for {url}") from exc
            retry_after = (exc.headers.get("Retry-After") or "").strip()
            wait_seconds = None
            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    try:
                        from email.utils import parsedate_to_datetime
                        wait_date = parsedate_to_datetime(retry_after)
                        wait_seconds = max(0.0, (wait_date - datetime.now(UTC)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        wait_seconds = None
            if wait_seconds is None:
                wait_seconds = min(15 * (2 ** attempt), 180)
            wait_seconds = min(max(wait_seconds, 1.0), 300.0)
            print(
                f"HTTP {exc.code} from source; respecting retry delay {wait_seconds:.0f}s "
                f"(attempt {attempt + 1}/{tries})",
                file=sys.stderr,
            )
            if attempt < tries - 1:
                time.sleep(wait_seconds)
        except (URLError, TimeoutError, OSError) as exc:
            error = exc
            wait_seconds = min(5 * (2 ** attempt), 120)
            print(
                f"Transient source error; retrying in {wait_seconds}s "
                f"(attempt {attempt + 1}/{tries}): {exc}",
                file=sys.stderr,
            )
            if attempt < tries - 1:
                time.sleep(wait_seconds)
    raise RuntimeError(f"Unable to retrieve {url} after {tries} bounded attempts: {error}")


def get_json(endpoint: str, params: dict) -> dict:
    url=f"{YT_API}/{endpoint}?{urlencode(params)}"
    try: return json.loads(http_bytes(url).decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc

def page_offsets(total: int,target: int,page_size: int=100) -> list[int]:
    if total<=0 or target<=0: return []
    pages=min((target+page_size-1)//page_size,(total+page_size-1)//page_size)
    if pages==1: return [0]
    end=max(0,total-page_size)
    return sorted(set(round(i*end/(pages-1)) for i in range(pages)))

def fetch_youtube(limit: int) -> tuple[list[dict],dict]:
    info=get_json("splits",{"dataset":YT_DATASET})
    train=[x for x in info.get("splits",[]) if x.get("split")=="train"]
    if not train: raise RuntimeError("YouTube dataset viewer returned no train split")
    split=next((x for x in train if "boinko-youtube-channel" in x.get("config","")),train[0])
    config=split["config"]
    size_info=get_json("size",{"dataset":YT_DATASET})
    size_splits=size_info.get("size",{}).get("splits",[])
    sized=next((x for x in size_splits if x.get("config")==config and x.get("split")=="train"),None)
    total=int((sized or {}).get("num_rows") or 0)
    if total<=0:
        probe=get_json("rows",{"dataset":YT_DATASET,"config":config,"split":"train","offset":0,"length":1})
        total=int(probe.get("num_rows_total") or 0)
    if total<=0: raise RuntimeError("YouTube dataset viewer size/rows endpoints did not report num_rows")
    rows=[]; offsets=page_offsets(total,limit)
    for i,offset in enumerate(offsets,1):
        length=min(100,limit-len(rows))
        if length<=0: break
        data=get_json("rows",{"dataset":YT_DATASET,"config":config,"split":"train","offset":offset,"length":length})
        rows.extend(x["row"] for x in data.get("rows",[]) if isinstance(x,dict) and isinstance(x.get("row"),dict))
        print(f"YouTube dataset pages {i}/{len(offsets)}; {len(rows)} rows",file=sys.stderr)
        # The dataset viewer returned HTTP 429 after a burst in the first build.
        # A conservative cadence reduces repeated pressure on the public service.
        if i < len(offsets):
            time.sleep(2.5)
    if len(rows)<min(limit,total): raise RuntimeError(f"Only retrieved {len(rows)} of {limit} YouTube rows; no synthetic top-up")
    return rows[:limit],{"dataset":YT_DATASET,"url":YT_CARD,"license":"CC BY-SA 4.0 compilation; underlying content rights remain separate","config":config,"total_rows":total,"retrieved_rows":len(rows),"sampling":"evenly spaced pages across source row index; not a probability sample","retrieved_at":datetime.now(UTC).isoformat()}

def fetch_instagram(limit: int) -> tuple[list[dict],dict]:
    text=http_bytes(IG_URL).decode("utf-8-sig"); latest={}
    for row in csv.DictReader(text.splitlines()):
        handle=(row.get("username") or "").strip().lstrip("@").casefold()
        if handle and (handle not in latest or row.get("date","")>latest[handle].get("date","")): latest[handle]=row
    rows=sorted(latest.values(),key=lambda x:(int(x.get("rank") or 10**9),x.get("username","").casefold()))
    if len(rows)<limit: raise RuntimeError(f"Instagram source has only {len(rows)} accounts; requested {limit}; no synthetic top-up")
    rows=rows[:limit]
    return rows,{"dataset":"arh1p/instagram-top-accounts","url":IG_CARD,"download_url":IG_URL,"license":"CC BY 4.0","retrieved_rows":len(rows),"max_observation_date":max((x.get("date","") for x in rows),default=""),"retrieved_at":datetime.now(UTC).isoformat(),"selection":"rank-ordered latest account snapshot; person and org types retained separately"}

def map_youtube(row: dict) -> dict|None:
    cid=str(row.get("channel_id") or "").strip(); url=str(row.get("url") or row.get("channel_url") or "").strip()
    handle=str(row.get("channel_handle") or "").strip().lstrip("@")
    if not handle and url:
        match=re.search(r"youtube\.com/@([^/?#]+)",url,re.I); handle=match.group(1) if match else ""
    if not cid and not url and not handle: return None
    if not url and cid: url=f"https://www.youtube.com/channel/{cid}"
    key=cid or handle.casefold() or url
    return {"account_id":f"yt:{key}","platform":"youtube","account_handle":f"@{handle}" if handle else "","account_url":url,"display_name":row.get("title") or row.get("channel_name") or "","entity_type":"unknown_person_or_org","country":row.get("country",""),"region":row.get("country",""),"language":"und","category":row.get("category",""),"followers_count":row.get("subscriber_count",""),"videos_count":row.get("video_count",""),"views_count":row.get("view_count",""),"rank":"","joined_date":row.get("joined_date",""),"source_dataset":YT_DATASET,"source_url":YT_CARD,"source_license":"CC BY-SA 4.0 compilation; underlying content rights remain separate","source_observed_at":"source dataset hydrated through 2026-11-14","discovery_status":"PUBLIC_CHANNEL_LEAD_NEEDS_LIVE_RECHECK","short_form_status":"NOT_VERIFIED_FOR_SHORTS","rights_status":"NOT_ASSESSED_DISCOVERY_ONLY","last_independent_verification_at":"","notes":"Channel account; person/organization and current Shorts activity unknown. Dataset compilation license does not authorize media retrieval or model training."}

def map_instagram(row: dict) -> dict|None:
    handle=(row.get("username") or "").strip().lstrip("@").casefold()
    if not handle: return None
    typ=(row.get("type") or "").casefold(); entity="person" if typ=="person" else "organization" if typ=="org" else "unknown"
    return {"account_id":f"ig:{handle}","platform":"instagram","account_handle":f"@{handle}","account_url":f"https://www.instagram.com/{handle}/","display_name":row.get("name",""),"entity_type":entity,"country":row.get("country",""),"region":row.get("countries",""),"language":"und","category":row.get("category",""),"followers_count":row.get("followers",""),"videos_count":"","views_count":"","rank":row.get("rank",""),"joined_date":"","source_dataset":"arh1p/instagram-top-accounts","source_url":IG_CARD,"source_license":"CC BY 4.0","source_observed_at":row.get("date",""),"discovery_status":"PUBLIC_ACCOUNT_LEAD_NEEDS_LIVE_RECHECK","short_form_status":"NOT_VERIFIED_FOR_REELS","rights_status":"NOT_ASSESSED_DISCOVERY_ONLY","last_independent_verification_at":"","notes":"Follower-ranked account lead. Dataset type distinguishes person and organization; follower count does not prove Reels activity, originality, language or location. Dataset license does not authorize media use."}

def slug(value: str) -> str:
    value=value.casefold().replace("&"," and ").replace("+"," plus ").strip()
    return re.sub(r"[^a-z0-9]+","",value)

def build_tags(research_dir: Path,target: int=10650) -> list[dict]:
    lp,cp=research_dir/"languages.csv",research_dir/"categories.csv"
    if not lp.is_file() or not cp.is_file():
        bundled=research_dir/"hashtags_generated_compositional_v0.2.csv"
        if not bundled.is_file(): bundled=research_dir.parent/"hashtags_generated_compositional_v0.2.csv"
        if bundled.is_file():
            with bundled.open("r",encoding="utf-8-sig",newline="") as stream:
                rows=list(csv.DictReader(stream))
            if len(rows)<target: raise RuntimeError(f"Bundled hashtag file has {len(rows)} rows; requested {target}")
            return rows[:target]
        raise RuntimeError("Research catalogue v0.1 missing; install languages.csv/categories.csv or use bundled v0.2 hashtags")
    with lp.open("r",encoding="utf-8-sig",newline="") as f: langs=list(csv.DictReader(f))
    with cp.open("r",encoding="utf-8-sig",newline="") as f: cat_rows=list(csv.DictReader(f))
    cats=OrderedDict()
    for row in cat_rows:
        if row.get("category_id") and row.get("category_name"): cats.setdefault(row["category_id"],row["category_name"])
    patterns=[("language_category","{l}{c}"),("language_category_reels","{l}{c}reels"),("language_category_shorts","{l}{c}shorts"),("category_language_reels","{c}{l}reels"),("language_video_category","{l}video{c}")]
    out=[]; seen=set()
    for lang in langs:
        l,code=slug(lang.get("language","")),lang.get("iso_code","")
        if not l: continue
        for cat_id,cat_name in cats.items():
            c=slug(cat_name)
            for i,(rule,form) in enumerate(patterns,1):
                tag="#"+form.format(l=l,c=c); norm=tag[1:]
                if norm in seen: continue
                seen.add(norm)
                out.append({"hashtag_id":f"HGEN_{code}_{cat_id}_{i}","hashtag":tag,"normalized_hashtag":norm,"language":lang["language"],"language_code":code,"category":cat_name,"candidate_platform_scope":"instagram;youtube_search_text","generation_rule":rule,"verification_state":"GENERATED_UNVERIFIED_COMPOSITIONAL_CANDIDATE","frequency_measured_at":"","native_speaker_review_status":"PENDING","source_url":"","notes":"Composed from language slug + English taxonomy label; not a translation or popularity claim. Review with a native speaker and test retrieval yield."})
                if len(out)>=target: return out
    raise RuntimeError(f"Taxonomy generated only {len(out)} unique tags; target={target}; no fake top-up")

def research_leads(research_dir: Path) -> dict[str,list[dict]]:
    found={"youtube":[],"instagram":[]}
    path=research_dir/"creators.csv"
    if not path.is_file(): path=research_dir/"v0.1"/"creators.csv"
    if not path.is_file(): path=research_dir/"creators_ai_research_leads_v0.1.csv"
    if path.is_file():
        with path.open("r",encoding="utf-8-sig",newline="") as f:
            for row in csv.DictReader(f):
                # Compact 291-row file exported from the Gemini/other-AI catalogue.
                if row.get("platform") and row.get("handle"):
                    platform=row["platform"].strip().casefold()
                    handle=row["handle"].strip().lstrip("@")
                    if platform not in found or not handle: continue
                    found[platform].append({
                        "account_id":f"{platform[:2]}:ai_research:{handle.casefold()}",
                        "platform":platform,"account_handle":f"@{handle}",
                        "account_url":row.get("profile_url",""),
                        "display_name":row.get("creator_name",""),
                        "entity_type":"unknown_person_or_org",
                        "country":row.get("country_reported",""),
                        "region":row.get("region_reported",""),
                        "language":row.get("language_reported","und"),
                        "category":row.get("categories_reported",""),
                        "followers_count":"","videos_count":"","views_count":"","rank":"","joined_date":"",
                        "source_dataset":"submitted_Gemini_and_other_AI_research",
                        "source_url":"",
                        "source_license":"not specified for the imported account leads",
                        "source_observed_at":"2026-11-23 research reconciliation",
                        "discovery_status":"AI_RESEARCH_LEAD_NEEDS_LIVE_RECHECK",
                        "short_form_status":"NOT_VERIFIED",
                        "rights_status":"NOT_ASSESSED_DISCOVERY_ONLY",
                        "last_independent_verification_at":"",
                        "notes":"AI/source-reported state="+row.get("verification_state","UNKNOWN")+"; reported verification="+row.get("source_reported_verification_status","UNKNOWN")+"; source records="+row.get("source_record_ids","")+"; not independent confirmation and no media rights are granted."
                    })
                    continue
                for platform,col,url_col in (("youtube","youtube_channel_handles","youtube_urls"),("instagram","instagram_handles","instagram_urls")):
                    handles=[x.strip().lstrip("@") for x in (row.get(col) or "").split(";") if x.strip()]
                    urls=[x.strip() for x in (row.get(url_col) or "").split(";") if x.strip()]
                    for i,h in enumerate(handles):
                        found[platform].append({"account_id":f"{platform[:2]}:research:{h.casefold()}","platform":platform,"account_handle":f"@{h}","account_url":urls[i] if i<len(urls) else "","display_name":row.get("creator_name",""),"entity_type":"unknown_person_or_org","country":row.get("country_reported",""),"region":row.get("region_reported",""),"language":row.get("primary_languages_reported","und"),"category":row.get("categories_reported",""),"followers_count":"","videos_count":"","views_count":"","rank":"","joined_date":"","source_dataset":"submitted_AI_research_and_repository_seeds","source_url":"","source_license":"not specified in submitted seed source","source_observed_at":"2026-11-23 uploads","discovery_status":"AI_OR_REPOSITORY_LEAD_NEEDS_LIVE_RECHECK","short_form_status":"NOT_VERIFIED","rights_status":"NOT_ASSESSED_DISCOVERY_ONLY","last_independent_verification_at":"","notes":"Submitted research lead; reported status is not independently confirmed and does not grant media rights."})
    # The checked-in 100-handle Instagram starter file is always merged, even when
    # the full v0.1 creator catalogue ZIP has not been installed locally.
    instagram_seed_path=research_dir.parent/"instagram_creator_seeds.txt"
    if not instagram_seed_path.is_file(): instagram_seed_path=Path("data/instagram_creator_seeds.txt")
    if instagram_seed_path.is_file():
        for raw in instagram_seed_path.read_text(encoding="utf-8-sig").splitlines():
            handle=raw.strip().lstrip("@")
            if not handle or handle.startswith("#"): continue
            found["instagram"].append({
                "account_id":f"ig:repository_seed:{handle.casefold()}","platform":"instagram",
                "account_handle":f"@{handle}","account_url":f"https://www.instagram.com/{handle}/",
                "display_name":"","entity_type":"unknown_person_or_org","country":"","region":"",
                "language":"und","category":"","followers_count":"","videos_count":"","views_count":"",
                "rank":"","joined_date":"","source_dataset":"checked_in_repository_instagram_creator_seeds",
                "source_url":"https://github.com/Arhanpg/Shorts-Language-Model/blob/main/data/instagram_creator_seeds.txt",
                "source_license":"not specified; public profile link only","source_observed_at":"repository seed file",
                "discovery_status":"REPOSITORY_SEED_NEEDS_LIVE_RECHECK","short_form_status":"NOT_VERIFIED_FOR_REELS",
                "rights_status":"NOT_ASSESSED_DISCOVERY_ONLY","last_independent_verification_at":"",
                "notes":"Existing project starter handle; identity, originality and active Reels publishing need live recheck. No media rights implied."
            })
    youtube_seed_path=research_dir.parent/"youtube_channel_seeds.txt"
    if not youtube_seed_path.is_file(): youtube_seed_path=Path("data/youtube_channel_seeds.txt")
    if youtube_seed_path.is_file():
        for raw in youtube_seed_path.read_text(encoding="utf-8-sig").splitlines():
            url=raw.strip()
            if not url or url.startswith("#"): continue
            handle_match=re.search(r"youtube\.com/@([^/?#]+)",url,re.I)
            handle=handle_match.group(1) if handle_match else url
            found["youtube"].append({
                "account_id":f"yt:repository_seed:{handle.casefold()}","platform":"youtube",
                "account_handle":f"@{handle}" if handle_match else "","account_url":url,
                "display_name":"","entity_type":"unknown_person_or_org","country":"","region":"",
                "language":"und","category":"","followers_count":"","videos_count":"","views_count":"",
                "rank":"","joined_date":"","source_dataset":"checked_in_repository_youtube_creator_seeds",
                "source_url":"https://github.com/Arhanpg/Shorts-Language-Model/blob/main/data/youtube_channel_seeds.txt",
                "source_license":"not specified; public profile link only","source_observed_at":"repository seed file",
                "discovery_status":"REPOSITORY_SEED_NEEDS_LIVE_RECHECK","short_form_status":"NOT_VERIFIED_FOR_SHORTS",
                "rights_status":"NOT_ASSESSED_DISCOVERY_ONLY","last_independent_verification_at":"",
                "notes":"Existing project starter URL; identity, originality and active Shorts publishing need live recheck. No media rights implied."
            })
    return found

def dedupe(rows: list[dict]) -> list[dict]:
    out=OrderedDict()
    for row in rows:
        key=(row.get("account_handle") or row.get("account_url") or row.get("account_id") or "").casefold().lstrip("@")
        if not key: continue
        old=out.get(key)
        if old is None or ("submitted_AI_research" in str(old.get("source_dataset")) and "submitted_AI_research" not in str(row.get("source_dataset"))): out[key]=row
    return list(out.values())

def write_csv(path: Path,rows: list[dict],fields: list[str]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)

def youtube_scan_target(target: int) -> int:
    """Oversample raw source rows so incomplete channel records cannot underfill the final list."""
    return target + max(250, int(target * 0.05))


def build(research_dir: Path,out_dir: Path,yt_limit: int,ig_limit: int,tag_target: int,hashtags_only: bool=False) -> dict:
    out_dir.mkdir(parents=True,exist_ok=True)
    tags=build_tags(research_dir,tag_target); write_csv(out_dir/"hashtags_generated_candidates.csv",tags,TAG_FIELDS)
    if hashtags_only: return {"counts":{"hashtags":len(tags)},"network_sources_downloaded":False}
    youtube_scan_limit=youtube_scan_target(yt_limit)
    yt_raw,yt_meta=fetch_youtube(youtube_scan_limit); ig_raw,ig_meta=fetch_instagram(ig_limit)
    yt=[x for r in yt_raw if (x:=map_youtube(r))]; ig=[x for r in ig_raw if (x:=map_instagram(r))]
    leads=research_leads(research_dir); yt,ig=dedupe(yt+leads["youtube"]),dedupe(ig+leads["instagram"])
    if len(yt)<yt_limit:
        raise RuntimeError(f"Only {len(yt)} unique YouTube channel candidates survived normalization; target={yt_limit}. Increase source scan only after reviewing data quality.")
    if len(ig)<ig_limit:
        raise RuntimeError(f"Only {len(ig)} unique Instagram account candidates survived normalization; target={ig_limit}. No fabricated top-up was performed.")
    yt_meta["raw_rows_requested_for_valid_account_target"]=youtube_scan_limit
    yt_meta["unique_output_candidates"]=len(yt)
    people=[x for x in ig if x["entity_type"]=="person"]; orgs=[x for x in ig if x["entity_type"]=="organization"]
    for name,rows in (("youtube_channel_candidates.csv",yt),("instagram_account_candidates.csv",ig),("instagram_person_candidates.csv",people),("instagram_organization_publisher_candidates.csv",orgs)):
        write_csv(out_dir/name,rows,ACCOUNT_FIELDS)
    (out_dir/"instagram_creator_seeds.txt").write_text("\n".join(x["account_handle"].lstrip("@") for x in ig if x["account_handle"])+"\n",encoding="utf-8")
    (out_dir/"youtube_channel_seeds.txt").write_text("\n".join(x["account_url"] for x in yt if x["account_url"])+"\n",encoding="utf-8")
    summary={"release":"Shorts-LM large discovery seed catalogue v0.2","generated_at":datetime.now(UTC).isoformat(),"counts":{"youtube_channel_candidates":len(yt),"instagram_account_candidates":len(ig),"instagram_person_candidates":len(people),"instagram_organization_publishers":len(orgs),"generated_hashtags":len(tags),"submitted_AI_youtube_leads":len(leads["youtube"]),"submitted_AI_instagram_leads":len(leads["instagram"])},"sources":{"youtube":yt_meta,"instagram":ig_meta},"limitations":["Not 10,000 verified humans per platform; records are account-level leads.","YouTube entity type is unknown; current Shorts activity must be checked.","Instagram person and organization counts are kept separate; no organization is relabelled as a person.","Cross-platform identities are not merged without explicit evidence.","No row grants retrieval, storage, analysis, derived-artifact retention or model-training rights.","Generated hashtags are not proof of native usage, popularity or retrieval yield."]}
    (out_dir/"QA_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-dir",type=Path,default=Path("data/research_catalogue"))
    p.add_argument("--output-dir",type=Path,default=Path("data/generated_seed_catalogue/v0.2"))
    p.add_argument("--youtube-limit",type=int,default=10000)
    p.add_argument("--instagram-limit",type=int,default=10000)
    p.add_argument("--hashtag-target",type=int,default=10650)
    p.add_argument("--hashtags-only",action="store_true")
    a=p.parse_args()
    if min(a.youtube_limit,a.instagram_limit,a.hashtag_target)<=0: p.error("targets must be positive")
    try: result=build(a.research_dir,a.output_dir,a.youtube_limit,a.instagram_limit,a.hashtag_target,a.hashtags_only)
    except (RuntimeError,OSError,csv.Error) as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not a.hashtags_only and result["counts"]["instagram_person_candidates"]<a.instagram_limit:
        print("WARNING: Instagram person-only count is below target; organization records were not used to top it up.",file=sys.stderr)
    return 0

if __name__=="__main__": raise SystemExit(main())
