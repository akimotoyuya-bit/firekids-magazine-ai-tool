"""
FIRE KIDS WP投稿アップローダー（ローカルWebアプリ・最大8件一括対応）

機能:
  - HTMLファイルから自動抽出: タイトル / アイキャッチ画像 / ブランド名
  - 「｜FIRE KIDS Magazine」サフィックスは自動削除
  - カテゴリー: 「時計の基礎知識」「コラム」の2択
  - 投稿者・ライター: ファイアーキッズ編集部に固定
  - タグ: 個別入力＋ブランド名を自動付与
  - 予約投稿日時: 個別指定（空欄なら即時公開）

使い方:
  cd scripts/wp_uploader_local
  pip3 install -r requirements.txt
  cp .env.example .env  # WP認証情報を設定
  python3 app.py
  # ブラウザで http://localhost:8000
"""
import os
import re
import json
from flask import Flask, render_template, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024  # 80MB


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return jsonify({'error': f'サーバーエラー: {str(e)}', 'type': type(e).__name__}), 500

WP_BASE_URL = os.getenv('WP_BASE_URL', 'https://m.firekids.jp').rstrip('/')
WP_USER = os.getenv('WP_USER', '')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD', '')

MAX_FILES = 8
WRITER_NAME_KEYWORD = '編集部'  # 投稿者ユーザー検索キーワード

# ブランド名マッピング（記事から検出するキーワード）
BRAND_KEYWORDS = [
    ('ロレックス', 'ロレックス'),
    ('ROLEX', 'ロレックス'),
    ('オメガ', 'オメガ'),
    ('OMEGA', 'オメガ'),
    ('セイコー', 'セイコー'),
    ('SEIKO', 'セイコー'),
    ('シチズン', 'シチズン'),
    ('CITIZEN', 'シチズン'),
    ('ロンジン', 'ロンジン'),
    ('LONGINES', 'ロンジン'),
    ('ブライトリング', 'ブライトリング'),
    ('BREITLING', 'ブライトリング'),
    ('チューダー', 'チューダー'),
    ('TUDOR', 'チューダー'),
    ('カルティエ', 'カルティエ'),
    ('CARTIER', 'カルティエ'),
    ('オリエント', 'オリエント'),
    ('ORIENT', 'オリエント'),
    ('ジャガー・ルクルト', 'ジャガー・ルクルト'),
    ('ジャガールクルト', 'ジャガー・ルクルト'),
    ('Jaeger-LeCoultre', 'ジャガー・ルクルト'),
    ('IWC', 'IWC'),
    ('ハミルトン', 'ハミルトン'),
    ('HAMILTON', 'ハミルトン'),
    ('ティソ', 'ティソ'),
    ('TISSOT', 'ティソ'),
    ('タグホイヤー', 'タグホイヤー'),
    ('TAG HEUER', 'タグホイヤー'),
    ('ボーム&メルシエ', 'ボーム&メルシエ'),
    ('Baume', 'ボーム&メルシエ'),
    ('オーデマピゲ', 'オーデマピゲ'),
    ('Audemars', 'オーデマピゲ'),
    ('パテックフィリップ', 'パテックフィリップ'),
    ('Patek', 'パテックフィリップ'),
    ('エルメス', 'エルメス'),
    ('Hermes', 'エルメス'),
]


# XSERVER 等の WAF は python-requests のデフォルト UA を 403 で弾くため、
# ブラウザ相当の User-Agent を全 WP リクエストに付与する。
WP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}


def get_auth():
    # Application Password のスペースを除去（requests の latin-1 制限を回避）
    password = WP_APP_PASSWORD.replace(' ', '')
    return (WP_USER, password)


def clean_title(title):
    """『｜FIRE KIDS Magazine』サフィックスを除去"""
    return re.sub(r'\s*[｜|]\s*FIRE\s*KIDS\s*Magazine\s*$', '', title, flags=re.IGNORECASE).strip()


def extract_title(html_content):
    """HTMLメタコメントから title: を抽出（｜FIRE KIDS Magazine除去）"""
    match = re.search(r'^title:\s*(.+?)$', html_content, re.MULTILINE)
    if match:
        return clean_title(match.group(1).strip())
    match = re.search(r'<h1[^>]*>(.+?)</h1>', html_content, re.DOTALL)
    if match:
        return clean_title(re.sub(r'<[^>]+>', '', match.group(1)).strip())
    return ''


