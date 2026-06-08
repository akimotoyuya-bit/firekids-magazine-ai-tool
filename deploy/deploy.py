#!/usr/bin/env python3
"""Deploy FIRE KIDS Magazine Tool to AWS App Runner + Vercel."""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-1"
SERVICE_NAME = "firekids-magazine-tool"
REPO_NAME = "firekids-magazine-tool"
ROLE_NAME = "AppRunnerECRAccessRole-FK"
# App Runner が latest タグだと古いイメージを使い続けることがあるため
# デプロイ毎にユニークなタグを付け、それを ImageIdentifier に使う
IMAGE_TAG = datetime.now().strftime("%Y%m%d-%H%M%S")


def load_env_files() -> dict:
    env = {}
    for path in [
        ROOT / "deploy" / "env.production",
        ROOT / "scripts" / "article_generator" / ".env",
        ROOT / "scripts" / "wp_uploader_local" / ".env",
    ]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def file_uri(p: Path) -> str:
    return "file://" + str(p.resolve()).replace("\\", "/")


# 実シークレット（RuntimeEnvironmentVariables 等）を含む設定 JSON は
# リポジトリ直下に残さない。システムの一時ディレクトリに書き、実行後に削除する。
_TEMP_FILES: list[Path] = []


def write_temp_json(data: dict, label: str) -> Path:
    fd, name = tempfile.mkstemp(prefix=f"fk-{label}-", suffix=".json")
    path = Path(name)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    _TEMP_FILES.append(path)
    return path


def cleanup_temp_files() -> None:
    for p in _TEMP_FILES:
        try:
            p.unlink()
        except OSError:
            pass


