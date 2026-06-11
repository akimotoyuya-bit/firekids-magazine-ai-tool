"""
FIRE KIDS Magazine - X投稿用画像生成スクリプト
CDN商品画像から5:2比率のX投稿用画像を自動生成します。

使い方:
  # 記事番号を指定（スペース区切りで複数可）
  python3 scripts/make_x_image.py 014 016 052

  # 画像URLを直接指定
  python3 scripts/make_x_image.py --url https://cdn.firekids.jp/products/12392/12392_1.jpg --name 052_x_tropical_dial --brand ROLEX

  # 全記事のHTML内画像から自動生成
  python3 scripts/make_x_image.py --all

出力:
  x_posts/{BRAND}/{番号}_x_{slug}.jpg  (1200x480, 5:2)

処理内容:
  1. CDNから商品画像をダウンロード
  2. 元画像からぼかし暗い背景を生成
  3. 時計画像を中央配置（文字盤を潰さない）
  4. 1200x480 (5:2) で保存
"""

import sys
import os
import re
import urllib.request
from pathlib import Path

try:
    from PIL import Image, ImageFilter
except ImportError:
    print("エラー: Pillow が必要です。 pip3 install Pillow")
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent
ARTICLES_DIR = BASE_DIR / "articles"
XPOSTS_DIR = BASE_DIR / "x_posts"
DATA_DIR = BASE_DIR / "data"

TARGET_W = 1200
TARGET_H = 480  # 5:2 ratio

# ブランドフォルダ → 日本語名
BRAND_JP = {
    "ROLEX": "ロレックス", "OMEGA": "オメガ", "SEIKO": "セイコー",
    "TUDOR": "チューダー", "IWC": "IWC", "JLC": "ジャガー・ルクルト",
    "LONGINES": "ロンジン", "CARTIER": "カルティエ", "CITIZEN": "シチズン",
    "ORIENT": "オリエント", "BREITLING": "ブライトリング",
    "VACHERON": "ヴァシュロン", "UNIVERSAL": "ユニバーサル",
    "THEME": "テーマ", "OTHER": "その他", "AP": "オーデマ・ピゲ"
}


def create_x_image(src_path, out_path):
    """商品画像から5:2のX投稿用画像を生成"""
    watch = Image.open(src_path).convert("RGB")
    w, h = watch.size

    # 暗いぼかし背景を生成
    bg = watch.copy().resize((TARGET_W, TARGET_W), Image.LANCZOS)
    top = (TARGET_W - TARGET_H) // 2
    bg = bg.crop((0, top, TARGET_W, top + TARGET_H))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
    dark = Image.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
    bg = Image.blend(bg, dark, 0.7)

    # 時計画像をリサイズ（高さ92%に収める）
    watch_h = int(TARGET_H * 0.92)
    ratio = watch_h / h
    watch_w = int(w * ratio)
    watch_resized = watch.resize((watch_w, watch_h), Image.LANCZOS)

    # 中央配置
    x_offset = (TARGET_W - watch_w) // 2
    y_offset = (TARGET_H - watch_h) // 2

    canvas = bg.copy()
    canvas.paste(watch_resized, (x_offset, y_offset))

    # 保存
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, "JPEG", quality=92)
    return True


def find_article_image(num_str):
    """記事番号からHTML内の最初のCDN画像URLを取得"""
    for brand_dir in ARTICLES_DIR.iterdir():
        if not brand_dir.is_dir():
            continue
        # HTMLファイルを検索
        for f in brand_dir.glob(f"{num_str}_article_*.html"):
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read()
            # og:image または最初のCDN画像URLを取得
            og_match = re.search(r'og:image:\s*(https://cdn\.firekids\.jp/[^\s]+)', content)
            if og_match:
                return og_match.group(1), brand_dir.name, f.stem
            img_match = re.search(r'src="(https://cdn\.firekids\.jp/[^"]+)"', content)
            if img_match:
                return img_match.group(1), brand_dir.name, f.stem
        # TXTファイル内のMarkdown画像を検索
        for f in brand_dir.glob(f"{num_str}_article_*.txt"):
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read()
            img_match = re.search(r'!\[.*?\]\((https://cdn\.firekids\.jp/[^)]+)\)', content)
            if img_match:
                return img_match.group(1), brand_dir.name, f.stem
        # _postedも検索
        posted = brand_dir / "_posted"
        if posted.exists():
            for f in posted.glob(f"{num_str}_article_*.html"):
                with open(f, "r", encoding="utf-8") as fh:
                    content = fh.read()
                og_match = re.search(r'og:image:\s*(https://cdn\.firekids\.jp/[^\s]+)', content)
                if og_match:
                    return og_match.group(1), brand_dir.name, f.stem
    return None, None, None


def download_image(url, dest):
    """画像をダウンロード"""
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"  ダウンロード失敗: {e}")
        return False


def process_by_number(num_str):
    """記事番号で処理"""
    padded = num_str.zfill(3)
    print(f"\n📷 No.{padded} の画像を検索中...")

    url, brand, stem = find_article_image(padded)
    if not url:
        print(f"  ❌ No.{padded} のCDN画像が見つかりません（HTML/TXTに画像URLがない）")
        return False

    print(f"  ブランド: {brand}")
    print(f"  画像URL: {url}")

    # ダウンロード
    tmp_path = f"/tmp/x_img_{padded}.jpg"
    if not download_image(url, tmp_path):
        return False

    # X用画像名を生成
    x_name = stem.replace("article_", "x_")
    out_path = XPOSTS_DIR / brand / f"{x_name}.jpg"

    # 生成
    create_x_image(tmp_path, str(out_path))
    print(f"  ✅ 保存: {out_path.relative_to(BASE_DIR)}")
    return True


def process_by_url(url, name, brand):
    """URLを直接指定して処理"""
    tmp_path = f"/tmp/x_img_direct.jpg"
    if not download_image(url, tmp_path):
        return False

    out_path = XPOSTS_DIR / brand / f"{name}.jpg"
    create_x_image(tmp_path, str(out_path))
    print(f"  ✅ 保存: {out_path.relative_to(BASE_DIR)}")
    return True


def process_all():
    """全HTMLファイルからX画像を生成"""
    count = 0
    for brand_dir in sorted(ARTICLES_DIR.iterdir()):
        if not brand_dir.is_dir():
            continue
        for html_file in sorted(brand_dir.glob("*.html")):
            num_match = re.match(r"(\d{3})_", html_file.name)
            if not num_match:
                continue
            num = num_match.group(1)
            x_name = html_file.stem.replace("article_", "x_")
            out_path = XPOSTS_DIR / brand_dir.name / f"{x_name}.jpg"
            if out_path.exists():
                continue  # 既存はスキップ
            if process_by_number(num):
                count += 1
    print(f"\n完了: {count}件の画像を生成しました")


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == "--all":
        process_all()
    elif args[0] == "--url":
        if len(args) < 6 or args[2] != "--name" or args[4] != "--brand":
            print("使い方: --url URL --name NAME --brand BRAND")
            sys.exit(1)
        process_by_url(args[1], args[3], args[5])
    else:
        # 記事番号のリスト
        success = 0
        for num in args:
            if process_by_number(num):
                success += 1
        print(f"\n完了: {success}/{len(args)}件")


if __name__ == "__main__":
    main()
