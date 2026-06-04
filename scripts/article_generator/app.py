"""
FIRE KIDS Magazine 記事生成アプリ（AWS Bedrock + Claude版）

ブラウザから：
  1. ブランド・テーマ・画像URL等を入力
  2. AWS Bedrock（Claude）で記事TXTを生成
  3. TXTをプレビュー・編集
  4. HTML化してWP投稿（wp_uploader_local と連携）

起動:
  cd scripts/article_generator
  pip install -r requirements.txt
  python app.py
  ブラウザで http://localhost:8001
"""
import os
import re
import json
import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# プロジェクトルートを特定
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / "scripts" / "wp_uploader_local" / ".env", override=True)
load_dotenv(ROOT / "scripts" / "article_generator" / ".env", override=True)

app = Flask(__name__)

# ブランド設定
BRANDS = {
    "ROLEX":     {"jp": "ロレックス",              "category_id": 8,  "path": "rolex"},
    "OMEGA":     {"jp": "オメガ",                  "category_id": 9,  "path": "omega"},
    "SEIKO":     {"jp": "セイコー",                "category_id": 10, "path": "seiko"},
    "CITIZEN":   {"jp": "シチズン",                "category_id": 11, "path": "citizen"},
    "IWC":       {"jp": "IWC",                     "category_id": 12, "path": "iwc"},
    "TUDOR":     {"jp": "チューダー",              "category_id": 13, "path": "tudor"},
    "ORIENT":    {"jp": "オリエント",              "category_id": 14, "path": "orient"},
    "LONGINES":  {"jp": "ロンジン",                "category_id": 15, "path": "longines"},
    "JLC":       {"jp": "ジャガー・ルクルト",      "category_id": 16, "path": "jaeger-lecoultre"},
    "CARTIER":   {"jp": "カルティエ",              "category_id": 17, "path": "cartier"},
    "UNIVERSAL": {"jp": "ユニバーサルジュネーブ",  "category_id": 18, "path": "universal-geneve"},
    "BREITLING": {"jp": "ブライトリング",          "category_id": 19, "path": "breitling"},
    "VACHERON":  {"jp": "ヴァシュロン・コンスタンタン", "category_id": 20, "path": "vacheron-constantin"},
    "THEME":     {"jp": "FIRE KIDS Magazine",      "category_id": None, "path": "column"},
    "OTHER":     {"jp": "その他",                  "category_id": None, "path": "other"},
}

TONES = ["guide", "verify", "comparison", "ranking"]


def get_bedrock_client():
    """AWS Bedrock クライアントを取得"""
    import boto3
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def load_rules_context():
    """CLAUDE.mdとcaliber_db.jsonの要点を読み込む"""
    rules = ""
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        # 絶対ルールと禁止事項の部分だけ抽出（トークン節約）
        rules = text[:6000]

    caliber_summary = ""
    caliber_db = ROOT / "data" / "caliber_db.json"
    if caliber_db.exists():
        try:
            db = json.loads(caliber_db.read_text(encoding="utf-8"))
            caliber_summary = f"キャリバーDB保有ブランド: {list(db.keys())}"
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


def build_prompt(brand_key, title, theme, tone, keywords, notes, article_number):
    """記事生成用プロンプトを構築"""
    brand = BRANDS.get(brand_key, BRANDS["OTHER"])
    brand_jp = brand["jp"]
    category_id = brand["category_id"]
    brand_path = brand["path"]

    rules, caliber_summary, correction_summary = load_rules_context()

    if category_id:
        cta_base = f"https://firekids.jp/products/list?category_id={category_id}&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
    else:
        cta_base = "https://firekids.jp/?utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"

    tone_guide = {
        "guide": "ガイド系（○○とは・解説・わかりやすく）7000〜9000字",
        "verify": "検証系（本当に○○？・なぜ高い・やめとけ）6000〜8000字",
        "comparison": "比較系（○○と○○の違い・比較）6500〜8500字",
        "ranking": "ランキング系（TOP10・おすすめ10選）7000〜9000字",
    }.get(tone, "ガイド系 7000〜9000字")

    prompt = f"""あなたはFIRE KIDS Magazineの記事ライターです。
以下のルールと条件に従い、ヴィンテージ時計のSEO記事（Markdown形式）を1本生成してください。

━━━━━ 記事情報 ━━━━━
ブランド: {brand_jp}（フォルダ: {brand_key}）
記事番号: {article_number}
タイトル: {title}｜FIRE KIDS Magazine
テーマ: {theme}
トーン: {tone_guide}
キーワード: {keywords}
追加指示: {notes if notes else "なし"}

━━━━━ データソース情報 ━━━━━
{caliber_summary}
{correction_summary}
※事実情報（Cal.番号・石数・振動数・年代・Ref.番号）は必ずcaliber_db.jsonとcorrection_log.jsonの値に基づくこと。
※上記DBに存在しない仕様・歴史情報は書かずに省略すること。AIの一般知識で補完しないこと。

━━━━━ 絶対ルール（必ず守ること）━━━━━
1. FK番号（FK + 6桁数字）を本文に含めない
2. 相場価格・販売価格を記載しない
3. 個別商品URL（/products/detail等）を使わない
4. CTAはカテゴリページのみ使用: {cta_base}
5. 外部サイト（Wikipedia・Ranfft等）の情報を本文事実として採用しない
6. 「店頭でよく聞かれる」「お客様から質問される」等の擬似エピソードを書かない
7. 「断言します」「正直に言います」「時計屋として」等の語気を使わない
8. 職業×特定モデルを根拠なく結びつけない
9. 商品説明文をそのまま引用・羅列しない（モデル全体の特徴として書く）
10. 「確認できていない」「未登録」等の内部用語を本文に出さない

━━━━━ 必須構成（この順序で書くこと）━━━━━
1. # タイトル（上記タイトルをそのまま使う）
2. 対象ブランド: {brand_jp}
カテゴリ: {brand_jp}
生成日: {datetime.date.today().strftime("%Y.%m.%d")}
---
3. 導入文（リード文）2〜3段落
4. ---
5. ## セクション1（H2）〜 ## セクションN（H2）
   - H2ごとにセクション冒頭に結論1文（30〜50字）を入れる
   - 比較・スペックはMarkdownテーブルで整理する
   - 重要なRef.番号・Cal.番号・ケースサイズは**太字**にする
6. ## こんな方におすすめしたい
   - H3で3〜4パターンのペルソナを書く
7. ## よくある質問
   - Q/A形式で3〜5問（**Q:** から始める、次行に **A:** ）
8. ## まとめ
9. CTA（以下の形式で2箇所: 中間と末尾）:
   → [具体的な中間CTA文言]
   {cta_base}

   → [具体的な末尾CTA文言]
   {cta_base}

━━━━━ 文体ルール ━━━━━
- 丁寧語だが堅すぎない、専門性のある文体
- 語尾: 「〜ではないでしょうか」「〜かもしれません」「〜といえます」
- 「関連記事」セクションは含めない
- 「ひとつ目・ふたつ目」は「一つ目・二つ目」に統一（漢数字）
- 「結論から〜」は記事全体で最大1箇所

では記事本文をMarkdown形式で生成してください。"""

    return prompt


