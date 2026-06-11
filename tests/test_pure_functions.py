"""純粋関数のスナップショットテスト（Phase 0 安全網）。

現状の出力をそのまま正解とする。仕様の正しさは問わない。
リファクタリング後もこのテストがグリーンであれば挙動が保存されている。
"""
import json
from pathlib import Path

import pytest

import app

SNAPSHOTS = json.loads((Path(__file__).parent / "_snapshots.json").read_text(encoding="utf-8"))


# ─── title_to_slug ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,expected", list(SNAPSHOTS["title_to_slug"].items()))
def test_title_to_slug(title, expected):
    assert app.title_to_slug(title) == expected


# ─── markdown_to_wp_html ─────────────────────────────────────────────────────

MD_SAMPLE = """# タイトル行

## 見出し2

これは段落です。**強調**と[リンク](https://example.com)を含みます。

- 箇条書き1
- 箇条書き2

1. 番号付き1
2. 番号付き2

| モデル | 年代 |
|---|---|
| 62GS | 1967 |
| 44GS | 1968 |

---

### 見出し3

最後の段落。
"""


def test_markdown_to_wp_html_snapshot():
    assert app.markdown_to_wp_html(MD_SAMPLE) == SNAPSHOTS["markdown_to_wp_html"]


def test_markdown_to_wp_html_table_is_gutenberg_block():
    html = app.markdown_to_wp_html(MD_SAMPLE)
    assert '<!-- wp:table {"hasFixedLayout":true,"className":"is-style-stripes"} -->' in html
    assert "<!-- /wp:table -->" in html


# ─── strip_tags ──────────────────────────────────────────────────────────────

def test_strip_tags_snapshot():
    src = '<p>Hello &amp; <b>world</b></p>\n<div>second &nbsp; line &#8211; dash</div>'
    assert app.strip_tags(src) == SNAPSHOTS["strip_tags"]


# ─── extract_h2_sections ─────────────────────────────────────────────────────

def test_extract_h2_sections_snapshot():
    src = (
        "<p>intro</p><h2>First Heading</h2><p>body one text</p>"
        "<h2><span>Second</span> Heading</h2><p>body two text</p><h2></h2><p>skipped</p>"
    )
    assert app.extract_h2_sections(src) == SNAPSHOTS["extract_h2_sections"]


# ─── cosine ──────────────────────────────────────────────────────────────────

def test_cosine_snapshot():
    values = [
        app.cosine([1, 0, 0], [1, 0, 0]),
        app.cosine([1, 2, 3], [4, 5, 6]),
        app.cosine(None, [1]),
        app.cosine([1], [1, 2]),
        app.cosine([0, 0], [0, 0]),
    ]
    assert values == pytest.approx(SNAPSHOTS["cosine"])


# ─── check_ngram_overlap ─────────────────────────────────────────────────────

def test_check_ngram_overlap_flags_identical_text(monkeypatch):
    body = "ヴィンテージロレックスの魅力は経年変化したダイヤルにあります。" * 5
    records = [
        {"title": "過去記事A", "url": "https://example.com/a", "body_snippet": body},
        {"title": "過去記事B", "url": "https://example.com/b", "body_snippet": "全く別の内容です。" * 10},
    ]
    monkeypatch.setattr(app, "_prioritized_cached_records", lambda *a, **k: records)

    flagged = app.check_ngram_overlap(body, "ROLEX")
    assert len(flagged) == 1
    assert flagged[0]["title"] == "過去記事A"
    assert flagged[0]["ngram_overlap"] == 1.0


def test_check_ngram_overlap_empty_input(monkeypatch):
    monkeypatch.setattr(app, "_prioritized_cached_records", lambda *a, **k: [])
    assert app.check_ngram_overlap("", "ROLEX") == []
