#!/usr/bin/env python3
"""
修正検出・ログ蓄積スクリプト

人間がレビューファイルを修正した後に実行。
スナップショット（修正前）とレビューファイル（修正後）を比較し、
差分をcorrection_log.jsonに蓄積する。

使い方:
  python3 scripts/review_diff.py 039 022 198    # 指定記事
  python3 scripts/review_diff.py --all           # 全レビュー済み記事
  python3 scripts/review_diff.py --apply         # diffログ後、TXTにも反映

出力: data/correction_log.json
"""

import argparse
import difflib
import json
import re
import shutil
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARTICLES_DIR = BASE / "articles"
REVIEW_DIR = BASE / "review_docs"
SNAPSHOT_DIR = BASE / "data" / "snapshots"
LOG_PATH = BASE / "data" / "correction_log.json"


def load_log() -> dict:
    """修正ログを読み込み"""
    if LOG_PATH.exists():
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"corrections": [], "summary": {"total": 0, "by_type": {}}}


def save_log(log: dict):
    """修正ログを保存"""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def classify_diff(before: str, after: str) -> str:
    """修正内容を自動分類"""
    if not before.strip():
        return "追加"
    if not after.strip():
        return "削除"

    # 数値の変更
    nums_before = set(re.findall(r'\d{2,6}', before))
    nums_after = set(re.findall(r'\d{2,6}', after))
    if nums_before != nums_after:
        if re.search(r'Cal\.|キャリバー', before + after):
            return "キャリバー仕様修正"
        if re.search(r'Ref\.', before + after):
            return "リファレンス修正"
        if re.search(r'振動|石', before + after):
            return "仕様データ修正"
        if re.search(r'年', before + after):
            return "年代修正"
        return "数値修正"

    if re.search(r'utm_|https?:', before + after):
        return "リンク・UTM修正"

    return "文言修正"


def extract_review_content(review_text: str) -> str:
    """レビューファイルからファクトチェック欄を除去し、本文のみ返す"""
    marker = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    lines = review_text.split("\n")

    # ヘッダー部分（レビュー:タイトル、ファイル:、生成日:）をスキップ
    content_start = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            content_start = i + 1
            break

    # ファクトチェック欄の開始位置を検出
    content_end = len(lines)
    for i, line in enumerate(lines):
        if marker in line and i > content_start:
            content_end = i
            break

    return "\n".join(lines[content_start:content_end]).strip()


def compute_diffs(old_text: str, new_text: str) -> list:
    """行単位のdiffを検出し、変更箇所のリストを返す"""
    old_lines = old_text.split("\n")
    new_lines = new_text.split("\n")

    diffs = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue

        if op == "replace":
            # 変更：旧行と新行を対応付け
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                old_line = old_lines[i1 + k].strip() if (i1 + k) < i2 else ""
                new_line = new_lines[j1 + k].strip() if (j1 + k) < j2 else ""
                if old_line or new_line:
                    if old_line != new_line:
                        diffs.append({
                            "before": old_line,
                            "after": new_line,
                            "type": classify_diff(old_line, new_line)
                        })

        elif op == "delete":
            for k in range(i1, i2):
                line = old_lines[k].strip()
                if line and line != "---":
                    diffs.append({
                        "before": line,
                        "after": "",
                        "type": "削除"
                    })

        elif op == "insert":
            for k in range(j1, j2):
                line = new_lines[k].strip()
                if line and line != "---":
                    diffs.append({
                        "before": "",
                        "after": line,
                        "type": "追加"
                    })

    # 空行や装飾行の変更は除外
    diffs = [d for d in diffs if _is_significant(d)]
    return diffs


def _is_significant(diff: dict) -> bool:
    """意味のある変更かどうか判定"""
    before = diff["before"].strip()
    after = diff["after"].strip()

    # 空行・区切り線のみの変更は無視
    if not before and not after:
        return False
    if before in ("---", "", "##", "###") and after in ("---", "", "##", "###"):
        return False

    # メタ情報行のみの変更は無視
    if before.startswith("対象ブランド:") or before.startswith("カテゴリ:"):
        return False

    return True


