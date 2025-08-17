# 株式分析システム デプロイスクリプト (PowerShell版)
# Usage: .\scripts\deploy.ps1 [Environment] [Options]

param(
    [Parameter(Position=0)]
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment = "dev",
    
    [switch]$Guided,
    [switch]$Verbose,
    [switch]$BuildOnly,
    [switch]$NoConfirm,
    [string]$Profile = "",
    [string]$Region = "us-east-1",
    [switch]$Help
)

# カラー定義
$Colors = @{
    Red = "Red"
    Green = "Green"
    Yellow = "Yellow"
    Blue = "Blue"
    Cyan = "Cyan"
}

# ヘルプ表示
function Show-Help {
    Write-Host "株式分析システム デプロイスクリプト (PowerShell版)" -ForegroundColor $Colors.Blue
    Write-Host ""
    Write-Host "Usage: .\scripts\deploy.ps1 [ENVIRONMENT] [OPTIONS]" -ForegroundColor $Colors.Cyan
    Write-Host ""
    Write-Host "ENVIRONMENT:" -ForegroundColor $Colors.Yellow
    Write-Host "  dev       開発環境 (default)"
    Write-Host "  staging   ステージング環境"
    Write-Host "  prod      本番環境"
    Write-Host ""
    Write-Host "OPTIONS:" -ForegroundColor $Colors.Yellow
    Write-Host "  -Guided           ガイド付きデプロイ"
    Write-Host "  -Verbose          詳細ログ出力"
    Write-Host "  -BuildOnly        ビルドのみ実行"
    Write-Host "  -NoConfirm        確認なしでデプロイ"
    Write-Host "  -Profile PROFILE  AWS プロファイル"
    Write-Host "  -Region REGION    AWS リージョン (default: us-east-1)"
    Write-Host "  -Help             このヘルプを表示"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor $Colors.Yellow
    Write-Host "  .\scripts\deploy.ps1 dev                 開発環境にデプロイ"
    Write-Host "  .\scripts\deploy.ps1 prod -Guided        本番環境にガイド付きデプロイ"
    Write-Host "  .\scripts\deploy.ps1 staging -Profile myprofile -Region us-west-2"
    Write-Host ""
}

# ログ出力関数
function Write-LogInfo($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor $Colors.Blue
}

function Write-LogSuccess($Message) {
    Write-Host "[SUCCESS] $Message" -ForegroundColor $Colors.Green
}

function Write-LogWarning($Message) {
    Write-Host "[WARNING] $Message" -ForegroundColor $Colors.Yellow
}

function Write-LogError($Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor $Colors.Red
}

# 必要なツールのチェック
function Test-Dependencies {
    Write-LogInfo "依存関係をチェック中..."
    
    # SAM CLI チェック
    try {
        $samVersion = & sam --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "SAM CLI not found"
        }
        Write-LogInfo "SAM CLI: $samVersion"
    }
    catch {
        Write-LogError "AWS SAM CLI がインストールされていません"
        Write-LogInfo "インストール: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
        exit 1
    }
    
    # AWS CLI チェック
    try {
        $awsVersion = & aws --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "AWS CLI not found"
        }
        Write-LogInfo "AWS CLI: $awsVersion"
    }
    catch {
        Write-LogError "AWS CLI がインストールされていません"
        Write-LogInfo "インストール: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    }
    
    # Python チェック
    try {
        $pythonVersion = & python --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            $pythonVersion = & python3 --version 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "Python not found"
            }
        }
        Write-LogInfo "Python: $pythonVersion"
    }
    catch {
        Write-LogError "Python がインストールされていません"
        exit 1
    }
    
    Write-LogSuccess "依存関係チェック完了"
}

# AWS認証情報チェック
function Test-AwsCredentials {
    Write-LogInfo "AWS認証情報をチェック中..."
    
    $awsCmd = "aws"
    if ($Profile) {
        $awsCmd += " --profile $Profile"
    }
    $awsCmd += " --region $Region"
    
    try {
        $identity = & aws sts get-caller-identity --region $Region $(if ($Profile) { "--profile", $Profile }) --output json 2>$null | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) {
            throw "AWS credentials check failed"
        }
        
        Write-LogSuccess "AWS認証OK - Account: $($identity.Account), User: $($identity.Arn)"
    }
    catch {
        Write-LogError "AWS認証情報が設定されていません"
        Write-LogInfo "AWS設定: aws configure"
        exit 1
    }
}

# 環境確認
function Confirm-Deployment {
    if ($NoConfirm) {
        return
    }
    
    Write-Host ""
    Write-LogWarning "デプロイ設定確認:"
    Write-Host "  Environment: $Environment"
    Write-Host "  Region: $Region"
    Write-Host "  Profile: $(if ($Profile) { $Profile } else { 'default' })"
    Write-Host "  Stack Name: stock-analysis-$Environment"
    Write-Host ""
    
    if ($Environment -eq "prod") {
        Write-LogWarning "本番環境にデプロイしようとしています！"
        $response = Read-Host "本当に続行しますか？ (yes/no)"
        if ($response -ne "yes") {
            Write-LogInfo "デプロイをキャンセルしました"
            exit 0
        }
    } else {
        $response = Read-Host "続行しますか？ (y/N)"
        if ($response -ne "y" -and $response -ne "Y") {
            Write-LogInfo "デプロイをキャンセルしました"
            exit 0
        }
    }
}