def invoke_claude(prompt: str) -> str:
    """AWS Bedrock経由でClaudeを呼び出す"""
    model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

    try:
        client = get_bedrock_client()
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8000,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except Exception as e:
        raise RuntimeError(f"Bedrock呼び出しエラー: {e}")


def title_to_slug(title: str) -> str:
    """タイトルからSEO最適なスラッグを自動生成する。
    日本語はローマ字的に読みやすいキーワードに変換せず、
    ASCII英数字部分だけを抽出してハイフン連結する。
    例: 'IWC ポルトフィーノ ヴィンテージ 1960年代解説' → 'iwc-portofino-vintage-1960'
    """
    # よく使うブランド・モデル名の日本語→英語マッピング
    JP_TO_EN = {
        "ロレックス": "rolex", "オメガ": "omega", "セイコー": "seiko",
        "シチズン": "citizen", "チューダー": "tudor", "オリエント": "orient",
        "ロンジン": "longines", "カルティエ": "cartier", "ブライトリング": "breitling",
        "ジャガー": "jaeger", "ルクルト": "lecoultre", "ユニバーサル": "universal",
        "ヴァシュロン": "vacheron", "コンスタンタン": "constantin",
        "ポルトフィーノ": "portofino", "スピードマスター": "speedmaster",
        "コンステレーション": "constellation", "シーマスター": "seamaster",
        "デイトナ": "daytona", "サブマリーナ": "submariner", "エクスプローラ": "explorer",
        "デイトジャスト": "datejust", "グランドセイコー": "grand-seiko",
        "キングセイコー": "king-seiko", "ヴィンテージ": "vintage",
        "ヴィンテイジ": "vintage", "解説": "", "とは": "", "について": "",
        "年代": "s", "年": "", "代": "s",
    }
    result = title
    for jp, en in JP_TO_EN.items():
        result = result.replace(jp, f" {en} " if en else " ")

    # ASCII英数字とハイフンだけ残す
    result = result.lower()
    result = re.sub(r"[^\w\s\-]", " ", result)
    result = re.sub(r"[\s_]+", "-", result.strip())
    result = re.sub(r"-{2,}", "-", result).strip("-")

    # 空になったらフォールバック
    if not result:
        result = "article"
    return result[:60]  # SEO的に60字以内


def save_article(brand_key: str, slug: str, content: str) -> Path:
    """記事TXTをarticles/{BRAND}/に保存。ファイル名: {日付}_{slug}.txt"""
    brand_dir = ROOT / "articles" / brand_key
    brand_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"{date_str}_{slug}.txt"
    path = brand_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ルーティング
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS, tones=TONES)


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    brand_key = data.get("brand", "ROLEX")
    title     = (data.get("title") or "").strip()
    theme     = (data.get("theme") or "").strip()
    tone      = data.get("tone", "guide")
    keywords  = (data.get("keywords") or "").strip()
    notes     = (data.get("notes") or "").strip()

    if not title or not theme:
        return jsonify({"ok": False, "error": "タイトルとテーマは必須です"}), 400

    slug = title_to_slug(title)
    try:
        prompt = build_prompt(brand_key, title, theme, tone, keywords, notes, "")
        article_txt = invoke_claude(prompt)
        return jsonify({"ok": True, "article": article_txt, "slug": slug})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json(silent=True) or {}
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


@app.route("/ping")
def ping():
    aws_key = os.getenv("AWS_ACCESS_KEY_ID", "")
    return jsonify({
        "ok": True,
        "aws_key_set": bool(aws_key),
        "aws_key_prefix": aws_key[:8] + "..." if aws_key else "(未設定)",
        "bedrock_model": os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
        "region": os.getenv("AWS_REGION", "us-east-1"),
    })


if __name__ == "__main__":
    port = int(os.getenv("GENERATOR_PORT", 8001))
    print(f"記事生成アプリ起動: http://localhost:{port}")
    app.run(debug=True, port=port, host="127.0.0.1")
