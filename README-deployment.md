# 株式分析システム デプロイメントガイド

## 概要

このドキュメントでは、株式分析システムのAWSへのデプロイ方法について説明します。

## 前提条件

### 必要なツール

1. **AWS CLI** (v2.0以上)
   ```bash
   # インストール確認
   aws --version
   
   # 設定
   aws configure
   ```

2. **AWS SAM CLI** (v1.80以上)
   ```bash
   # インストール確認
   sam --version
   
   # インストール (Windows)
   # https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html
   ```

3. **Python 3.11**
   ```bash
   python --version
   # または
   python3 --version
   ```

### 必要な情報

デプロイ前に以下の情報を準備してください：

1. **Slack Webhook URL**
   - Slackワークスペースでアプリを作成し、Incoming Webhookを有効化
   - Webhook URLを取得

2. **Google Sheets設定**
   - Google Cloud Projectを作成
   - Google Sheets APIを有効化
   - サービスアカウントを作成し、認証情報JSONをダウンロード
   - スプレッドシートIDを取得

3. **Gemini AI API Key**
   - Google AI Studioでプロジェクトを作成
   - Gemini AI APIキーを取得

## デプロイ方法

### 1. クイックデプロイ（開発環境）

```bash
# Linux/Mac
./scripts/deploy.sh dev --guided

# Windows (PowerShell)
.\scripts\deploy.ps1 dev -Guided
```

### 2. 環境別デプロイ

#### 開発環境
```bash
# パラメータなしデプロイ
./scripts/deploy.sh dev

# パラメータ付きデプロイ
./scripts/deploy.sh dev --guided
```

#### ステージング環境
```bash
./scripts/deploy.sh staging --guided
```

#### 本番環境
```bash
# 本番環境は慎重に！
./scripts/deploy.sh prod --guided
```

### 3. SAMコマンド直接実行

```bash
# ビルド
sam build

# デプロイ（初回）
sam deploy --guided --config-env dev

# デプロイ（2回目以降）
sam deploy --config-env dev
```

## パラメータ設定

### 環境変数での設定

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export GOOGLE_SHEETS_SPREADSHEET_ID="1ABC123..."
export GOOGLE_SHEETS_CREDENTIALS='{"type": "service_account", ...}'
export GEMINI_API_KEY="AIza..."

./scripts/deploy.sh dev
```

### コマンドラインでの設定

```bash
sam deploy --config-env dev \
  --parameter-overrides \
    SlackWebhookUrl="https://hooks.slack.com/services/..." \
    GoogleSheetsSpreadsheetId="1ABC123..." \
    GoogleSheetsCredentials='{"type": "service_account", ...}' \
    GeminiApiKey="AIza..."
```

## 設定ファイル

### samconfig.toml

デプロイ設定は `samconfig.toml` で管理されます。

```toml
[dev.deploy.parameters]
stack_name = "stock-analysis-dev"
region = "us-east-1"
capabilities = "CAPABILITY_IAM"
parameter_overrides = [
    "Environment=dev"
]
```

### template.yaml

AWS リソースの定義は `template.yaml` で管理されます。

主要なリソース：
- Lambda関数 (`StockAnalysisFunction`)
- EventBridge ルール（日次・週次・月次）
- Parameter Store パラメータ
- IAMロール
- CloudWatch ログ
- SQS キュー（エラーハンドリング用）

## デプロイ後の確認

### 1. AWS コンソールでの確認

#### Lambda関数
```
https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/stock-analysis-{environment}
```

#### CloudWatch ログ
```
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%2Faws%2Flambda%2Fstock-analysis-{environment}
```

#### Parameter Store
```
https://us-east-1.console.aws.amazon.com/systems-manager/parameters?region=us-east-1&tab=Table
```

### 2. CLI での確認

```bash
# スタック状態確認
aws cloudformation describe-stacks --stack-name stock-analysis-dev

# Lambda関数確認
aws lambda get-function --function-name stock-analysis-dev

# ログ確認
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/stock-analysis"
```

### 3. テスト実行

```bash
# Lambda関数の手動実行
aws lambda invoke \
  --function-name stock-analysis-dev \
  --payload '{"source": "aws.events", "detail-type": "Scheduled Event", "detail": {"analysis_type": "daily"}}' \
  response.json

cat response.json
```

## トラブルシューティング

### よくある問題

#### 1. デプロイ権限エラー
```
User: ... is not authorized to perform: cloudformation:CreateStack
```

**解決方法：**
- IAMユーザーに適切な権限を付与
- PowerUserAccess または AdministratorAccess ポリシーをアタッチ

#### 2. Parameter Store 権限エラー
```
User: ... is not authorized to perform: ssm:PutParameter
```

**解決方法：**
- IAMユーザーにSSM権限を追加
- カスタムポリシーで ssm:* 権限を付与

#### 3. S3バケット作成エラー
```
Failed to create/update the stack. No export named ...
```

**解決方法：**
```bash
# S3バケットを手動作成
aws s3 mb s3://sam-deployment-bucket-{unique-suffix}

# samconfig.toml でバケット名を指定
s3_bucket = "sam-deployment-bucket-{unique-suffix}"
```

#### 4. Lambda デプロイサイズエラー
```
Unzipped size must be smaller than 262144000 bytes
```

**解決方法：**
```bash
# 不要なファイルを除外
echo "__pycache__/" >> .samignore
echo "tests/" >> .samignore
echo "docs/" >> .samignore
```

### ログの確認

```bash
# CloudWatch ログ取得
aws logs tail /aws/lambda/stock-analysis-dev --follow

# エラーログのフィルタリング
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-analysis-dev \
  --filter-pattern "ERROR"
```

## 運用

### 1. モニタリング

#### CloudWatch ダッシュボード（本番環境のみ）
```
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=StockAnalysis-prod
```

#### アラーム
- Lambda エラー率
- Lambda 実行時間
- Lambda スロットリング

### 2. バックアップ

```bash
# 設定のバックアップ
aws ssm get-parameters-by-path \
  --path "/stock-analysis-prod" \
  --recursive \
  --with-decryption > config-backup.json
```

### 3. 削除

```bash
# スタック削除
aws cloudformation delete-stack --stack-name stock-analysis-dev

# S3バケットの削除（手動）
aws s3 rb s3://sam-deployment-bucket-{suffix} --force
```

## セキュリティ

### 1. 認証情報の管理

- Parameter Store（SecureString）を使用
- IAMロールベースのアクセス制御
- 最小権限の原則

### 2. ネットワークセキュリティ

- VPC設定（必要に応じて）
- セキュリティグループ
- NACLs

### 3. 監査

```bash
# CloudTrail ログの確認
aws logs filter-log-events \
  --log-group-name /aws/cloudtrail \
  --filter-pattern "stock-analysis"
```

## 参考リンク

- [AWS SAM 開発者ガイド](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/)
- [AWS Lambda 開発者ガイド](https://docs.aws.amazon.com/lambda/latest/dg/)
- [AWS CloudFormation ユーザーガイド](https://docs.aws.amazon.com/cloudformation/latest/userguide/)
- [AWS CLI リファレンス](https://docs.aws.amazon.com/cli/latest/reference/)