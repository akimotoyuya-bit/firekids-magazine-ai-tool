"""
FIRE KIDS Magazine 記事生成アプリ（AWS Bedrock + Claude版）

被り防止ロジック（多粒度 Embedding 方式）:

  スキャン時:
    - WordPress content.rendered を取得
    - H2 見出し + 直下本文 400 字を抽出
    - article_embedding  : title + excerpt + H2 一覧 + 本文冒頭 1500 字
    - heading_embeddings : H2 ごとのベクトル
    - content_hash で未変更記事の再 Embedding をスキップ

  生成時（3 ステージ）:
    Stage 1 – propose_structure()
      Claude にタイトル・H2 構成案・テーマを小型コール（最大 800 トークン）で生成させる。
      本文はまだ生成しない。

    Stage 2 – check_overlap()
      Level 1: 候補全体 vs article_embedding（閾値 0.88）
      Level 2: 候補 H2 vs heading_embeddings（1 記事に 3 本以上が閾値 0.86 超）
      被りあり → revise_structure() で再構成（最大 MAX_REGEN_RETRIES 回）

    Stage 3 – build_article_prompt() → invoke_claude()
      類似記事タイトル・類似 H2 を「避けるリスト」としてプロンプトに注入して本文生成。

  後処理 – check_ngram_overlap()
    文字 n-gram（デフォルト n=8）で body_snippet と Jaccard 比較。
    警告として返すが生成をブロックしない。

起動:
  cd scripts/article_generator
  python app.py   # localhost:8001
"""
import datetime
import json
import logging
import math
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, Response

# 兄弟モジュール（vector_store / inventory）を、
# - ローカル実行（python app.py / cwd=このフォルダ）
# - 本番（wsgi が article_generator.app をパッケージ読み込み）
# のどちらでも import できるよう、このファイルのフォルダを sys.path に追加する。
# これを忘れると本番で ModuleNotFoundError → gunicorn crash → App Runner が旧版へ
# 自動ロールバックし「デプロイしても何も変わらない」状態になる。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vector_store import ArticleVectorStore, get_store
from inventory import (
    find_by_fk, format_for_prompt, get_image_for_item, get_in_stock,
    inventory_summary, reload_from_bytes,
    select_feature_item, summarize_item,
)

# ─── 初期化 ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / "scripts" / "wp_uploader_local" / ".env", override=True)
load_dotenv(ROOT / "scripts" / "article_generator" / ".env", override=True)

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY", "firekids-default-secret-change-me")

# ─── ロギング ──────────────────────────────────────────────────────────────────
# ジョブの進行を追跡するための構造化ログ。秘密情報（キー・パスワード等）は
# 絶対に出力しない。job_id / brand / stage など非機密の運用情報のみを記録する。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fk_generator")

# ─── 非同期ジョブストア ────────────────────────────────────────────────────────
# App Runner のロードバランサーは ~120 秒でタイムアウトするため、
# 記事生成（1〜3 分）を同期 HTTP で返すと必ず 504 になる。
# → POST /generate で即座に job_id を返し、バックグラウンドで生成。
# → GET /generate-status/<job_id> で完了を 3 秒ごとにポーリング。
# gunicorn は 1 worker + 複数スレッドで動かすことで JOBS dict を共有する。
_JOB_LOCK: threading.Lock = threading.Lock()
JOBS: dict[str, dict] = {}
_JOB_TTL_SECONDS = 1800  # 30 分で古いジョブを削除


def _cleanup_jobs() -> None:
    """古いジョブを定期削除（メモリリーク防止）。"""
    cutoff = time.time() - _JOB_TTL_SECONDS
    with _JOB_LOCK:
        expired = [jid for jid, j in JOBS.items() if j.get("created_at", 0) < cutoff]
        for jid in expired:
            JOBS.pop(jid, None)


class InventoryMissingError(Exception):
    """ブランド指定生成で在庫が 1 件も見つからず、かつ一般記事継続も許可されていない。"""


# ─── スキャン状態（多重起動防止 + 進行ステータス）─────────────────────────────
# 初回キャッシュ無しの状態で生成を連打すると、WordPress 全件スキャンが
# 何本も並行起動してしまう。_SCAN_STATE でロックを取り、1 本だけ走らせる。
_SCAN_LOCK: threading.Lock = threading.Lock()
_SCAN_STATE: dict = {
    "running":          False,
    "last_started_at":  "",
    "last_finished_at": "",
    "last_error":       "",
    "degraded_modes":   [],
}


def _run_scan_locked(incremental: bool) -> bool:
    """スキャンをロック付きで実行する。既に実行中なら False を返して何もしない。

    呼び出し側がスレッドを起こすかどうかは任意。この関数自体は同期実行。
    """
    with _SCAN_LOCK:
        if _SCAN_STATE["running"]:
            return False
        _SCAN_STATE["running"]         = True
        _SCAN_STATE["last_started_at"] = datetime.datetime.now().isoformat()
        _SCAN_STATE["last_error"]      = ""
        _SCAN_STATE["degraded_modes"]  = []
    reset_embed_state()
    log.info("scan_started incremental=%s", incremental)
    try:
        scan_wordpress_posts(incremental=incremental)
    except Exception as e:
        _SCAN_STATE["last_error"] = str(e)
        log.warning("scan_error incremental=%s err=%s", incremental, e)
    finally:
        if embedding_degraded():
            _SCAN_STATE["degraded_modes"] = ["embedding_unavailable"]
        _SCAN_STATE["running"]          = False
        _SCAN_STATE["last_finished_at"] = datetime.datetime.now().isoformat()
        log.info("scan_finished degraded=%s", _SCAN_STATE["degraded_modes"])
    return True

# ─── 定数 ────────────────────────────────────────────────────────────────────

EMBED_MODEL_ID        = os.getenv("EMBED_MODEL_ID",        "amazon.titan-embed-text-v2:0")
CACHE_REFRESH_HOURS   = int(os.getenv("CACHE_REFRESH_HOURS",   "12"))
LOOKBACK_DAYS         = int(os.getenv("LOOKBACK_DAYS",          "60"))
ARTICLE_SIM_THRESHOLD = float(os.getenv("ARTICLE_SIM_THRESHOLD", "0.88"))
HEADING_SIM_THRESHOLD = float(os.getenv("HEADING_SIM_THRESHOLD", "0.86"))
HEADING_HIT_MIN       = int(os.getenv("HEADING_HIT_MIN",        "3"))
MAX_REGEN_RETRIES     = int(os.getenv("MAX_REGEN_RETRIES",      "3"))
NGRAM_SIZE            = int(os.getenv("NGRAM_SIZE",             "8"))
NGRAM_THRESHOLD       = float(os.getenv("NGRAM_THRESHOLD",      "0.18"))

BRANDS = {
    "ROLEX":     {"jp": "ロレックス",               "category_id": 8,    "path": "rolex"},
    "OMEGA":     {"jp": "オメガ",                   "category_id": 9,    "path": "omega"},
    "SEIKO":     {"jp": "セイコー",                 "category_id": 10,   "path": "seiko"},
    "CITIZEN":   {"jp": "シチズン",                 "category_id": 11,   "path": "citizen"},
    "IWC":       {"jp": "IWC",                      "category_id": 12,   "path": "iwc"},
    "TUDOR":     {"jp": "チューダー",               "category_id": 13,   "path": "tudor"},
    "ORIENT":    {"jp": "オリエント",               "category_id": 14,   "path": "orient"},
    "LONGINES":  {"jp": "ロンジン",                 "category_id": 15,   "path": "longines"},
    "JLC":       {"jp": "ジャガー・ルクルト",       "category_id": 16,   "path": "jaeger-lecoultre"},
    "CARTIER":   {"jp": "カルティエ",               "category_id": 17,   "path": "cartier"},
    "UNIVERSAL": {"jp": "ユニバーサルジュネーブ",   "category_id": 18,   "path": "universal-geneve"},
    "BREITLING": {"jp": "ブライトリング",           "category_id": 19,   "path": "breitling"},
    "VACHERON":  {"jp": "ヴァシュロン・コンスタンタン", "category_id": 20, "path": "vacheron-constantin"},
    "THEME":     {"jp": "FIRE KIDS Magazine",       "category_id": None, "path": "column"},
    "OTHER":     {"jp": "その他",                   "category_id": None, "path": "other"},
}

TONES = ["guide", "verify", "comparison", "ranking"]

TONE_LABELS = {
    "guide":      "ガイド系（○○とは・解説）",
    "verify":     "検証系（本当に○○？・やめとけ）",
    "comparison": "比較系（AとBの違い）",
    "ranking":    "ランキング系（TOP10・10選）",
}

