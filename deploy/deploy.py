#!/usr/bin/env python3
"""Deploy FIRE KIDS Magazine Tool to AWS App Runner."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-1"
SERVICE_NAME = "firekids-magazine-tool"
REPO_NAME = "firekids-magazine-tool"
ROLE_NAME = "AppRunnerECRAccessRole-FK"


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
    subprocess.run(["docker", "build", "-t", f"{REPO_NAME}:latest", str(ROOT)], check=True)
    subprocess.run(["docker", "tag", f"{REPO_NAME}:latest", f"{ecr_uri}:latest"], check=True)
    subprocess.run(["docker", "push", f"{ecr_uri}:latest"], check=True)

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
        trust_file = ROOT / "deploy" / "_trust-policy.json"
        trust_file.write_text(json.dumps(trust), encoding="utf-8")
        run(["aws", "iam", "create-role", "--role-name", ROLE_NAME,
             "--assume-role-policy-document", file_uri(trust_file)])
        run(["aws", "iam", "attach-role-policy", "--role-name", ROLE_NAME,
             "--policy-arn", "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"])
        time.sleep(10)

    runtime_env = {k: v for k, v in env_vars.items() if v}
    runtime_env["AWS_REGION"] = REGION

    source_config = {
        "ImageRepository": {
            "ImageIdentifier": f"{ecr_uri}:latest",
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
        cfg_file = ROOT / "deploy" / "_source-config.json"
        cfg_file.write_text(json.dumps(source_config), encoding="utf-8")
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
        cfg_file = ROOT / "deploy" / "_create-service.json"
        cfg_file.write_text(json.dumps(create_input), encoding="utf-8")
        r = run(["aws", "apprunner", "create-service", "--region", REGION,
                 "--cli-input-json", file_uri(cfg_file), "--output", "json"])
        svc_arn = json.loads(r.stdout)["Service"]["ServiceArn"]

    print("Waiting for deployment...")
    for _ in range(30):
        time.sleep(15)
        r = run(["aws", "apprunner", "describe-service", "--region", REGION,
                 "--service-arn", svc_arn, "--output", "json"])
        svc = json.loads(r.stdout)["Service"]
        status = svc["Status"]
        print(f"  Status: {status}")
        if status == "RUNNING":
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


if __name__ == "__main__":
    main()
