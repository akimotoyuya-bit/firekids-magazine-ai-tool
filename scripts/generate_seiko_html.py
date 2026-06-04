#!/usr/bin/env python3
"""
Generate WordPress Gutenberg HTML for SEIKO articles.
Reads TXT (Markdown), outputs HTML with meta comments, JSON-LD, Gutenberg blocks.
"""

import os
import re
import json
import html
from pathlib import Path

# プロジェクトルートを自動判定（scripts/ の親ディレクトリ）
BASE = str(Path(__file__).resolve().parent.parent)
SEIKO_DIR = os.path.join(BASE, "articles", "SEIKO")
CTA_URL = "https://firekids.jp/products/list?category_id=10&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic"
DATE_PUBLISHED = "2026-03-19"

SEIKO_IMAGES = [
    "https://cdn.firekids.jp/products/13179/13179_1_137568.jpg",
    "https://cdn.firekids.jp/products/13177/13177_1_137547.jpg",
    "https://cdn.firekids.jp/products/13172/13172_1_137499.jpg",
    "https://cdn.firekids.jp/products/13171/13171_1_137489.jpg",
    "https://cdn.firekids.jp/products/13133/13133_1_137300.jpg",
    "https://cdn.firekids.jp/products/13128/13128_1_136917.jpg",
    "https://cdn.firekids.jp/products/13127/13127_1_136897.jpg",
    "https://cdn.firekids.jp/products/13124/13124_1_136877.jpg",
    "https://cdn.firekids.jp/products/13123/13123_1_137060.jpg",
    "https://cdn.firekids.jp/products/13119/13119_1_136639.jpg",
    "https://cdn.firekids.jp/products/13115/13115_1_136817.jpg",
    "https://cdn.firekids.jp/products/13111/13111_1_136755.jpg",
    "https://cdn.firekids.jp/products/13068/13068_1_137456.jpg",
    "https://cdn.firekids.jp/products/13067/13067_1_137447.jpg",
    "https://cdn.firekids.jp/products/13051/13051_1_136097.jpg",
    "https://cdn.firekids.jp/products/13049/13049_1_136076.jpg",
    "https://cdn.firekids.jp/products/13041/13041_1_135996.jpg",
    "https://cdn.firekids.jp/products/13040/13040_1_135931.jpg",
    "https://cdn.firekids.jp/products/13039/13039_1_135922.jpg",
    "https://cdn.firekids.jp/products/13038/13038_1_135682.jpg",
    "https://cdn.firekids.jp/products/13037/13037_1_135611.jpg",
    "https://cdn.firekids.jp/products/13035/13035_1_135600.jpg",
    "https://cdn.firekids.jp/products/13033/13033_1_135915.jpg",
    "https://cdn.firekids.jp/products/13032/13032_1_135906.jpg",
    "https://cdn.firekids.jp/products/13031/13031_1_135897.jpg",
    "https://cdn.firekids.jp/products/13028/13028_1_135671.jpg",
    "https://cdn.firekids.jp/products/13027/13027_1_135751.jpg",
    "https://cdn.firekids.jp/products/13021/13021_1_136067.jpg",
    "https://cdn.firekids.jp/products/13009/13009_1_135561.jpg",
    "https://cdn.firekids.jp/products/13004/13004_1_136180.jpg",
    "https://cdn.firekids.jp/products/13000/13000_1_135824.jpg",
    "https://cdn.firekids.jp/products/12963/12963_1_135134.jpg",
    "https://cdn.firekids.jp/products/12957/12957_1_135082.jpg",
    "https://cdn.firekids.jp/products/12925/12925_1_134804.jpg",
    "https://cdn.firekids.jp/products/12914/12914_1_134768.jpg",
    "https://cdn.firekids.jp/products/12913/12913_1_134417.jpg",
    "https://cdn.firekids.jp/products/12911/12911_1_134748.jpg",
    "https://cdn.firekids.jp/products/12909/12909_1_134518.jpg",
    "https://cdn.firekids.jp/products/12887/12887_1_133771.jpg",
    "https://cdn.firekids.jp/products/12884/12884_1_133740.jpg",
    "https://cdn.firekids.jp/products/12883/12883_1_133731.jpg",
    "https://cdn.firekids.jp/products/12878/12878_1_133682.jpg",
    "https://cdn.firekids.jp/products/12877/12877_1_133673.jpg",
    "https://cdn.firekids.jp/products/12852/12852_1_133316.jpg",
    "https://cdn.firekids.jp/products/12848/12848_1_133643.jpg",
    "https://cdn.firekids.jp/products/12837/12837_1_133558.jpg",
    "https://cdn.firekids.jp/products/12833/12833_1_133108.jpg",
    "https://cdn.firekids.jp/products/12828/12828_1_133076.jpg",
    "https://cdn.firekids.jp/products/12827/12827_1_133549.jpg",
    "https://cdn.firekids.jp/products/12825/12825_1_133540.jpg",
    "https://cdn.firekids.jp/products/12819/12819_1_133034.jpg",
    "https://cdn.firekids.jp/products/12817/12817_1_133012.jpg",
    "https://cdn.firekids.jp/products/12810/12810_1_133590.jpg",
    "https://cdn.firekids.jp/products/12809/12809_1_133240.jpg",
    "https://cdn.firekids.jp/products/12804/12804_1_136014.jpg",
    "https://cdn.firekids.jp/products/12800/12800_1_132947.jpg",
    "https://cdn.firekids.jp/products/12774/12774_1_134277.jpg",
    "https://cdn.firekids.jp/products/12761/12761_1_133497.jpg",
    "https://cdn.firekids.jp/products/12715/12715_1_131557.jpg",
    "https://cdn.firekids.jp/products/12705/12705_1_131243.jpg",
    "https://cdn.firekids.jp/products/12704/12704_1_131387.jpg",
    "https://cdn.firekids.jp/products/12703/12703_1_131734.jpg",
    "https://cdn.firekids.jp/products/12700/12700_1_131486.jpg",
    "https://cdn.firekids.jp/products/12699/12699_1_131225.jpg",
    "https://cdn.firekids.jp/products/12695/12695_1_131351.jpg",
    "https://cdn.firekids.jp/products/12682/12682_1_131645.jpg",
    "https://cdn.firekids.jp/products/12680/12680_1_131627.jpg",
    "https://cdn.firekids.jp/products/12671/12671_1_134268.jpg",
    "https://cdn.firekids.jp/products/12655/12655_1_130952.jpg",
    "https://cdn.firekids.jp/products/12645/12645_1_130815.jpg",
    "https://cdn.firekids.jp/products/12643/12643_1_130806.jpg",
    "https://cdn.firekids.jp/products/12641/12641_1_130934.jpg",
    "https://cdn.firekids.jp/products/12629/12629_1_134250.jpg",
    "https://cdn.firekids.jp/products/12623/12623_1_134241.jpg",
    "https://cdn.firekids.jp/products/12622/12622_1_134232.jpg",
    "https://cdn.firekids.jp/products/12587/12587_1_130236.jpg",
    "https://cdn.firekids.jp/products/12572/12572_1_129768.jpg",
    "https://cdn.firekids.jp/products/12504/12504_1_127930.jpg",
    "https://cdn.firekids.jp/products/12450/12450_1.jpg",
    "https://cdn.firekids.jp/products/12445/12445_1.jpg",
    "https://cdn.firekids.jp/products/12434/12434_1.jpg",
    "https://cdn.firekids.jp/products/12430/12430_1.jpg",
    "https://cdn.firekids.jp/products/12413/12413_1.jpg",
    "https://cdn.firekids.jp/products/12360/12360_1.jpg",
    "https://cdn.firekids.jp/products/12343/12343_1.jpg",
    "https://cdn.firekids.jp/products/12337/12337_1_132231.jpg",
    "https://cdn.firekids.jp/products/12298/12298_1_129533.jpg",
    "https://cdn.firekids.jp/products/12278/12278_1.jpg",
    "https://cdn.firekids.jp/products/12268/12268_1.jpg",
    "https://cdn.firekids.jp/products/12227/12227_1.jpg",
]

