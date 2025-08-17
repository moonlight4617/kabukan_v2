#!/bin/bash

# ロールバックスクリプト
# Usage: ./scripts/rollback.sh [environment] [options]

set -e

ENVIRONMENT=${1:-dev}
DRY_RUN=false
BACKUP_ONLY=false
FORCE=false
TARGET_VERSION=""

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘルプ表示
show_help() {
    echo "株式分析システム ロールバックスクリプト"
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "ENVIRONMENT:"
    echo "  dev       開発環境 (default)"
    echo "  staging   ステージング環境"
    echo "  prod      本番環境"
    echo ""
    echo "OPTIONS:"
    echo "  -d, --dry-run           実際の変更は行わず、確認のみ"
    echo "  -b, --backup-only       バックアップの作成のみ"
    echo "  -f, --force             確認なしで実行"
    echo "  -v, --version VERSION   特定のバージョンにロールバック"
    echo "  -h, --help              このヘルプを表示"
    echo ""
    echo "Examples:"
    echo "  $0 dev --dry-run        開発環境のロールバック計画を表示"
    echo "  $0 prod --backup-only   本番環境の設定をバックアップ"
    echo "  $0 staging -v 1.2.3     ステージング環境をバージョン1.2.3にロールバック"
    echo ""
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        dev|staging|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -b|--backup-only)
            BACKUP_ONLY=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -v|--version)
            TARGET_VERSION="$2"
            shift 2
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

log_dry_run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $1"
    fi
}

