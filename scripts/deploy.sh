#!/bin/bash

# 株式分析システム デプロイスクリプト
# Usage: ./scripts/deploy.sh [environment] [options]

set -e

# デフォルト値
ENVIRONMENT="dev"
GUIDED=false
VERBOSE=false
BUILD_ONLY=false
NO_CONFIRM=false
AWS_PROFILE=""
AWS_REGION="us-east-1"

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ヘルプ表示
show_help() {
    echo "株式分析システム デプロイスクリプト"
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "ENVIRONMENT:"
    echo "  dev       開発環境 (default)"
    echo "  staging   ステージング環境"
    echo "  prod      本番環境"
    echo ""
    echo "OPTIONS:"
    echo "  -g, --guided           ガイド付きデプロイ"
    echo "  -v, --verbose          詳細ログ出力"
    echo "  -b, --build-only       ビルドのみ実行"
    echo "  -y, --no-confirm       確認なしでデプロイ"
    echo "  -p, --profile PROFILE  AWS プロファイル"
    echo "  -r, --region REGION    AWS リージョン (default: us-east-1)"
    echo "  -h, --help             このヘルプを表示"
    echo ""
    echo "Examples:"
    echo "  $0 dev                 開発環境にデプロイ"
    echo "  $0 prod --guided       本番環境にガイド付きデプロイ"
    echo "  $0 staging -p myprofile -r us-west-2"
    echo ""
}

# ログ出力関数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        dev|staging|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        -g|--guided)
            GUIDED=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -b|--build-only)
            BUILD_ONLY=true
            shift
            ;;
        -y|--no-confirm)
            NO_CONFIRM=true
            shift
            ;;
        -p|--profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# 必要なツールのチェック
check_dependencies() {
    log_info "依存関係をチェック中..."
    
    if ! command -v sam &> /dev/null; then
        log_error "AWS SAM CLI がインストールされていません"
        log_info "インストール: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI がインストールされていません"
        log_info "インストール: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 がインストールされていません"
        exit 1
    fi
    
    log_success "依存関係チェック完了"
}

# AWS認証情報チェック
check_aws_credentials() {
    log_info "AWS認証情報をチェック中..."
    
    local aws_cmd="aws"
    if [[ -n "$AWS_PROFILE" ]]; then
        aws_cmd="aws --profile $AWS_PROFILE"
    fi
    
    if ! $aws_cmd sts get-caller-identity --region $AWS_REGION &> /dev/null; then
        log_error "AWS認証情報が設定されていません"
        log_info "AWS設定: aws configure"
        exit 1
    fi
    
    local account_id=$($aws_cmd sts get-caller-identity --query Account --output text --region $AWS_REGION)
    local user_arn=$($aws_cmd sts get-caller-identity --query Arn --output text --region $AWS_REGION)
    
    log_success "AWS認証OK - Account: $account_id, User: $user_arn"
}

# 環境確認
confirm_deployment() {
    if [[ "$NO_CONFIRM" == "true" ]]; then
        return 0
    fi
    
    echo ""
    log_warning "デプロイ設定確認:"
    echo "  Environment: $ENVIRONMENT"
    echo "  Region: $AWS_REGION"
    echo "  Profile: ${AWS_PROFILE:-default}"
    echo "  Stack Name: stock-analysis-$ENVIRONMENT"
    echo ""
    
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        log_warning "本番環境にデプロイしようとしています！"
        echo -n "本当に続行しますか？ (yes/no): "
        read -r response
        if [[ "$response" != "yes" ]]; then
            log_info "デプロイをキャンセルしました"
            exit 0
        fi
    else
        echo -n "続行しますか？ (y/N): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            log_info "デプロイをキャンセルしました"
            exit 0
        fi
    fi
}

# 必要なパラメータの入力
prompt_parameters() {
    if [[ "$GUIDED" != "true" ]]; then
        return 0
    fi
    
    log_info "必要なパラメータを入力してください："
    
    echo -n "Slack Webhook URL: "
    read -r slack_webhook
    export SLACK_WEBHOOK_URL="$slack_webhook"
    
    echo -n "Google Sheets Spreadsheet ID: "
    read -r sheets_id
    export GOOGLE_SHEETS_SPREADSHEET_ID="$sheets_id"
    
    echo -n "Google Sheets Credentials JSON (file path): "
    read -r creds_file
    if [[ -f "$creds_file" ]]; then
        export GOOGLE_SHEETS_CREDENTIALS=$(cat "$creds_file" | tr -d '\n' | tr -d ' ')
    else
        log_error "認証情報ファイルが見つかりません: $creds_file"
        exit 1
    fi
    
    echo -n "Gemini AI API Key: "
    read -r gemini_key
    export GEMINI_API_KEY="$gemini_key"
}

