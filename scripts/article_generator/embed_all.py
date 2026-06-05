"""Build or repair the full article embedding cache.

This maintenance script is intentionally not called from the Flask generate
button or the normal /scan endpoint. Run it manually when rebuilding the full
S3 vector cache is needed:

    python scripts/article_generator/embed_all.py
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(ROOT / "scripts" / "article_generator" / ".env", override=True)

from app import (  # noqa: E402
    ArticleVectorStore,
    EMBED_MODEL_ID,
    bedrock_embed,
    extract_h2_sections,
    strip_tags,
)
from vector_store import (  # noqa: E402
    LocalJsonStore,
    _cache_stats_from_payload,
    cache_writer_lock,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("embed_all")

WORKERS = int(os.getenv("EMBED_ALL_WORKERS", "8"))
FLUSH_EVERY = int(os.getenv("EMBED_ALL_FLUSH_EVERY", "100"))
LOCAL_PATH = SCRIPT_DIR / "article_vector_cache.json"


def fetch_posts() -> list[dict]:
    wp_url = os.getenv("WP_URL", "https://m.firekids.jp")
    wp_user = os.getenv("WP_USER", "")
    wp_pass = os.getenv("WP_APP_PASSWORD", "").replace(" ", "")
    auth = (wp_user, wp_pass) if wp_user and wp_pass else None
    api_base = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"

    all_posts: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            api_base,
            params={
                "per_page": 100,
                "page": page,
                "orderby": "modified",
                "order": "desc",
                "_fields": "id,title,excerpt,categories,date,modified,link,content",
            },
            auth=auth,
            timeout=90,
        )
        if resp.status_code == 400:
            break
        if resp.status_code != 200:
            raise RuntimeError(f"WP API error {resp.status_code}: {resp.text[:200]}")

        posts = resp.json()
        if not posts:
            break

        all_posts.extend(posts)
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        log.info("fetched page %s/%s posts_so_far=%s", page, total_pages, len(all_posts))
        if page >= total_pages:
            break
        page += 1

    return all_posts


def build_record(item: tuple[dict, str]) -> dict | None:
    post, content_hash = item
    pid = post.get("id")
    try:
        content_html = post.get("content", {}).get("rendered", "")
        title = strip_tags(post.get("title", {}).get("rendered", ""))
        excerpt = strip_tags(post.get("excerpt", {}).get("rendered", ""))[:300]
        h2_sections = extract_h2_sections(content_html, body_chars=400)
        h2_texts = [section["heading"] for section in h2_sections]
        body_plain = re.sub(r"\s+", " ", strip_tags(content_html)).strip()
        body_snippet = body_plain[:3000]

        article_text = title + "。" + excerpt + "。" + "。".join(h2_texts) + "。" + body_snippet[:1500]
        article_embedding = bedrock_embed(article_text)

        heading_embeddings: list[dict] = []
        for section in h2_sections:
            heading_text = section["heading"] + "\n" + section["body_snippet"]
            heading_embeddings.append({
                "heading": section["heading"],
                "text": heading_text,
                "vec": bedrock_embed(heading_text),
            })

        return {
            "post_id": pid,
            "title": title,
            "url": post.get("link", ""),
            "brand_categories": post.get("categories", []),
            "modified": post.get("modified", post.get("date", ""))[:19],
            "content_hash": content_hash,
            "article_embedding": article_embedding,
            "heading_embeddings": heading_embeddings,
            "h2_texts": h2_texts,
            "body_snippet": body_snippet,
            "embedding_model": EMBED_MODEL_ID,
            "updated_at": datetime.datetime.now().isoformat(),
        }
    except Exception as exc:
        log.error("embed_error post_id=%s err=%s", pid, exc)
        return None


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION", "ap-northeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def _remote_stats(s3, bucket: str, key: str) -> dict:
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return _cache_stats_from_payload(obj["Body"].read())
    except Exception:
        return {"count": 0, "with_article_embedding": 0, "with_heading_embeddings": 0}


def _is_downgrade(local_stats: dict, remote_stats: dict) -> bool:
    local_art = local_stats["with_article_embedding"]
    remote_art = remote_stats["with_article_embedding"]
    local_hdg = local_stats["with_heading_embeddings"]
    remote_hdg = remote_stats["with_heading_embeddings"]
    return local_art < remote_art or (local_art == remote_art and local_hdg < remote_hdg)


def write_cache(store: LocalJsonStore, upload_s3: bool) -> int:
    store._data["scanned_at"] = datetime.datetime.now().isoformat()
    store._data["meta"]["count"] = len(store._data["index"])
    serializable = {
        **store._data,
        "index": {str(k): v for k, v in store._data["index"].items()},
    }
    payload = json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))
    LOCAL_PATH.write_text(payload, encoding="utf-8")

    if upload_s3 and os.getenv("S3_BUCKET"):
        bucket = os.getenv("S3_BUCKET")
        final_key = os.getenv("VECTOR_CACHE_S3_KEY", "cache/article_vector_cache.json")
        building_key = final_key.replace(".json", ".building.json")
        local_stats = _cache_stats_from_payload(payload)
        s3 = _s3_client()

        with cache_writer_lock():
            s3.put_object(
                Bucket=bucket,
                Key=building_key,
                Body=payload.encode("utf-8"),
                ContentType="application/json",
                Metadata={
                    "count": str(local_stats["count"]),
                    "with_article_embedding": str(local_stats["with_article_embedding"]),
                    "with_heading_embeddings": str(local_stats["with_heading_embeddings"]),
                },
            )
            building_stats = _remote_stats(s3, bucket, building_key)
            if building_stats != local_stats:
                raise RuntimeError(f"building cache validation failed: {building_stats} != {local_stats}")

            remote_stats = _remote_stats(s3, bucket, final_key)
            if _is_downgrade(local_stats, remote_stats):
                log.warning("promotion_skipped_downgrade local=%s remote=%s", local_stats, remote_stats)
            else:
                s3.put_object(
                    Bucket=bucket,
                    Key=final_key,
                    Body=payload.encode("utf-8"),
                    ContentType="application/json",
                    Metadata={
                        "count": str(local_stats["count"]),
                        "with_article_embedding": str(local_stats["with_article_embedding"]),
                        "with_heading_embeddings": str(local_stats["with_heading_embeddings"]),
                    },
                )
                log.info("s3_promoted building_key=%s final_key=%s bytes=%s stats=%s",
                         building_key, final_key, len(payload), local_stats)

    return len(payload)


def main() -> int:
    store = LocalJsonStore(path=LOCAL_PATH, s3_bucket="", s3_key="")
    initial = store.meta()
    log.info(
        "initial count=%s with_article_embedding=%s with_heading_embeddings=%s",
        initial["count"],
        initial["with_article_embedding"],
        initial["with_heading_embeddings"],
    )

    posts = fetch_posts()
    to_embed: list[tuple[dict, str]] = []
    for post in posts:
        pid = post.get("id")
        if not pid:
            continue
        content_html = post.get("content", {}).get("rendered", "")
        content_hash = ArticleVectorStore.content_hash(content_html)
        existing = store.get(pid)
        if existing and not ArticleVectorStore.needs_reembed(existing, content_hash, EMBED_MODEL_ID):
            continue
        to_embed.append((post, content_hash))

    log.info("posts_needing_embedding=%s skipped=%s", len(to_embed), len(posts) - len(to_embed))

    started = time.time()
    completed = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(build_record, item): item[0].get("id") for item in to_embed}
        for future in as_completed(futures):
            record = future.result()
            if record is None:
                errors += 1
                continue

            store.upsert(record)
            completed += 1

            if completed % FLUSH_EVERY == 0:
                bytes_written = write_cache(store, upload_s3=False)
                elapsed = max(round(time.time() - started), 1)
                remaining = len(to_embed) - completed
                eta = round(remaining / (completed / elapsed)) if completed else 0
                log.info(
                    "progress %s/%s bytes=%s errors=%s elapsed=%ss eta=%ss",
                    completed,
                    len(to_embed),
                    bytes_written,
                    errors,
                    elapsed,
                    eta,
                )

    final_bytes = write_cache(store, upload_s3=True)
    final = store.meta()
    log.info(
        "complete bytes=%s count=%s with_article_embedding=%s with_heading_embeddings=%s errors=%s",
        final_bytes,
        final["count"],
        final["with_article_embedding"],
        final["with_heading_embeddings"],
        errors,
    )

    print(json.dumps({
        "count": final["count"],
        "with_article_embedding": final["with_article_embedding"],
        "with_heading_embeddings": final["with_heading_embeddings"],
        "embedding_model": EMBED_MODEL_ID,
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