TONE_CHARS = {
    "guide":      "7000〜9000字",
    "verify":     "6000〜8000字",
    "comparison": "6500〜8500字",
    "ranking":    "7000〜9000字",
}


def _parse_modified(value: str) -> datetime.datetime | None:
    """WordPress modified/date 文字列を naive datetime に正規化する。"""
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value[:19])
    except Exception:
        return None


def _lookback_cutoff() -> datetime.datetime:
    return datetime.datetime.now() - datetime.timedelta(days=LOOKBACK_DAYS)


def _brand_records(brand_key: str) -> list[dict]:
    store     = get_store()
    brand_cat = BRANDS.get(brand_key, {}).get("category_id")
    records   = store.list_by_category(brand_cat) if brand_cat else store.list_all()
    return sorted(records, key=lambda r: r.get("modified", ""), reverse=True)


def _prioritized_cached_records(brand_key: str) -> list[dict]:
    """生成時の重複チェック用キャッシュ。

    通常運用では直近 LOOKBACK_DAYS 日を優先する。古い記事は WordPress へ
    再取得しに行かず、S3/ローカルに存在するキャッシュだけを参照する。
    """
    cutoff = _lookback_cutoff()
    recent: list[dict] = []
    older_cached: list[dict] = []
    for record in _brand_records(brand_key):
        modified = _parse_modified(record.get("modified", ""))
        if modified and modified >= cutoff:
            recent.append(record)
        else:
            older_cached.append(record)
    return recent + older_cached


# ─── AWS Bedrock ──────────────────────────────────────────────────────────────

def get_bedrock_client():
    import boto3
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def invoke_claude(prompt: str, max_tokens: int = 8000) -> str:
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def invoke_claude_stream(prompt: str, on_chunk, max_tokens: int = 8000) -> str:
    """Bedrock のレスポンスストリーミングで本文を生成し、
    テキスト断片が届くたびに on_chunk(delta_text) を呼ぶ。完成テキストを返す。

    リアルタイムの「生成中」プレビュー用。ストリーミング非対応エラー時は
    通常の invoke_claude にフォールバックする。
    """
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = client.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception:
        full = invoke_claude(prompt, max_tokens=max_tokens)
        if on_chunk:
            on_chunk(full)
        return full

    parts: list[str] = []
    for event in resp["body"]:
        chunk = event.get("chunk")
        if not chunk:
            continue
        data = json.loads(chunk["bytes"].decode("utf-8"))
        if data.get("type") == "content_block_delta":
            text = data.get("delta", {}).get("text", "")
            if text:
                parts.append(text)
                if on_chunk:
                    on_chunk(text)
    return "".join(parts)


# Embedding 失敗をジョブ単位で追跡するためのスレッドローカル状態。
# 生成はバックグラウンドスレッドで動くため、スレッドごとに独立して持つ。
_embed_state = threading.local()


def reset_embed_state() -> None:
    _embed_state.failed = False


def embedding_degraded() -> bool:
    return getattr(_embed_state, "failed", False)


def bedrock_embed(text: str) -> list | None:
    """Titan Embeddings でテキストをベクトル化。失敗時は None（劣化動作）。

    呼び出し例外時はスレッドローカルに失敗フラグを立て、上位で
    degraded_modes=["embedding_unavailable"] として表面化できるようにする。
    """
    if not text.strip():
        return None
    try:
        client = get_bedrock_client()
        resp = client.invoke_model(
            modelId=EMBED_MODEL_ID,
            body=json.dumps({"inputText": text[:8000]}),
            contentType="application/json",
            accept="application/json",
        )
        emb = json.loads(resp["body"].read()).get("embedding")
        if not emb:
            _embed_state.failed = True
        return emb
    except Exception as e:
        _embed_state.failed = True
        log.warning("embed_error err=%s", e)
        return None


def cosine(a: list | None, b: list | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ─── HTML ヘルパー ────────────────────────────────────────────────────────────

def strip_tags(html: str) -> str:
    """HTML タグを除去してプレーンテキスト化する。"""
    text = re.sub(r"<[^>]+>", " ", html)
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&nbsp;", " "), ("&#8211;", "–"), ("&#8212;", "—"),
        ("&quot;", '"'), ("&#39;", "'"),
    ]:
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def extract_h2_sections(html: str, body_chars: int = 400) -> list[dict]:
    """H2 見出しと直下の本文冒頭テキストを抽出する。

    戻り値: [{"heading": str, "body_snippet": str}, ...]
    """
    # <h2>…</h2> で分割
    # parts = [pre_h2, h2_1, after_h2_1, h2_2, after_h2_2, ...]
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", html, flags=re.IGNORECASE | re.DOTALL)
    sections: list[dict] = []
    for i in range(1, len(parts), 2):
        heading = strip_tags(parts[i]).strip()
        if not heading:
            continue
        after = parts[i + 1] if i + 1 < len(parts) else ""
        # H3 以下の見出しを除去して本文のみ取得
        body_html = re.sub(r"<h[3-6][^>]*>.*?</h[3-6]>", "", after,
                           flags=re.IGNORECASE | re.DOTALL)
        body_text = re.sub(r"\s+", " ", strip_tags(body_html)).strip()
        sections.append({
            "heading":      heading,
            "body_snippet": body_text[:body_chars],
        })
    return sections


# ─── WordPress スキャン ───────────────────────────────────────────────────────

def scan_wordpress_posts(incremental: bool = True) -> dict:
    """WordPress REST API で記事を取得してキャッシュを更新する。

    - content.rendered / modified / link を取得
    - H2 抽出 → article_embedding + heading_embeddings を計算
    - content_hash が同じ記事は Embedding をスキップ（増分対応）
    - flush() で JSON ファイル + S3 に永続化
    """
    store   = get_store()
    wp_url  = os.getenv("WP_URL", "https://m.firekids.jp")
    wp_user = os.getenv("WP_USER", "")
    wp_pass = os.getenv("WP_APP_PASSWORD", "").replace(" ", "")
    auth    = (wp_user, wp_pass) if wp_user and wp_pass else None
    api_base = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"

    # 増分スキャン: 通常運用では直近 LOOKBACK_DAYS 日を下限にし、
    # 古い記事の全件再 Embedding を自動実行しない。
    after_param: str | None = None
    if incremental:
        m = store.meta()
        sa = m.get("scanned_at", "")
        cutoff = _lookback_cutoff()
        after_dt = cutoff
        if sa:
            last = _parse_modified(sa)
            if last and last > after_dt:
                after_dt = last
        after_param = after_dt.isoformat(timespec="seconds")
        log.info("scan_incremental_window after=%s lookback_days=%s", after_param, LOOKBACK_DAYS)

    total_new = total_updated = 0
    total_skipped = 0
    page = 1
    _FLUSH_EVERY = 50  # 50件ごとに中間 flush して S3 に保存

    while True:
        params: dict = {
            "per_page":  100,  # content.rendered を含むが大きめにして WP I/O を削減
            "page":      page,
            "orderby":   "modified",
            "order":     "desc",
            "_fields":   "id,title,excerpt,categories,date,modified,link,content",
        }
        if after_param:
            params["modified_after"] = after_param

        try:
            resp = requests.get(api_base, params=params, auth=auth, timeout=60)
        except requests.RequestException as e:
            raise RuntimeError(f"WordPress API アクセスエラー: {e}")

        if resp.status_code == 400:
            break
        if resp.status_code != 200:
            raise RuntimeError(f"WP API エラー {resp.status_code}: {resp.text[:200]}")

        posts = resp.json()
        if not posts:
            break

        for p in posts:
            pid = p.get("id")
            if not pid:
                continue

            content_html = p.get("content", {}).get("rendered", "")
            new_hash     = ArticleVectorStore.content_hash(content_html)
            existing     = store.get(pid)

            if existing and not ArticleVectorStore.needs_reembed(existing, new_hash, EMBED_MODEL_ID):
                total_skipped += 1
                continue  # 変更なし・Embedding スキップ

            title    = strip_tags(p.get("title",   {}).get("rendered", ""))
            excerpt  = strip_tags(p.get("excerpt", {}).get("rendered", ""))[:300]
            cats     = p.get("categories", [])
            modified = p.get("modified", p.get("date", ""))[:19]
            url      = p.get("link", "")

            # H2 セクション抽出
            h2_sections = extract_h2_sections(content_html, body_chars=400)
            h2_texts    = [s["heading"] for s in h2_sections]

            # 本文スニペット（n-gram 比較用）
            body_plain   = re.sub(r"\s+", " ", strip_tags(content_html)).strip()
            body_snippet = body_plain[:3000]

            # article_embedding: タイトル + 抜粋 + H2 一覧 + 本文冒頭 1500 字
            art_text = (
                title + "。"
                + excerpt + "。"
                + "。".join(h2_texts) + "。"
                + body_snippet[:1500]
            )
            art_emb = bedrock_embed(art_text)

            # heading_embeddings: H2 テキスト + 直下本文冒頭
            heading_embs: list[dict] = []
            for sec in h2_sections:
                h_text = sec["heading"] + "\n" + sec["body_snippet"]
                h_vec  = bedrock_embed(h_text)
                heading_embs.append({
                    "heading": sec["heading"],
                    "text":    h_text,
                    "vec":     h_vec,
                })

            record = {
                "post_id":            pid,
                "title":              title,
                "url":                url,
                "brand_categories":   cats,
                "modified":           modified,
                "content_hash":       new_hash,
                "article_embedding":  art_emb,
                "heading_embeddings": heading_embs,
                "h2_texts":           h2_texts,
                "body_snippet":       body_snippet,
                "embedding_model":    EMBED_MODEL_ID,
                "updated_at":         datetime.datetime.now().isoformat(),
            }
            store.upsert(record)

            if existing:
                total_updated += 1
            else:
                total_new += 1

            # 一定件数ごとに中間 flush（S3 保存）して進捗を保護する
            if (total_new + total_updated) % _FLUSH_EVERY == 0:
                store.flush()
                log.info("scan_progress page=%s new=%s updated=%s skipped=%s",
                         page, total_new, total_updated, total_skipped)

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        log.info("scan_page page=%s/%s new=%s updated=%s skipped=%s",
                 page, total_pages, total_new, total_updated, total_skipped)
        if page >= total_pages:
            break
        page += 1

    store.flush()
    m = store.meta()
    m["new_added"] = total_new
    m["updated"]   = total_updated
    m["skipped"]   = total_skipped
    log.info("scan_complete total=%s new=%s updated=%s skipped=%s art_emb=%s hdg_emb=%s",
             m["count"], total_new, total_updated, total_skipped,
             m["with_article_embedding"], m["with_heading_embeddings"])
    return m


