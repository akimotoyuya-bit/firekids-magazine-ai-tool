"""FIRE KIDS Magazine 統合ポータル（トップページ）"""
from flask import Flask

portal = Flask(__name__)


@portal.route("/")
def home():
    return """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>FIRE KIDS Magazine Tools</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 60px auto; padding: 0 20px; color: #1a1a1a; }
  h1 { font-size: 22px; border-left: 4px solid #1a1a1a; padding-left: 14px; }
  .cards { display: grid; gap: 16px; margin-top: 32px; }
  a.card { display: block; padding: 24px; border: 1px solid #e8e4de; border-radius: 4px;
    text-decoration: none; color: inherit; background: #fafafa; }
  a.card:hover { border-color: #1a1a1a; background: #f7f5f2; }
  a.card h2 { margin: 0 0 8px; font-size: 17px; }
  a.card p { margin: 0; font-size: 13px; color: #5a5248; line-height: 1.7; }
</style>
</head>
<body>
<h1>FIRE KIDS Magazine Tools</h1>
<p style="color:#5a5248;font-size:14px;">記事生成 → 確認 → WordPress投稿</p>
<div class="cards">
  <a class="card" href="/generator/">
    <h2>📝 記事生成（AWS Bedrock）</h2>
    <p>テーマを入力してClaudeでSEO記事を生成。TXTとして保存。</p>
  </a>
  <a class="card" href="/upload/">
    <h2>📤 WP投稿アップローダー</h2>
    <p>HTMLファイルを読み込み、m.firekids.jp へ予約投稿。</p>
  </a>
</div>
</body>
</html>"""
