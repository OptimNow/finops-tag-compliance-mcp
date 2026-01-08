# deploy_policy.ps1
# One-click policy deployment to remote EC2
# Usage: .\scripts\deploy_policy.ps1

param(
    [string]$PolicyFile = "policies/tagging_policy.json",
    [string]$S3Bucket = "finops-mcp-config",
    [string]$EC2InstanceId = "i-0dc314272ccf812db",
    [string]$Region = "us-east-1"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  FinOps MCP Policy Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Validate JSON
Write-Host "[1/4] Validating policy JSON..." -ForegroundColor Yellow
try {
    $policy = Get-Content $PolicyFile -Raw | ConvertFrom-Json
    Write-Host "      OK - Valid JSON" -ForegroundColor Green
} catch {
    Write-Host "      FAILED - Invalid JSON: $_" -ForegroundColor Red
    exit 1
}

# Step 2: Upload to S3
Write-Host "[2/4] Uploading to S3..." -ForegroundColor Yellow
aws s3 cp $PolicyFile "s3://$S3Bucket/policies/tagging_policy.json" --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "      FAILED - Could not upload to S3" -ForegroundColor Red
    exit 1
}
Write-Host "      OK - Uploaded to s3://$S3Bucket/policies/" -ForegroundColor Green

# Step 3: Trigger EC2 to pull new policy and restart
Write-Host "[3/4] Updating EC2 instance..." -ForegroundColor Yellow
$command = @"
aws s3 cp s3://$S3Bucket/policies/tagging_policy.json /home/ec2-user/mcp-policies/tagging_policy.json && docker restart finops-mcp-server
"@

$result = aws ssm send-command `
    --instance-ids $EC2InstanceId `
    --document-name "AWS-RunShellScript" `
    --parameters "commands=[$command]" `
    --region $Region `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Host "      FAILED - Could not send command to EC2" -ForegroundColor Red
    exit 1
}

$commandId = $result.Command.CommandId
Write-Host "      OK - Command sent (ID: $commandId)" -ForegroundColor Green

# Step 4: Wait for completion
Write-Host "[4/4] Waiting for deployment to complete..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$status = aws ssm get-command-invocation `
    --command-id $commandId `
    --instance-id $EC2InstanceId `
    --region $Region `
    --output json | ConvertFrom-Json

if ($status.Status -eq "Success") {
    Write-Host "      OK - Policy deployed successfully!" -ForegroundColor Green
} else {
    Write-Host "      Status: $($status.Status)" -ForegroundColor Yellow
    Write-Host "      Output: $($status.StandardOutputContent)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verify with: curl http://YOUR_EC2_IP:8080/mcp/tools/call -X POST -H 'Content-Type: application/json' -d '{\"name\":\"get_tagging_policy\",\"arguments\":{}}'"