ARTICLES = [
    "120_article_grand_seiko.txt",
    "130_article_king_seiko.txt",
    "145_article_speed_timer.txt",
    "150_article_seikomatic.txt",
    "151_article_pocket_watch.txt",
    "152_article_silver_wave.txt",
    "153_article_skyliner_worldtime.txt",
    "154_article_hand_wind_chrono.txt",
    "155_article_diver_2nd.txt",
    "156_article_diver_3rd.txt",
    "157_article_gs_first.txt",
    "158_article_gs_44gs.txt",
    "159_article_gs_56gs.txt",
    "160_article_ks_first.txt",
    "161_article_gs_61gs.txt",
    "162_article_gs_sport.txt",
    "163_article_ks_45ks.txt",
    "164_article_ks_56ks.txt",
    "165_article_ks_vs_gs.txt",
    "270_article_gs_caliber_table.txt",
    "271_article_gs_dial_all.txt",
    "272_article_5actus.txt",
    "279_article_ks_all_models.txt",
    "293_article_gs_seiko_style.txt",
    "294_article_gs_vintage_year.txt",
    "295_article_ks_case_material.txt",
    "296_article_ks_kameido.txt",
    "297_article_ks_chrono.txt",
    "336_article_seiko_jointpointer.txt",
    "337_article_seiko_alpinist.txt",
    "346_article_seiko_chrono_first.txt",
    "347_article_seiko_caliber_table.txt",
    "360_article_seiko_business.txt",
    "365_article_seiko_self_dater.txt",
    "366_article_seiko_vs_gs.txt",
]


