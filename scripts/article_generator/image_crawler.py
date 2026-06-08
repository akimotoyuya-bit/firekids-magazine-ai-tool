"""
FIRE KIDS Magazine 画像クローラー

firekids.jp の在庫一覧ページ（status[]=1）を全ページ巡回し、
FK番号・商品ID・メイン画像URL を同一商品ブロック内から抽出する。

出力: list[dict]
  {
    "fk_id":         "FK014781",
    "product_id":    "14781",
    "brand_key":     "SEIKO",
    "name":          "セイコー キングセイコー ...",
    "main_image_url":"https://cdn.firekids.jp/products/14781/14781_1_xxx.jpg",
    "crawled_at":    "2026-06-08T03:00:00Z",
  }

使い方（手動実行）:
  python -m scripts.article_generator.image_crawler
  python scripts/article_generator/image_crawler.py
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ─── 設定 ───────────────────────────────────────────────────────────────
BASE_URL = "https://firekids.jp/products/list"
CDN_PATTERN = re.compile(
    r'<img[^>]*src="(https://cdn\.firekids\.jp/products/(\d+)/([^"]+))"[^>]*alt="([^"]*)"'
)
FK_PATTERN = re.compile(r'FK(\d{6})')
DETAIL_PATTERN = re.compile(r'/products/detail/(\d+)')

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SLEEP_MIN = 1.0
SLEEP_MAX = 1.5


# ─── ブランド正規化（inventory.py の normalize_brand を再利用） ────────────
def _get_normalize_brand():
    """inventory.py の normalize_brand を遅延 import して返す。"""
    try:
        from inventory import normalize_brand  # type: ignore
        return normalize_brand
    except ImportError:
        try:
            from scripts.article_generator.inventory import normalize_brand
            return normalize_brand
        except ImportError:
            # フォールバック: 常に OTHER
            def normalize_brand(raw: str) -> str:  # type: ignore
                return "OTHER"
            return normalize_brand


# ─── HTTP ────────────────────────────────────────────────────────────────
def _fetch(url: str) -> str:
    """URL を GET してデコード済み HTML を返す。失敗時は例外を伝播させる。"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


# ─── HTML パース ─────────────────────────────────────────────────────────
def _extract_product_blocks(html: str) -> list[str]:
    """商品カード（<li> または <div> 単位）ごとに HTML を分割して返す。

    firekids.jp の一覧ページは商品が <li class="..."> ブロックで囲まれている。
    ブロック単位でパースすることで FK 番号と画像の対応ずれを防ぐ。
    """
    # EC-CUBE 系の商品カードは <li> 単位
    blocks = re.split(r'(?=<li[^>]*class="[^"]*ec-shelfGrid__item)', html)
    if len(blocks) < 2:
        # フォールバック: <div class="...item..."> 単位
        blocks = re.split(r'(?=<div[^>]*class="[^"]*product[^"]*")', html)
    return blocks


def _parse_block(block: str, normalize_brand) -> dict | None:
    """1 商品ブロックから必要なフィールドをすべて抽出する。

    FK 番号が取れなければ None を返す（FK なし商品はスキップ）。
    """
    # FK 番号
    fk_match = FK_PATTERN.search(block)
    if not fk_match:
        return None
    fk_id = f"FK{fk_match.group(1)}"

    # 商品 ID（詳細ページリンクから）
    detail_match = DETAIL_PATTERN.search(block)
    product_id = detail_match.group(1) if detail_match else ""

    # メイン画像 URL・商品名
    img_match = CDN_PATTERN.search(block)
    main_image_url = ""
    name = ""
    if img_match:
        main_image_url = img_match.group(1)
        name = img_match.group(4)

    # ブランド推定：商品名の先頭単語から normalize
    brand_key = "OTHER"
    if name:
        first_word = name.split()[0] if name.split() else ""
        brand_key = normalize_brand(first_word)

    return {
        "fk_id":          fk_id,
        "product_id":     product_id,
        "brand_key":      brand_key,
        "name":           name,
        "main_image_url": main_image_url,
        "crawled_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _has_next_page(html: str) -> bool:
    return 'ec-pager__item--next' in html


# ─── メイン処理 ──────────────────────────────────────────────────────────
def crawl_all(max_pages: int = 200) -> list[dict]:
    """在庫一覧を全ページ巡回し、FK→画像レコードのリストを返す。

    Args:
        max_pages: 安全上限（通常 35 ページ程度）。

    Returns:
        list[dict] — FK が取れた商品のみ。重複 FK は後勝ち。
    """
    normalize_brand = _get_normalize_brand()
    records: dict[str, dict] = {}  # fk_id → record（重複排除）
    page = 1
    consecutive_empty = 0

    log.info("crawl_start max_pages=%d", max_pages)

    while page <= max_pages:
        url = f"{BASE_URL}?status[]=1&pageno={page}"
        log.info("crawl_page page=%d url=%s", page, url)

        try:
            html = _fetch(url)
        except Exception as e:
            log.warning("crawl_fetch_error page=%d err=%s", page, e)
            break

        blocks = _extract_product_blocks(html)
        page_count = 0

        for block in blocks:
            rec = _parse_block(block, normalize_brand)
            if rec:
                records[rec["fk_id"]] = rec
                page_count += 1

        log.info("crawl_page_done page=%d found=%d cumulative=%d",
                 page, page_count, len(records))

        if page_count == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                log.info("crawl_stop_empty page=%d", page)
                break
        else:
            consecutive_empty = 0

        if not _has_next_page(html):
            log.info("crawl_last_page page=%d", page)
            break

        page += 1
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    result = list(records.values())
    log.info("crawl_complete total=%d", len(result))
    return result


def crawl_and_save_local(output_path: Path | None = None) -> list[dict]:
    """クロールして結果を data/fk_image_index_raw.json に保存する（手動実行用）。"""
    records = crawl_all()

    if output_path is None:
        base = Path(__file__).parent.parent.parent
        output_path = base / "data" / "fk_image_index_raw.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"クロール完了: {len(records)} 件 → {output_path}")

    # FK マッチ率レポート
    _print_match_report(records)

    return records


def _print_match_report(records: list[dict]) -> None:
    """在庫 CSV との FK マッチ率を表示する。"""
    try:
        try:
            from inventory import load_inventory  # type: ignore
        except ImportError:
            from scripts.article_generator.inventory import load_inventory

        inv = load_inventory()
        inv_fk_set = {item["fk_id"] for item in inv}
        crawled_fk_set = {r["fk_id"] for r in records}

        matched = inv_fk_set & crawled_fk_set
        no_image = inv_fk_set - crawled_fk_set
        extra = crawled_fk_set - inv_fk_set

        print("\n=== FK マッチ率レポート ===")
        print(f"  在庫 CSV:    {len(inv_fk_set)} 件")
        print(f"  クロール:    {len(crawled_fk_set)} 件")
        print(f"  マッチ:      {len(matched)} 件 ({len(matched)/max(len(inv_fk_set),1)*100:.1f}%)")
        print(f"  画像なし:    {len(no_image)} 件（在庫 CSV にあるがクロールで取れず）")
        print(f"  CSV 外:      {len(extra)} 件（クロールで取れたが在庫 CSV にない）")
        print("=" * 28)
    except Exception as e:
        print(f"マッチ率計算スキップ: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    crawl_and_save_local()
