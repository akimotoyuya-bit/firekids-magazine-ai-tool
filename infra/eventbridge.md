# EventBridge スケジュール設定メモ

## 概要

画像クローラー Lambda を毎日 JST 04:00（UTC 19:00）に起動する EventBridge ルール。

## スケジュール式

```
cron(0 19 * * ? *)
```

- UTC 19:00 = JST 04:00（翌日）
- 毎日実行

## AWS コンソールでの設定手順

1. **AWS コンソール** → **EventBridge** → **スケジュール** → 「スケジュールを作成」
2. **スケジュール名**: `firekids-image-crawler-daily`
3. **スケジュールパターン**: 定期的なスケジュール → cron 式 → `0 19 * * ? *`
4. **ターゲット**: Lambda 関数 → `firekids-image-crawler`（Lambda デプロイ後に設定）
5. **入力**: 定数（JSON）を選択し、以下を指定（省略可）:
   ```json
   {"max_pages": 200, "dry_run": false}
   ```
6. **実行ロール**: EventBridge がターゲット Lambda を起動できるロールを選択または新規作成

## Lambda 設定推奨値

| 項目 | 値 |
|---|---|
| タイムアウト | 15 分（全件巡回 + 画像 DL の合計） |
| メモリ | 512 MB |
| ランタイム | Python 3.12 |
| ハンドラー | handler.handler |

## IAM 権限（Lambda 実行ロール）

最小権限として以下を付与：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:HeadObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::firekids-magazine-generator-apne1-prod",
        "arn:aws:s3:::firekids-magazine-generator-apne1-prod/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

## Lambda デプロイ手順（初回）

```bash
# Lambda 用パッケージを作成
cd lambda
pip install -r requirements.txt -t ./package
cp ../scripts/article_generator/image_crawler.py ./package/
cp ../scripts/article_generator/image_store.py ./package/
cp ../scripts/article_generator/inventory.py ./package/
cp handler.py ./package/

# ZIP 化
cd package
zip -r ../function.zip .

# AWS CLI でデプロイ
aws lambda create-function \
  --function-name firekids-image-crawler \
  --runtime python3.12 \
  --handler handler.handler \
  --zip-file fileb://../function.zip \
  --role arn:aws:iam::{ACCOUNT_ID}:role/firekids-lambda-role \
  --timeout 900 \
  --memory-size 512 \
  --environment Variables="{
    S3_BUCKET=firekids-magazine-generator-apne1-prod,
    S3_REGION=ap-northeast-1,
    AWS_ACCESS_KEY_ID=...,
    AWS_SECRET_ACCESS_KEY=...
  }"
```

## 初回手動実行（全件ベース作成）

Lambda デプロイ前に、ローカルで全件クロールを実行してベースを作成する：

```bash
# 1. クロール（全件）
python scripts/article_generator/image_crawler.py
# → data/fk_image_index_raw.json が生成される

# 2. S3 同期
python scripts/article_generator/image_store.py
# → S3 に画像をアップロードし、data/fk_image_index.json を更新

# 3. マッチ率を確認
# クロール終了時に FK マッチ率レポートが表示される
```

## 失敗時の通知（任意）

EventBridge ルールの失敗通知は CloudWatch Alarm または SNS で設定：

1. CloudWatch → アラーム → Lambda の `Errors` メトリクスを監視
2. SNS トピックに通知 → メール or Slack Webhook

## 参考リンク

- [EventBridge スケジュール cron 式リファレンス](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-scheduled-rule-pattern.html)
- [Lambda 環境変数](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html)