def escape(text):
    return html.escape(text, quote=True)


def make_slug(filename):
    """Extract slug from filename like '120_article_grand_seiko.txt' -> 'grand_seiko'"""
    name = filename.replace(".txt", "")
    parts = name.split("_", 2)
    if len(parts) >= 3:
        return parts[2]
    return parts[-1]


def extract_title(content):
    """Extract title from first # line"""
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            # Remove trailing "|FIRE KIDS Magazine" if present
            if "|" in title:
                parts = title.rsplit("|", 1)
                if "FIRE KIDS" in parts[-1]:
                    title = parts[0].strip()
                elif "｜" not in title:
                    pass
            if "｜" in title:
                parts = title.rsplit("｜", 1)
                if "FIRE KIDS" in parts[-1]:
                    title = parts[0].strip()
            return title
    return "セイコー記事"


def extract_full_title(title):
    """Create full title with FIRE KIDS Magazine suffix"""
    return f"{title}｜FIRE KIDS Magazine"


def extract_meta_description(content, title):
    """Extract first meaningful paragraph as meta description"""
    lines = content.split("\n")
    in_header = True
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            in_header = True
            continue
        if line.startswith("---"):
            in_header = False
            continue
        if line.startswith("対象ブランド") or line.startswith("カテゴリ") or line.startswith("生成日"):
            continue
        if not line:
            continue
        if not in_header and len(line) > 30:
            # Trim to ~160 chars
            desc = line[:200]
            if len(line) > 200:
                desc = desc[:desc.rfind("。") + 1] if "。" in desc else desc
            return desc
    # fallback
    return f"{title}について解説します。FIRE KIDSの取り扱い情報をもとに、特徴と選び方をご紹介。"


def extract_keywords(title, content):
    """Extract keywords from title and content"""
    keywords = []
    # Extract from title
    title_words = re.findall(r'[A-Za-z0-9]+|[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', title)
    for w in title_words[:5]:
        if len(w) > 1:
            keywords.append(w)

    keywords.extend(["セイコー", "ヴィンテージ時計", "FIRE KIDS"])
    # Deduplicate
    seen = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result[:10]


def extract_canonical_slug(title):
    """Create a slug for canonical URL"""
    # Simple mapping from title
    slug = title.lower()
    # Replace Japanese characters with hyphens
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:80]