def find_article_and_review(num_str: str):
    """記事番号からスナップショットとレビューファイルを検索"""
    padded = num_str.zfill(3)
    for brand_dir in sorted(REVIEW_DIR.iterdir()):
        if not brand_dir.is_dir():
            continue
        review = brand_dir / f"{padded}_review.md"
        if review.exists():
            # 対応するスナップショットを検索
            snap_dir = SNAPSHOT_DIR / brand_dir.name
            for snap in snap_dir.glob(f"{padded}_article_*.txt"):
                return snap, review, brand_dir.name
    return None, None, None


def process_article(num_str: str, apply: bool = False) -> list:
    """1記事のdiffを検出してログに追加"""
    snap, review, brand = find_article_and_review(num_str)
    if not snap or not review:
        print(f"  ⏭ {num_str}: スナップショットまたはレビューが見つかりません")
        return []

    with open(snap, "r", encoding="utf-8") as f:
        old_text = f.read()

    with open(review, "r", encoding="utf-8") as f:
        review_text = f.read()

    new_text = extract_review_content(review_text)

    if old_text.strip() == new_text.strip():
        print(f"  ⏭ {num_str}: 変更なし")
        return []

    diffs = compute_diffs(old_text, new_text)
    if not diffs:
        print(f"  ⏭ {num_str}: 有意な変更なし")
        return []

    # チェッカー名を抽出（レビューファイルから）
    checker = ""
    for line in review_text.split("\n"):
        if line.startswith("チェッカー名："):
            checker = line.replace("チェッカー名：", "").strip()
            break

    # 判定を抽出
    judgment = ""
    for line in review_text.split("\n"):
        if "判定" in line and ("OK" in line or "NG" in line):
            if "OK" in line and "NG" not in line:
                judgment = "OK"
            elif "NG" in line:
                judgment = "NG"
            break

    entries = []
    for d in diffs:
        entries.append({
            "date": date.today().isoformat(),
            "article": snap.name,
            "brand": brand,
            "before": d["before"],
            "after": d["after"],
            "type": d["type"],
            "checker": checker,
            "judgment": judgment
        })

    print(f"  ✅ {num_str}: {len(entries)}件の修正を検出")
    for e in entries:
        print(f"     [{e['type']}] {e['before'][:40]}... → {e['after'][:40]}...")

    # TXTに反映
    if apply:
        txt_path = None
        for brand_dir in ARTICLES_DIR.iterdir():
            if brand_dir.name == brand:
                for txt in brand_dir.glob(f"{num_str.zfill(3)}_article_*.txt"):
                    txt_path = txt
                    break
        if txt_path:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(new_text)
            # スナップショットも更新
            shutil.copy2(txt_path, snap)
            print(f"     → TXT反映済み: {txt_path.name}")

    return entries


def main():
    parser = argparse.ArgumentParser(description="修正検出・ログ蓄積")
    parser.add_argument("numbers", nargs="*", help="記事番号（例: 039 022 198）")
    parser.add_argument("--all", action="store_true", help="全レビュー済み記事")
    parser.add_argument("--apply", action="store_true", help="TXTにも修正を反映")
    args = parser.parse_args()

    targets = []
    if args.all:
        for brand_dir in sorted(REVIEW_DIR.iterdir()):
            if not brand_dir.is_dir():
                continue
            for review in sorted(brand_dir.glob("*_review.md")):
                num = re.match(r"(\d{3})_", review.name)
                if num:
                    targets.append(num.group(1))
    else:
        targets = [n.zfill(3) for n in args.numbers]

    if not targets:
        print("対象記事がありません。")
        print("使い方: python3 scripts/review_diff.py 039 022 198")
        print("        python3 scripts/review_diff.py --all")
        return

    # ログ読み込み
    log = load_log()

    print(f"修正検出: {len(targets)}件")
    total_new = 0

    for num in targets:
        entries = process_article(num, apply=args.apply)
        log["corrections"].extend(entries)
        total_new += len(entries)

    # サマリー更新
    log["summary"]["total"] = len(log["corrections"])
    type_counts = {}
    for c in log["corrections"]:
        t = c.get("type", "不明")
        type_counts[t] = type_counts.get(t, 0) + 1
    log["summary"]["by_type"] = type_counts
    log["summary"]["last_updated"] = date.today().isoformat()

    # 保存
    save_log(log)

    print(f"\n完了: {total_new}件の修正を記録")
    print(f"累計: {log['summary']['total']}件")
    print(f"種別: {json.dumps(log['summary']['by_type'], ensure_ascii=False)}")
    print(f"ログ: {LOG_PATH}")


if __name__ == "__main__":
    main()
