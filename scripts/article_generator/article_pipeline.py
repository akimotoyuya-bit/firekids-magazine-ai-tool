"""記事生成パイプライン Stage 1〜3 + オーケストレーション（Phase 2 リファクタリングで app.py から分離）。"""
import datetime
import json
import re

from bedrock_client import invoke_claude, invoke_claude_stream
from embeddings import embedding_degraded, reset_embed_state
from facets import (build_facet_cta_url, detect_mentioned_brands, facet_labels,
                    has_any_facet, sellable_brands_jp)
from formatting import markdown_to_wp_html, title_to_slug
from inventory import (fetch_image_for_item, fetch_theme_image, find_by_fk,
                       format_for_prompt, inventory_summary, select_feature_item,
                       summarize_item)
from overlap import check_ngram_overlap, check_overlap, sample_past_titles
from state import (ARTICLE_CATEGORIES, BRANDS, MAX_REGEN_RETRIES, ROOT,
                   TONE_CHARS, TONE_LABELS, InventoryMissingError, log)
from vector_store import get_store
from wp_scanner import ensure_cache_fresh


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

def propose_structure(brand_key: str, tone: str = "auto", item: dict | None = None,
                      direction: str = "", article_category: str = "basic",
                      facet_desc: str = "") -> dict:
    """タイトル・H2 構成案・テーマ・キーワードを小型コール（最大 800 トークン）で生成する。

    tone:
      - "auto"（既定）: 過去記事タイトルの口調・表現を参照し、Claude が最適な切り口
        （ガイド/検証/比較/ランキング等）を自動選定する。ユーザーはブランドを選ぶだけ。
      - それ以外      : 指定トーンで企画させる（従来動作）。
    item が渡された場合はその在庫商品に特化した構成を提案させる。
    facet_desc が渡された場合（テーマ記事モード）は、特定の1本を主役にせず、
    指定条件（カテゴリ/年代/性別/予算/モデル系統など）を横断的に扱う構成を提案させる。
    被り判定はここでは行わない（check_overlap で行う）。

    戻り値: {"title", "h2s", "theme", "keywords"}
    """
    brand_jp  = BRANDS[brand_key]["jp"]
    is_auto   = (not tone) or tone == "auto"
    tone_jp   = TONE_LABELS.get(tone, "")

    # 過去タイトルを「口調・表現の参考」として注入（被り回避は後段の check_overlap が担う）
    art_cat_jp = ARTICLE_CATEGORIES.get(article_category, {}).get("jp", "時計の基礎知識")
    past_titles = sample_past_titles(brand_key, article_category=article_category)
    if past_titles:
        style_block = (
            f"【過去記事タイトル（「{art_cat_jp}」カテゴリの口調・表現・粒度の参考）】\n"
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

    facet_block = ""
    if facet_desc:
        allowed_brands = "、".join(sellable_brands_jp(brand_key))
        facet_block = f"""【この記事の軸（テーマ条件）】
{facet_desc}

この記事は特定の1本のモデルを主役にせず、上記の条件に当てはまる時計を横断的に紹介する「テーマ記事」です。
複数のブランド・モデルを比較・紹介する構成にしてください（在庫データに基づく個別商品の紹介は不要です）。
取り上げてよいブランドは FIRE KIDS が実際に取り扱う次のブランドに限定してください: {allowed_brands}
上記に無いブランド（パテック・フィリップ、A.ランゲ＆ゾーネ等、FIRE KIDSで取り扱いのないブランド）は企画・タイトル・見出しに一切含めないでください。
"""

    direction_block = ""
    if direction:
        direction_block = f"""【今回ユーザーが寄せたい方向性】
{direction}

この方向性を優先して企画してください。ただし事実確認できない内容、価格断定、個別商品URL、FK番号は使わないでください。
"""

    # カテゴリ別：トーン指示 + 実際の過去タイトル例（ベクトルフィルタに関係なく常に注入）
    cat_style_examples = {
        "basic": [
            "ロレックス サブマリーナーとはどんな時計？初心者が知っておくべき基礎知識",
            "ヴィンテージ時計の「Cal.」「Ref.」って何？基礎知識を体系的に解説",
            "オメガ スピードマスターのムーブメントを徹底解説",
        ],
        "column": [
            "FIRE KIDS顧問・野村氏が語る、36年のヴィンテージ時計人生",
            "「考えたら負け」ヴィンテージ腕時計・菅藤サブの買い逃しが教えてくれたこと",
            "ロレックスの敵分なんてもう言い？ 再評価が進むヴィンテージチューダー3選",
        ],
        "trend": [
            "「昔は選ばなかった」でも今、大人になって刺さるヴィンテージ腕時計3選",
            "「考えたら負け」ヴィンテージ腕時計・菅藤サブの買い逃しが教えてくれたこと",
            "ヴィンテージ腕時計好きが最後に残す1本とは？「菅サブ」に行き着いた理由",
            "気づいたら値近く？ 2025年に「本当に値上がりした」ヴィンテージ腕時計3選",
            "ロレックスの敵分なんてもう言い？ 再評価が進むヴィンテージチューダー3選",
        ],
    }
    cat_tone_desc = {
        "basic":  "教育的・体系的で、初心者にもわかりやすく体系的な解説記事。丁寧で専門性のある文体。",
        "column": "書き手の個人的体験・視点を前面に出したエッセイ調の読み物。語りかけるような文体。",
        "trend":  (
            "読者の感情・体験に寄り添った、エッセイ調の読み物記事。"
            "「昔は選ばなかった」「考えたら負け」のような引用・体験談・エモーショナルな語り口で始まるタイトル。"
            "「〇〇3選」「〇〇に行き着いた理由」「〇〇が教えてくれたこと」といった構造のタイトルが多い。"
            "ニュース的・データ的な表現より、人の気持ちや実体験に基づいた語り口を優先する。"
        ),
    }

    cat_examples = cat_style_examples.get(article_category, cat_style_examples["basic"])
    cat_example_block = (
        f"【「{art_cat_jp}」カテゴリの実際の記事タイトル例（このトーン・表現スタイルに必ず合わせること）】\n"
        + "\n".join(f"・{t}" for t in cat_examples)
        + "\n\n上記タイトルの『語り口・感情的な引き・構文・長さ感』を参考にして、"
        "同じカテゴリに並んでも違和感のないタイトルを作ってください。\n"
    )

    cat_directive = (
        f"この記事は「{art_cat_jp}」カテゴリに掲載されます。\n"
        f"{cat_tone_desc.get(article_category, cat_tone_desc['basic'])}\n"
        f"{cat_example_block}"
    )

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事を1本企画してください。
{cat_directive}
{tone_directive}
{item_block}
{facet_block}
{direction_block}
{style_block}SEO 効果が高く、読者が具体的に求めているテーマを選んでください。

以下の JSON 形式のみで出力してください（前後に説明文・コードブロック記号を付けない）:
{{"title": "記事タイトル（｜FIRE KIDS Magazine は付けない・カテゴリのスタイルに合わせた具体的なタイトル）",
  "tone": "選んだ記事タイプ（guide/verify/comparison/ranking のいずれか）",
  "h2s": ["見出し1", "見出し2", "見出し3", "見出し4", "見出し5", "見出し6"],
  "theme": "記事で扱う内容の詳細を2〜3文で",
  "keywords": "キーワード1, キーワード2, キーワード3"}}"""

    def _parse_structure(raw: str) -> dict | None:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
            chosen_tone = str(d.get("tone", "")).strip().lower()
            if chosen_tone not in TONE_LABELS:
                chosen_tone = tone if not is_auto else "guide"
            title = str(d.get("title", "")).strip()
            if not title:
                return None
            return {
                "title":    title,
                "tone":     chosen_tone,
                "h2s":      [str(h).strip() for h in d.get("h2s", []) if str(h).strip()],
                "theme":    str(d.get("theme",    "")).strip(),
                "keywords": str(d.get("keywords", "")).strip(),
            }
        except Exception:
            return None

    for _attempt in range(2):
        raw = invoke_claude(prompt, max_tokens=1000)
        result = _parse_structure(raw)
        if result:
            return result
        log.warning("propose_structure_parse_failed attempt=%s raw_snippet=%s", _attempt, raw[:120])

    return {"title": "", "tone": (tone if not is_auto else "guide"),
            "h2s": [], "theme": raw.strip()[:200], "keywords": ""}


def revise_structure(brand_key: str, tone: str, previous: dict, flagged: list,
                     direction: str = "", article_category: str = "basic",
                     facet_desc: str = "") -> dict:
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
    direction_block = f"\n【維持したい方向性】\n{direction}\n" if direction else ""
    facet_block = (
        f"\n【維持したいテーマ条件】\n{facet_desc}\n"
        f"（特定の1本を主役にせず、この条件を横断的に扱うこと。"
        f"取り上げてよいブランドは FIRE KIDS が実際に取り扱う次のブランドに限定する: "
        f"{'、'.join(sellable_brands_jp(brand_key))}。上記に無いブランドは登場させない）\n"
        if facet_desc else ""
    )

    prompt = f"""FIRE KIDS Magazine の「{brand_jp}」ブランド記事（{tone_jp}）の企画を修正してください。

【前回の企画案（構成被りあり）】
タイトル: {previous.get('title', '')}
H2 構成: {json.dumps(previous.get('h2s', []), ensure_ascii=False)}

【被りが検出された既存記事との比較】
{conflict_text}
{direction_block}{facet_block}

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
    direction: str = "",
    article_category: str = "basic",
    facet_desc: str = "",
    cta_override: str = "",
) -> tuple[str, str]:
    brand      = BRANDS.get(brand_key, BRANDS["OTHER"])
    brand_jp   = brand["jp"]
    cat_id     = brand["category_id"]
    tone_label = f"{TONE_LABELS.get(tone, 'ガイド系')} {TONE_CHARS.get(tone, '7000〜9000字')}"
    art_cat_jp = ARTICLE_CATEGORIES.get(article_category, {}).get("jp", "時計の基礎知識")
    _, caliber_summary, correction_summary = load_rules_context()

    cta_base = cta_override or (
        f"https://firekids.jp/products/list?category_id={cat_id}"
        "&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
        if cat_id else
        "https://firekids.jp/?utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
    )

    facet_block = ""
    if facet_desc:
        allowed_brands = "、".join(sellable_brands_jp(brand_key))
        facet_block = f"""━━━━━ テーマ条件（特定の1本を主役にしない） ━━━━━
この記事の軸: {facet_desc}
- 上記条件に当てはまる時計を横断的に紹介する記事であり、在庫の特定商品を主役にしない
- 複数のブランド・モデル・年代を比較・紹介する構成にする
- 本文で扱ってよいブランドは FIRE KIDS が実際に取り扱う次のブランドに限定する: {allowed_brands}
- 上記に無いブランド（パテック・フィリップ、A.ランゲ＆ゾーネ等）は一切登場させない。歴史・時代背景の説明のために他ブランドの一般論を持ち出すことも禁止する
- Cal.番号・Ref.番号など具体的な型番スペックは、caliber_db.json / correction_log.json にデータがあるブランドのみで記載する（{caliber_summary}）。データの無いブランドは型番を創作せず、一般的な特徴・時代背景のみに留める
- 予算（金額）が条件に含まれる場合も、個別商品の相場価格・販売価格は断定的に記載しない。あくまで読者の目安として扱う
- caliber_db.json / correction_log.json で裏付けられない仕様・年代・事実は記載しない

"""

    inventory_block = ""
    image_placeholder = ""
    if item:
        inventory_block = f"""━━━━━ 在庫連携：特集対象商品 ━━━━━
{format_for_prompt(item)}

執筆ルール:
- この商品（{item['brand_raw']} {item['model']}）を記事の軸として自然に紹介すること
- 「当店に入荷」「実際に手に取れる」「在庫あり」等の表現で販売ページへの動線を作ること
- 価格・仕入れ値は一切記載しない
- 商品の特性・時代背景・選び方の文脈で登場させる（押し売り感を出さない）
- CTA には必ず {cta_base} をリンク先URLとして使用すること（リンクテキストにURLを表示しない）
- CTA は必ず独立した1行として記述し、文中にリンクを埋め込まないこと

"""
        # 画像プレースホルダー（LLM に URL を渡さず後処理で置換する）
        img = fetch_image_for_item(item)
        if img:
            image_placeholder = f"__IMAGE_PLACEHOLDER_{item['fk_id']}__"
            inventory_block += (
                f"━━━━━ 商品画像 ━━━━━\n"
                f"記事内の商品紹介セクションの直後に、以下の文字列を**そのまま**出力してください（改変・省略禁止）:\n"
                f"{image_placeholder}\n\n"
            )

    avoid_block = ""
    if avoid_articles:
        lines = []
        for f in avoid_articles[:3]:
            lines.append(f"・「{f['title']}」（{f.get('url', '')}）")
            for p in f.get("hit_pairs", [])[:3]:
                lines.append(f"  ↳ 章「{p['past']}」と類似 → 同じ切り口・具体例・導入を避ける")
        avoid_block = "━━━━━ 内容が被ってはいけない既存記事 ━━━━━\n" + "\n".join(lines) + "\n"

    direction_block = ""
    if direction:
        direction_block = f"""━━━━━ 今回ユーザーが寄せたい方向性 ━━━━━
{direction}

この方向性を本文の切り口・導入・見出しの優先順位に反映する。
ただし未検証事実、価格断定、FK番号、個別商品URLは使わない。

"""

    purchase_topic = facet_desc if facet_desc else brand_jp
    purchase_block = f"""━━━━━ 購買意欲を高める方針 ━━━━━
- 読者が「{purchase_topic} を実際に探してみたい・手に入れたい」と感じる読後感を目指す。
- 資産価値・状態の見極め・長く使う満足感など、所有/購入の魅力を具体的に描く。
- 過去記事の口調・見出し設計は「参考」にとどめ、本文の構成・切り口・具体例は被らせない。
- 煽り・誇張・断定は避け、信頼できる専門メディアとして購買の背中を押す。
- CTA は条件に対応する一覧ページ（{cta_base}）に誘導し、個別商品ページには誘導しない。リンクテキストは自然な日本語にし、URLをそのまま表示してはならない。CTA は必ず独立した1行（前後に空行）として記述し、文中にリンクを埋め込まないこと。

"""

    cat_tone_map = {
        "basic": (
            "この記事は「時計の基礎知識」カテゴリです。"
            "教育的・体系的で、時計初心者にもわかりやすく丁寧に解説してください。"
            "専門用語には簡潔な補足を添え、読者が体系的に知識を得られる構成にしてください。"
        ),
        "column": (
            "この記事は「コラム」カテゴリです。"
            "書き手の個人的体験・視点を前面に出したエッセイ調の読み物にしてください。"
            "語りかけるような文体で、読者の共感を引き出す内容にしてください。"
        ),
        "trend": (
            "この記事は「トレンド」カテゴリです。"
            "読者の感情・体験に寄り添った、エッセイ調の読み物にしてください。"
            "FIRE KIDS Magazineのトレンド記事は、ニュース的・データ的な記事ではなく、"
            "「昔は選ばなかった」「考えたら負け」のような個人的な体験談や感情的な語り口が特徴です。"
            "「〇〇3選」「〇〇に行き着いた理由」「〇〇が教えてくれたこと」といった構成で、"
            "読者が「わかる、自分もそうだ」と共感できる内容・文体にしてください。"
            "市場動向のデータを羅列するのではなく、人の気持ちや選択の物語として描いてください。"
        ),
    }
    category_instruction = cat_tone_map.get(article_category, cat_tone_map["basic"])

    prompt = f"""あなたは FIRE KIDS Magazine の記事ライターです。
以下の条件に従い、ヴィンテージ時計の SEO 記事（Markdown 形式）を1本生成してください。

━━━━━ 記事カテゴリ ━━━━━
{category_instruction}

━━━━━ 記事情報 ━━━━━
ブランド: {brand_jp}（フォルダ: {brand_key}）
記事カテゴリ: {art_cat_jp}
タイトル: {title}｜FIRE KIDS Magazine
テーマ: {theme}
トーン: {tone_label}
キーワード: {keywords}
生成日: {datetime.date.today().strftime("%Y.%m.%d")}

{purchase_block}{facet_block}{inventory_block}{direction_block}{avoid_block}
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
   - 必ず独立した1行として記述すること（前後に空行を入れる）。文中にリンクを埋め込まない
   - 直前の段落は句点で終える。CTA 行の後に文章を続けない
   - 形式: 単独行のみ [CTA文言]({cta_base})
   - リンクテキストには「在庫を確認する」「厳選されたヴィンテージ○○の在庫をFIRE KIDSで確認する」等の自然な日本語を使うこと
   - リンクテキストにURLを表示してはいけない
   - 悪い例: 「〜を探す方は、FIRE KIDSの[こちら]({cta_base})をご覧ください。」
   - 良い例:
     「〜に興味を持った方もいるかもしれません。」

     [オリエントのヴィンテージ時計をFIRE KIDSで探す]({cta_base})

━━━━━ 文体ルール ━━━━━
- 丁寧語・専門性あり・堅すぎない
- 語尾: 「〜ではないでしょうか」「〜といえます」
- 「関連記事」セクション不要
- 「結論から〜」は記事全体で最大1箇所

記事本文を Markdown 形式で生成してください（タイトル行から開始）。"""

    return prompt, image_placeholder