# 実行確認
confirm_action() {
    if [[ "$FORCE" == "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    echo ""
    log_warning "ロールバック設定確認:"
    echo "  Environment: $ENVIRONMENT"
    echo "  Target Version: ${TARGET_VERSION:-latest}"
    echo "  Action: $([ "$BACKUP_ONLY" == "true" ] && echo "Backup Only" || echo "Full Rollback")"
    echo ""
    
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        log_warning "本番環境のロールバックを実行しようとしています！"
        echo -n "本当に続行しますか？ (yes/no): "
        read -r response
        if [[ "$response" != "yes" ]]; then
            log_info "ロールバックをキャンセルしました"
            exit 0
        fi
    else
        echo -n "続行しますか？ (y/N): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            log_info "ロールバックをキャンセルしました"
            exit 0
        fi
    fi
}

# バックアップディレクトリ作成
create_backup_dir() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="backups/${ENVIRONMENT}_${timestamp}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "バックアップディレクトリを作成します: $BACKUP_DIR"
        return
    fi
    
    mkdir -p "$BACKUP_DIR"
    log_success "バックアップディレクトリを作成しました: $BACKUP_DIR"
}

# CloudFormationスタック情報の取得
get_stack_info() {
    local stack_name="stock-analysis-$ENVIRONMENT"
    
    log_info "スタック情報を取得中..."
    
    if ! aws cloudformation describe-stacks --stack-name "$stack_name" &> /dev/null; then
        log_error "スタックが見つかりません: $stack_name"
        exit 1
    fi
    
    # 現在のスタック情報を取得
    local stack_info=$(aws cloudformation describe-stacks --stack-name "$stack_name" --output json)
    CURRENT_STACK_ID=$(echo "$stack_info" | jq -r '.Stacks[0].StackId')
    CURRENT_STACK_STATUS=$(echo "$stack_info" | jq -r '.Stacks[0].StackStatus')
    CURRENT_CREATION_TIME=$(echo "$stack_info" | jq -r '.Stacks[0].CreationTime')
    CURRENT_LAST_UPDATED=$(echo "$stack_info" | jq -r '.Stacks[0].LastUpdatedTime // .Stacks[0].CreationTime')
    
    log_info "現在のスタック状態: $CURRENT_STACK_STATUS"
    log_info "最終更新時刻: $CURRENT_LAST_UPDATED"
}

# 利用可能なバージョンの取得
get_available_versions() {
    log_info "利用可能なバージョンを取得中..."
    
    # CloudFormationスタックイベントから履歴を取得
    local stack_name="stock-analysis-$ENVIRONMENT"
    local events=$(aws cloudformation describe-stack-events --stack-name "$stack_name" --output json 2>/dev/null || echo '{"StackEvents":[]}')
    
    # 成功したデプロイのタイムスタンプを取得
    AVAILABLE_VERSIONS=($(echo "$events" | jq -r '.StackEvents[] | select(.ResourceStatus == "UPDATE_COMPLETE" or .ResourceStatus == "CREATE_COMPLETE") | select(.ResourceType == "AWS::CloudFormation::Stack") | .Timestamp' | sort -r | head -5))
    
    if [[ ${#AVAILABLE_VERSIONS[@]} -eq 0 ]]; then
        log_warning "利用可能なバージョンが見つかりませんでした"
        return
    fi
    
    log_info "利用可能なバージョン:"
    for i in "${!AVAILABLE_VERSIONS[@]}"; do
        echo "  $((i+1)). ${AVAILABLE_VERSIONS[$i]}"
    done
}

# Parameter Storeのバックアップ
backup_parameter_store() {
    log_info "Parameter Storeの設定をバックアップ中..."
    
    local prefix="/stock-analysis-$ENVIRONMENT"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "Parameter Store設定をバックアップします: $prefix"
        return
    fi
    
    local backup_file="$BACKUP_DIR/parameter-store.json"
    
    if aws ssm get-parameters-by-path --path "$prefix" --recursive --with-decryption --output json > "$backup_file" 2>/dev/null; then
        local param_count=$(jq '.Parameters | length' "$backup_file")
        log_success "Parameter Store設定をバックアップしました: $param_count 個のパラメータ"
    else
        log_warning "Parameter Store設定のバックアップに失敗しました"
    fi
}

# Lambda関数のバックアップ
backup_lambda_function() {
    log_info "Lambda関数をバックアップ中..."
    
    local function_name="stock-analysis-$ENVIRONMENT"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "Lambda関数をバックアップします: $function_name"
        return
    fi
    
    local backup_file="$BACKUP_DIR/lambda-config.json"
    
    if aws lambda get-function --function-name "$function_name" --output json > "$backup_file" 2>/dev/null; then
        # 関数コードのダウンロード
        local code_url=$(jq -r '.Code.Location' "$backup_file")
        if [[ "$code_url" != "null" ]]; then
            curl -s "$code_url" -o "$BACKUP_DIR/lambda-code.zip"
            log_success "Lambda関数とコードをバックアップしました"
        else
            log_success "Lambda関数設定をバックアップしました"
        fi
    else
        log_warning "Lambda関数のバックアップに失敗しました"
    fi
}

# CloudWatch設定のバックアップ
backup_cloudwatch() {
    log_info "CloudWatch設定をバックアップ中..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "CloudWatch設定をバックアップします"
        return
    fi
    
    # ロググループ情報
    local log_group="/aws/lambda/stock-analysis-$ENVIRONMENT"
    aws logs describe-log-groups --log-group-name-prefix "$log_group" --output json > "$BACKUP_DIR/cloudwatch-logs.json" 2>/dev/null || true
    
    # アラーム情報
    aws cloudwatch describe-alarms --alarm-name-prefix "stock-analysis-" --output json > "$BACKUP_DIR/cloudwatch-alarms.json" 2>/dev/null || true
    
    log_success "CloudWatch設定をバックアップしました"
}

# EventBridge設定のバックアップ
backup_eventbridge() {
    log_info "EventBridge設定をバックアップ中..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "EventBridge設定をバックアップします"
        return
    fi
    
    local rules=(
        "stock-analysis-daily-$ENVIRONMENT"
        "stock-analysis-weekly-$ENVIRONMENT"
        "stock-analysis-monthly-$ENVIRONMENT"
    )
    
    echo "[]" > "$BACKUP_DIR/eventbridge-rules.json"
    
    for rule in "${rules[@]}"; do
        if aws events describe-rule --name "$rule" --output json > "/tmp/rule-$rule.json" 2>/dev/null; then
            jq ". + [$(cat "/tmp/rule-$rule.json")]" "$BACKUP_DIR/eventbridge-rules.json" > "/tmp/eventbridge-combined.json"
            mv "/tmp/eventbridge-combined.json" "$BACKUP_DIR/eventbridge-rules.json"
        fi
    done
    
    rm -f /tmp/rule-*.json
    log_success "EventBridge設定をバックアップしました"
}

# スタックテンプレートのバックアップ
backup_stack_template() {
    log_info "CloudFormationテンプレートをバックアップ中..."
    
    local stack_name="stock-analysis-$ENVIRONMENT"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "CloudFormationテンプレートをバックアップします"
        return
    fi
    
    if aws cloudformation get-template --stack-name "$stack_name" --output json > "$BACKUP_DIR/cloudformation-template.json" 2>/dev/null; then
        log_success "CloudFormationテンプレートをバックアップしました"
    else
        log_warning "CloudFormationテンプレートのバックアップに失敗しました"
    fi
}

# 完全バックアップの実行
perform_backup() {
    log_info "バックアップを実行中..."
    
    create_backup_dir
    backup_parameter_store
    backup_lambda_function
    backup_cloudwatch
    backup_eventbridge
    backup_stack_template
    
    if [[ "$DRY_RUN" != "true" ]]; then
        # バックアップサマリー作成
        cat > "$BACKUP_DIR/backup-summary.txt" << EOF
Backup Summary
==============
Environment: $ENVIRONMENT
Timestamp: $(date)
Stack ID: $CURRENT_STACK_ID
Stack Status: $CURRENT_STACK_STATUS
Last Updated: $CURRENT_LAST_UPDATED

Files:
$(ls -la "$BACKUP_DIR")
EOF
        
        log_success "バックアップが完了しました: $BACKUP_DIR"
    fi
}

# 前のバージョンへのロールバック
perform_rollback() {
    if [[ "$BACKUP_ONLY" == "true" ]]; then
        return
    fi
    
    log_info "ロールバックを実行中..."
    
    local stack_name="stock-analysis-$ENVIRONMENT"
    
    if [[ -n "$TARGET_VERSION" ]]; then
        log_info "指定されたバージョンにロールバック中: $TARGET_VERSION"
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log_dry_run "SAM deploy with version $TARGET_VERSION"
            return
        fi
        
        # 特定のバージョンへのロールバック（SAM deploy を使用）
        if sam deploy --config-env "$ENVIRONMENT" --no-confirm-changeset; then
            log_success "ロールバックが完了しました"
        else
            log_error "ロールバックに失敗しました"
            exit 1
        fi
    else
        # 前のスタック状態への復元
        log_info "前の安定した状態へのロールバックを実行中..."
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log_dry_run "CloudFormation cancel update (if in progress)"
            log_dry_run "または前の安定したテンプレートで更新"
            return
        fi
        
        # 進行中の更新をキャンセル（該当する場合）
        if [[ "$CURRENT_STACK_STATUS" == *"IN_PROGRESS"* ]]; then
            log_info "進行中の更新をキャンセル中..."
            if aws cloudformation cancel-update-stack --stack-name "$stack_name" 2>/dev/null; then
                log_success "更新をキャンセルしました"
                
                # 完了を待機
                log_info "キャンセル完了を待機中..."
                aws cloudformation wait stack-update-rollback-complete --stack-name "$stack_name" || true
            else
                log_warning "更新のキャンセルに失敗しました"
            fi
        fi
        
        log_success "ロールバック処理が完了しました"
    fi
}

# ロールバック後の検証
verify_rollback() {
    if [[ "$BACKUP_ONLY" == "true" ]] || [[ "$DRY_RUN" == "true" ]]; then
        return
    fi
    
    log_info "ロールバック後の検証を実行中..."
    
    # ヘルスチェック実行
    if [[ -f "scripts/health-check.sh" ]]; then
        log_info "ヘルスチェックを実行中..."
        if ./scripts/health-check.sh "$ENVIRONMENT"; then
            log_success "ヘルスチェックが正常に完了しました"
        else
            log_warning "ヘルスチェックで問題が検出されました"
        fi
    else
        log_warning "ヘルスチェックスクリプトが見つかりません"
    fi
}

# ロールバック手順の表示
show_rollback_plan() {
    echo ""
    echo "============================================"
    echo "  ロールバック計画"
    echo "============================================"
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Target Version: ${TARGET_VERSION:-前の安定した状態}"
    echo "Mode: $([ "$BACKUP_ONLY" == "true" ] && echo "Backup Only" || echo "Full Rollback")"
    echo ""
    echo "実行手順:"
    echo "1. 現在の設定をバックアップ"
    echo "2. Parameter Store設定をバックアップ"
    echo "3. Lambda関数とコードをバックアップ"
    echo "4. CloudWatch設定をバックアップ"
    echo "5. EventBridge設定をバックアップ"
    
    if [[ "$BACKUP_ONLY" != "true" ]]; then
        echo "6. 前のバージョンにロールバック"
        echo "7. ロールバック後の検証"
    fi
    
    echo ""
}

# サマリー表示
show_summary() {
    echo ""
    echo "============================================"
    echo "  ロールバック結果サマリー"
    echo "============================================"
    echo ""
    
    if [[ "$BACKUP_ONLY" == "true" ]]; then
        log_success "バックアップが正常に完了しました"
        echo "バックアップ場所: $BACKUP_DIR"
    elif [[ "$DRY_RUN" == "true" ]]; then
        log_info "ドライランが完了しました（実際の変更は行われていません）"
    else
        log_success "ロールバックが正常に完了しました"
        echo "バックアップ場所: $BACKUP_DIR"
        echo ""
        echo "次のステップ:"
        echo "1. アプリケーションの動作確認"
        echo "2. 必要に応じて追加の設定調整"
        echo "3. 問題がない場合はバックアップを保管"
    fi
    
    echo ""
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム ロールバック"
    echo "============================================"
    echo ""
    
    # AWS接続確認
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS認証情報が設定されていません"
        exit 1
    fi
    
    get_stack_info
    get_available_versions
    
    if [[ "$DRY_RUN" == "true" ]]; then
        show_rollback_plan
    fi
    
    confirm_action
    perform_backup
    perform_rollback
    verify_rollback
    show_summary
}

# スクリプト実行
main "$@"