# 必要なパラメータの入力
function Get-Parameters {
    if (-not $Guided) {
        return @{}
    }
    
    Write-LogInfo "必要なパラメータを入力してください："
    
    $parameters = @{}
    
    $slackWebhook = Read-Host "Slack Webhook URL"
    if ($slackWebhook) {
        $parameters["SlackWebhookUrl"] = $slackWebhook
    }
    
    $sheetsId = Read-Host "Google Sheets Spreadsheet ID"
    if ($sheetsId) {
        $parameters["GoogleSheetsSpreadsheetId"] = $sheetsId
    }
    
    $credsFile = Read-Host "Google Sheets Credentials JSON (file path)"
    if ($credsFile -and (Test-Path $credsFile)) {
        $credentials = Get-Content $credsFile -Raw | ConvertFrom-Json | ConvertTo-Json -Compress
        $parameters["GoogleSheetsCredentials"] = $credentials
    } elseif ($credsFile) {
        Write-LogError "認証情報ファイルが見つかりません: $credsFile"
        exit 1
    }
    
    $geminiKey = Read-Host "Gemini AI API Key"
    if ($geminiKey) {
        $parameters["GeminiApiKey"] = $geminiKey
    }
    
    return $parameters
}

# SAM ビルド
function Invoke-SamBuild {
    Write-LogInfo "SAM ビルドを実行中..."
    
    $buildArgs = @("build")
    if ($Verbose) {
        $buildArgs += "--debug"
    }
    
    try {
        & sam @buildArgs
        if ($LASTEXITCODE -ne 0) {
            throw "SAM build failed"
        }
        Write-LogSuccess "SAM ビルド完了"
    }
    catch {
        Write-LogError "SAM ビルドに失敗しました"
        exit 1
    }
}

# SAM デプロイ
function Invoke-SamDeploy($Parameters) {
    if ($BuildOnly) {
        Write-LogInfo "ビルドのみが指定されているため、デプロイをスキップします"
        return
    }
    
    Write-LogInfo "SAM デプロイを実行中..."
    
    $deployArgs = @("deploy", "--config-env", $Environment)
    
    if ($Profile) {
        $deployArgs += "--profile", $Profile
    }
    
    if ($NoConfirm) {
        $deployArgs += "--no-confirm-changeset"
    }
    
    if ($Verbose) {
        $deployArgs += "--debug"
    }
    
    # パラメータオーバーライド
    $paramOverrides = @("Environment=$Environment")
    
    foreach ($key in $Parameters.Keys) {
        $paramOverrides += "$key=$($Parameters[$key])"
    }
    
    if ($paramOverrides.Count -gt 0) {
        $deployArgs += "--parameter-overrides"
        $deployArgs += $paramOverrides
    }
    
    try {
        & sam @deployArgs
        if ($LASTEXITCODE -ne 0) {
            throw "SAM deploy failed"
        }
        Write-LogSuccess "SAM デプロイ完了"
    }
    catch {
        Write-LogError "SAM デプロイに失敗しました"
        exit 1
    }
}

# デプロイ後の確認
function Test-PostDeploy {
    if ($BuildOnly) {
        return
    }
    
    Write-LogInfo "デプロイ後の確認を実行中..."
    
    $stackName = "stock-analysis-$Environment"
    $awsArgs = @("--region", $Region)
    if ($Profile) {
        $awsArgs += "--profile", $Profile
    }
    
    try {
        # スタック状態確認
        $stackStatus = & aws cloudformation describe-stacks --stack-name $stackName @awsArgs --query 'Stacks[0].StackStatus' --output text 2>$null
        
        if ($stackStatus -eq "CREATE_COMPLETE" -or $stackStatus -eq "UPDATE_COMPLETE") {
            Write-LogSuccess "スタック状態: $stackStatus"
        } else {
            Write-LogWarning "スタック状態: $stackStatus"
        }
        
        # Lambda関数の確認
        $functionName = "stock-analysis-$Environment"
        & aws lambda get-function --function-name $functionName @awsArgs >$null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-LogSuccess "Lambda関数が正常にデプロイされました: $functionName"
        } else {
            Write-LogWarning "Lambda関数の確認に失敗しました: $functionName"
        }
        
        # 出力値の表示
        Write-LogInfo "スタック出力値:"
        & aws cloudformation describe-stacks --stack-name $stackName @awsArgs --query 'Stacks[0].Outputs' --output table 2>$null
    }
    catch {
        Write-LogWarning "デプロイ後の確認でエラーが発生しました: $($_.Exception.Message)"
    }
}

# メイン処理
function Main {
    if ($Help) {
        Show-Help
        exit 0
    }
    
    Write-Host "============================================" -ForegroundColor $Colors.Blue
    Write-Host "  株式分析システム デプロイスクリプト" -ForegroundColor $Colors.Blue
    Write-Host "============================================" -ForegroundColor $Colors.Blue
    Write-Host ""
    
    Test-Dependencies
    Test-AwsCredentials
    Confirm-Deployment
    $parameters = Get-Parameters
    Invoke-SamBuild
    Invoke-SamDeploy $parameters
    Test-PostDeploy
    
    Write-Host ""
    Write-LogSuccess "デプロイ処理が完了しました！"
    
    if (-not $BuildOnly) {
        Write-LogInfo "AWS コンソール: https://$Region.console.aws.amazon.com/lambda/home?region=$Region#/functions/stock-analysis-$Environment"
        Write-LogInfo "CloudWatch ログ: https://$Region.console.aws.amazon.com/cloudwatch/home?region=$Region#logsV2:log-groups/log-group/%2Faws%2Flambda%2Fstock-analysis-$Environment"
    }
}

# スクリプト実行
Main