def run(cmd: list[str], check=True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd[:6]), "..." if len(cmd) > 6 else "")
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def main():
    print("=== FIRE KIDS Magazine Tool Deploy ===")

    env_vars = load_env_files()
    if not env_vars.get("APP_USER") or not env_vars.get("APP_PASSWORD"):
        print("ERROR: Set APP_USER and APP_PASSWORD in deploy/env.production")
        sys.exit(1)

    account = json.loads(run(["aws", "sts", "get-caller-identity", "--output", "json"]).stdout)["Account"]
    ecr_uri = f"{account}.dkr.ecr.{REGION}.amazonaws.com/{REPO_NAME}"
    print(f"Account: {account}  Region: {REGION}")

    # ECR repo
    r = run(["aws", "ecr", "describe-repositories", "--repository-names", REPO_NAME, "--region", REGION], check=False)
    if r.returncode != 0:
        print(f"Creating ECR repository: {REPO_NAME}")
        run(["aws", "ecr", "create-repository", "--repository-name", REPO_NAME, "--region", REGION])

    # Docker build & push
    login = run(["aws", "ecr", "get-login-password", "--region", REGION])
    subprocess.run(
        ["docker", "login", "--username", "AWS", "--password-stdin", f"{account}.dkr.ecr.{REGION}.amazonaws.com"],
        input=login.stdout, text=True, check=True,
    )
    subprocess.run(["docker", "build", "--no-cache", "-t", f"{REPO_NAME}:latest", str(ROOT)], check=True)
    subprocess.run(["docker", "tag", f"{REPO_NAME}:latest", f"{ecr_uri}:{IMAGE_TAG}"], check=True)
    subprocess.run(["docker", "tag", f"{REPO_NAME}:latest", f"{ecr_uri}:latest"], check=True)
    subprocess.run(["docker", "push", f"{ecr_uri}:{IMAGE_TAG}"], check=True)
    subprocess.run(["docker", "push", f"{ecr_uri}:latest"], check=True)
    print(f"Pushed image tag: {IMAGE_TAG}")

    # IAM role for App Runner ECR access
    role_arn = f"arn:aws:iam::{account}:role/{ROLE_NAME}"
    r = run(["aws", "iam", "get-role", "--role-name", ROLE_NAME], check=False)
    if r.returncode != 0:
        print(f"Creating IAM role: {ROLE_NAME}")
        trust = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": ["build.apprunner.amazonaws.com", "tasks.apprunner.amazonaws.com"]},
                "Action": "sts:AssumeRole",
            }],
        }
        trust_file = write_temp_json(trust, "trust-policy")
        run(["aws", "iam", "create-role", "--role-name", ROLE_NAME,
             "--assume-role-policy-document", file_uri(trust_file)])
        run(["aws", "iam", "attach-role-policy", "--role-name", ROLE_NAME,
             "--policy-arn", "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"])
        time.sleep(10)

    runtime_env = {k: v for k, v in env_vars.items() if v}
    runtime_env["AWS_REGION"] = REGION

    source_config = {
        "ImageRepository": {
            "ImageIdentifier": f"{ecr_uri}:{IMAGE_TAG}",
            "ImageRepositoryType": "ECR",
            "ImageConfiguration": {
                "Port": "8080",
                "RuntimeEnvironmentVariables": runtime_env,
            },
        },
        "AuthenticationConfiguration": {"AccessRoleArn": role_arn},
        "AutoDeploymentsEnabled": False,
    }

    # Check existing service
    r = run(["aws", "apprunner", "list-services", "--region", REGION, "--output", "json"])
    services = json.loads(r.stdout).get("ServiceSummaryList", [])
    existing = next((s for s in services if s["ServiceName"] == SERVICE_NAME), None)

    if existing:
        print(f"Updating App Runner service: {SERVICE_NAME}")
        svc_arn = existing["ServiceArn"]
        cfg_file = write_temp_json(source_config, "source-config")
        # ImageIdentifier に毎回ユニークなタグを指定するため
        # update-service だけで確実に新しいイメージのデプロイが走る
        run(["aws", "apprunner", "update-service", "--region", REGION,
             "--service-arn", svc_arn,
             "--source-configuration", file_uri(cfg_file)])
    else:
        print(f"Creating App Runner service: {SERVICE_NAME}")
        create_input = {
            "ServiceName": SERVICE_NAME,
            "SourceConfiguration": source_config,
            "InstanceConfiguration": {"Cpu": "1 vCPU", "Memory": "2 GB"},
        }
        cfg_file = write_temp_json(create_input, "create-service")
        r = run(["aws", "apprunner", "create-service", "--region", REGION,
                 "--cli-input-json", file_uri(cfg_file), "--output", "json"])
        svc_arn = json.loads(r.stdout)["Service"]["ServiceArn"]

    print("Waiting for deployment...")
    # update-service + start-deployment 後、まず OPERATION_IN_PROGRESS になるまで待つ
    # その後 RUNNING に戻ったら新バージョンのデプロイ完了
    saw_in_progress = False
    for _ in range(40):
        time.sleep(15)
        r = run(["aws", "apprunner", "describe-service", "--region", REGION,
                 "--service-arn", svc_arn, "--output", "json"])
        svc = json.loads(r.stdout)["Service"]
        status = svc["Status"]
        print(f"  Status: {status}")
        if "OPERATION_IN_PROGRESS" in status or "CREATE_IN_PROGRESS" in status:
            saw_in_progress = True
        if status == "RUNNING" and saw_in_progress:
            url = svc["ServiceUrl"]
            print("\n=== DEPLOY SUCCESS ===")
            print(f"URL: https://{url}")
            print(f"Login: {env_vars['APP_USER']} / (your APP_PASSWORD)")
            print(f"  Generator: https://{url}/generator/")
            print(f"  Uploader:  https://{url}/upload/")
            return
        if "FAILED" in status:
            print("Deploy failed. Check AWS Console logs.")
            sys.exit(1)

    print(f"Timeout. Check AWS Console: {svc_arn}")
    sys.exit(1)


def deploy_vercel() -> None:
    """Vercel deploy using token from deploy/.vercel_token (bypasses CLI login)."""
    token_file = ROOT / "deploy" / ".vercel_token"
    if not token_file.exists():
        print("SKIP Vercel: deploy/.vercel_token not found.")
        return
    token = token_file.read_text(encoding="utf-8").strip()
    if not token or token == "PASTE_YOUR_VERCEL_TOKEN_HERE":
        print("SKIP Vercel: token not set in deploy/.vercel_token")
        return

    print("\n=== Vercel Deploy ===")
    env = os.environ.copy()
    env["VERCEL_TOKEN"] = token
    # ASCII-only VERCEL_ORG_ID / VERCEL_PROJECT_ID are read from .vercel/project.json if present
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
    result = subprocess.run(
        [npx_cmd, "vercel", "--prod", "--yes", "--token", token, "--scope", "takashi-gotos-projects"],
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode == 0:
        print("Vercel deploy SUCCESS")
    else:
        print(f"Vercel deploy FAILED (exit {result.returncode})")


if __name__ == "__main__":
    try:
        main()
        deploy_vercel()
    finally:
        cleanup_temp_files()