def ensure_cache_fresh() -> None:
    """キャッシュが空または CACHE_REFRESH_HOURS より古ければ増分スキャンを実行する。
    失敗時は生成を続行（劣化動作）。

    初回（キャッシュ未作成）はスキャンをバックグラウンドで実行して
    記事生成をブロックしない。既存キャッシュがあれば同期実行（増分のみ）。
    """
    m          = get_store().meta()
    scanned_at = m.get("scanned_at", "")
    count      = m.get("count", 0)

    # 初回: ローカルキャッシュが存在しない or 空
    # → バックグラウンドで走らせて生成はすぐ開始する。
    #   _run_scan_locked が二重起動を防ぐので、連打されても 1 本だけ走る。
    # 通常導線では全件再 Embedding を走らせず、直近 LOOKBACK_DAYS 日だけを見る。
    # 全件構築は scripts/article_generator/embed_all.py を手動実行する。
    if not scanned_at or not count:
        if not _SCAN_STATE["running"]:
            threading.Thread(
                target=_run_scan_locked, args=(True,), daemon=True
            ).start()
        return  # 生成を即ブロック解除

    # 2 回目以降: キャッシュが古ければ増分スキャン（短時間・同期）
    needs = False
    try:
        last  = datetime.datetime.fromisoformat(scanned_at)
        age_h = (datetime.datetime.now() - last).total_seconds() / 3600
        needs = age_h >= CACHE_REFRESH_HOURS
    except Exception:
        needs = True

    if needs:
        _run_scan_locked(incremental=True)


# ─── 類似度チェック ───────────────────────────────────────────────────────────

def check_overlap(brand_key: str, title: str, h2s: list[str]) -> dict:
    """2 レベルの被り検出。

    Level 1: 候補全体ベクトル vs article_embedding >= ARTICLE_SIM_THRESHOLD
    Level 2: 候補 H2 のうち HEADING_HIT_MIN 本以上が同一記事の heading_embeddings
             と >= HEADING_SIM_THRESHOLD で一致

    戻り値: {"ok": bool, "flagged": [{"title", "url", "article_similarity",
                                       "heading_hit_count", "hit_pairs", "h2_texts"}, ...]}
    """
    past_arts = _prioritized_cached_records(brand_key)

    # 候補の article-level embedding
    art_text = title + "。" + "。".join(h2s)
    art_vec  = bedrock_embed(art_text)

    # 候補 H2 ごとの embedding（まとめて計算）
    h2_vecs = [bedrock_embed(h) for h in h2s]

    flagged: list[dict] = []

    for past in past_arts:
        past_art_emb = past.get("article_embedding")
        art_sim      = cosine(art_vec, past_art_emb)

        # H2 レベル比較
        heading_hit_count = 0
        hit_pairs: list[dict] = []
        past_h_embs = past.get("heading_embeddings") or []

        for cand_h, cand_v in zip(h2s, h2_vecs):
            if not cand_v:
                continue
            best_sim    = 0.0
            best_past_h = ""
            for ph in past_h_embs:
                ph_vec = ph.get("vec")
                if ph_vec:
                    s = cosine(cand_v, ph_vec)
                    if s > best_sim:
                        best_sim    = s
                        best_past_h = ph.get("heading", "")
            if best_sim >= HEADING_SIM_THRESHOLD:
                heading_hit_count += 1
                hit_pairs.append({
                    "candidate":  cand_h,
                    "past":       best_past_h,
                    "similarity": round(best_sim, 3),
                })

        if art_sim >= ARTICLE_SIM_THRESHOLD or heading_hit_count >= HEADING_HIT_MIN:
            flagged.append({
                "title":              past.get("title", ""),
                "url":                past.get("url", ""),
                "article_similarity": round(art_sim, 3),
                "heading_hit_count":  heading_hit_count,
                "hit_pairs":          hit_pairs,
                "h2_texts":           past.get("h2_texts", []),
            })

    # 被り度の高い順にソート
    flagged.sort(key=lambda x: (x["heading_hit_count"], x["article_similarity"]), reverse=True)

    return {"ok": len(flagged) == 0, "flagged": flagged[:3]}


# ─── n-gram 重複チェック（本文生成後） ───────────────────────────────────────

def check_ngram_overlap(generated_text: str, brand_key: str) -> list[dict]:
    """文字 n-gram の Jaccard 類似度で本文表現の重複を検出する。
    生成をブロックせず警告として返す。
    モデル名・記号・改行を正規化してから比較する。
    """
    def clean(text: str) -> str:
        # タイトル行・メタ行・URL・記号を除去
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]", "", text)
        return text

    def char_ngrams(text: str, n: int) -> set[str]:
        return set(text[i:i + n] for i in range(len(text) - n + 1))

    gen_clean = clean(generated_text)
    gen_grams = char_ngrams(gen_clean, NGRAM_SIZE)
    if not gen_grams:
        return []

    past_arts = _prioritized_cached_records(brand_key)

    flagged: list[dict] = []
    for art in past_arts:
        snippet = art.get("body_snippet", "")
        if not snippet:
            continue
        past_grams = char_ngrams(clean(snippet), NGRAM_SIZE)
        if not past_grams:
            continue
        union = gen_grams | past_grams
        if not union:
            continue
        jaccard = len(gen_grams & past_grams) / len(union)
        if jaccard >= NGRAM_THRESHOLD:
            flagged.append({
                "title":        art.get("title", ""),
                "url":          art.get("url", ""),
                "ngram_overlap": round(jaccard, 3),
            })

    flagged.sort(key=lambda x: x["ngram_overlap"], reverse=True)
    return flagged[:5]


# ─── ルール・コンテキスト読み込み ────────────────────────────────────────────

def load_rules_context() -> tuple[str, str, str]:
    rules = ""
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        rules = claude_md.read_text(encoding="utf-8")[:6000]

    caliber_summary = ""
    caliber_db = ROOT / "data" / "caliber_db.json"
    if caliber_db.exists():
        try:
            db = json.loads(caliber_db.read_text(encoding="utf-8"))
            caliber_summary = f"キャリバー DB 保有ブランド: {list(db.keys())}"
        except Exception:
            pass

    correction_summary = ""
    correction_log = ROOT / "data" / "correction_log.json"
    if correction_log.exists():
        try:
            log = json.loads(correction_log.read_text(encoding="utf-8"))
            corrections = log.get("caliber_corrections", {})
            total = sum(len(v) for v in corrections.values())
            correction_summary = f"修正ログ登録数: {total}件（人間チェック済み）"
        except Exception:
            pass

    return rules, caliber_summary, correction_summary


