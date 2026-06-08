"""
FIRE KIDS Magazine 画像クロール Lambda エントリポイント

EventBridge から 1 日 1 回（JST 04:00 = UTC 19:00）起動される。
image_crawler.crawl_all() → image_store.sync_to_s3() を順に実行し、
S3 の画像インデックスを差分更新する。

Lambda 設定推奨値:
  タイムアウト: 15 分（全件巡回 + 画像 DL の合計時間）
  メモリ:      512 MB
  ランタイム:  Python 3.12

IAM 権限（Lambda 実行ロールに付与すること）:
  s3:PutObject, s3:GetObject, s3:HeadObject, s3:ListBucket
  logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
"""
from __future__ import annotations

import json
import logging
import os
import sys

# Lambda の場合、モジュールは /var/task/ 直下に配置する想定
# ローカルテスト時は PYTHONPATH に scripts/article_generator を追加すること
sys.path.insert(0, os.path.dirname(__file__))

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event: dict, context) -> dict:
    """Lambda ハンドラー。

    event パラメータ（任意）:
      max_pages (int): クロールするページ上限（デフォルト 200）
      dry_run   (bool): True のときクロールのみ実行し S3 保存をスキップ
    """
    max_pages = int(event.get("max_pages", 200))
    dry_run   = bool(event.get("dry_run", False))

    log.info("handler_start max_pages=%d dry_run=%s", max_pages, dry_run)

    try:
        from image_crawler import crawl_all
        from image_store import sync_to_s3

        records = crawl_all(max_pages=max_pages)
        log.info("crawl_done count=%d", len(records))

        if dry_run:
            log.info("dry_run_skip_s3_sync")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "ok": True,
                    "crawled": len(records),
                    "dry_run": True,
                }),
            }

        index = sync_to_s3(records)
        in_stock = sum(1 for v in index.values() if v.get("in_stock"))
        log.info("sync_done total_index=%d in_stock=%d", len(index), in_stock)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "ok": True,
                "crawled": len(records),
                "index_total": len(index),
                "in_stock": in_stock,
            }),
        }

    except Exception as e:
        log.exception("handler_error err=%s", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"ok": False, "error": str(e)}),
        }
