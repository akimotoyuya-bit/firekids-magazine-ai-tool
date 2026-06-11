# Flask ルート一覧（scripts/article_generator/app.py）

Phase 0 時点（commit 3fa7db8 直後）の全ルート。リファクタリング後にこの一覧と完全一致すること。

## フック

| 種別 | 関数 |
|---|---|
| `@app.before_request` | `_require_login` |

## ルート

| URL | メソッド | 関数 |
|---|---|---|
| `/` | GET | `index` |
| `/generate` | POST | `generate` |
| `/generate-status/<job_id>` | GET | `generate_status` |
| `/inventory-items` | GET | `inventory_items` |
| `/upload-inventory` | POST | `upload_inventory` |
| `/save` | POST | `save` |
| `/scan` | POST | `scan` |
| `/patch-categories` | POST | `patch_categories` |
| `/scan-status` | GET | `scan_status` |
| `/save-draft` | POST | `save_draft` |
| `/drafts` | GET | `drafts` |
| `/delete-draft` | POST | `delete_draft` |
| `/upload-article-image` | POST | `upload_article_image` |
| `/update-draft-image` | POST | `update_draft_image` |
| `/log-post` | POST | `log_post` |
| `/posts-log` | GET | `posts_log` |
| `/image-proxy` | GET | `image_proxy` |
| `/draft-content/<brand>/<filename>` | GET | `draft_content` |
| `/ping` | GET | `ping` |

合計: 19 ルート + before_request 1 件