# ─── Stage 1: 構成案の生成 ───────────────────────────────────────────────────

def sample_past_titles(brand_key: str, limit: int = 14) -> list[str]:
    """指定ブランドの過去記事タイトルを取得する（タイトルの口調・表現の参考用）。

    新しい記事ほど現行の文体に近いので modified 降順で返す。
    キャッシュが空なら空リスト（その場合は参考なしで生成）。
    """
    records   = _prioritized_cached_records(brand_key)
    titles: list[str] = []
    for r in records:
        t = (r.get("title") or "").strip()
        if t:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def propose_structure(brand_key: str, tone: str = "auto", item: dict | None = None,
                      direction: str = "") -> dict:
    """タイトル・H2 構成案・テーマ・キーワードを小型コール（最大 800 トークン）で生成する。

    tone:
      - "auto"（既定）: 過去記事タイトルの口調・表現を参照し、Claude が最適な切り口
        （ガイド/検証/比較/ランキング等）を自動選定する。ユーザーはブランドを選ぶだけ。
      - それ以外      : 指定トーンで企画させる（従来動作）。
    item が渡された場合はその在庫商品に特化した構成を提案させる。
    被り判定はここでは行わない（check_overlap で行う）。

    戻り値: {"title", "h2s", "theme", "keywords"}
    """
    brand_jp  = BRANDS[brand_key]["jp"]
    is_auto   = (not tone) or tone == "auto"
    tone_jp   = TONE_LABELS.get(tone, "")

    # 過去タイトルを「口調・表現の参考」として注入（被り回避は後段の check_overlap が担う）
    past_titles = sample_past_titles(brand_key)
    if past_titles:
        style_block = (
            "【過去記事タイトル（口調・表現・粒度の参考）】\n"
            + "\n".join(f"・{t}" for t in past_titles)
            + "\n\n上記タイトルの『言い回し・丁寧さ・語尾・記号の使い方・長さ感』を踏襲してください。\n"
            "ただし扱うテーマ・切り口は上記と重複させず、必ず新しい内容にしてください。\n"
        )
    else:
        style_block = ""

    if is_auto:
        tone_directive = (
            "記事タイプ（ガイド系/検証系/比較系/ランキング系など）は、"
            "このブランドで読者の検索需要が高く、かつ過去記事と被らないものをあなたが選んでください。"
        )
    else:
        tone_directive = f"記事タイプは「{tone_jp}」で企画してください。"

    if item:
        item_block = f"""【特集対象の在庫商品】
ブランド: {item['brand_raw']}  モデル: {item['model']}  製造年代: {item.get('era', '')}
{f"Ref.{item['ref']}" if item.get('ref') else ""}  {f"Cal.{item['cal']}" if item.get('cal') else ""}
{f"備考: {item['notes']}" if item.get('notes') else ""}

この商品を記事の中心に据え、読者が「この時計をもっと知りたい・手に入れたい」と感じる構成を提案してください。
商品を直接売り込む表現は避け、知識・歴史・選び方の文脈で自然に登場させてください。"""
    else:
        item_block = ""

    direction_block = ""
    if direction:
        direction_block = f"""【今回ユーザーが寄せたい方向性】
{direction}

この方向性を優先して企画してください。ただし事実確認できない内容、価格断定、個別商品URL、FK番号は使わないでください。
"""

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事を1本企画してください。
{tone_directive}
{item_block}
{direction_block}
{style_block}SEO 効果が高く、読者が具体的に求めているテーマを選んでください。

以下の JSON 形式のみで出力してください（前後に説明文を付けない）:
{{"title": "記事タイトル（｜FIRE KIDS Magazine は付けない・具体的なテーマを含む）",
  "tone": "選んだ記事タイプ（guide/verify/comparison/ranking のいずれか）",
  "h2s": ["見出し1", "見出し2", "見出し3", "見出し4", "見出し5", "見出し6"],
  "theme": "記事で扱う内容の詳細を2〜3文で",
  "keywords": "キーワード1, キーワード2, キーワード3"}}"""

    raw = invoke_claude(prompt, max_tokens=800)
    m   = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            chosen_tone = str(d.get("tone", "")).strip().lower()
            if chosen_tone not in TONE_LABELS:
                chosen_tone = tone if not is_auto else "guide"
            return {
                "title":    str(d.get("title",    "")).strip(),
                "tone":     chosen_tone,
                "h2s":      [str(h).strip() for h in d.get("h2s", []) if str(h).strip()],
                "theme":    str(d.get("theme",    "")).strip(),
                "keywords": str(d.get("keywords", "")).strip(),
            }
        except Exception:
            pass
    return {"title": "", "tone": (tone if not is_auto else "guide"),
            "h2s": [], "theme": raw.strip()[:200], "keywords": ""}


def revise_structure(brand_key: str, tone: str, previous: dict, flagged: list,
                     direction: str = "") -> dict:
    """被りが検出された構成案を類似記事情報を与えて再構成させる。

    flagged: check_overlap() の flagged リスト
    """
    brand_jp = BRANDS[brand_key]["jp"]
    tone_jp  = TONE_LABELS.get(tone, "ガイド系")

    lines: list[str] = []
    for f in flagged[:3]:
        lines.append(f"既存記事: 「{f['title']}」（{f['url']}）")
        for p in f.get("hit_pairs", [])[:4]:
            lines.append(
                f"  → あなたの「{p['candidate']}」が既存の「{p['past']}」と類似"
                f"（類似度 {p['similarity']}）"
            )
    conflict_text = "\n".join(lines) if lines else "（詳細なし）"
    direction_block = f"\n【維持したい方向性】\n{direction}\n" if direction else ""

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事（{tone_jp}）の企画を修正してください。

【前回の企画案（構成被りあり）】
タイトル: {previous.get('title', '')}
H2 構成: {json.dumps(previous.get('h2s', []), ensure_ascii=False)}

【被りが検出された既存記事との比較】
{conflict_text}
{direction_block}

上記の章立て・切り口と重複しない新しい企画案を出してください。
同じブランドでも全く別の角度（対象年代・モデル系統・読者層・技術視点など）を選んでください。

以下の JSON 形式のみで出力してください:
{{"title": "修正後のタイトル",
  "h2s": ["見出し1", "見出し2", "見出し3", "見出し4", "見出し5"],
  "theme": "修正後のテーマ詳細を2〜3文で",
  "keywords": "キーワード1, キーワード2, キーワード3"}}"""

    raw = invoke_claude(prompt, max_tokens=800)
    m   = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            return {
                "title":    str(d.get("title",    "")).strip(),
                "h2s":      [str(h).strip() for h in d.get("h2s", []) if str(h).strip()],
                "theme":    str(d.get("theme",    "")).strip(),
                "keywords": str(d.get("keywords", "")).strip(),
            }
        except Exception:
            pass
    return previous  # フォールバック: 前の案をそのまま使う


# ─── Stage 3: 本文生成プロンプト ─────────────────────────────────────────────