def extract_faq(content):
    """Extract FAQ Q&A pairs from content"""
    faqs = []
    lines = content.split("\n")
    current_q = None
    current_a_lines = []
    in_faq = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check for FAQ section headers
        if re.match(r'^#{1,3}\s*(よくある質問|FAQ)', stripped):
            in_faq = True
            continue

        # Check for Q: patterns (both ### Q: and **Q: styles)
        q_match = re.match(r'^(?:#{2,3}\s*)?(?:\*\*)?Q[:\s：](.+?)(?:\*\*)?$', stripped)
        if not q_match:
            q_match = re.match(r'^#{2,3}\s*Q[:\s：]\s*(.+)$', stripped)
        if not q_match:
            # Also match ### Q1. patterns
            q_match = re.match(r'^#{2,3}\s*Q\d*[\.\s]\s*(.+)$', stripped)

        if q_match:
            # Save previous Q&A
            if current_q and current_a_lines:
                answer = " ".join(current_a_lines).strip()
                # Clean up answer markers
                answer = re.sub(r'^(?:\*\*)?A[:\s：]?\s*(?:\*\*)?\s*', '', answer)
                if answer:
                    faqs.append({"q": current_q, "a": answer})
            current_q = q_match.group(1).strip().rstrip("*")
            current_a_lines = []
            continue

        if current_q is not None:
            if stripped.startswith("---") or (stripped.startswith("## ") and not stripped.startswith("### ")):
                # End of FAQ section
                if current_a_lines:
                    answer = " ".join(current_a_lines).strip()
                    answer = re.sub(r'^(?:\*\*)?A[:\s：]?\s*(?:\*\*)?\s*', '', answer)
                    if answer:
                        faqs.append({"q": current_q, "a": answer})
                current_q = None
                current_a_lines = []
                if stripped.startswith("---"):
                    in_faq = False
                continue

            if stripped and not stripped.startswith("**Q"):
                # Clean answer line
                cleaned = stripped
                cleaned = re.sub(r'^\*\*A[:\s：]?\s*\*\*\s*', '', cleaned)
                cleaned = re.sub(r'^A[:\s：]\s*', '', cleaned)
                if cleaned:
                    current_a_lines.append(cleaned)

    # Don't forget last Q&A
    if current_q and current_a_lines:
        answer = " ".join(current_a_lines).strip()
        answer = re.sub(r'^(?:\*\*)?A[:\s：]?\s*(?:\*\*)?\s*', '', answer)
        if answer:
            faqs.append({"q": current_q, "a": answer})

    return faqs[:5]  # Max 5 FAQs


def md_inline_to_html(text):
    """Convert inline markdown (bold, links) to HTML"""
    # Bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Links [text](url)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    return text


def parse_table(lines):
    """Parse markdown table lines into HTML table"""
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]  # Remove empty
        if all(set(c) <= set("-: ") for c in cells):
            continue  # Skip separator line
        rows.append(cells)

    if not rows:
        return ""

    html_out = '<!-- wp:table -->\n<figure class="wp-block-table"><table class="has-fixed-layout"><tbody>\n'
    for i, row in enumerate(rows):
        html_out += "<tr>"
        for cell in row:
            cell_html = md_inline_to_html(escape(cell))
            if i == 0:
                html_out += f"<td><strong>{cell_html}</strong></td>"
            else:
                html_out += f"<td>{cell_html}</td>"
        html_out += "</tr>\n"
    html_out += "</tbody></table></figure>\n<!-- /wp:table -->"
    return html_out