# SAM ビルド
sam_build() {
    log_info "SAM ビルドを実行中..."
    
    local build_cmd="sam build"
    if [[ "$VERBOSE" == "true" ]]; then
        build_cmd="$build_cmd --debug"
    fi
    
    if ! $build_cmd; then
        log_error "SAM ビルドに失敗しました"
        exit 1
    fi
    
    log_success "SAM ビルド完了"
}

# SAM デプロイ
sam_deploy() {
    if [[ "$BUILD_ONLY" == "true" ]]; then
        log_info "ビルドのみが指定されているため、デプロイをスキップします"
        return 0
    fi
    
    log_info "SAM デプロイを実行中..."
    
    local deploy_cmd="sam deploy --config-env $ENVIRONMENT"
    
    if [[ -n "$AWS_PROFILE" ]]; then
        deploy_cmd="$deploy_cmd --profile $AWS_PROFILE"
    fi
    
    if [[ "$NO_CONFIRM" == "true" ]]; then
        deploy_cmd="$deploy_cmd --no-confirm-changeset"
    fi
    
    if [[ "$VERBOSE" == "true" ]]; then
        deploy_cmd="$deploy_cmd --debug"
    fi
    
    # パラメータオーバーライド
    local param_overrides="Environment=$ENVIRONMENT"
    
    if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
        param_overrides="$param_overrides SlackWebhookUrl=$SLACK_WEBHOOK_URL"
    fi
    
    if [[ -n "$GOOGLE_SHEETS_SPREADSHEET_ID" ]]; then
        param_overrides="$param_overrides GoogleSheetsSpreadsheetId=$GOOGLE_SHEETS_SPREADSHEET_ID"
    fi
    
    if [[ -n "$GOOGLE_SHEETS_CREDENTIALS" ]]; then
        param_overrides="$param_overrides GoogleSheetsCredentials=$GOOGLE_SHEETS_CREDENTIALS"
    fi
    
    if [[ -n "$GEMINI_API_KEY" ]]; then
        param_overrides="$param_overrides GeminiApiKey=$GEMINI_API_KEY"
    fi
    
    deploy_cmd="$deploy_cmd --parameter-overrides $param_overrides"
    
    if ! eval $deploy_cmd; then
        log_error "SAM デプロイに失敗しました"
        exit 1
    fi
    
    log_success "SAM デプロイ完了"
}

# デプロイ後の確認
post_deploy_check() {
    if [[ "$BUILD_ONLY" == "true" ]]; then
        return 0
    fi
    
    log_info "デプロイ後の確認を実行中..."
    
    local stack_name="stock-analysis-$ENVIRONMENT"
    local aws_cmd="aws"
    if [[ -n "$AWS_PROFILE" ]]; then
        aws_cmd="aws --profile $AWS_PROFILE"
    fi
    
    # スタック状態確認
    local stack_status=$($aws_cmd cloudformation describe-stacks \
        --stack-name $stack_name \
        --query 'Stacks[0].StackStatus' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$stack_status" == "CREATE_COMPLETE" || "$stack_status" == "UPDATE_COMPLETE" ]]; then
        log_success "スタック状態: $stack_status"
    else
        log_warning "スタック状態: $stack_status"
    fi
    
    # Lambda関数の確認
    local function_name="stock-analysis-$ENVIRONMENT"
    if $aws_cmd lambda get-function --function-name $function_name --region $AWS_REGION &> /dev/null; then
        log_success "Lambda関数が正常にデプロイされました: $function_name"
    else
        log_warning "Lambda関数の確認に失敗しました: $function_name"
    fi
    
    # 出力値の表示
    log_info "スタック出力値:"
    $aws_cmd cloudformation describe-stacks \
        --stack-name $stack_name \
        --query 'Stacks[0].Outputs' \
        --output table \
        --region $AWS_REGION 2>/dev/null || log_warning "出力値の取得に失敗しました"
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム デプロイスクリプト"
    echo "============================================"
    echo ""
    
    check_dependencies
    check_aws_credentials
    confirm_deployment
    prompt_parameters
    sam_build
    sam_deploy
    post_deploy_check
    
    echo ""
    log_success "デプロイ処理が完了しました！"
    
    if [[ "$BUILD_ONLY" != "true" ]]; then
        log_info "AWS コンソール: https://$AWS_REGION.console.aws.amazon.com/lambda/home?region=$AWS_REGION#/functions/stock-analysis-$ENVIRONMENT"
        log_info "CloudWatch ログ: https://$AWS_REGION.console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups/log-group/%2Faws%2Flambda%2Fstock-analysis-$ENVIRONMENT"
    fi
}

# スクリプト実行
main "$@"