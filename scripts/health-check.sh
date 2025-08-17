#!/bin/bash

# ヘルスチェックスクリプト
# Usage: ./scripts/health-check.sh [environment] [options]

set -e

ENVIRONMENT=${1:-dev}
VERBOSE=false
CHECK_ALL=false
FIX_ISSUES=false

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘルプ表示
show_help() {
    echo "株式分析システム ヘルスチェックスクリプト"
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "ENVIRONMENT:"
    echo "  dev       開発環境 (default)"
    echo "  staging   ステージング環境"
    echo "  prod      本番環境"
    echo ""
    echo "OPTIONS:"
    echo "  -v, --verbose     詳細出力"
    echo "  -a, --all         全項目チェック"
    echo "  -f, --fix         問題の自動修正を試行"
    echo "  -h, --help        このヘルプを表示"
    echo ""
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        dev|staging|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -a|--all)
            CHECK_ALL=true
            shift
            ;;
        -f|--fix)
            FIX_ISSUES=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

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

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}[VERBOSE]${NC} $1"
    fi
}

# ヘルスチェック結果
HEALTH_STATUS=0
ISSUES_FOUND=()
CHECKS_PASSED=0
CHECKS_TOTAL=0

# チェック結果記録
record_check() {
    local check_name="$1"
    local status="$2"
    local message="$3"
    
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
    
    if [[ "$status" == "pass" ]]; then
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
        log_success "$check_name: $message"
    elif [[ "$status" == "warning" ]]; then
        log_warning "$check_name: $message"
        ISSUES_FOUND+=("WARNING: $check_name - $message")
    else
        log_error "$check_name: $message"
        ISSUES_FOUND+=("ERROR: $check_name - $message")
        HEALTH_STATUS=1
    fi
}

# AWS接続チェック
check_aws_connectivity() {
    log_info "AWS接続チェック中..."
    
    if ! command -v aws &> /dev/null; then
        record_check "AWS CLI" "error" "AWS CLIがインストールされていません"
        return
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        record_check "AWS認証" "error" "AWS認証情報が設定されていません"
        return
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    local region=$(aws configure get region 2>/dev/null || echo "us-east-1")
    
    record_check "AWS接続" "pass" "Account: $account_id, Region: $region"
    
    # IAM権限チェック
    if aws iam get-user &> /dev/null; then
        record_check "IAM権限" "pass" "基本的なIAM権限が確認されました"
    else
        record_check "IAM権限" "warning" "IAM権限の確認ができませんでした"
    fi
}

# Lambda関数チェック
check_lambda_function() {
    log_info "Lambda関数チェック中..."
    
    local function_name="stock-analysis-$ENVIRONMENT"
    
    if ! aws lambda get-function --function-name "$function_name" &> /dev/null; then
        record_check "Lambda関数" "error" "関数が見つかりません: $function_name"
        return
    fi
    
    # 関数設定確認
    local function_info=$(aws lambda get-function --function-name "$function_name" --output json 2>/dev/null)
    local runtime=$(echo "$function_info" | jq -r '.Configuration.Runtime // "unknown"')
    local memory=$(echo "$function_info" | jq -r '.Configuration.MemorySize // "unknown"')
    local timeout=$(echo "$function_info" | jq -r '.Configuration.Timeout // "unknown"')
    
    record_check "Lambda関数" "pass" "$function_name (Runtime: $runtime, Memory: ${memory}MB, Timeout: ${timeout}s)"
    
    # 関数の実行テスト
    if [[ "$CHECK_ALL" == "true" ]]; then
        log_verbose "Lambda関数の実行テストを行います..."
        local test_payload='{"source": "health-check", "detail-type": "Health Check", "detail": {"test": true}}'
        
        if aws lambda invoke --function-name "$function_name" --payload "$test_payload" --output json /tmp/lambda-response.json &> /dev/null; then
            local status_code=$(jq -r '.StatusCode' /tmp/lambda-response.json 2>/dev/null || echo "unknown")
            if [[ "$status_code" == "200" ]]; then
                record_check "Lambda実行テスト" "pass" "正常に実行されました"
            else
                record_check "Lambda実行テスト" "warning" "ステータスコード: $status_code"
            fi
        else
            record_check "Lambda実行テスト" "error" "実行に失敗しました"
        fi
        
        rm -f /tmp/lambda-response.json
    fi
}

