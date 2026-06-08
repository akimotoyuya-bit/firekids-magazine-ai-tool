"""
FIRE KIDS Magazine 画像 S3 保存・インデックス管理

クロールで取得した FK→画像レコードを S3 に保存し、
fk_image_index.json（FK番号 → 画像メタ）を管理する。

S3 キー設計:
  images/{brand_key}/{fk_id}/main.jpg   ← 各商品のメイン画像
  index/fk_image_index.json             ← FK→画像メタの索引

環境変数:
  S3_BUCKET           既存バケット（inventory.py と同一）
  S3_REGION           S3 リージョン
  IMAGE_INDEX_S3_KEY  索引キー（デフォルト: index/fk_image_index.json）
  IMAGE_PREFIX        画像プレフィックス（デフォルト: images）
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

IMAGE_INDEX_S3_KEY = os.getenv("IMAGE_INDEX_S3_KEY", "index/fk_image_index.json")
IMAGE_PREFIX       = os.getenv("IMAGE_PREFIX", "images")
LOCAL_INDEX_PATH   = Path(__file__).parent.parent.parent / "data" / "fk_image_index.json"


# ─── S3 クライアント（inventory.py と同一ヘルパーを再利用） ─────────────
def _s3():
    """inventory.py の _s3_client を再利用。認証・リージョンを統一する。"""
    try:
        from inventory import _s3_client  # type: ignore
        return _s3_client()
    except ImportError:
        from scripts.article_generator.inventory import _s3_client
        return _s3_client()


def _bucket() -> str:
    return os.getenv("S3_BUCKET", "")


# ─── インデックス読み込み ────────────────────────────────────────────────
def load_index() -> dict:
    """fk_image_index.json を S3 → ローカルの順で読み込む。無ければ空 dict。"""
    bucket = _bucket()
    if bucket:
        try:
            resp = _s3().get_object(Bucket=bucket, Key=IMAGE_INDEX_S3_KEY)
            return json.loads(resp["Body"].read().decode("utf-8"))
        except Exception as e:
            log.warning("index_s3_load_failed key=%s err=%s", IMAGE_INDEX_S3_KEY, e)

    if LOCAL_INDEX_PATH.exists():
        try:
            return json.loads(LOCAL_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("index_local_load_failed path=%s err=%s", LOCAL_INDEX_PATH, e)

    return {}


def _save_index(index: dict) -> None:
    """インデックスを S3 とローカルに書き込む。"""
    payload = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")

    bucket = _bucket()
    if bucket:
        try:
            _s3().put_object(
                Bucket=bucket,
                Key=IMAGE_INDEX_S3_KEY,
                Body=payload,
                ContentType="application/json",
            )
            log.info("index_s3_saved key=%s count=%d", IMAGE_INDEX_S3_KEY, len(index))
        except Exception as e:
            log.warning("index_s3_save_failed err=%s", e)

    LOCAL_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_INDEX_PATH.write_bytes(payload)
    log.info("index_local_saved path=%s count=%d", LOCAL_INDEX_PATH, len(index))


# ─── 画像の S3 保存 ──────────────────────────────────────────────────────
def _s3_key_for(brand_key: str, fk_id: str) -> str:
    return f"{IMAGE_PREFIX}/{brand_key}/{fk_id}/main.jpg"


def _image_exists(bucket: str, s3_key: str, source_url: str, index: dict, fk_id: str) -> bool:
    """同一 S3 キーが存在かつ source_url が変わっていなければ True（スキップ判定）。"""
    existing = index.get(fk_id, {})
    if existing.get("source_url") == source_url:
        try:
            _s3().head_object(Bucket=bucket, Key=s3_key)
            return True
        except Exception:
            pass
    return False


def _download_image(url: str) -> bytes:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def _upload_image(bucket: str, s3_key: str, data: bytes) -> None:
    _s3().put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=data,
        ContentType="image/jpeg",
    )


# ─── 在庫 CSV の FK セットを取得 ─────────────────────────────────────────
def _inventory_fk_set() -> set[str]:
    try:
        try:
            from inventory import load_inventory  # type: ignore
        except ImportError:
            from scripts.article_generator.inventory import load_inventory
        return {item["fk_id"] for item in load_inventory()}
    except Exception as e:
        log.warning("inventory_load_failed err=%s", e)
        return set()


# ─── メイン同期処理 ──────────────────────────────────────────────────────
def sync_to_s3(records: list[dict]) -> dict:
    """クロール結果を S3 に同期し、更新済みインデックスを返す。

    - 既存 S3 画像かつ URL 変化なしはスキップ（冪等）
    - 今回クロールに出なかった FK は in_stock: false に更新
    - 返り値: 更新後の fk_image_index（dict）
    """
    bucket = _bucket()
    index = load_index()
    crawled_fk_set = {r["fk_id"] for r in records}
    inv_fk_set = _inventory_fk_set()

    saved = skipped = failed = 0

    for rec in records:
        fk_id         = rec["fk_id"]
        brand_key     = rec.get("brand_key", "OTHER")
        source_url    = rec.get("main_image_url", "")
        name          = rec.get("name", "")
        s3_key        = _s3_key_for(brand_key, fk_id)

        # 画像が取れていない場合はインデックスのみ更新
        if not source_url:
            index[fk_id] = {
                **index.get(fk_id, {}),
                "fk_id":      fk_id,
                "brand_key":  brand_key,
                "name":       name,
                "in_stock":   True,
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            continue

        # スキップ判定
        if bucket and _image_exists(bucket, s3_key, source_url, index, fk_id):
            log.debug("image_skip fk_id=%s", fk_id)
            index[fk_id]["in_stock"] = True
            skipped += 1
            continue

        # ダウンロード → S3 保存
        try:
            img_data = _download_image(source_url)
            if bucket:
                _upload_image(bucket, s3_key, img_data)
                log.info("image_saved fk_id=%s s3_key=%s", fk_id, s3_key)
            saved += 1
        except Exception as e:
            log.warning("image_save_failed fk_id=%s err=%s", fk_id, e)
            failed += 1
            s3_key = index.get(fk_id, {}).get("s3_main", "")  # 保存失敗でも既存を維持

        index[fk_id] = {
            "fk_id":      fk_id,
            "brand_key":  brand_key,
            "s3_main":    s3_key,
            "s3_images":  [s3_key] if s3_key else [],
            "source_url": source_url,
            "name":       name,
            "in_stock":   True,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # 今回のクロールに出なかった FK を in_stock: false に
    for fk_id in list(index.keys()):
        if fk_id not in crawled_fk_set:
            index[fk_id]["in_stock"] = False

    _save_index(index)

    # サマリーログ
    matched = len(crawled_fk_set & inv_fk_set)
    log.info(
        "sync_complete saved=%d skipped=%d failed=%d "
        "crawled=%d inv_matched=%d inv_total=%d",
        saved, skipped, failed,
        len(crawled_fk_set), matched, len(inv_fk_set),
    )
    print(f"\n=== S3 同期完了 ===")
    print(f"  保存:    {saved} 件")
    print(f"  スキップ:{skipped} 件（変化なし）")
    print(f"  失敗:    {failed} 件")
    print(f"  在庫CSV マッチ: {matched}/{len(inv_fk_set)} 件")
    print("=" * 20)

    return index


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    raw_path = Path(__file__).parent.parent.parent / "data" / "fk_image_index_raw.json"
    if not raw_path.exists():
        print(f"クロール結果が見つかりません: {raw_path}")
        print("先に image_crawler.py を実行してください。")
        sys.exit(1)

    with open(raw_path, encoding="utf-8") as f:
        records = json.load(f)

    sync_to_s3(records)
