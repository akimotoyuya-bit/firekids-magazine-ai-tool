"""
ArticleVectorStore – 過去記事Embeddingキャッシュのリポジトリ抽象化。

現在のバックエンド : JSON ファイル（+ 任意の S3 同期）
将来のバックエンド : Aurora PostgreSQL + pgvector  /  OpenSearch Serverless

移行方法: ArticleVectorStore ABC を実装した新クラスを作り、
          get_store() が返すインスタンスを差し替えるだけで完了。

────────────────────────────────────────────────
レコードスキーマ（1記事1レコード）:
  post_id            int    WP 投稿ID
  title              str    タイトル（rendered）
  url                str    パーマリンク
  brand_categories   list   WP カテゴリ ID リスト
  modified           str    WP modified 日時 ISO8601
  content_hash       str    content.rendered の SHA-256 先頭 16 桁
                            （変更なければ再 Embedding をスキップする）
  article_embedding  list   title + excerpt + H2 一覧 + 本文冒頭 1500 字のベクトル
  heading_embeddings list   [{heading, text, vec}, ...]  H2 ごとのベクトル
  h2_texts           list   H2 テキスト一覧（プロンプト注入・被り説明用）
  body_snippet       str    本文プレーンテキスト冒頭 3000 字（n-gram 比較用）
  embedding_model    str    使用 Embedding モデル ID
  updated_at         str    このレコードの最終更新日時 ISO8601
────────────────────────────────────────────────
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

log = logging.getLogger("fk_generator")

_LOCK_STALE_SECONDS = 60 * 30


@contextmanager
def cache_writer_lock(timeout_seconds: int = 600):
    """同一マシン上の Flask background scan とメンテナンス script の同時書込を防ぐ。

    App Runner は現状 1 instance / 1 worker 前提。複数 instance にする場合は
    DynamoDB 等の分散ロックへ置き換える。
    """
    lock_path = Path(tempfile.gettempdir()) / "firekids_article_vector_cache.lock"
    deadline = time.time() + timeout_seconds
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.time() >= deadline:
                raise TimeoutError("vector cache writer lock timeout")
            time.sleep(0.5)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _cache_stats(raw: dict) -> dict:
    index = raw.get("index") or {}
    records = index.values() if isinstance(index, dict) else []
    return {
        "count": len(index) if isinstance(index, dict) else 0,
        "with_article_embedding": sum(1 for r in records if r.get("article_embedding")),
        "with_heading_embeddings": sum(1 for r in records if r.get("heading_embeddings")),
    }


def _cache_stats_from_payload(payload: str | bytes) -> dict:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return _cache_stats(json.loads(payload))


# ─── S3 ヘルパー ─────────────────────────────────────────────────────────────
# Bedrock は AWS_REGION（us-east-1 等）を使う。
# S3 バケットは ap-northeast-1 に存在するため S3_REGION で別管理する。

def _s3_client():
    """S3 専用クライアント。S3_REGION を使い、AWS_REGION（Bedrock 用）とは分離する。"""
    import boto3
    return boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION", os.getenv("AWS_REGION", "ap-northeast-1")),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def _s3_download_cache(local_path: Path, bucket: str, key: str) -> bool:
    """S3 からキャッシュを local_path にダウンロードする。

    - local_path が既に存在し内容が同じなら上書きしない（False を返す）。
    - S3 未存在・例外時は False を返す。成功時のみ True。
    """
    if not bucket:
        return False
    try:
        s3   = _s3_client()
        obj  = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        if local_path.exists() and local_path.read_bytes() == body:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(body)
        log.info("vector_cache_downloaded bucket=%s key=%s bytes=%s", bucket, key, len(body))
        return True
    except Exception as e:
        code = getattr(getattr(e, "response", None), "get", lambda *_: "")("Error", {}).get("Code", "")
        if code not in ("NoSuchKey", "404"):
            log.warning("vector_cache_download_failed bucket=%s key=%s err=%s", bucket, key, e)
        return False


# ─── Abstract Repository ─────────────────────────────────────────────────────

class ArticleVectorStore(ABC):
    """過去記事 Embedding リポジトリの抽象基底クラス。"""

    @abstractmethod
    def get(self, post_id: int) -> Optional[dict]:
        """post_id でレコードを取得。存在しなければ None。"""

    @abstractmethod
    def upsert(self, record: dict) -> None:
        """レコードを追加または更新（post_id をキーとする）。"""

    @abstractmethod
    def list_all(self) -> list[dict]:
        """全レコードのリストを返す。"""

    @abstractmethod
    def list_by_category(self, category_id: int) -> list[dict]:
        """指定 WP カテゴリ ID を含むレコードのリストを返す。"""

    @abstractmethod
    def flush(self) -> None:
        """変更をストレージに永続化する（JSON 書き込み・S3 アップロード等）。"""

    @abstractmethod
    def meta(self) -> dict:
        """件数・最終スキャン日時・Embedding 済み数などのメタ情報を返す。"""

    # ── 共通ヘルパー（サブクラスで再利用可） ─────────────────────────────

    @staticmethod
    def content_hash(text: str) -> str:
        """コンテンツの SHA-256 先頭 16 桁（変更検出用）。"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def needs_reembed(record: dict, new_hash: str, embed_model: str) -> bool:
        """content_hash・embedding_model が変わった、または heading_embeddings が
        ない（旧フォーマット）場合に True を返す。"""
        return (
            record.get("content_hash") != new_hash
            or record.get("embedding_model") != embed_model
            or not record.get("heading_embeddings")
        )