def extract_featured_image_url(html_content):
    """HTMLから アイキャッチ画像URL を抽出（og:image優先、次に最初の<img>）"""
    m = re.search(r'^og:image:\s*(https?://\S+)', html_content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
    if m:
        return m.group(1).strip()
    return None


def extract_brand(html_content):
    """記事からブランド名を抽出（JSON-LD about配列優先、フォールバックでキーワード検索）"""
    # JSON-LD aboutの最初のBrandエンティティ
    about_match = re.search(r'"about"\s*:\s*\[(.*?)\](?=\s*[,}])', html_content, re.DOTALL)
    if about_match:
        block = about_match.group(1)
        brand_match = re.search(r'"@type"\s*:\s*"Brand"\s*,\s*"name"\s*:\s*"([^"]+)"', block)
        if brand_match:
            return brand_match.group(1).strip()
    # キーワード検索（タイトル/冒頭500文字）
    title_region = html_content[:1500]
    for keyword, brand in BRAND_KEYWORDS:
        if keyword in title_region:
            return brand
    return None


def get_or_create_tag(name):
    try:
        r = requests.get(
            f'{WP_BASE_URL}/wp-json/wp/v2/tags',
            params={'search': name, 'per_page': 100},
            auth=get_auth(),
            headers=WP_HEADERS,
            timeout=15,
        )
        if r.ok:
            for t in r.json():
                if t['name'] == name:
                    return t['id']
        r = requests.post(
            f'{WP_BASE_URL}/wp-json/wp/v2/tags',
            json={'name': name},
            auth=get_auth(),
            headers=WP_HEADERS,
            timeout=15,
        )
        if r.ok:
            return r.json()['id']
        if r.status_code == 400:
            try:
                existing = r.json().get('data', {}).get('term_id')
                if existing:
                    return existing
            except Exception:
                pass
    except Exception as e:
        print(f'get_or_create_tag error ({name}): {e}')
    return None


def get_category_id_by_name(name):
    """カテゴリ名から ID を取得（完全一致）"""
    try:
        r = requests.get(
            f'{WP_BASE_URL}/wp-json/wp/v2/categories',
            params={'search': name, 'per_page': 100},
            auth=get_auth(),
            headers=WP_HEADERS,
            timeout=15,
        )
        if r.ok:
            for c in r.json():
                if c['name'] == name:
                    return c['id']
    except Exception as e:
        print(f'get_category_id_by_name error ({name}): {e}')
    return None


def get_writer_user_id():
    """『編集部』を含むWPユーザーのIDを取得（ライター固定）"""
    try:
        r = requests.get(
            f'{WP_BASE_URL}/wp-json/wp/v2/users',
            params={'per_page': 100, 'context': 'edit'},
            auth=get_auth(),
            headers=WP_HEADERS,
            timeout=15,
        )
        if r.ok:
            for u in r.json():
                if WRITER_NAME_KEYWORD in u.get('name', ''):
                    return u['id']
    except Exception as e:
        print(f'get_writer_user_id error: {e}')
    return None


def upload_media_from_url(image_url):
    """画像URLからダウンロードしてWPメディアにアップロード、IDを返す"""
    try:
        img_resp = requests.get(image_url, headers=WP_HEADERS, timeout=30)
        if not img_resp.ok:
            return None
        filename = image_url.split('/')[-1].split('?')[0]
        if not filename:
            filename = 'featured.jpg'
        headers = {
            **WP_HEADERS,
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': img_resp.headers.get('Content-Type', 'image/jpeg'),
        }
        r = requests.post(
            f'{WP_BASE_URL}/wp-json/wp/v2/media',
            data=img_resp.content,
            headers=headers,
            auth=get_auth(),
            timeout=60,
        )
        if r.ok:
            return r.json().get('id')
    except Exception as e:
        print(f'media upload error: {e}')
    return None


def post_one(title, content, tags_input, brand, featured_image_url, category_name, schedule, author_id, status=None):
    if not title:
        return {'success': False, 'error': 'タイトルが空です'}
    if not content:
        return {'success': False, 'error': 'HTML本文が空です'}

    # タグ処理（ユーザー入力＋ブランド自動付与）
    tag_ids = []
    tag_names = []
    if tags_input:
        tag_names = [t.strip() for t in re.split(r'[,、，]', tags_input) if t.strip()]
    if brand and brand not in tag_names:
        tag_names.append(brand)
    for name in tag_names:
        tag_id = get_or_create_tag(name)
        if tag_id:
            tag_ids.append(tag_id)

    # カテゴリー
    category_ids = []
    if category_name:
        cat_id = get_category_id_by_name(category_name)
        if cat_id:
            category_ids.append(cat_id)

    # アイキャッチ画像アップロード
    featured_media_id = None
    if featured_image_url:
        featured_media_id = upload_media_from_url(featured_image_url)

    post_data = {
        'title': title,
        'content': content,
        'tags': tag_ids,
    }
    if category_ids:
        post_data['categories'] = category_ids
    if featured_media_id:
        post_data['featured_media'] = featured_media_id
    if author_id:
        post_data['author'] = author_id

    # ステータス決定: 明示指定（publish/future/draft）を優先。
    # 未指定時は従来通り schedule があれば future、なければ publish。
    if status == 'draft':
        post_data['status'] = 'draft'
    elif status == 'future' or (status is None and schedule):
        post_data['status'] = 'future'
        if schedule:
            post_data['date'] = schedule
    else:
        post_data['status'] = 'publish'

    # メタフィールド（writer = 編集部）— テーマ側で登録されている場合のみ反映
    post_data['meta'] = {'writer': '編集部'}

    r = requests.post(
        f'{WP_BASE_URL}/wp-json/wp/v2/posts',
        json=post_data,
        auth=get_auth(),
        headers=WP_HEADERS,
        timeout=30,
    )
    if r.ok:
        post = r.json()
        return {
            'success': True,
            'id': post['id'],
            'link': post.get('link', ''),
            'status': post.get('status', ''),
            'date': post.get('date', ''),
            'featured_media_id': featured_media_id,
            'category_id': category_ids[0] if category_ids else None,
            'brand': brand,
        }
    try:
        err = r.json()
    except Exception:
        err = {'message': r.text}
    return {'success': False, 'error': err}


@app.route('/')
def index():
    return render_template('index.html', max_files=MAX_FILES)


@app.route('/parse', methods=['POST'])
def parse():
    files = request.files.getlist('html_files')
    if not files:
        return jsonify({'error': 'HTMLファイルがアップロードされていません'}), 400
    if len(files) > MAX_FILES:
        return jsonify({'error': f'一度にアップロードできるのは{MAX_FILES}件までです'}), 400

    parsed = []
    for f in files:
        try:
            content = f.read().decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({'error': f'{f.filename}: UTF-8で読み込めません'}), 400
        parsed.append({
            'filename': f.filename,
            'title': extract_title(content),
            'content': content,
            'brand': extract_brand(content),
            'featured_image_url': extract_featured_image_url(content),
        })
    return jsonify({'files': parsed})


@app.route('/parse-text', methods=['POST'])
def parse_text():
    """テキスト貼り付けモード用。JSON で複数HTMLを受け取る"""
    data = request.get_json(silent=True) or {}
    htmls = data.get('htmls', [])

    # 空でないものだけ処理
    htmls = [h for h in htmls if (h.get('content') or '').strip()]

    if not htmls:
        return jsonify({'error': 'HTMLが入力されていません'}), 400
    if len(htmls) > MAX_FILES:
        return jsonify({'error': f'一度に処理できるのは{MAX_FILES}件までです'}), 400

    parsed = []
    for i, h in enumerate(htmls, start=1):
        content = h.get('content', '')
        filename = h.get('filename') or f'paste_{i}.html'
        parsed.append({
            'filename': filename,
            'title': extract_title(content),
            'content': content,
            'brand': extract_brand(content),
            'featured_image_url': extract_featured_image_url(content),
        })
    return jsonify({'files': parsed})


@app.route('/publish', methods=['POST'])
def publish():
    try:
        data = request.get_json(silent=True) or {}
        posts = data.get('posts', [])

        if not posts:
            return jsonify({'error': '投稿データがありません'}), 400
        if len(posts) > MAX_FILES:
            return jsonify({'error': f'一度に投稿できるのは{MAX_FILES}件までです'}), 400

        author_id = get_writer_user_id()

        results = []
        for p in posts:
            filename = p.get('filename', '(no filename)')
            try:
                result = post_one(
                    title=clean_title((p.get('title') or '').strip()),
                    content=p.get('content') or '',
                    tags_input=p.get('tags', ''),
                    brand=p.get('brand'),
                    featured_image_url=p.get('featured_image_url'),
                    category_name=p.get('category'),
                    schedule=p.get('schedule'),
                    author_id=author_id,
                    status=p.get('status'),
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                result = {'success': False, 'error': f'post_one例外: {str(e)}'}
            result['filename'] = filename
            results.append(result)

        success_count = sum(1 for r in results if r.get('success'))
        return jsonify({
            'total': len(results),
            'success_count': success_count,
            'fail_count': len(results) - success_count,
            'results': results,
            'writer_id': author_id,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'publish例外: {str(e)}', 'results': []}), 500


@app.route('/upload-media', methods=['POST'])
def upload_media():
    """記事生成ツールから画像URLを受け取りWPメディアにアップロードする。
    Request JSON: { "image_url": "https://...", "alt": "商品名" }
    Response JSON: { "media_id": 123, "url": "https://wp.../wp-content/..." }
    """
    data = request.get_json(silent=True) or {}
    image_url = (data.get('image_url') or '').strip()
    alt = (data.get('alt') or '').strip()

    if not image_url:
        return jsonify({'error': 'image_url が指定されていません'}), 400

    try:
        img_resp = requests.get(image_url, headers=WP_HEADERS, timeout=30)
        if not img_resp.ok:
            return jsonify({'error': f'画像取得失敗 HTTP {img_resp.status_code}'}), 502

        filename = image_url.split('/')[-1].split('?')[0] or 'image.jpg'
        content_type = img_resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()

        headers = {
            **WP_HEADERS,
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': content_type,
        }
        r = requests.post(
            f'{WP_BASE_URL}/wp-json/wp/v2/media',
            data=img_resp.content,
            headers=headers,
            auth=get_auth(),
            timeout=60,
        )
        if r.ok:
            media = r.json()
            media_id = media.get('id')
            media_url = media.get('source_url') or media.get('guid', {}).get('rendered', '')
            # alt テキストを設定
            if alt and media_id:
                requests.post(
                    f'{WP_BASE_URL}/wp-json/wp/v2/media/{media_id}',
                    json={'alt_text': alt},
                    auth=get_auth(),
                    headers=WP_HEADERS,
                    timeout=15,
                )
            return jsonify({'media_id': media_id, 'url': media_url})
        try:
            err_detail = r.json().get('message', r.text[:200])
        except Exception:
            err_detail = r.text[:200]
        return jsonify({'error': f'WPメディアアップロード失敗: {err_detail}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/ping')
def ping():
    return jsonify({'pong': True, 'user': os.getenv('WP_USER', ''), 'pw_len': len(os.getenv('WP_APP_PASSWORD', '').replace(' ', ''))})


@app.route('/health')
def health():
    user = os.getenv('WP_USER', '')
    pw = os.getenv('WP_APP_PASSWORD', '').replace(' ', '')
    base = os.getenv('WP_BASE_URL', 'https://m.firekids.jp').rstrip('/')
    if not user or not pw:
        return jsonify({'ok': False, 'error': '.envにWP_USER/WP_APP_PASSWORDを設定してください'})
    try:
        r = requests.get(f'{base}/wp-json/wp/v2/users/me', auth=(user, pw), headers=WP_HEADERS, timeout=15)
        if r.ok:
            u = r.json()
            try:
                writer_id = get_writer_user_id()
            except Exception:
                writer_id = None
            return jsonify({
                'ok': True,
                'user': u.get('name'),
                'id': u.get('id'),
                'writer_user_id': writer_id,
                'writer_user_found': writer_id is not None,
            })
        return jsonify({'ok': False, 'status': r.status_code, 'error': r.text[:200]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, port=8000, host='127.0.0.1', use_reloader=debug_mode)
