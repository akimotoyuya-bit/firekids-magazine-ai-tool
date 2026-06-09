"""
仕入れデータ CSV ローダー & 在庫フィルター

CSV カラム定義（0 始まり / 実データから確認済み）:
  0  : 特記事項（修理不能品 等 / 旧FK番号）
  1  : FK番号       ← 主キー (FK + 6桁)
  2  : ブランド
  3  : モデル名（正式名称 / 表示上は「正」）
  4  : 製造年製
  5  : 仕入日
  6  : HP掲載日
  7  : 支払日
  8  : 支払状況（「済」等）
  9  : 区分
  10 : 出金口座
  11 : 個人 or ディーラー
  12 : バイヤー（仕入先）
  13 : 仕入価格
  14 : OH費用
  15 : 原価
  16 : 売上日       ← 空 = 在庫中
  17 : 入金日
  18 : お客様
  19 : 売上種類
  20 : 店頭価格
  21 : 商品部（予算価格等）
  22 : 売上価格
  23 : 消費税
  24 : 入力方法
  25 : 販売チャネル
  26 : 粗利益（予算）
  27 : 粗利益率（予算）
  28 : 粗利益（実績）
  29 : 粗利益率（実績）
  30 : 備考         ← Ref./Cal./Ser. 等を含む
  31 : 買い取り理由
  32 : 値付け理由

在庫判定: 売上日（Col 16）が空 かつ FK番号が存在するレコード

S3 連携:
  S3_BUCKET         バケット名（未設定なら S3 スキップ）
  INVENTORY_S3_KEY  オブジェクトキー（デフォルト: inventory.csv）
  INVENTORY_CSV_PATH ローカルパス（ローカル開発用）
"""
from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from typing import Optional

# ── カラムインデックス ─────────────────────────────────────────────
COL_FLAGS      = 0
COL_FK_ID      = 1
COL_BRAND      = 2
COL_MODEL      = 3
COL_ERA        = 4
COL_HP_DATE    = 6
COL_SOLD_DATE  = 16
COL_LIST_PRICE = 20
COL_CHANNEL    = 25
COL_NOTES      = 30

# ── ブランド名正規化（CSV 表記 → BRANDS キー） ─────────────────────
_BRAND_MAP: dict[str, str] = {
    "ROLEX":               "ROLEX",
    "TUDOR":               "TUDOR",
    "TUDOR ROLEX":         "TUDOR",
    "OMEGA":               "OMEGA",
    "SEIKO":               "SEIKO",
    "GRAND SEIKO":         "SEIKO",
    "CITIZEN":             "CITIZEN",
    "IWC":                 "IWC",
    "ORIENT":              "ORIENT",
    "LONGINES":            "LONGINES",
    "JAEGER":              "JLC",
    "JAEGER-LECOULTRE":    "JLC",
    "CARTIER":             "CARTIER",
    "UNIVERSAL GENEVE":    "UNIVERSAL",
    "UNIVERSAL":           "UNIVERSAL",
    "BREITLING":           "BREITLING",
    "VACHERON":            "VACHERON",
    "VACHERON CONSTANTIN": "VACHERON",
}


def normalize_brand(raw: str) -> str:
    """CSV のブランド文字列を BRANDS キーに変換する。未知ブランドは OTHER。"""
    return _BRAND_MAP.get(raw.strip().upper(), "OTHER")


def _parse_notes(notes: str) -> dict[str, str]:
    """備考欄から Ref./Cal./Ser. を抽出する（大小文字・区切り文字の揺れに対応）。"""
    ref = cal = serial = ""
    m = re.search(r'[Rr]ef[.\s#:]*([A-Za-z0-9\-/\.]+)', notes)
    if m:
        ref = m.group(1).strip(".")
    m = re.search(r'[Cc]al[.\s#:]*([A-Za-z0-9\-/\.]+)', notes)
    if m:
        cal = m.group(1).strip(".")
    m = re.search(r'[Ss]er[.\s#:]*([A-Za-z0-9\-/\.]+)', notes)
    if m:
        serial = m.group(1).strip(".")
    return {"ref": ref, "cal": cal, "serial": serial}


def _parse_csv(content: str) -> list[dict]:
    """CSV テキストを在庫レコードのリストに変換する。売却済みは除外。"""
    items: list[dict] = []
    reader = csv.reader(io.StringIO(content))
    for idx, row in enumerate(reader):
        if idx == 0:
            continue  # ヘッダー行スキップ

        def col(n: int) -> str:
            return row[n].strip() if len(row) > n else ""

        fk_id = col(COL_FK_ID)
        if not re.match(r"^FK\d+$", fk_id):
            continue  # FK番号がない行をスキップ

        if col(COL_SOLD_DATE):
            continue  # 売却済み

        notes  = col(COL_NOTES)
        parsed = _parse_notes(notes)

        items.append({
            "fk_id":      fk_id,
            "brand_raw":  col(COL_BRAND),
            "brand_key":  normalize_brand(col(COL_BRAND)),
            "model":      col(COL_MODEL),
            "era":        col(COL_ERA),
            "ref":        parsed["ref"],
            "cal":        parsed["cal"],
            "serial":     parsed["serial"],
            "notes":      notes,
            "hp_date":    col(COL_HP_DATE),
            "channel":    col(COL_CHANNEL),
            "flags":      col(COL_FLAGS),
            "list_price": col(COL_LIST_PRICE),
            "is_listed":  bool(col(COL_HP_DATE)),
        })

    return items