# Parameter Storeチェック
check_parameter_store() {
    log_info "Parameter Storeチェック中..."
    
    local prefix="/stock-analysis-$ENVIRONMENT"
    local required_params=(
        "slack/webhook-url"
        "google-sheets/spreadsheet-id"
        "google-sheets/credentials"
        "gemini/api-key"
    )
    
    local params_found=0
    local params_total=${#required_params[@]}
    
    for param in "${required_params[@]}"; do
        local param_name="$prefix/$param"
        if aws ssm get-parameter --name "$param_name" &> /dev/null; then
            params_found=$((params_found + 1))
            log_verbose "パラメータ確認: $param_name ✓"
        else
            log_verbose "パラメータ未設定: $param_name ✗"
        fi
    done
    
    if [[ "$params_found" -eq "$params_total" ]]; then
        record_check "Parameter Store" "pass" "全ての必要なパラメータが設定されています ($params_found/$params_total)"
    elif [[ "$params_found" -gt 0 ]]; then
        record_check "Parameter Store" "warning" "一部のパラメータが未設定です ($params_found/$params_total)"
    else
        record_check "Parameter Store" "error" "必要なパラメータが設定されていません"
    fi
}

# CloudWatchチェック
check_cloudwatch() {
    log_info "CloudWatchチェック中..."
    
    local log_group="/aws/lambda/stock-analysis-$ENVIRONMENT"
    
    if aws logs describe-log-groups --log-group-name-prefix "$log_group" --output json | jq -e '.logGroups | length > 0' &> /dev/null; then
        record_check "CloudWatch Logs" "pass" "ロググループが存在します: $log_group"
        
        # 最近のログエントリ確認
        if [[ "$CHECK_ALL" == "true" ]]; then
            local recent_logs=$(aws logs describe-log-streams --log-group-name "$log_group" --order-by LastEventTime --descending --max-items 1 --output json 2>/dev/null)
            if echo "$recent_logs" | jq -e '.logStreams | length > 0' &> /dev/null; then
                local last_event=$(echo "$recent_logs" | jq -r '.logStreams[0].lastEventTime // 0')
                if [[ "$last_event" -gt 0 ]]; then
                    local last_date=$(date -d "@$((last_event / 1000))" 2>/dev/null || echo "unknown")
                    record_check "CloudWatch活動" "pass" "最新ログ: $last_date"
                else
                    record_check "CloudWatch活動" "warning" "最近の活動が確認できません"
                fi
            else
                record_check "CloudWatch活動" "warning" "ログストリームが見つかりません"
            fi
        fi
    else
        record_check "CloudWatch Logs" "error" "ロググループが見つかりません: $log_group"
    fi
    
    # CloudWatchアラーム確認
    if [[ "$CHECK_ALL" == "true" ]]; then
        local alarms=$(aws cloudwatch describe-alarms --alarm-name-prefix "stock-analysis-" --output json 2>/dev/null)
        local alarm_count=$(echo "$alarms" | jq '.MetricAlarms | length' 2>/dev/null || echo "0")
        
        if [[ "$alarm_count" -gt 0 ]]; then
            record_check "CloudWatchアラーム" "pass" "$alarm_count 個のアラームが設定されています"
        else
            record_check "CloudWatchアラーム" "warning" "アラームが設定されていません"
        fi
    fi
}

# EventBridgeスケジュールチェック
check_eventbridge() {
    log_info "EventBridgeスケジュールチェック中..."
    
    local schedule_names=(
        "stock-analysis-daily-$ENVIRONMENT"
        "stock-analysis-weekly-$ENVIRONMENT"
        "stock-analysis-monthly-$ENVIRONMENT"
    )
    
    local schedules_found=0
    
    for schedule in "${schedule_names[@]}"; do
        if aws events describe-rule --name "$schedule" &> /dev/null; then
            schedules_found=$((schedules_found + 1))
            log_verbose "スケジュール確認: $schedule ✓"
            
            # スケジュールの状態確認
            local rule_info=$(aws events describe-rule --name "$schedule" --output json 2>/dev/null)
            local state=$(echo "$rule_info" | jq -r '.State // "unknown"')
            if [[ "$state" != "ENABLED" ]]; then
                log_verbose "スケジュール無効: $schedule ($state)"
            fi
        else
            log_verbose "スケジュール未設定: $schedule ✗"
        fi
    done
    
    if [[ "$schedules_found" -eq 3 ]]; then
        record_check "EventBridge" "pass" "全てのスケジュールが設定されています (3/3)"
    elif [[ "$schedules_found" -gt 0 ]]; then
        record_check "EventBridge" "warning" "一部のスケジュールが未設定です ($schedules_found/3)"
    else
        record_check "EventBridge" "error" "スケジュールが設定されていません"
    fi
}

# SQSキューチェック
check_sqs_queues() {
    log_info "SQSキューチェック中..."
    
    local queue_names=(
        "stock-analysis-error-queue-$ENVIRONMENT"
        "stock-analysis-dlq-$ENVIRONMENT"
    )
    
    local queues_found=0
    
    for queue_name in "${queue_names[@]}"; do
        if aws sqs get-queue-url --queue-name "$queue_name" &> /dev/null; then
            queues_found=$((queues_found + 1))
            log_verbose "キュー確認: $queue_name ✓"
        else
            log_verbose "キュー未設定: $queue_name ✗"
        fi
    done
    
    if [[ "$queues_found" -eq 2 ]]; then
        record_check "SQSキュー" "pass" "全てのキューが設定されています (2/2)"
    elif [[ "$queues_found" -gt 0 ]]; then
        record_check "SQSキュー" "warning" "一部のキューが未設定です ($queues_found/2)"
    else
        record_check "SQSキュー" "error" "キューが設定されていません"
    fi
}

# 外部API接続チェック
check_external_apis() {
    if [[ "$CHECK_ALL" != "true" ]]; then
        return
    fi
    
    log_info "外部API接続チェック中..."
    
    # Google Sheets API
    if command -v curl &> /dev/null; then
        log_verbose "Google Sheets APIチェック..."
        if curl -s --connect-timeout 5 "https://sheets.googleapis.com" &> /dev/null; then
            record_check "Google Sheets API" "pass" "APIエンドポイントにアクセス可能"
        else
            record_check "Google Sheets API" "warning" "APIエンドポイントにアクセスできません"
        fi
        
        log_verbose "Gemini APIチェック..."
        if curl -s --connect-timeout 5 "https://generativelanguage.googleapis.com" &> /dev/null; then
            record_check "Gemini AI API" "pass" "APIエンドポイントにアクセス可能"
        else
            record_check "Gemini AI API" "warning" "APIエンドポイントにアクセスできません"
        fi
    else
        record_check "外部API" "warning" "curlが利用できないためAPIチェックをスキップしました"
    fi
}

# 問題の自動修正
fix_issues() {
    if [[ "$FIX_ISSUES" != "true" ]] || [[ ${#ISSUES_FOUND[@]} -eq 0 ]]; then
        return
    fi
    
    log_info "問題の自動修正を試行中..."
    
    # CloudWatch Log Groupの作成
    local log_group="/aws/lambda/stock-analysis-$ENVIRONMENT"
    if ! aws logs describe-log-groups --log-group-name-prefix "$log_group" --output json | jq -e '.logGroups | length > 0' &> /dev/null; then
        log_info "CloudWatch Log Groupを作成中..."
        if aws logs create-log-group --log-group-name "$log_group" 2>/dev/null; then
            log_success "CloudWatch Log Groupを作成しました: $log_group"
        else
            log_warning "CloudWatch Log Groupの作成に失敗しました"
        fi
    fi
    
    # その他の修正は手動対応を推奨
    log_info "一部の問題は手動での対応が必要です"
}

# サマリー表示
show_summary() {
    echo ""
    echo "============================================"
    echo "  ヘルスチェック結果サマリー"
    echo "============================================"
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Checks: $CHECKS_PASSED/$CHECKS_TOTAL passed"
    echo ""
    
    if [[ $HEALTH_STATUS -eq 0 ]]; then
        log_success "全体的なヘルス状態: 正常"
    else
        log_error "全体的なヘルス状態: 問題あり"
    fi
    
    if [[ ${#ISSUES_FOUND[@]} -gt 0 ]]; then
        echo ""
        echo "発見された問題:"
        for issue in "${ISSUES_FOUND[@]}"; do
            echo "  - $issue"
        done
        echo ""
        echo "推奨アクション:"
        echo "  1. AWS リソースが正しくデプロイされているか確認"
        echo "  2. Parameter Store にすべての設定が保存されているか確認"
        echo "  3. IAM ロールに適切な権限が付与されているか確認"
        echo "  4. ./scripts/deploy.sh $ENVIRONMENT --guided でデプロイを実行"
    fi
    
    echo ""
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム ヘルスチェック"
    echo "============================================"
    echo ""
    
    check_aws_connectivity
    check_lambda_function
    check_parameter_store
    check_cloudwatch
    check_eventbridge
    check_sqs_queues
    check_external_apis
    
    fix_issues
    show_summary
    
    exit $HEALTH_STATUS
}

# スクリプト実行
main "$@"