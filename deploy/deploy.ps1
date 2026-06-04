# AWS App Runner deploy script (PowerShell)

param(
    [string]$Region = "us-east-1",
    [string]$ServiceName = "firekids-magazine-tool",
    [string]$RepoName = "firekids-magazine-tool"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== FIRE KIDS Magazine Tool Deploy ===" -ForegroundColor Cyan

$AccountId = (aws sts get-caller-identity --query Account --output text)
$EcrUri = "${AccountId}.dkr.ecr.${Region}.amazonaws.com/${RepoName}"
Write-Host "Account: $AccountId  Region: $Region  ECR: $EcrUri"

function Import-DotEnvFile($path) {
    $vars = @{}
    if (-not (Test-Path $path)) { return $vars }
    Get-Content $path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        $vars[$key] = $val
    }
    return $vars
}

$envVars = @{}
foreach ($f in @(
    "$Root\deploy\env.production",
    "$Root\scripts\article_generator\.env",
    "$Root\scripts\wp_uploader_local\.env"
)) {
    $loaded = Import-DotEnvFile $f
    foreach ($k in $loaded.Keys) { $envVars[$k] = $loaded[$k] }
}

if (-not $envVars["APP_USER"] -or -not $envVars["APP_PASSWORD"]) {
    Write-Host "ERROR: Set APP_USER and APP_PASSWORD in deploy\env.production" -ForegroundColor Red
    exit 1
}

$repoExists = aws ecr describe-repositories --repository-names $RepoName --region $Region 2>$null
if (-not $repoExists) {
    Write-Host "Creating ECR repository: $RepoName"
    aws ecr create-repository --repository-name $RepoName --region $Region | Out-Null
}

Write-Host "Building and pushing Docker image..."
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "${AccountId}.dkr.ecr.${Region}.amazonaws.com"
docker build -t "${RepoName}:latest" .
docker tag "${RepoName}:latest" "${EcrUri}:latest"
docker push "${EcrUri}:latest"

$RoleName = "AppRunnerECRAccessRole-FK"
$RoleArn = "arn:aws:iam::${AccountId}:role/${RoleName}"
$roleExists = aws iam get-role --role-name $RoleName 2>$null
if (-not $roleExists) {
    Write-Host "Creating IAM role: $RoleName"
    $trust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["build.apprunner.amazonaws.com","tasks.apprunner.amazonaws.com"]},"Action":"sts:AssumeRole"}]}'
    aws iam create-role --role-name $RoleName --assume-role-policy-document $trust | Out-Null
    aws iam attach-role-policy --role-name $RoleName --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess | Out-Null
    Start-Sleep -Seconds 10
}

$runtimeEnv = @{}
foreach ($k in $envVars.Keys) {
    if ($envVars[$k]) { $runtimeEnv[$k] = $envVars[$k] }
}
$runtimeEnv["AWS_REGION"] = $Region

$sourceConfig = @{
    ImageRepository = @{
        ImageIdentifier = "${EcrUri}:latest"
        ImageRepositoryType = "ECR"
        ImageConfiguration = @{
            Port = "8080"
            RuntimeEnvironmentVariables = $runtimeEnv
        }
    }
    AuthenticationConfiguration = @{
        AccessRoleArn = $RoleArn
    }
    AutoDeploymentsEnabled = $false
} | ConvertTo-Json -Depth 6 -Compress

$instanceConfig = '{"Cpu":"1 vCPU","Memory":"2 GB"}'

$existing = aws apprunner list-services --region $Region --query "ServiceSummaryList[?ServiceName=='$ServiceName'].ServiceArn" --output text

if ($existing) {
    Write-Host "Updating App Runner service: $ServiceName"
    aws apprunner update-service --region $Region --service-arn $existing --source-configuration $sourceConfig | Out-Null
    $ServiceArn = $existing
} else {
    Write-Host "Creating App Runner service: $ServiceName"
    $result = aws apprunner create-service --region $Region --service-name $ServiceName --source-configuration $sourceConfig --instance-configuration $instanceConfig --output json | ConvertFrom-Json
    $ServiceArn = $result.Service.ServiceArn
}

Write-Host "Waiting for deployment..." -ForegroundColor Yellow
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 15
    $svc = aws apprunner describe-service --region $Region --service-arn $ServiceArn --output json | ConvertFrom-Json
    $status = $svc.Service.Status
    Write-Host "  Status: $status"
    if ($status -eq "RUNNING") {
        $url = $svc.Service.ServiceUrl
        Write-Host ""
        Write-Host "=== DEPLOY SUCCESS ===" -ForegroundColor Green
        Write-Host "URL: https://$url"
        Write-Host "Login: $($envVars['APP_USER']) / (your APP_PASSWORD)"
        Write-Host "  Generator: https://$url/generator/"
        Write-Host "  Uploader:  https://$url/upload/"
        exit 0
    }
    if ($status -match "FAILED") {
        Write-Host "Deploy failed. Check AWS Console logs." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Timeout. Check status in AWS Console: $ServiceArn" -ForegroundColor Yellow
exit 1