def build_article_prompt(
    brand_key: str,
    tone: str,
    title: str,
    theme: str,
    keywords: str,
    avoid_articles: list,   # check_overlap の flagged リスト
    item: dict | None = None,
    direction: str = "",
) -> str:
    brand      = BRANDS.get(brand_key, BRANDS["OTHER"])
    brand_jp   = brand["jp"]
    cat_id     = brand["category_id"]
    tone_label = f"{TONE_LABELS.get(tone, 'ガイド系')} {TONE_CHARS.get(tone, '7000〜9000字')}"
    _, caliber_summary, correction_summary = load_rules_context()

    cta_base = (
        f"https://firekids.jp/products/list?category_id={cat_id}"
        "&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
        if cat_id else
        "https://firekids.jp/?utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
    )

    inventory_block = ""
    image_placeholder = ""
    if item:
        inventory_block = f"""━━━━━ 在庫連携：特集対象商品 ━━━━━
{format_for_prompt(item)}

執筆ルール:
- この商品（{item['brand_raw']} {item['model']}）を記事の軸として自然に紹介すること
- 「当店に入荷」「実際に手に取れる」「在庫あり」等の表現で販売ページへの動線を作ること
- 価格・仕入れ値は一切記載しない
- 商品の特性・時代背景・選び方の文脈で登場させる（押し売り感を出さない）
- CTA には必ず {cta_base} を使用すること

"""
        # 画像プレースホルダー（LLM に URL を渡さず後処理で置換する）
        img = get_image_for_item(item)
        if img:
            image_placeholder = f"__IMAGE_PLACEHOLDER_{item['fk_id']}__"
            inventory_block += (
                f"━━━━━ 商品画像 ━━━━━\n"
                f"記事内の商品紹介セクションの直後に、以下の文字列を**そのまま**出力してください（改変・省略禁止）:\n"
                f"{image_placeholder}\n\n"
            )

    avoid_block = ""
    if avoid_articles:
        lines = []
        for f in avoid_articles[:3]:
            lines.append(f"・「{f['title']}」（{f.get('url', '')}）")
            for p in f.get("hit_pairs", [])[:3]:
                lines.append(f"  ↳ 章「{p['past']}」と類似 → 同じ切り口・具体例・導入を避ける")
        avoid_block = "━━━━━ 内容が被ってはいけない既存記事 ━━━━━\n" + "\n".join(lines) + "\n"

    direction_block = ""
    if direction:
        direction_block = f"""━━━━━ 今回ユーザーが寄せたい方向性 ━━━━━
{direction}

この方向性を本文の切り口・導入・見出しの優先順位に反映する。
ただし未検証事実、価格断定、FK番号、個別商品URLは使わない。

"""

    purchase_block = f"""━━━━━ 購買意欲を高める方針 ━━━━━
- 読者が「{brand_jp} を実際に探してみたい・手に入れたい」と感じる読後感を目指す。
- 資産価値・状態の見極め・長く使う満足感など、所有/購入の魅力を具体的に描く。
- 過去記事の口調・見出し設計は「参考」にとどめ、本文の構成・切り口・具体例は被らせない。
- 煽り・誇張・断定は避け、信頼できる専門メディアとして購買の背中を押す。
- CTA はブランドカテゴリページ（{cta_base}）に誘導し、個別商品ページには誘導しない。

"""

    prompt = f"""あなたは FIRE KIDS Magazine の記事ライターです。
以下の条件に従い、ヴィンテージ時計の SEO 記事（Markdown 形式）を1本生成してください。

━━━━━ 記事情報 ━━━━━
ブランド: {brand_jp}（フォルダ: {brand_key}）
タイトル: {title}｜FIRE KIDS Magazine
テーマ: {theme}
トーン: {tone_label}
キーワード: {keywords}
生成日: {datetime.date.today().strftime("%Y.%m.%d")}

{purchase_block}{inventory_block}{direction_block}{avoid_block}
━━━━━ データソース情報 ━━━━━
{caliber_summary}
{correction_summary}
※ 事実情報（Cal.番号・石数・振動数・年代・Ref.番号）は必ず caliber_db.json と
  correction_log.json の値に基づくこと。DB にない情報は省略すること。

━━━━━ 絶対ルール ━━━━━
1. FK 番号（FK + 6桁数字）を本文に含めない
2. 相場価格・販売価格を記載しない
3. 個別商品 URL を使わない
4. CTA はカテゴリページのみ: {cta_base}
5. 外部サイト（Wikipedia・Ranfft 等）の情報を事実として採用しない
6. 「店頭でよく聞かれる」等の擬似エピソードを書かない
7. 「断言します」「時計屋として」等の語気を使わない
8. 職業×特定モデルを根拠なく結びつけない
9. 商品説明文をそのまま羅列しない
10. 「確認できていない」「未登録」等の内部用語を出さない

━━━━━ 必須構成 ━━━━━
1. # タイトル（上記タイトルをそのまま使う）
2. 対象ブランド: {brand_jp}
   生成日: {datetime.date.today().strftime("%Y.%m.%d")}
   ---
3. 導入文（2〜3段落）
4. ---
5. ## セクション H2（上記で決めた H2 を順番どおりに使う）
   - 各 H2 冒頭に結論1文（30〜50字）
   - スペック比較は Markdown テーブル
   - Ref.番号・Cal.番号・ケースサイズは **太字**
6. ## こんな方におすすめしたい（H3 で 3〜4 ペルソナ）
7. ## よくある質問（Q/A 形式 3〜5問）
8. ## まとめ
9. CTA（中間と末尾の2箇所）:
   → [具体的な文言]
   {cta_base}

━━━━━ 文体ルール ━━━━━
- 丁寧語・専門性あり・堅すぎない
- 語尾: 「〜ではないでしょうか」「〜といえます」
- 「関連記事」セクション不要
- 「結論から〜」は記事全体で最大1箇所

記事本文を Markdown 形式で生成してください（タイトル行から開始）。"""

    return prompt, image_placeholder


# ─── 生成オーケストレーション ─────────────────────────────────────────────────

def generate_article(brand_key: str, tone: str = "auto", fk_id: str = "",
                     on_stage=None, on_chunk=None, allow_no_inventory: bool = False,
                     direction: str = "") -> dict:
    """3 ステージ生成フロー + 後処理 n-gram チェック。

    在庫連携:
      - fk_id 指定時: 在庫 CSV から商品情報を取得（ブランド上書き）
      - fk_id 未指定（ブランドのみ）時: select_feature_item() で記事軸を自動選定
        在庫が無く allow_no_inventory=False なら InventoryMissingError を送出

    on_stage(msg, stage_id): 進行状況（UI 表示 + ログ）
    on_chunk(text): 本文生成中のテキスト断片（リアルタイムプレビュー）

    1. ensure_cache_fresh()     — 増分スキャン（必要時のみ）
    2. propose_structure()      — タイトル + H2 構成案（小型コール）
    3. check_overlap() × N      — 2 レベル被り検出 + 再構成
    4. build_article_prompt()   — 本文プロンプト構築
    5. invoke_claude_stream()   — 本文生成（大型コール・ストリーミング）
    6. check_ngram_overlap()    — n-gram 重複チェック（警告のみ）
    """
    def stage(msg: str, stage_id: str = "") -> None:
        if on_stage:
            try:
                on_stage(msg, stage_id)
            except TypeError:
                on_stage(msg)

    reset_embed_state()

    stage("過去記事を照合しています…", "cache_check")
    cache_had_data = get_store().meta().get("count", 0) > 0
    ensure_cache_fresh()

    # ── アイテム決定 ───────────────────────────────────────────────
    item: dict | None = None
    if fk_id:
        item = find_by_fk(fk_id)
        if item:
            brand_key = item["brand_key"]  # ブランドを在庫データから上書き
    else:
        # ブランドのみ指定 → 記事軸の在庫を自動選定
        item = select_feature_item(brand_key)
        if item is None and not allow_no_inventory:
            # 在庫があるアプリ（loaded）でブランド在庫ゼロのときだけ中断。
            # CSV 自体が未ロードの場合は一般記事として続行する。
            if inventory_summary().get("loaded"):
                raise InventoryMissingError(brand_key)

    stage("被らないテーマ・構成を考えています…", "prompt_build")
    direction = (direction or "").strip()[:500]
    structure  = propose_structure(brand_key, tone, item=item, direction=direction)
    effective_tone = structure.get("tone") or (tone if tone and tone != "auto" else "guide")
    overlap    = {"ok": True, "flagged": []}

    stage("過去記事との被りをチェックしています…")
    for attempt in range(MAX_REGEN_RETRIES):
        overlap = check_overlap(brand_key, structure.get("title", ""), structure.get("h2s", []))
        if overlap["ok"]:
            break
        if attempt < MAX_REGEN_RETRIES - 1:
            stage("構成を調整しています…")
            log.info("structure_revise brand=%s attempt=%s flagged=%s",
                     brand_key, attempt + 1, len(overlap.get("flagged", [])))
            structure = revise_structure(brand_key, effective_tone, structure, overlap["flagged"], direction=direction)

    title    = structure.get("title")    or f"{BRANDS[brand_key]['jp']} 特集記事"
    h2s      = structure.get("h2s",      [])
    theme    = structure.get("theme",    "")
    keywords = structure.get("keywords", "")

    prompt, image_placeholder = build_article_prompt(
        brand_key, effective_tone, title, theme, keywords, overlap.get("flagged", []),
        item=item, direction=direction,
    )
    stage("本文を執筆しています…", "bedrock_call")
    if on_chunk:
        article = invoke_claude_stream(prompt, on_chunk)
    else:
        article = invoke_claude(prompt)

    # 画像メタをリザルトに含める（WordPress 連携は別ステップ）
    # プレースホルダーは記事本文から除去し、メタ情報として返す
    image_meta: dict | None = None
    if image_placeholder and item:
        img = get_image_for_item(item)
        if img:
            image_meta = img
        # プレースホルダーを本文から除去（CDN URL 直貼りは避ける）
        article = article.replace(image_placeholder, "")

    stage("仕上げチェック中…")
    slug         = title_to_slug(title)
    ngram_issues = check_ngram_overlap(article, brand_key)

    # ── 劣化モード / 重複ステータスの判定 ─────────────────────────
    degraded_modes: list[str] = []
    if embedding_degraded():
        degraded_modes.append("embedding_unavailable")

    if embedding_degraded() or not cache_had_data:
        overlap_status = "unchecked"   # 過去記事チェックが信頼できない
    elif overlap["ok"]:
        overlap_status = "ok"
    else:
        overlap_status = "flagged"

    tone_titles = sample_past_titles(brand_key, limit=6)
    tone_reference_summary = (
        "過去記事の口調・見出し設計を参考: " + " / ".join(tone_titles)
        if tone_titles else "参考にできる過去記事が見つかりませんでした"
    )

    return {
        "title":        title,
        "tone":         effective_tone,
        "tone_label":   TONE_LABELS.get(effective_tone, "ガイド系"),
        "h2s":          h2s,
        "keywords":     keywords,
        "theme":        theme,
        "direction":    direction,
        "article":      article,
        "html":         markdown_to_wp_html(article),
        "slug":         slug,
        "brand_key":    brand_key,
        "brand_jp":     BRANDS.get(brand_key, {}).get("jp", brand_key),
        "overlap_ok":   overlap["ok"],
        "overlap_status": overlap_status,
        "degraded_modes": degraded_modes,
        "ngram_issues": ngram_issues,
        "item_summary": summarize_item(item) if item else "",
        "tone_reference_summary": tone_reference_summary,
        "fk_id":        fk_id,
        "item":         item,
        "image_meta":   image_meta,  # WordPress 連携用（s3_key, source_url, alt）
    }