def convert_md_to_gutenberg(content, images, title):
    """Convert markdown content to Gutenberg blocks"""
    lines = content.split("\n")
    blocks = []
    i = 0
    in_header = True
    in_list = False
    list_items = []
    in_table = False
    table_lines = []
    h2_count = 0
    image_positions = set()
    cta_added = False

    # Determine where to place images (after 1st, 3rd, and 5th h2)
    h2_indices = []
    for idx, line in enumerate(lines):
        if line.strip().startswith("## "):
            h2_indices.append(idx)

    # Place images after h2 sections: after 1st, middle, and 2/3 through
    if len(h2_indices) >= 3:
        image_positions = {1, len(h2_indices) // 2, len(h2_indices) * 2 // 3}
    elif len(h2_indices) >= 2:
        image_positions = {1, 2}
    elif len(h2_indices) >= 1:
        image_positions = {1}

    img_idx = 0

    def flush_list():
        nonlocal list_items
        if list_items:
            block = '<!-- wp:list -->\n<ul class="wp-block-list">\n'
            for item in list_items:
                item_html = md_inline_to_html(escape(item))
                block += f"<li>{item_html}</li>\n"
            block += "</ul>\n<!-- /wp:list -->"
            blocks.append(block)
            list_items = []

    def flush_table():
        nonlocal table_lines
        if table_lines:
            blocks.append(parse_table(table_lines))
            table_lines = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip header metadata
        if in_header:
            if stripped.startswith("# "):
                i += 1
                continue
            if stripped.startswith("対象ブランド") or stripped.startswith("カテゴリ") or stripped.startswith("生成日"):
                i += 1
                continue
            if stripped == "---":
                in_header = False
                i += 1
                continue
            if not stripped:
                i += 1
                continue
            in_header = False

        # Skip trailing CTA/links
        if stripped.startswith("→ ") or stripped.startswith("FIRE KIDS セイコーの商品一覧"):
            i += 1
            continue
        if stripped.startswith("https://firekids.jp"):
            i += 1
            continue
        if stripped == "---":
            i += 1
            continue

        # Skip "関連記事" section
        if stripped.startswith("## 関連記事"):
            # Skip until end
            i += 1
            while i < len(lines):
                i += 1
            continue

        # Table detection
        if stripped.startswith("|") and not in_table:
            flush_list()
            in_table = True
            table_lines = [stripped]
            i += 1
            continue
        elif in_table:
            if stripped.startswith("|"):
                table_lines.append(stripped)
                i += 1
                continue
            else:
                flush_table()
                in_table = False
                continue  # Don't increment, re-process this line

        # List items
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                flush_table()
                in_list = True
            list_items.append(stripped[2:])
            i += 1
            continue
        elif in_list and stripped:
            flush_list()
            in_list = False
            continue  # Re-process line
        elif in_list and not stripped:
            flush_list()
            in_list = False
            i += 1
            continue

        # H2 heading
        if stripped.startswith("## "):
            flush_list()
            flush_table()
            h2_count += 1
            heading_text = stripped[3:].strip()
            heading_html = md_inline_to_html(escape(heading_text))
            blocks.append(f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{heading_html}</h2>\n<!-- /wp:heading -->')

            # Add image after certain h2s
            if h2_count in image_positions and img_idx < len(images):
                img_url = images[img_idx]
                img_alt = f"セイコー {title}"
                blocks.append(f'<!-- wp:image {{"width":"480px","sizeSlug":"large"}} -->\n<figure class="wp-block-image size-large is-resized"><img src="{img_url}" alt="{escape(img_alt)}" style="width:480px"/></figure>\n<!-- /wp:image -->')
                img_idx += 1

            # Add CTA button after "まとめ" section
            if "まとめ" in heading_text and not cta_added:
                # Will add CTA after the summary paragraph
                pass

            i += 1
            continue

        # H3 heading
        if stripped.startswith("### "):
            flush_list()
            flush_table()
            heading_text = stripped[4:].strip()
            heading_html = md_inline_to_html(escape(heading_text))
            blocks.append(f'<!-- wp:heading {{"level":3}} -->\n<h3 class="wp-block-heading">{heading_html}</h3>\n<!-- /wp:heading -->')
            i += 1
            continue

        # Empty line
        if not stripped:
            flush_list()
            i += 1
            continue

        # Regular paragraph
        flush_list()
        flush_table()
        para_html = md_inline_to_html(escape(stripped))
        blocks.append(f'<!-- wp:paragraph -->\n<p>{para_html}</p>\n<!-- /wp:paragraph -->')
        i += 1

    # Flush remaining
    flush_list()
    flush_table()

    # Add final CTA button
    blocks.append(f'''<!-- wp:buttons -->
<div class="wp-block-buttons"><!-- wp:button -->
<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{CTA_URL}">FIRE KIDS セイコーの商品一覧を見る</a></div>
<!-- /wp:button --></div>
<!-- /wp:buttons -->''')

    return "\n\n".join(blocks)


def generate_html(txt_filename, article_index):
    """Generate full HTML for one article"""
    txt_path = os.path.join(SEIKO_DIR, txt_filename)

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    title = extract_title(content)
    full_title = extract_full_title(title)
    meta_desc = extract_meta_description(content, title)
    keywords = extract_keywords(title, content)

    slug = make_slug(txt_filename)
    canonical_url = f"https://m.firekids.jp/seiko-{slug.replace('_', '-')}"

    # Pick 3 images for this article (rotate through the pool)
    img_start = (article_index * 3) % len(SEIKO_IMAGES)
    article_images = []
    for j in range(3):
        article_images.append(SEIKO_IMAGES[(img_start + j) % len(SEIKO_IMAGES)])

    og_image = article_images[0]

    # Extract FAQs
    faqs = extract_faq(content)

    # Short description for OG
    og_desc = meta_desc[:120]
    if len(meta_desc) > 120:
        last_period = og_desc.rfind("。")
        if last_period > 60:
            og_desc = og_desc[:last_period + 1]

    # Build meta comment block
    meta_block = f"""<!--
■ 基本メタ情報
title: {full_title}
meta_description: {meta_desc}
meta_keywords: {', '.join(keywords)}
canonical_url: {canonical_url}

■ Open Graph（SNSシェア用）
og:title: {full_title}
og:description: {og_desc}
og:type: article
og:url: {canonical_url}
og:image: {og_image}
og:site_name: FIRE KIDS Magazine
og:locale: ja_JP

■ Twitter Card
twitter:card: summary_large_image
twitter:title: {title}
twitter:description: {og_desc}
twitter:image: {og_image}
-->"""

    # Build Article JSON-LD
    article_jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": meta_desc,
        "image": og_image,
        "author": {
            "@type": "Organization",
            "name": "FIRE KIDS",
            "url": "https://firekids.jp/"
        },
        "publisher": {
            "@type": "Organization",
            "name": "FIRE KIDS Magazine",
            "url": "https://m.firekids.jp/",
            "logo": {
                "@type": "ImageObject",
                "url": "https://m.firekids.jp/logo.png"
            }
        },
        "datePublished": DATE_PUBLISHED,
        "dateModified": DATE_PUBLISHED,
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        },
        "keywords": keywords,
        "articleSection": "セイコー",
        "inLanguage": "ja"
    }

    article_ld = json.dumps(article_jsonld, ensure_ascii=False, indent=2)

    # Build FAQPage JSON-LD
    faq_ld_block = ""
    if faqs:
        faq_jsonld = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": []
        }
        for faq in faqs:
            faq_jsonld["mainEntity"].append({
                "@type": "Question",
                "name": faq["q"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["a"]
                }
            })
        faq_ld = json.dumps(faq_jsonld, ensure_ascii=False, indent=2)
        faq_ld_block = f"""
<!-- wp:html -->
<script type="application/ld+json">
{faq_ld}
</script>
<!-- /wp:html -->"""

    # Convert body
    body_html = convert_md_to_gutenberg(content, article_images, title)

    # Assemble
    full_html = f"""{meta_block}

<!-- wp:html -->
<script type="application/ld+json">
{article_ld}
</script>
<!-- /wp:html -->
{faq_ld_block}

{body_html}"""

    return full_html


def main():
    os.makedirs(SEIKO_DIR, exist_ok=True)

    for idx, txt_file in enumerate(ARTICLES):
        txt_path = os.path.join(SEIKO_DIR, txt_file)
        if not os.path.exists(txt_path):
            print(f"SKIP (not found): {txt_file}")
            continue

        html_filename = txt_file.replace(".txt", ".html")
        html_path = os.path.join(SEIKO_DIR, html_filename)

        try:
            html_content = generate_html(txt_file, idx)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"OK: {html_filename}")
        except Exception as e:
            print(f"ERROR: {txt_file} -> {e}")


if __name__ == "__main__":
    main()
