"""現状の純粋関数出力を取得してスナップショットテストの正解値を生成する（一時スクリプト）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "article_generator"))

import app  # noqa: E402

results = {}

results["title_to_slug"] = {
    t: app.title_to_slug(t)
    for t in [
        "ロレックス サブマリーナーとはどんな時計？初心者が知っておくべき基礎知識",
        "「シチズンって渋すぎる」と笑っていた私が、1972年製クロノグラフに心を折られた話",
        "Grand Seiko 62GS 1967 Review!!",
        "オメガ スピードマスター 3選",
        "",
    ]
}

md_sample = """# タイトル行

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
results["markdown_to_wp_html"] = app.markdown_to_wp_html(md_sample)

results["strip_tags"] = app.strip_tags(
    '<p>Hello &amp; <b>world</b></p>\n<div>second &nbsp; line &#8211; dash</div>'
)

results["extract_h2_sections"] = app.extract_h2_sections(
    "<p>intro</p><h2>First Heading</h2><p>body one text</p>"
    "<h2><span>Second</span> Heading</h2><p>body two text</p><h2></h2><p>skipped</p>"
)

results["cosine"] = [
    app.cosine([1, 0, 0], [1, 0, 0]),
    app.cosine([1, 2, 3], [4, 5, 6]),
    app.cosine(None, [1]),
    app.cosine([1], [1, 2]),
    app.cosine([0, 0], [0, 0]),
]

out = Path(__file__).parent / "_snapshots.json"
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("written", out)
