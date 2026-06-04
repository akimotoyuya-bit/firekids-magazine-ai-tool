"""Gunicorn エントリポイント（本番デプロイ用）"""
import os
import sys
from pathlib import Path

from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Request, Response

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from deploy.portal import portal
from article_generator.app import app as generator_app
from wp_uploader_local.app import app as uploader_app


class BasicAuthMiddleware:
    """本番公開時のアクセス制限（APP_USER / APP_PASSWORD 設定時のみ有効）"""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        user = os.getenv("APP_USER", "")
        pwd = os.getenv("APP_PASSWORD", "")
        if not user or not pwd:
            return self.app(environ, start_response)

        req = Request(environ)
        auth = req.authorization
        if auth and auth.username == user and auth.password == pwd:
            return self.app(environ, start_response)

        res = Response("認証が必要です", 401, mimetype="text/plain; charset=utf-8")
        res.headers["WWW-Authenticate"] = 'Basic realm="FIRE KIDS Magazine"'
        return res(environ, start_response)


application = BasicAuthMiddleware(DispatcherMiddleware(portal, {
    "/generator": generator_app,
    "/upload": uploader_app,
}))