# ─── ユーティリティ ───────────────────────────────────────────────────────────

def title_to_slug(title: str) -> str:
    JP_TO_EN = {
        "ロレックス": "rolex",    "オメガ": "omega",       "セイコー": "seiko",
        "シチズン": "citizen",    "チューダー": "tudor",   "オリエント": "orient",
        "ロンジン": "longines",   "カルティエ": "cartier", "ブライトリング": "breitling",
        "ジャガー": "jaeger",     "ルクルト": "lecoultre", "ユニバーサル": "universal",
        "ヴァシュロン": "vacheron", "コンスタンタン": "constantin",
        "ポルトフィーノ": "portofino", "スピードマスター": "speedmaster",
        "コンステレーション": "constellation", "シーマスター": "seamaster",
        "デイトナ": "daytona",    "サブマリーナ": "submariner",
        "エクスプローラ": "explorer", "デイトジャスト": "datejust",
        "グランドセイコー": "grand-seiko", "キングセイコー": "king-seiko",
        "ヴィンテージ": "vintage", "ヴィンテイジ": "vintage",
        "解説": "", "とは": "", "について": "", "年代": "s", "年": "", "代": "s",
    }
    result = title
    for jp, en in JP_TO_EN.items():
        result = result.replace(jp, f" {en} " if en else " ")
    result = result.lower()
    result = re.sub(r"[^\w\s\-]", " ", result)
    result = re.sub(r"[\s_]+", "-", result.strip())
    result = re.sub(r"-{2,}", "-", result).strip("-")
    return (result or "article")[:60]