# ─── LocalJsonStore ───────────────────────────────────────────────────────────

class LocalJsonStore(ArticleVectorStore):
    """JSON ファイルバックエンド（+ 任意の S3 バックアップ）。

    内部データ構造:
      {
        "index":      {post_id_int: record, ...},
        "scanned_at": "ISO8601",
        "meta":       {"count": N, ...}
      }

    旧フォーマット（{"articles": [...]}）を自動移行する。
    """

    def __init__(
        self,
        path: Path,
        s3_bucket: str = "",
        s3_key: str = "article_vector_cache.json",
        legacy_path: Optional[Path] = None,
    ):
        self._path       = path
        self._s3_bucket  = s3_bucket
        self._s3_key     = s3_key
        self._legacy_path = legacy_path
        # cache_source: vector_cache / legacy_migrated / empty
        self._cache_source = "empty"

        # ── 起動時 S3 ダウンロード ───────────────────────────────────
        # App Runner / ローカル問わず、プロセス起動直後に S3 から最新キャッシュを
        # ローカルファイルへ同期する。これにより再起動後もキャッシュが引き継がれる。
        if s3_bucket:
            _s3_download_cache(path, s3_bucket, s3_key)

        self._data = self._load()

    # ── persistence ────────────────────────────────────────────────────────

    @staticmethod
    def _migrate_articles(raw: dict) -> dict:
        """旧フォーマット（"articles": [...]）を新フォーマット（index）へ移行。"""
        index: dict[int, dict] = {}
        for a in raw.get("articles", []):
            pid = a.get("id") or a.get("post_id")
            if pid is None:
                continue
            pid = int(pid)
            index[pid] = {
                "post_id":            pid,
                "title":              a.get("title", ""),
                "url":                a.get("url", ""),
                "brand_categories":   a.get("categories", a.get("brand_categories", [])),
                "modified":           a.get("date", a.get("modified", "")),
                # content_hash・embedding_model を空にして次回スキャン時に再 Embedding させる
                "content_hash":       "",
                "article_embedding":  a.get("embedding"),
                "heading_embeddings": [],
                "h2_texts":           [],
                "body_snippet":       "",
                "embedding_model":    "",
                "updated_at":         "",
            }
        return {"index": index, "scanned_at": raw.get("scanned_at", ""), "meta": {}}

    def _load(self) -> dict:
        # 1) 正規キャッシュ（article_vector_cache.json）が存在すればそれを使う
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                raw = None
            if raw is not None:
                if "articles" in raw and "index" not in raw:
                    data = self._migrate_articles(raw)
                    self._cache_source = "vector_cache" if data["index"] else "empty"
                    return data
                if "index" in raw:
                    raw["index"] = {int(k): v for k, v in raw["index"].items()}
                self._cache_source = "vector_cache" if raw.get("index") else "empty"
                return raw

        # 2) 正規キャッシュ不在 → 旧 past_articles_cache.json があれば互換ロード
        if self._legacy_path and self._legacy_path.exists():
            try:
                raw = json.loads(self._legacy_path.read_text(encoding="utf-8"))
            except Exception:
                raw = None
            if raw is not None:
                if "articles" in raw and "index" not in raw:
                    data = self._migrate_articles(raw)
                elif "index" in raw:
                    raw["index"] = {int(k): v for k, v in raw["index"].items()}
                    data = raw
                else:
                    data = {"index": {}, "scanned_at": "", "meta": {}}
                if data.get("index"):
                    self._cache_source = "legacy_migrated"
                return data

        # 3) どちらも無い
        self._cache_source = "empty"
        return {"index": {}, "scanned_at": "", "meta": {}}

    def flush(self) -> None:
        import datetime
        with cache_writer_lock():
            self._data["scanned_at"] = datetime.datetime.now().isoformat()
            self._data["meta"]["count"] = len(self._data["index"])
            # JSON は文字列キーしか許可しないので str(int) に変換
            serializable = {
                **self._data,
                "index": {str(k): v for k, v in self._data["index"].items()},
            }
            payload = json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))
            self._path.write_text(payload, encoding="utf-8")
            if self._s3_bucket:
                self._s3_sync(payload)

    def _flush_local_only(self) -> None:
        """S3 アップロードなしでローカルファイルのみに flush する（進捗保護用）。"""
        import datetime
        with cache_writer_lock():
            self._data["scanned_at"] = datetime.datetime.now().isoformat()
            self._data["meta"]["count"] = len(self._data["index"])
            serializable = {
                **self._data,
                "index": {str(k): v for k, v in self._data["index"].items()},
            }
            payload = json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))
            self._path.write_text(payload, encoding="utf-8")

    def _s3_sync(self, payload: str) -> None:
        try:
            s3 = _s3_client()
            local_stats = _cache_stats_from_payload(payload)
            try:
                existing = s3.get_object(Bucket=self._s3_bucket, Key=self._s3_key)
                remote_payload = existing["Body"].read()
                remote_stats = _cache_stats_from_payload(remote_payload)
            except Exception:
                remote_stats = {"count": 0, "with_article_embedding": 0, "with_heading_embeddings": 0}

            local_art = local_stats["with_article_embedding"]
            remote_art = remote_stats["with_article_embedding"]
            local_hdg = local_stats["with_heading_embeddings"]
            remote_hdg = remote_stats["with_heading_embeddings"]
            if local_art < remote_art or (local_art == remote_art and local_hdg < remote_hdg):
                log.warning(
                    "vector_cache_upload_skipped_downgrade bucket=%s key=%s local_art=%s remote_art=%s local_hdg=%s remote_hdg=%s",
                    self._s3_bucket, self._s3_key, local_art, remote_art, local_hdg, remote_hdg,
                )
                return

            s3.put_object(
                Bucket=self._s3_bucket,
                Key=self._s3_key,
                Body=payload.encode("utf-8"),
                ContentType="application/json",
                Metadata={
                    "count": str(local_stats["count"]),
                    "with_article_embedding": str(local_art),
                    "with_heading_embeddings": str(local_hdg),
                },
            )
            log.info("vector_cache_uploaded bucket=%s key=%s bytes=%s",
                     self._s3_bucket, self._s3_key, len(payload))
        except Exception as e:
            log.warning("vector_cache_upload_failed bucket=%s key=%s err=%s",
                        self._s3_bucket, self._s3_key, e)

    # ── CRUD ───────────────────────────────────────────────────────────────

    def get(self, post_id: int) -> Optional[dict]:
        return self._data["index"].get(int(post_id))

    def upsert(self, record: dict) -> None:
        self._data["index"][int(record["post_id"])] = record

    def list_all(self) -> list[dict]:
        return list(self._data["index"].values())

    def list_by_category(self, category_id: int) -> list[dict]:
        return [
            r for r in self._data["index"].values()
            if category_id in (r.get("brand_categories") or [])
        ]

    def meta(self) -> dict:
        records = self.list_all()
        with_art = sum(1 for r in records if r.get("article_embedding"))
        with_hdg = sum(1 for r in records if r.get("heading_embeddings"))
        return {
            "count":                   len(records),
            "with_article_embedding":  with_art,
            "with_heading_embeddings": with_hdg,
            "scanned_at":              self._data.get("scanned_at", ""),
            "cache_source":            self._cache_source,
        }


# ─── Factory ─────────────────────────────────────────────────────────────────

_store_instance: Optional[LocalJsonStore] = None


def get_store(cache_path: Optional[Path] = None) -> LocalJsonStore:
    """プロセス内シングルトンとしてストアを返す。
    cache_path を省略すると vector_store.py と同ディレクトリの
    article_vector_cache.json を使用する。
    """
    global _store_instance
    if _store_instance is None:
        if cache_path is None:
            cache_path = Path(__file__).parent / "article_vector_cache.json"
        legacy_path = Path(__file__).parent / "past_articles_cache.json"
        _store_instance = LocalJsonStore(
            path=cache_path,
            s3_bucket=os.getenv("S3_BUCKET", ""),
            # VECTOR_CACHE_S3_KEY を env から読む。未設定なら s3://…/cache/article_vector_cache.json
            s3_key=os.getenv("VECTOR_CACHE_S3_KEY", "cache/article_vector_cache.json"),
            legacy_path=legacy_path,
        )
    return _store_instance
