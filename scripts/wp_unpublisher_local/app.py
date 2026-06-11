"""
WordPress 記事 非公開化ローカルツール
- URLを貼り付けて、WP REST API経由で記事を private/draft に変更する
- .env は wp_uploader_local/ の .env を共有可（パス指定）
"""
import os
import sys
from urllib.parse import urlparse, unquote
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import requests

# .env: wp_uploader_local 側を優先で読む（既存の認証情報を共有）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ENV = os.path.join(SCRIPT_DIR, '.env')
SHARED_ENV = os.path.join(os.path.dirname(SCRIPT_DIR), 'wp_uploader_local', '.env')

ENV_LOADED_FROM = None
for path in [LOCAL_ENV, SHARED_ENV]:
    if os.path.exists(path):
        loaded = load_dotenv(path, override=True)
        print(f'[env] try load: {path} → loaded={loaded}', file=sys.stderr)
        if loaded:
            ENV_LOADED_FROM = path
            break

# wp_uploader_local の .env と互換: WP_BASE_URL / WP_USER / WP_APP_PASSWORD
WP_API_URL = (os.getenv('WP_API_URL') or os.getenv('WP_BASE_URL') or '').rstrip('/')
WP_USERNAME = os.getenv('WP_USERNAME') or os.getenv('WP_USER') or ''
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD', '')

print(f'[env] source: {ENV_LOADED_FROM or "(none)"}', file=sys.stderr)
print(f'[env] WP_API_URL set: {bool(WP_API_URL)}', file=sys.stderr)
print(f'[env] WP_USERNAME set: {bool(WP_USERNAME)}', file=sys.stderr)
print(f'[env] WP_APP_PASSWORD set: {bool(WP_APP_PASSWORD)}', file=sys.stderr)

app = Flask(__name__)


def auth():
    return (WP_USERNAME, WP_APP_PASSWORD)


def find_post_by_url(url: str):
    """URLから投稿を検索。slugベースでヒットさせる。"""
    parsed = urlparse(url)
    path = unquote(parsed.path).strip('/')
    segments = [s for s in path.split('/') if s]
    if not segments:
        return None, 'URLからスラッグを抽出できませんでした'
    slug = segments[-1]

    # まず slug で検索
    r = requests.get(f'{WP_API_URL}/wp-json/wp/v2/posts',
                     params={'slug': slug, 'status': 'publish,private,draft,future,pending'},
                     auth=auth(), timeout=20)
    if r.status_code == 200 and r.json():
        return r.json()[0], None

    # 数字なら直接 ID として叩く
    if slug.isdigit():
        r = requests.get(f'{WP_API_URL}/wp-json/wp/v2/posts/{slug}',
                         auth=auth(), timeout=20)
        if r.status_code == 200:
            return r.json(), None

    # 上記でヒットしなければ search で広く検索（カテゴリ別パスがある場合の保険）
    r = requests.get(f'{WP_API_URL}/wp-json/wp/v2/posts',
                     params={'search': slug, 'per_page': 5,
                             'status': 'publish,private,draft,future,pending'},
                     auth=auth(), timeout=20)
    if r.status_code == 200 and r.json():
        # slugが完全一致するものを優先
        for p in r.json():
            if p.get('slug') == slug:
                return p, None
        return r.json()[0], None

    return None, f'記事が見つかりません (slug={slug})'


def update_status(post_id: int, status: str):
    """status: 'private' or 'draft'"""
    r = requests.post(f'{WP_API_URL}/wp-json/wp/v2/posts/{post_id}',
                      json={'status': status},
                      auth=auth(), timeout=30)
    if r.status_code in (200, 201):
        return r.json(), None
    return None, f'HTTP {r.status_code}: {r.text[:200]}'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    if not WP_API_URL or not WP_USERNAME or not WP_APP_PASSWORD:
        return jsonify({'ok': False, 'error': '.envが設定されていません (WP_API_URL/WP_USERNAME/WP_APP_PASSWORD)'}), 500
    try:
        r = requests.get(f'{WP_API_URL}/wp-json/wp/v2/users/me', auth=auth(), timeout=10)
        if r.status_code == 200:
            u = r.json()
            return jsonify({'ok': True, 'site': WP_API_URL, 'user': u.get('name')})
        return jsonify({'ok': False, 'error': f'認証NG ({r.status_code}): {r.text[:200]}'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/unpublish', methods=['POST'])
def unpublish():
    data = request.get_json(force=True)
    urls = data.get('urls') or []
    target_status = data.get('status', 'private')
    if target_status not in ('private', 'draft'):
        return jsonify({'error': 'invalid status'}), 400

    results = []
    for url in urls:
        url = url.strip()
        if not url:
            continue
        post, err = find_post_by_url(url)
        if err:
            results.append({'url': url, 'ok': False, 'message': err})
            continue
        post_id = post['id']
        title = post.get('title', {}).get('rendered', '')
        before_status = post.get('status')
        if before_status == target_status:
            results.append({'url': url, 'ok': True, 'id': post_id, 'title': title,
                            'before': before_status, 'after': target_status,
                            'message': '変更不要（既に対象ステータス）'})
            continue
        updated, err = update_status(post_id, target_status)
        if err:
            results.append({'url': url, 'ok': False, 'id': post_id, 'title': title,
                            'before': before_status, 'message': err})
            continue
        results.append({'url': url, 'ok': True, 'id': post_id, 'title': title,
                        'before': before_status, 'after': updated.get('status'),
                        'message': '完了'})
    return jsonify({'results': results})


if __name__ == '__main__':
    port = int(os.getenv('UNPUBLISHER_PORT', 8001))
    print(f'WP Unpublisher 起動: http://localhost:{port}')
    print(f'  WP_API_URL: {WP_API_URL}')
    print(f'  WP_USERNAME: {WP_USERNAME}')
    print(f'  .env source: {LOCAL_ENV if os.path.exists(LOCAL_ENV) else SHARED_ENV if os.path.exists(SHARED_ENV) else "(none)"}')
    app.run(host='127.0.0.1', port=port, debug=False)
