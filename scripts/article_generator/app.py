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
    find_by_fk, format_for_prompt, get_in_stock,
    inventory_summary, reload_from_bytes,
)

# ─── 初期化 ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / "scripts" / "wp_uploader_local" / ".env", override=True)
load_dotenv(ROOT / "scripts" / "article_generator" / ".env", override=True)

app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY", "firekids-default-secret-change-me")

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

# ─── 定数 ────────────────────────────────────────────────────────────────────

EMBED_MODEL_ID        = os.getenv("EMBED_MODEL_ID",        "amazon.titan-embed-text-v2:0")
CACHE_REFRESH_HOURS   = int(os.getenv("CACHE_REFRESH_HOURS",   "12"))
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


def bedrock_embed(text: str) -> list | None:
    """Titan Embeddings でテキストをベクトル化。失敗時は None（劣化動作）。"""
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
        return json.loads(resp["body"].read()).get("embedding")
    except Exception:
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

    # 増分スキャン: 最終スキャン以降に modified された記事のみ取得
    after_param: str | None = None
    if incremental:
        m = store.meta()
        sa = m.get("scanned_at", "")
        if sa:
            after_param = sa[:19]  # マイクロ秒を除去

    total_new = total_updated = 0
    page = 1

    while True:
        params: dict = {
            "per_page":  20,   # content.rendered を含むため小さめに
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

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    store.flush()
    m = store.meta()
    m["new_added"] = total_new
    m["updated"]   = total_updated
    return m


def ensure_cache_fresh() -> None:
    """キャッシュが空または CACHE_REFRESH_HOURS より古ければ増分スキャンを実行する。
    失敗時は生成を続行（劣化動作）。
    """
    m          = get_store().meta()
    scanned_at = m.get("scanned_at", "")
    needs      = not scanned_at or not m.get("count")
    if not needs and scanned_at:
        try:
            last  = datetime.datetime.fromisoformat(scanned_at)
            age_h = (datetime.datetime.now() - last).total_seconds() / 3600
            needs = age_h >= CACHE_REFRESH_HOURS
        except Exception:
            needs = True
    if needs:
        try:
            scan_wordpress_posts(incremental=True)
        except Exception:
            pass


# ─── 類似度チェック ───────────────────────────────────────────────────────────

def check_overlap(brand_key: str, title: str, h2s: list[str]) -> dict:
    """2 レベルの被り検出。

    Level 1: 候補全体ベクトル vs article_embedding >= ARTICLE_SIM_THRESHOLD
    Level 2: 候補 H2 のうち HEADING_HIT_MIN 本以上が同一記事の heading_embeddings
             と >= HEADING_SIM_THRESHOLD で一致

    戻り値: {"ok": bool, "flagged": [{"title", "url", "article_similarity",
                                       "heading_hit_count", "hit_pairs", "h2_texts"}, ...]}
    """
    store     = get_store()
    brand_cat = BRANDS.get(brand_key, {}).get("category_id")
    past_arts = store.list_by_category(brand_cat) if brand_cat else store.list_all()

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

    store     = get_store()
    brand_cat = BRANDS.get(brand_key, {}).get("category_id")
    past_arts = store.list_by_category(brand_cat) if brand_cat else store.list_all()

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
    store     = get_store()
    brand_cat = BRANDS.get(brand_key, {}).get("category_id")
    records   = store.list_by_category(brand_cat) if brand_cat else store.list_all()
    records   = sorted(records, key=lambda r: r.get("modified", ""), reverse=True)
    titles: list[str] = []
    for r in records:
        t = (r.get("title") or "").strip()
        if t:
            titles.append(t)
        if len(titles) >= limit:
            break
    return titles


def propose_structure(brand_key: str, tone: str = "auto", item: dict | None = None) -> dict:
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

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事を1本企画してください。
{tone_directive}
{item_block}
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


def revise_structure(brand_key: str, tone: str, previous: dict, flagged: list) -> dict:
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

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事（{tone_jp}）の企画を修正してください。

【前回の企画案（構成被りあり）】
タイトル: {previous.get('title', '')}
H2 構成: {json.dumps(previous.get('h2s', []), ensure_ascii=False)}

【被りが検出された既存記事との比較】
{conflict_text}

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

    avoid_block = ""
    if avoid_articles:
        lines = []
        for f in avoid_articles[:3]:
            lines.append(f"・「{f['title']}」（{f.get('url', '')}）")
            for p in f.get("hit_pairs", [])[:3]:
                lines.append(f"  ↳ 章「{p['past']}」と類似 → 同じ切り口・具体例・導入を避ける")
        avoid_block = "━━━━━ 内容が被ってはいけない既存記事 ━━━━━\n" + "\n".join(lines) + "\n"

    return f"""あなたは FIRE KIDS Magazine の記事ライターです。
以下の条件に従い、ヴィンテージ時計の SEO 記事（Markdown 形式）を1本生成してください。

━━━━━ 記事情報 ━━━━━
ブランド: {brand_jp}（フォルダ: {brand_key}）
タイトル: {title}｜FIRE KIDS Magazine
テーマ: {theme}
トーン: {tone_label}
キーワード: {keywords}
生成日: {datetime.date.today().strftime("%Y.%m.%d")}

{inventory_block}{avoid_block}
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


# ─── 生成オーケストレーション ─────────────────────────────────────────────────

def generate_article(brand_key: str, tone: str = "auto", fk_id: str = "") -> dict:
    """3 ステージ生成フロー + 後処理 n-gram チェック。

    fk_id が指定された場合は在庫連携モード:
      - 在庫 CSV から商品情報を取得してブランドキーを上書き
      - propose_structure / build_article_prompt にアイテム情報を注入

    1. ensure_cache_fresh()     — 増分スキャン（必要時のみ）
    2. propose_structure()      — タイトル + H2 構成案（小型コール）
    3. check_overlap() × N      — 2 レベル被り検出 + 再構成
    4. build_article_prompt()   — 本文プロンプト構築
    5. invoke_claude()          — 本文生成（大型コール）
    6. check_ngram_overlap()    — n-gram 重複チェック（警告のみ）
    """
    ensure_cache_fresh()

    # 在庫連携モード: FK番号でアイテムを取得
    item: dict | None = None
    if fk_id:
        item = find_by_fk(fk_id)
        if item:
            brand_key = item["brand_key"]  # ブランドを在庫データから上書き

    structure  = propose_structure(brand_key, tone, item=item)
    # auto モードでは Claude が選んだ記事タイプを以降の本文生成にも引き継ぐ
    effective_tone = structure.get("tone") or (tone if tone and tone != "auto" else "guide")
    overlap    = {"ok": True, "flagged": []}

    for attempt in range(MAX_REGEN_RETRIES):
        overlap = check_overlap(brand_key, structure.get("title", ""), structure.get("h2s", []))
        if overlap["ok"]:
            break
        if attempt < MAX_REGEN_RETRIES - 1:
            structure = revise_structure(brand_key, effective_tone, structure, overlap["flagged"])

    title    = structure.get("title")    or f"{BRANDS[brand_key]['jp']} 特集記事"
    h2s      = structure.get("h2s",      [])
    theme    = structure.get("theme",    "")
    keywords = structure.get("keywords", "")

    prompt  = build_article_prompt(brand_key, effective_tone, title, theme, keywords, overlap.get("flagged", []), item=item)
    article = invoke_claude(prompt)

    slug         = title_to_slug(title)
    ngram_issues = check_ngram_overlap(article, brand_key)

    return {
        "title":        title,
        "tone":         effective_tone,
        "tone_label":   TONE_LABELS.get(effective_tone, "ガイド系"),
        "h2s":          h2s,
        "keywords":     keywords,
        "theme":        theme,
        "article":      article,
        "slug":         slug,
        "overlap_ok":   overlap["ok"],
        "ngram_issues": ngram_issues,
        "fk_id":        fk_id,
        "item":         item,
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


def save_article(brand_key: str, slug: str, content: str) -> Path:
    brand_dir = ROOT / "articles" / brand_key
    brand_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.date.today().strftime('%Y-%m-%d')}_{slug}.txt"
    path     = brand_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ─── Flask ルーティング ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS, tones=TONES)


@app.route("/review")
def review():
    return render_template(
        "review.html",
        article=session.get("draft_article", ""),
        brand=session.get("draft_brand",   "ROLEX"),
        slug=session.get("draft_slug",     "article"),
        title=session.get("draft_title",   ""),
        brands=BRANDS,
    )


@app.route("/generate", methods=["POST"])
def generate():
    """記事生成を非同期ジョブとして開始し、job_id を即座に返す。

    App Runner のロードバランサーは ~120 秒でタイムアウトするため、
    生成処理（1〜3 分）を同期で返すと必ず 504 になる。
    クライアントは GET /generate-status/<job_id> を 3 秒ごとにポーリングして結果を取得する。
    """
    data      = request.get_json(silent=True) or {}
    brand_key = data.get("brand", "ROLEX")
    tone      = data.get("tone",  "auto")
    fk_id     = data.get("fk_id", "")

    job_id = str(uuid.uuid4())
    with _JOB_LOCK:
        JOBS[job_id] = {
            "status":     "running",
            "created_at": time.time(),
            "result":     None,
            "error":      None,
        }

    def _run(jid: str, bk: str, t: str, fk: str) -> None:
        try:
            result = generate_article(bk, t, fk_id=fk)
            with _JOB_LOCK:
                JOBS[jid]["status"] = "done"
                JOBS[jid]["result"] = {k: v for k, v in result.items() if k != "item"}
                # セッションへの書き込みはスレッドから行えないため
                # クライアントが /generate-status で受け取った後に /set-draft で保存する
        except Exception as e:
            with _JOB_LOCK:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"]  = str(e)

    threading.Thread(target=_run, args=(job_id, brand_key, tone, fk_id), daemon=True).start()
    _cleanup_jobs()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/generate-status/<job_id>")
def generate_status(job_id: str):
    """ジョブの完了状態を返す。ポーリング用エンドポイント。

    status:
      running  — 生成中（3 秒後に再ポーリング）
      done     — 完了（result フィールドに記事データ）
      error    — 失敗（error フィールドにエラーメッセージ）
      not_found — job_id が存在しない（再生成を促す）
    """
    with _JOB_LOCK:
        job = JOBS.get(job_id)

    if job is None:
        return jsonify({"status": "not_found"})

    if job["status"] == "done":
        result = job["result"] or {}
        # セッション保存（ポーリング成功時に行う）
        session["draft_article"] = result.get("article", "")
        session["draft_brand"]   = result.get("brand_key", "ROLEX")
        session["draft_slug"]    = result.get("slug", "article")
        session["draft_title"]   = result.get("title", "")
        return jsonify({"status": "done", "result": result})

    if job["status"] == "error":
        return jsonify({"status": "error", "error": job.get("error", "不明なエラー")})

    # まだ running
    elapsed = int(time.time() - job.get("created_at", time.time()))
    return jsonify({"status": "running", "elapsed": elapsed})


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
    """手動スキャン（増分）。通常は生成時に自動実行されるため任意。"""
    try:
        m = scan_wordpress_posts(incremental=True)
        return jsonify({"ok": True, **m})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/scan-status")
def scan_status():
    m = get_store().meta()
    return jsonify({
        "exists":                  m.get("count", 0) > 0,
        "count":                   m.get("count", 0),
        "with_article_embedding":  m.get("with_article_embedding", 0),
        "with_heading_embeddings": m.get("with_heading_embeddings", 0),
        "scanned_at":              m.get("scanned_at", ""),
    })


@app.route("/ping")
def ping():
    aws_key = os.getenv("AWS_ACCESS_KEY_ID", "")
    inv     = inventory_summary()
    return jsonify({
        "ok":              True,
        "aws_key_set":     bool(aws_key),
        "aws_key_prefix":  aws_key[:8] + "..." if aws_key else "(未設定)",
        "bedrock_model":   os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        "embed_model":     EMBED_MODEL_ID,
        "region":          os.getenv("AWS_REGION", "us-east-1"),
        "cache_exists":    get_store().meta().get("count", 0) > 0,
        "inventory_count": inv["total"],
        "inventory_loaded": inv["loaded"],
    })


if __name__ == "__main__":
    port = int(os.getenv("GENERATOR_PORT", 8001))
    print(f"記事生成アプリ起動: http://localhost:{port}")
    app.run(debug=True, port=port, host="127.0.0.1")