# ── ファイル読み込みヘルパー ──────────────────────────────────────

def _decode(raw: bytes) -> str | None:
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return None


def _read_local(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return _decode(path.read_bytes())
    except Exception:
        return None


def _s3_client():
    """S3 専用クライアント。Bedrock 用の AWS_REGION とは独立した S3_REGION を使う。"""
    import boto3
    return boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION", os.getenv("AWS_REGION", "ap-northeast-1")),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def _read_s3() -> str | None:
    """S3 から在庫 CSV を読み込む。S3_REGION / INVENTORY_S3_KEY を使用する。"""
    bucket = os.getenv("S3_BUCKET", "")
    key    = os.getenv("INVENTORY_S3_KEY", "inventory/inventory.csv")
    if not bucket:
        return None
    try:
        obj = _s3_client().get_object(Bucket=bucket, Key=key)
        return _decode(obj["Body"].read())
    except Exception:
        return None


def write_s3(csv_bytes: bytes) -> bool:
    """S3 に CSV バイト列をアップロードする。S3_REGION / INVENTORY_S3_KEY を使用する。成功したら True。"""
    bucket = os.getenv("S3_BUCKET", "")
    key    = os.getenv("INVENTORY_S3_KEY", "inventory/inventory.csv")
    if not bucket:
        return False
    try:
        _s3_client().put_object(Bucket=bucket, Key=key, Body=csv_bytes, ContentType="text/csv")
        return True
    except Exception:
        return False


# ── メモリキャッシュ ──────────────────────────────────────────────

_cache: list[dict] | None = None


def load_inventory(force: bool = False) -> list[dict]:
    """在庫データを返す（メモリキャッシュあり）。

    読み込み優先順位:
      1. 環境変数 INVENTORY_CSV_PATH で指定したローカルファイル
      2. S3（S3_BUCKET が設定されている場合）
      3. /tmp/inventory.csv（Web UI からアップロードされたファイル）
    """
    global _cache
    if _cache is not None and not force:
        return _cache

    content: str | None = None

    env_path = os.getenv("INVENTORY_CSV_PATH", "")
    if env_path:
        content = _read_local(Path(env_path))

    if content is None:
        content = _read_s3()

    if content is None:
        content = _read_local(Path("/tmp/inventory.csv"))

    _cache = _parse_csv(content) if content else []
    return _cache


def reload_from_bytes(csv_bytes: bytes) -> list[dict]:
    """アップロードされた CSV バイト列でキャッシュを更新し、S3 にも保存する。"""
    global _cache
    Path("/tmp/inventory.csv").write_bytes(csv_bytes)
    write_s3(csv_bytes)
    content = _decode(csv_bytes)
    _cache = _parse_csv(content) if content else []
    return _cache


def get_in_stock(brand_key: str | None = None) -> list[dict]:
    """在庫アイテムのリストを返す。brand_key でフィルター可能。"""
    items = load_inventory()
    if brand_key:
        return [i for i in items if i["brand_key"] == brand_key]
    return items


def find_by_fk(fk_id: str) -> dict | None:
    """FK 番号でアイテムを検索する。"""
    return next((i for i in load_inventory() if i["fk_id"] == fk_id), None)


# ── 記事軸の自動選定 ──────────────────────────────────────────────

# 備考・特記事項に含まれていると「推し」度が上がるキーワード
_HIGHLIGHT_KEYWORDS = (
    "希少", "レア", "美品", "極美", "OH済", "オーバーホール", "整備", "新品",
    "未使用", "フルセット", "付属", "保証書", "ギャラ", "純正", "限定", "貴重",
)


def _feature_score(item: dict) -> tuple:
    """記事軸としての魅力度スコア（決定的）。タプルで降順比較する。

    情報量が多く、販売対象として掲載済みで、推しメモがある個体ほど高評価。
    同点時は fk_id 昇順で安定させるため、末尾に -fk_num を入れる。
    """
    score = 0
    # 掲載済み（HP掲載日あり）は記事化の前提として強く加点
    if item.get("is_listed"):
        score += 5
    # スペック情報の充実度
    if item.get("model"):  score += 2
    if item.get("era"):    score += 2
    if item.get("ref"):    score += 2
    if item.get("cal"):    score += 2
    if item.get("list_price"): score += 1
    notes = item.get("notes", "") or ""
    if notes:
        score += 1
        # 備考が長い（情報量が多い）ほど僅かに加点（上限あり）
        score += min(len(notes) // 40, 3)
    # 推しキーワード
    flags_text = (notes + " " + (item.get("flags", "") or ""))
    score += sum(1 for kw in _HIGHLIGHT_KEYWORDS if kw in flags_text)

    # fk_id を数値化して決定的タイブレーク（小さい＝古い在庫を優先）
    try:
        fk_num = int(re.sub(r"\D", "", item.get("fk_id", "0")) or 0)
    except ValueError:
        fk_num = 0
    return (score, -fk_num)


def select_feature_item(brand_key: str) -> dict | None:
    """ブランド指定だけで生成する際、記事軸にする在庫時計を1点だけ決定的に選ぶ。

    条件: 当該ブランドの在庫（売却済みでない）かつ掲載済みを優先。
    掲載済みが無ければ在庫全体から、それも無ければ None。
    """
    items = get_in_stock(brand_key)
    if not items:
        return None
    listed = [i for i in items if i.get("is_listed")]
    pool = listed if listed else items
    # 画像がある在庫を優先（記事に主役商品の画像を差し込めるようにする）
    index = _load_image_index()
    with_image = [
        i for i in pool
        if index.get(i.get("fk_id", "")) and index[i["fk_id"]].get("in_stock", True)
        and (index[i["fk_id"]].get("s3_main") or index[i["fk_id"]].get("source_url"))
    ]
    if with_image:
        pool = with_image
    return max(pool, key=_feature_score)


def summarize_item(item: dict) -> str:
    """UI 表示用の「今回の記事軸」1行要約（FK番号は含めない）。"""
    parts = [item.get("brand_raw", "")]
    if item.get("model"):
        parts.append(item["model"])
    if item.get("era"):
        parts.append(f"{item['era']}年代")
    if item.get("ref"):
        parts.append(f"Ref.{item['ref']}")
    if item.get("cal"):
        parts.append(f"Cal.{item['cal']}")
    return " / ".join([p for p in parts if p])


def format_for_prompt(item: dict) -> str:
    """在庫アイテムをプロンプト挿入用テキストに変換する。"""
    lines = [
        f"FK番号: {item['fk_id']}",
        f"ブランド: {item['brand_raw']}",
        f"モデル名: {item['model']}",
    ]
    if item.get("era"):
        lines.append(f"製造年代: {item['era']}")
    if item.get("ref"):
        lines.append(f"Ref.{item['ref']}")
    if item.get("cal"):
        lines.append(f"Cal.{item['cal']}")
    if item.get("notes"):
        lines.append(f"備考: {item['notes']}")
    return "\n".join(lines)


def inventory_summary() -> dict:
    """在庫統計（UI 表示用）。"""
    items = load_inventory()
    brands: dict[str, int] = {}
    for i in items:
        brands[i["brand_raw"]] = brands.get(i["brand_raw"], 0) + 1
    return {
        "total":   len(items),
        "listed":  sum(1 for i in items if i["is_listed"]),
        "brands":  brands,
        "loaded":  len(items) > 0,
    }


# ─── 画像メタ参照 ────────────────────────────────────────────────────────
_image_index_cache: dict | None = None


def _load_image_index() -> dict:
    """fk_image_index.json をキャッシュ付きで読み込む。空だった場合はリトライする。"""
    global _image_index_cache
    # キャッシュが存在し、かつ中身がある場合のみキャッシュを返す
    if _image_index_cache:
        return _image_index_cache
    try:
        from image_store import load_index  # type: ignore
        result = load_index()
    except ImportError:
        try:
            from scripts.article_generator.image_store import load_index
            result = load_index()
        except Exception:
            result = {}
    except Exception:
        result = {}
    # 中身があるときだけキャッシュする（空なら次回リトライ）
    if result:
        _image_index_cache = result
    return result


def get_image_for_item(item: dict) -> dict | None:
    """item['fk_id'] に対応する画像メタを返す。無ければ None。

    返す dict:
      {
        "s3_key":     "images/SEIKO/FK014781/main.jpg",
        "source_url": "https://cdn.firekids.jp/products/14781/...",
        "alt":        "セイコー / キングセイコー / 1960年代",
      }

    alt には FK 番号・価格を含めない（summarize_item() を流用）。
    インデックスが無い / 読めない / in_stock=false の場合は None を返し
    記事生成は画像なしで続行する（degrade 動作）。
    """
    fk_id = item.get("fk_id", "")
    if not fk_id:
        return None

    index = _load_image_index()
    meta = index.get(fk_id)
    if not meta:
        return None

    if not meta.get("in_stock", True):
        return None

    s3_key = meta.get("s3_main", "")
    source_url = meta.get("source_url", "")
    if not s3_key and not source_url:
        return None

    alt = summarize_item(item)  # FK 番号・価格を含まない 1 行要約

    return {
        "s3_key":     s3_key,
        "source_url": source_url,
        "alt":        alt,
    }