def markdown_to_wp_html(md: str) -> str:
    """記事 Markdown を WordPress 投稿用の最小限の HTML へ変換する（依存ライブラリ無し）。

    見出し / 段落 / 箇条書き / 番号付きリスト / テーブル / 水平線 / 強調 / リンクに対応。
    投稿の本文用途であり、プレビューは引き続き marked.js を使う。
    """
    lines = md.replace("\r\n", "\n").split("\n")
    # 先頭の H1（タイトル）とフロントマター（--- ... ---）は本文から除外
    out: list[str] = []
    i = 0

    def inline(text: str) -> str:
        text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', text)
        return text

    # 先頭 H1 を捨てる
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and re.match(r"^#\s+", lines[i]):
        i += 1

    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s == "":
            i += 1
            continue
        if re.match(r"^-{3,}$", s):
            out.append("<hr />")
            i += 1
            continue
        m = re.match(r"^(#{2,4})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue
        # テーブル（| a | b | 行が連続し、2行目が区切り）
        if s.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|?$", lines[i + 1].strip()):
            header = [c.strip() for c in s.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue
        # 箇条書き
        if re.match(r"^[-*]\s+", s):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append("<li>" + inline(re.sub(r"^[-*]\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        # 番号付きリスト
        if re.match(r"^\d+\.\s+", s):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append("<li>" + inline(re.sub(r"^\d+\.\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        # 段落（空行まで結合）
        para = [s]
        i += 1
        while i < n and lines[i].strip() != "" and not re.match(r"^(#{2,4}\s|[-*]\s|\d+\.\s|\||-{3,}$)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


def _next_article_number(brand_dir: Path) -> str:
    """ブランドディレクトリ内の既存番号から次の3桁連番を返す。"""
    existing = []
    if brand_dir.exists():
        for f in brand_dir.iterdir():
            m = re.match(r"^(\d+)_article_", f.name)
            if m:
                existing.append(int(m.group(1)))
    return f"{(max(existing) + 1 if existing else 1):03d}"


def save_article(brand_key: str, slug: str, content: str) -> Path:
    brand_dir = ROOT / "articles" / brand_key
    brand_dir.mkdir(parents=True, exist_ok=True)
    number = _next_article_number(brand_dir)
    filename = f"{number}_article_{slug}.txt"
    path = brand_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ─── Flask ルーティング ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS, tones=TONES)


@app.route("/generate", methods=["POST"])
def generate():
    """記事生成を非同期ジョブとして開始し、job_id を即座に返す。

    App Runner のロードバランサーは ~120 秒でタイムアウトするため、
    生成処理（1〜3 分）を同期で返すと必ず 504 になる。
    クライアントは GET /generate-status/<job_id> を 3 秒ごとにポーリングして結果を取得する。
    """
    data        = request.get_json(silent=True) or {}
    brand_key   = data.get("brand", "ROLEX")
    tone        = data.get("tone",  "auto")
    fk_id       = data.get("fk_id", "")
    direction   = str(data.get("direction", "") or "").strip()[:500]
    allow_no_inv = bool(data.get("allow_no_inventory", False))
    mode        = "inventory" if fk_id else "brand"

    job_id = str(uuid.uuid4())
    with _JOB_LOCK:
        JOBS[job_id] = {
            "status":     "running",
            "created_at": time.time(),
            "result":     None,
            "error":      None,
            "stage":      "生成を開始しています…",
            "partial":    "",
        }
    log.info("job_created job_id=%s brand=%s mode=%s direction_set=%s",
             job_id, brand_key, mode, bool(direction))

    def _run(jid: str, bk: str, t: str, fk: str, dir_text: str) -> None:
        def on_stage(msg: str, stage_id: str = "") -> None:
            with _JOB_LOCK:
                if jid in JOBS:
                    JOBS[jid]["stage"] = msg
            if stage_id:
                log.info("job_stage job_id=%s stage=%s", jid, stage_id)

        def on_chunk(text: str) -> None:
            with _JOB_LOCK:
                if jid in JOBS:
                    JOBS[jid]["partial"] += text

        log.info("job_thread_started job_id=%s", jid)
        try:
            result = generate_article(
                bk, t, fk_id=fk, on_stage=on_stage, on_chunk=on_chunk,
                allow_no_inventory=allow_no_inv, direction=dir_text,
            )
            with _JOB_LOCK:
                JOBS[jid]["status"] = "done"
                JOBS[jid]["stage"]  = "完成しました"
                JOBS[jid]["result"] = {k: v for k, v in result.items() if k != "item"}
            log.info("job_done job_id=%s degraded=%s overlap=%s",
                     jid, result.get("degraded_modes"), result.get("overlap_status"))
        except InventoryMissingError:
            with _JOB_LOCK:
                JOBS[jid]["status"] = "inventory_missing"
                JOBS[jid]["error"]  = f"{BRANDS.get(bk, {}).get('jp', bk)} の在庫が見つかりませんでした"
            log.info("job_inventory_missing job_id=%s brand=%s", jid, bk)
        except Exception as e:
            with _JOB_LOCK:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"]  = str(e)
            log.warning("job_error job_id=%s err=%s", jid, e)

    threading.Thread(target=_run, args=(job_id, brand_key, tone, fk_id, direction), daemon=True).start()
    _cleanup_jobs()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/generate-status/<job_id>")
def generate_status(job_id: str):
    """ジョブの完了状態を返す。ポーリング用エンドポイント。

    status:
      running          — 生成中（再ポーリング）
      done             — 完了（result フィールドに記事データ）
      error            — 失敗（error フィールドにエラーメッセージ）
      inventory_missing — 在庫なし（error フィールドにメッセージ）
      not_found        — job_id が存在しない（再生成を促す）
    """
    with _JOB_LOCK:
        job = JOBS.get(job_id)

    if job is None:
        return jsonify({"status": "not_found"})

    if job["status"] == "done":
        result = job["result"] or {}
        return jsonify({"status": "done", "result": result})

    if job["status"] == "error":
        return jsonify({"status": "error", "error": job.get("error", "不明なエラー")})

    if job["status"] == "inventory_missing":
        return jsonify({"status": "inventory_missing", "error": job.get("error", "在庫が見つかりませんでした")})

    # まだ running — 進行状況と生成途中の本文を返す
    elapsed = int(time.time() - job.get("created_at", time.time()))
    return jsonify({
        "status":  "running",
        "elapsed": elapsed,
        "stage":   job.get("stage", ""),
        "partial": job.get("partial", ""),
    })


@app.route("/inventory-items")
def inventory_items():
    """在庫中のアイテム一覧を返す（UI 用）。"""
    brand_key = request.args.get("brand", "")
    try:
        items = get_in_stock(brand_key or None)
        summary = inventory_summary()
        return jsonify({
            "ok":      True,
            "items":   items,
            "summary": summary,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "items": [], "summary": {}})


@app.route("/upload-inventory", methods=["POST"])
def upload_inventory():
    """CSV ファイルをアップロードして在庫キャッシュを更新する。
    App Runner（本番）では S3 に保存し、次回起動時も維持される。
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "ファイルが選択されていません"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".csv"):
        return jsonify({"ok": False, "error": ".csv ファイルを選択してください"}), 400
    try:
        csv_bytes = f.read()
        items     = reload_from_bytes(csv_bytes)
        return jsonify({
            "ok":      True,
            "message": f"在庫データを更新しました（{len(items)} 件の在庫）",
            "count":   len(items),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/save", methods=["POST"])
def save():
    data      = request.get_json(silent=True) or {}
    brand_key = data.get("brand", "ROLEX")
    slug      = (data.get("slug") or "article").strip()
    content   = data.get("content", "")
    if not content.strip():
        return jsonify({"ok": False, "error": "本文が空です"}), 400
    slug_clean = re.sub(r"[^\w\-]", "-", slug).strip("-") or "article"
    try:
        path = save_article(brand_key, slug_clean, content)
        return jsonify({"ok": True, "saved_path": str(path.relative_to(ROOT))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/scan", methods=["POST"])
def scan():
    """手動スキャン（増分）。ロック付きで多重起動を防止する。"""
    if _SCAN_STATE["running"]:
        return jsonify({"ok": False, "error": "スキャンは既に実行中です", "running": True})
    started = _run_scan_locked(incremental=True)
    if not started:
        return jsonify({"ok": False, "error": "スキャンは既に実行中です", "running": True})
    m = get_store().meta()
    return jsonify({"ok": True, **m, "last_error": _SCAN_STATE["last_error"]})


@app.route("/scan-status")
def scan_status():
    m = get_store().meta()
    return jsonify({
        "exists":                  m.get("count", 0) > 0,
        "running":                 _SCAN_STATE["running"],
        "last_started_at":         _SCAN_STATE["last_started_at"],
        "last_finished_at":        _SCAN_STATE["last_finished_at"],
        "last_error":              _SCAN_STATE["last_error"],
        "article_count":           m.get("count", 0),
        "count":                   m.get("count", 0),
        "with_article_embedding":  m.get("with_article_embedding", 0),
        "with_heading_embeddings": m.get("with_heading_embeddings", 0),
        "cache_source":            m.get("cache_source", "empty"),
        "lookback_days":           LOOKBACK_DAYS,
        "degraded_modes":          _SCAN_STATE["degraded_modes"],
        "scanned_at":              m.get("scanned_at", ""),
    })


def _s3_client_simple():
    import boto3
    region = os.getenv("S3_REGION") or os.getenv("AWS_REGION", "us-east-1")
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


@app.route("/save-draft", methods=["POST"])
def save_draft():
    """記事生成完了時に自動呼び出し。TXT + HTML を articles/ に保存し S3 にもバックアップ。"""
    data      = request.get_json(silent=True) or {}
    brand_key = (data.get("brand") or "ROLEX").strip()
    slug      = re.sub(r"[^\w\-]", "-", (data.get("slug") or "article").strip()).strip("-") or "article"
    title     = (data.get("title") or "").strip()
    content   = (data.get("content") or "").strip()   # Markdown / プレーンテキスト
    html      = (data.get("html") or "").strip()       # WP HTML
    image_meta = data.get("image_meta")                # {s3_key, source_url, alt} or null

    if not content and not html:
        return jsonify({"ok": False, "error": "本文が空です"}), 400

    brand_dir = ROOT / "articles" / brand_key
    brand_dir.mkdir(parents=True, exist_ok=True)

    # 同一 slug が既に存在するか確認（重複保存防止）
    existing_numbers = []
    for f in brand_dir.iterdir():
        m = re.match(r"^(\d+)_article_", f.name)
        if m:
            existing_numbers.append(int(m.group(1)))
        # 同一slugが既存なら上書き
        if re.match(rf"^\d+_article_{re.escape(slug)}\.(txt|html)$", f.name):
            number_m = re.match(r"^(\d+)_", f.name)
            number = number_m.group(1) if number_m else f"{(max(existing_numbers, default=0) + 1):03d}"
            break
    else:
        number = f"{(max(existing_numbers, default=0) + 1):03d}"

    saved_paths = []
    if content:
        txt_path = brand_dir / f"{number}_article_{slug}.txt"
        txt_path.write_text(content, encoding="utf-8")
        saved_paths.append(str(txt_path.relative_to(ROOT)))
    if html:
        html_path = brand_dir / f"{number}_article_{slug}.html"
        html_path.write_text(html, encoding="utf-8")
        saved_paths.append(str(html_path.relative_to(ROOT)))

    # メタデータ JSON を保存（一覧表示用 title / image_url / excerpt）
    meta_path = brand_dir / f"{number}_article_{slug}.meta.json"
    excerpt_src = content or html or ""
    import re as _re_strip
    excerpt_plain = _re_strip.sub(r"<[^>]+>", "", excerpt_src).replace("\n", " ").strip()[:200]
    image_url = ""
    if image_meta:
        image_url = image_meta.get("source_url") or ""
        if not image_url and image_meta.get("s3_key"):
            image_url = f"/generator/image-proxy?s3_key={image_meta['s3_key']}"
    meta_obj = {
        "title": title or slug.replace("-", " ").title(),
        "brand": brand_key,
        "slug": slug,
        "number": number,
        "image_url": image_url,
        "excerpt": excerpt_plain,
        "char_count": len(content) if content else len(html),
        "has_html": bool(html),
        "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    meta_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # S3 バックアップ（非同期で行い失敗しても本処理に影響しない）
    bucket = os.getenv("S3_BUCKET", "")
    if bucket:
        def _s3_backup():
            try:
                s3 = _s3_client_simple()
                meta_extra = {"Metadata": {"title": title[:256], "brand": brand_key}}
                if content:
                    s3.put_object(
                        Bucket=bucket,
                        Key=f"drafts/{brand_key}/{number}_article_{slug}.txt",
                        Body=content.encode("utf-8"),
                        ContentType="text/plain; charset=utf-8",
                        **meta_extra,
                    )
                if html:
                    s3.put_object(
                        Bucket=bucket,
                        Key=f"drafts/{brand_key}/{number}_article_{slug}.html",
                        Body=html.encode("utf-8"),
                        ContentType="text/html; charset=utf-8",
                        **meta_extra,
                    )
                # メタデータ JSON も S3 へ保存（一覧復元用）
                s3.put_object(
                    Bucket=bucket,
                    Key=f"drafts/{brand_key}/{number}_article_{slug}.meta.json",
                    Body=json.dumps(meta_obj, ensure_ascii=False, indent=2).encode("utf-8"),
                    ContentType="application/json",
                )
            except Exception as e:
                print(f"[save-draft] S3 backup error: {e}")
        import threading as _threading
        _threading.Thread(target=_s3_backup, daemon=True).start()

    return jsonify({
        "ok": True,
        "number": number,
        "slug": slug,
        "saved_paths": saved_paths,
    })


def _restore_drafts_from_s3():
    """S3 の drafts/ プレフィックスからメタデータと本文をローカルに復元する。"""
    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        return
    try:
        s3 = _s3_client_simple()
        paginator = s3.get_paginator("list_objects_v2")
        articles_dir = ROOT / "articles"
        for page in paginator.paginate(Bucket=bucket, Prefix="drafts/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]  # e.g. drafts/BREITLING/001_article_Breitling_30S.meta.json
                parts = key.split("/", 2)  # ["drafts", "BRAND", "filename"]
                if len(parts) < 3:
                    continue
                brand_key, filename = parts[1], parts[2]
                brand_dir = articles_dir / brand_key
                local_path = brand_dir / filename
                if local_path.exists():
                    continue
                brand_dir.mkdir(parents=True, exist_ok=True)
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                local_path.write_bytes(body)
        print(f"[drafts] S3 restore complete")
    except Exception as e:
        print(f"[drafts] S3 restore error: {e}")


_s3_drafts_restored = False


@app.route("/drafts")
def drafts():
    """保存済み記事一覧を返す（articles/ ディレクトリ走査＋S3フォールバック）。"""
    global _s3_drafts_restored
    articles_dir = ROOT / "articles"

    # 初回のみ S3 から復元（コンテナ再デプロイ後）
    if not _s3_drafts_restored:
        _s3_drafts_restored = True
        _restore_drafts_from_s3()

    result = []
    if not articles_dir.exists():
        return jsonify([])

    for brand_dir in sorted(articles_dir.iterdir()):
        if not brand_dir.is_dir():
            continue
        brand_key = brand_dir.name
        entries: dict[str, dict] = {}
        for f in sorted(brand_dir.iterdir(), reverse=True):
            if f.name.endswith(".meta.json"):
                m = re.match(r"^(\d+)_article_(.+)\.meta\.json$", f.name)
                if not m:
                    continue
                number, slug = m.group(1), m.group(2)
                key = f"{brand_key}/{number}_{slug}"
                if key not in entries:
                    try:
                        meta = json.loads(f.read_text(encoding="utf-8"))
                        entries[key] = {
                            "brand": meta.get("brand", brand_key),
                            "number": meta.get("number", number),
                            "slug": meta.get("slug", slug),
                            "title": meta.get("title", slug.replace("-", " ").title()),
                            "saved_at": meta.get("saved_at", ""),
                            "has_txt": False,
                            "has_html": meta.get("has_html", False),
                            "char_count": meta.get("char_count", 0),
                            "image_url": meta.get("image_url") or None,
                            "excerpt": meta.get("excerpt", ""),
                        }
                    except Exception:
                        pass
                continue

            m = re.match(r"^(\d+)_article_(.+)\.(txt|html)$", f.name)
            if not m:
                continue
            number, slug, ext = m.group(1), m.group(2), m.group(3)
            key = f"{brand_key}/{number}_{slug}"
            if key not in entries:
                stat = f.stat()
                entries[key] = {
                    "brand": brand_key,
                    "number": number,
                    "slug": slug,
                    "title": slug.replace("-", " ").title(),
                    "saved_at": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "has_txt": False,
                    "has_html": False,
                    "char_count": 0,
                    "image_url": None,
                    "excerpt": "",
                }
            entries[key][f"has_{ext}"] = True
            if ext == "txt" and not entries[key]["char_count"]:
                try:
                    entries[key]["char_count"] = len(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
        result.extend(sorted(entries.values(), key=lambda x: x["saved_at"], reverse=True))

    return jsonify(result)


@app.route("/delete-draft", methods=["POST"])
def delete_draft():
    """保存済み記事を削除する。"""
    data = request.get_json(silent=True) or {}
    brand = (data.get("brand") or "").strip()
    number = (data.get("number") or "").strip()
    slug = (data.get("slug") or "").strip()
    if not brand or not number or not slug:
        return jsonify({"ok": False, "error": "パラメータ不足"}), 400

    brand_dir = ROOT / "articles" / brand
    deleted = []
    for ext in ("txt", "html", "meta.json"):
        p = brand_dir / f"{number}_article_{slug}.{ext}"
        if p.exists():
            p.unlink()
            deleted.append(str(p.relative_to(ROOT)))

    # S3 からも削除（バックグラウンド）
    bucket = os.getenv("S3_BUCKET", "")
    if bucket:
        def _s3_delete():
            try:
                s3 = _s3_client_simple()
                for ext in ("txt", "html", "meta.json"):
                    try:
                        s3.delete_object(Bucket=bucket, Key=f"drafts/{brand}/{number}_article_{slug}.{ext}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"[delete-draft] S3 delete error: {e}")
        import threading as _threading
        _threading.Thread(target=_s3_delete, daemon=True).start()

    return jsonify({"ok": True, "deleted": deleted})


_POSTS_LOG_S3_KEY = "posts_log/posts_log.json"


def _load_posts_log() -> list:
    bucket = os.getenv("S3_BUCKET", "")
    if bucket:
        try:
            s3 = _s3_client_simple()
            obj = s3.get_object(Bucket=bucket, Key=_POSTS_LOG_S3_KEY)
            return json.loads(obj["Body"].read().decode("utf-8"))
        except Exception:
            pass
    # ローカルフォールバック
    local = ROOT / "data" / "posts_log.json"
    if local.exists():
        try:
            return json.loads(local.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_posts_log(log: list) -> None:
    bucket = os.getenv("S3_BUCKET", "")
    payload = json.dumps(log, ensure_ascii=False, indent=2)
    if bucket:
        try:
            s3 = _s3_client_simple()
            s3.put_object(
                Bucket=bucket,
                Key=_POSTS_LOG_S3_KEY,
                Body=payload.encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
        except Exception as e:
            print(f"[log-post] S3 save error: {e}")
    # ローカルにも保存
    local = ROOT / "data" / "posts_log.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(payload, encoding="utf-8")


@app.route("/log-post", methods=["POST"])
def log_post():
    """WP投稿完了後に投稿メタを記録する。"""
    data = request.get_json(silent=True) or {}
    required = ["brand", "title", "wp_id", "wp_link"]
    for k in required:
        if not data.get(k):
            return jsonify({"ok": False, "error": f"{k} is required"}), 400

    entry = {
        "brand":      data.get("brand", ""),
        "slug":       data.get("slug", ""),
        "title":      data.get("title", ""),
        "wp_id":      data.get("wp_id"),
        "wp_link":    data.get("wp_link", ""),
        "wp_status":  data.get("wp_status", "publish"),
        "image_url":  data.get("image_url", ""),
        "char_count": int(data.get("char_count", 0)),
        "logged_at":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date":       data.get("date", datetime.date.today().strftime("%Y.%-m.%-d") if hasattr(datetime.date.today(), "strftime") else ""),
    }
    log = _load_posts_log()
    # 同一 wp_id があれば上書き
    log = [e for e in log if str(e.get("wp_id")) != str(entry["wp_id"])]
    log.insert(0, entry)
    _save_posts_log(log)
    return jsonify({"ok": True})


@app.route("/posts-log")
def posts_log():
    """投稿済み記事ログを返す。"""
    return jsonify(_load_posts_log())


@app.route("/image-proxy")
def image_proxy():
    """S3から画像バイナリを取得して返す。
    Query: ?s3_key=images/BRAND/FK/main.jpg
    フロントから wp_uploader_local の /upload-media に渡すプロキシURL として使う。
    """
    s3_key = request.args.get("s3_key", "").strip()
    if not s3_key:
        return jsonify({"error": "s3_key is required"}), 400

    bucket = os.getenv("S3_BUCKET", "")
    if not bucket:
        return jsonify({"error": "S3_BUCKET not configured"}), 500

    try:
        import boto3
        region = os.getenv("S3_REGION") or os.getenv("AWS_REGION", "us-east-1")
        s3 = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        obj = s3.get_object(Bucket=bucket, Key=s3_key)
        data = obj["Body"].read()
        content_type = obj.get("ContentType", "image/jpeg")
        return Response(data, mimetype=content_type)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ping")
def ping():
    aws_key = os.getenv("AWS_ACCESS_KEY_ID", "")
    inv     = inventory_summary()
    return jsonify({
        "ok":              True,
        "aws_configured":  bool(aws_key and os.getenv("AWS_SECRET_ACCESS_KEY")),
        "bedrock_model":   os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        "embed_model":     EMBED_MODEL_ID,
        "region":          os.getenv("AWS_REGION", "us-east-1"),
        "lookback_days":   LOOKBACK_DAYS,
        "cache_exists":    get_store().meta().get("count", 0) > 0,
        "inventory_count": inv["total"],
        "inventory_loaded": inv["loaded"],
    })


if __name__ == "__main__":
    port = int(os.getenv("GENERATOR_PORT", 8001))
    print(f"記事生成アプリ起動: http://localhost:{port}")
    app.run(debug=True, port=port, host="127.0.0.1", use_reloader=False)
