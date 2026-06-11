#!/usr/bin/env python3
"""
レビュー用ドキュメント生成スクリプト

使い方:
  python3 scripts/review_generate.py 039 022 198    # 指定記事のみ
  python3 scripts/review_generate.py --all           # 未レビュー全記事
  python3 scripts/review_generate.py --brand ROLEX   # ブランド指定

出力先: review_docs/{BRAND}/{記事番号}_review.md
"""

import argparse
import re
import shutil
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE / "articles"
REVIEW_DIR = BASE / "review_docs"
SNAPSHOT_DIR = BASE / "data" / "snapshots"


def find_article(num_str: str):
    """記事番号からTXTファイルを検索"""
    padded = num_str.zfill(3)
    for brand_dir in sorted(ARTICLES_DIR.iterdir()):
        if not brand_dir.is_dir() or brand_dir.name == "_posted":
            continue
        for txt in brand_dir.glob(f"{padded}_article_*.txt"):
            return txt, brand_dir.name
    return None, None


def extract_facts(content: str) -> list:
    """記事内の検証すべき事実（数値・Cal・Ref・年代）を自動抽出"""
    facts = []

    # Cal.番号 + 仕様
    for m in re.finditer(r'Cal\.\s*(\w+)', content):
        facts.append(f"Cal.{m.group(1)}")

    # Ref.番号
    for m in re.finditer(r'Ref\.\s*([\w\-/]+)', content):
        facts.append(f"Ref.{m.group(1)}")

    # 振動数
    for m in re.finditer(r'([\d,]+)\s*振動/?時', content):
        facts.append(f"{m.group(1)}振動/時")

    # 石数
    for m in re.finditer(r'(\d+)\s*石', content):
        facts.append(f"{m.group(1)}石")

    # 年代（YYYY年）
    for m in re.finditer(r'((?:19|20)\d{2})\s*年', content):
        facts.append(f"{m.group(1)}年")

    # 重複除去して返す
    seen = set()
    result = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def generate_review(txt_path: Path, brand: str):
    """レビュー用ドキュメントを生成"""

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # タイトル抽出
    title = ""
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # 検証すべき事実を抽出
    facts = extract_facts(content)

    # スナップショット保存（diff用）
    snap_dir = SNAPSHOT_DIR / brand
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / txt_path.name
    if not snap_path.exists():
        shutil.copy2(txt_path, snap_path)

    # レビュー用ドキュメント生成
    review_dir = REVIEW_DIR / brand
    review_dir.mkdir(parents=True, exist_ok=True)

    num = re.match(r"(\d{3})_", txt_path.name).group(1)
    review_path = review_dir / f"{num}_review.md"

    lines = []
    lines.append(f"# レビュー: {title}")
    lines.append(f"")
    lines.append(f"ファイル: {brand}/{txt_path.name}")
    lines.append(f"生成日: {date.today().isoformat()}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # 本文
    lines.append(content)

    # ファクトチェック欄
    lines.append(f"")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"■ ファクトチェック欄（レビュアー記入）")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"")
    lines.append(f"この記事の事実関係を確認してください。")
    lines.append(f"誤りがあれば本文を直接修正してください。")
    lines.append(f"")

    # 自動抽出した要確認事実
    lines.append(f"### 要確認データ（自動抽出）")
    lines.append(f"")
    for fact in facts[:20]:
        lines.append(f"  - [ ] {fact}")
    lines.append(f"")

    # チェックリスト
    lines.append(f"### チェック項目")
    lines.append(f"")
    lines.append(f"  - [ ] Cal.番号・石数・振動数は正しいか")
    lines.append(f"  - [ ] 年代・Ref.番号に誤りはないか")
    lines.append(f"  - [ ] 読んで違和感のある記述はないか")
    lines.append(f"")
    lines.append(f"判定：  OK ／ NG")
    lines.append(f"")
    lines.append(f"NGの場合の理由：")
    lines.append(f"")
    lines.append(f"")
    lines.append(f"チェッカー名：")
    lines.append(f"チェック日：")
    lines.append(f"")
    lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    with open(review_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return review_path


def main():
    parser = argparse.ArgumentParser(description="レビュー用ドキュメント生成")
    parser.add_argument("numbers", nargs="*", help="記事番号（例: 039 022 198）")
    parser.add_argument("--all", action="store_true", help="未レビュー全記事を生成")
    parser.add_argument("--brand", help="ブランド指定（例: ROLEX）")
    args = parser.parse_args()

    targets = []

    if args.all or args.brand:
        for brand_dir in sorted(ARTICLES_DIR.iterdir()):
            if not brand_dir.is_dir() or brand_dir.name == "_posted":
                continue
            if args.brand and brand_dir.name != args.brand:
                continue
            for txt in sorted(brand_dir.glob("*_article_*.txt")):
                num = re.match(r"(\d{3})_", txt.name)
                if num:
                    # レビュー済みかチェック
                    review = REVIEW_DIR / brand_dir.name / f"{num.group(1)}_review.md"
                    if not review.exists():
                        targets.append((txt, brand_dir.name))
    else:
        for num in args.numbers:
            txt, brand = find_article(num)
            if txt:
                targets.append((txt, brand))
            else:
                print(f"  ❌ 記事番号 {num} が見つかりません")

    if not targets:
        print("対象記事がありません。")
        return

    print(f"レビュー用ドキュメント生成: {len(targets)}件")
    for txt, brand in targets:
        review_path = generate_review(txt, brand)
        print(f"  ✅ {brand}/{review_path.name}")

    print(f"\n出力先: {REVIEW_DIR}/")
    print(f"スナップショット: {SNAPSHOT_DIR}/")


if __name__ == "__main__":
    main()