# ─── 生成オーケストレーション ─────────────────────────────────────────────────

def generate_article(brand_key: str, tone: str = "auto", fk_id: str = "",
                     on_stage=None, on_chunk=None, allow_no_inventory: bool = False,
                     direction: str = "", article_category: str = "basic",
                     styles: list[str] | None = None, genders: list[str] | None = None,
                     decades: list[str] | None = None, model_query: str = "",
                     min_price=None, max_price=None) -> dict:
    """3 ステージ生成フロー + 後処理 n-gram チェック。

    在庫連携:
      - fk_id 指定時: 在庫 CSV から商品情報を取得（ブランド上書き）
      - fk_id 未指定（ブランドのみ）時: select_feature_item() で記事軸を自動選定
        在庫が無く allow_no_inventory=False なら InventoryMissingError を送出

    テーマ記事（時計を選ばない）モード:
      - styles/genders/decades/model_query/min_price/max_price のいずれかが指定された場合、
        自動的に「テーマ記事モード」になり、特定の1本の在庫商品を主役にしない。
      - brand_key が空 or BRANDS に無い場合は "THEME"（FIRE KIDS Magazine 扱い）にフォールバックする。
      - CTA リンクは facets.build_facet_cta_url() で firekids.jp/products/list の
        該当フィルタ付きURLを組み立てる（ブランド一覧ページ固定ではない）。
      - 本文で扱ってよいブランドは FIRE KIDS が実際に取り扱うブランドのみに制限する
        （sellable_brands_jp）。パテック・フィリップ等、取扱の無いブランドの一般知識での
        補完を防ぐため。
      - 画像は本文生成が完了した後に選ぶ。detect_mentioned_brands() で本文中に実際に
        登場するブランドを検出し、そのブランドの在庫画像を優先的に取得する（本文と無関係な
        ブランドの写真が付く事故を防ぐ）。見つからない場合のみ条件のみでフォールバック検索する。

    on_stage(msg, stage_id): 進行状況（UI 表示 + ログ）
    on_chunk(text): 本文生成中のテキスト断片（リアルタイムプレビュー）

    1. ensure_cache_fresh()     — 増分スキャン（必要時のみ）
    2. propose_structure()      — タイトル + H2 構成案（小型コール）
    3. check_overlap() × N      — 2 レベル被り検出 + 再構成
    4. build_article_prompt()   — 本文プロンプト構築
    5. invoke_claude_stream()   — 本文生成（大型コール・ストリーミング）
    6. check_ngram_overlap()    — n-gram 重複チェック（警告のみ）
    """
    def stage(msg: str, stage_id: str = "") -> None:
        if on_stage:
            try:
                on_stage(msg, stage_id)
            except TypeError:
                on_stage(msg)

    reset_embed_state()

    facet_mode = has_any_facet(styles, genders, decades, model_query, min_price, max_price)
    if not brand_key or brand_key not in BRANDS:
        brand_key = "THEME" if facet_mode else brand_key

    stage("過去記事を照合しています…", "cache_check")
    cache_had_data = get_store().meta().get("count", 0) > 0
    ensure_cache_fresh()

    # ── アイテム決定 ───────────────────────────────────────────────
    # テーマ記事モードでは特定の1本を主役にしないため、在庫連携を一切行わない。
    item: dict | None = None
    if facet_mode:
        pass
    elif fk_id:
        item = find_by_fk(fk_id)
        if item:
            brand_key = item["brand_key"]  # ブランドを在庫データから上書き
    else:
        # ブランドのみ指定 → 記事軸の在庫を自動選定
        item = select_feature_item(brand_key)
        if item is None and not allow_no_inventory:
            # 在庫があるアプリ（loaded）でブランド在庫ゼロのときだけ中断。
            # CSV 自体が未ロードの場合は一般記事として続行する。
            if inventory_summary().get("loaded"):
                raise InventoryMissingError(brand_key)

    if item:
        stage("主役商品の画像を確認しています…", "image_fetch")
        fetch_image_for_item(item)

    facet_desc = ""
    cta_override = ""
    if facet_mode:
        facet_desc = "・".join(facet_labels(styles, genders, decades, model_query, min_price, max_price))
        cta_override = build_facet_cta_url(
            brand_key=brand_key, styles=styles, genders=genders, decades=decades,
            model_query=model_query, min_price=min_price, max_price=max_price,
        )

    stage("被らないテーマ・構成を考えています…", "prompt_build")
    direction = (direction or "").strip()[:500]
    structure  = propose_structure(brand_key, tone, item=item, direction=direction,
                                   article_category=article_category, facet_desc=facet_desc)
    effective_tone = structure.get("tone") or (tone if tone and tone != "auto" else "guide")
    overlap    = {"ok": True, "flagged": []}

    stage("過去記事との被りをチェックしています…")
    for attempt in range(MAX_REGEN_RETRIES):
        overlap = check_overlap(brand_key, structure.get("title", ""), structure.get("h2s", []), article_category=article_category)
        if overlap["ok"]:
            break
        if attempt < MAX_REGEN_RETRIES - 1:
            stage("構成を調整しています…")
            log.info("structure_revise brand=%s attempt=%s flagged=%s",
                     brand_key, attempt + 1, len(overlap.get("flagged", [])))
            structure = revise_structure(brand_key, effective_tone, structure, overlap["flagged"],
                                        direction=direction, article_category=article_category,
                                        facet_desc=facet_desc)

    title    = structure.get("title")    or f"{BRANDS[brand_key]['jp']} 特集記事"
    h2s      = structure.get("h2s",      [])
    theme    = structure.get("theme",    "")
    keywords = structure.get("keywords", "")

    prompt, image_placeholder = build_article_prompt(
        brand_key, effective_tone, title, theme, keywords, overlap.get("flagged", []),
        item=item, direction=direction, article_category=article_category,
        facet_desc=facet_desc, cta_override=cta_override,
    )
    stage("本文を執筆しています…", "bedrock_call")
    if on_chunk:
        article = invoke_claude_stream(prompt, on_chunk)
    else:
        article = invoke_claude(prompt)

    # 画像メタをリザルトに含める（WordPress 連携は別ステップ）
    # プレースホルダーは記事本文から除去し、メタ情報として返す
    image_meta: dict | None = None
    if image_placeholder and item:
        img = fetch_image_for_item(item)
        if img:
            image_meta = img
        # プレースホルダーを本文から除去（CDN URL 直貼りは避ける）
        article = article.replace(image_placeholder, "")
    elif facet_mode:
        # 本文が確定した後に画像を選ぶことで、本文で実際に言及されたブランドの
        # 商品画像を優先する（条件だけで選ぶと本文と無関係なブランドの写真が付く事故が起きるため）。
        stage("記事に登場するブランドの画像を確認しています…", "image_fetch")
        image_meta = None
        # 遅延防止のため、言及頻度上位3ブランドまでに絞って画像を探す
        for candidate_brand in (detect_mentioned_brands(article)[:3] or [brand_key]):
            try:
                image_meta = fetch_theme_image(
                    brand_key=candidate_brand, styles=styles, genders=genders, decades=decades,
                    model_query=model_query, min_price=min_price, max_price=max_price,
                )
            except Exception:
                image_meta = None
            if image_meta:
                break
        if not image_meta:
            # 言及ブランドでは見つからない場合、条件のみでフォールバック検索する
            try:
                image_meta = fetch_theme_image(
                    brand_key=brand_key, styles=styles, genders=genders, decades=decades,
                    model_query=model_query, min_price=min_price, max_price=max_price,
                )
            except Exception:
                image_meta = None

    stage("仕上げチェック中…")
    slug         = title_to_slug(title)
    ngram_issues = check_ngram_overlap(article, brand_key, article_category=article_category)

    # ── 劣化モード / 重複ステータスの判定 ─────────────────────────
    degraded_modes: list[str] = []
    if embedding_degraded():
        degraded_modes.append("embedding_unavailable")

    if embedding_degraded() or not cache_had_data:
        overlap_status = "unchecked"   # 過去記事チェックが信頼できない
    elif overlap["ok"]:
        overlap_status = "ok"
    else:
        overlap_status = "flagged"

    tone_titles = sample_past_titles(brand_key, limit=6, article_category=article_category)
    tone_reference_summary = (
        "過去記事の口調・見出し設計を参考: " + " / ".join(tone_titles)
        if tone_titles else "参考にできる過去記事が見つかりませんでした"
    )

    return {
        "title":        title,
        "tone":         effective_tone,
        "tone_label":   TONE_LABELS.get(effective_tone, "ガイド系"),
        "h2s":          h2s,
        "keywords":     keywords,
        "theme":        theme,
        "direction":    direction,
        "article":      article,
        "html":         markdown_to_wp_html(article),
        "slug":         slug,
        "brand_key":    brand_key,
        "brand_jp":     BRANDS.get(brand_key, {}).get("jp", brand_key),
        "overlap_ok":   overlap["ok"],
        "overlap_status": overlap_status,
        "degraded_modes": degraded_modes,
        "ngram_issues": ngram_issues,
        "item_summary": summarize_item(item) if item else "",
        "tone_reference_summary": tone_reference_summary,
        "fk_id":        fk_id,
        "article_category": article_category,
        "article_category_wp_id": ARTICLE_CATEGORIES.get(article_category, {}).get("wp_id"),
        "article_category_jp": ARTICLE_CATEGORIES.get(article_category, {}).get("jp", ""),
        "facet_mode":   facet_mode,
        "facet_desc":   facet_desc,
        "cta_url":      cta_override,
        "item":         item,
        "image_meta":   image_meta,  # WordPress 連携用（s3_key, source_url, alt）
    }
