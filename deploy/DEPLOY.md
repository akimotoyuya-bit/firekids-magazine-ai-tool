# FIRE KIDS Magazine Tool - Deploy Guide

AWS App Runner へデプロイする手順です。

## デプロイ先URL（本番）

| 用途 | URL |
|------|-----|
| トップ | https://s5d6hqidtk.us-east-1.awsapprunner.com/ |
| 記事生成 | https://s5d6hqidtk.us-east-1.awsapprunner.com/generator/ |
| WP投稿 | https://s5d6hqidtk.us-east-1.awsapprunner.com/upload/ |

ログイン: `deploy/env.production` の `APP_USER` / `APP_PASSWORD`（Basic認証）

## 前提

- Docker Desktop 起動済み
- AWS CLI 設定済み（`aws sts get-caller-identity` が通る）
- 以下の `.env` が設定済み:
  - `deploy/env.production` … APP_USER / APP_PASSWORD
  - `scripts/article_generator/.env` … AWS Bedrock キー
  - `scripts/wp_uploader_local/.env` … WordPress 認証

## 初回・更新デプロイ

```powershell
cd C:\Users\goto_\FirekidsMagazine-main
python deploy\deploy.py
```

スクリプトが自動で行うこと:

1. ECR リポジトリ作成（なければ）
2. Docker イメージビルド & ECR プッシュ
3. App Runner サービス作成 or 更新
4. デプロイ完了まで待機（約5〜10分）

## ローカルで本番同等環境を試す

```powershell
docker build -t firekids-magazine-tool .
docker run -p 8080:8080 --env-file deploy\env.production --env-file scripts\article_generator\.env --env-file scripts\wp_uploader_local\.env firekids-magazine-tool
# http://localhost:8080
```

## 注意事項

- **認証**: 本番URLはインターネット公開です。`APP_PASSWORD` は必ず強力なものに変更してください。
- **記事保存**: App Runner のディスクは一時的です。生成記事はローカルにダウンロード・確認してから使ってください。
- **秘密情報**: `.env` ファイルは Git にコミットしないでください。
- **再デプロイ**: コード変更後は `python deploy\deploy.py` を再実行するだけでOKです。

## アーキテクチャ

```
ブラウザ
  └─ AWS App Runner (us-east-1)
       ├─ /              ポータル（トップ）
       ├─ /generator/    記事生成（Bedrock Claude）
       └─ /upload/       WP投稿アップローダー
```
