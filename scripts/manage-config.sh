#!/bin/bash

# 設定管理スクリプト
# Usage: ./scripts/manage-config.sh [environment] [action] [options]

set -e

ENVIRONMENT=""
ACTION=""
CONFIG_FILE=""
VERBOSE=false
DRY_RUN=false
FORCE=false

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘルプ表示
show_help() {
    echo "株式分析システム 設定管理スクリプト"
    echo ""
    echo "Usage: $0 [ENVIRONMENT] [ACTION] [OPTIONS]"
    echo ""
    echo "ENVIRONMENT:"
    echo "  dev       開発環境"
    echo "  staging   ステージング環境"
    echo "  prod      本番環境"
    echo ""
    echo "ACTION:"
    echo "  export    設定をエクスポート"
    echo "  import    設定をインポート"
    echo "  backup    設定をバックアップ"
    echo "  restore   設定を復元"
    echo "  validate  設定を検証"
    echo "  sync      環境間で設定を同期"
    echo ""
    echo "OPTIONS:"
    echo "  -f, --file FILE     設定ファイルパス"
    echo "  -v, --verbose       詳細出力"
    echo "  -d, --dry-run       実際の変更は行わず、確認のみ"
    echo "  --force             確認なしで実行"
    echo "  -h, --help          このヘルプを表示"
    echo ""
    echo "Examples:"
    echo "  $0 dev export -f config-dev.json       開発環境の設定をエクスポート"
    echo "  $0 prod backup                         本番環境の設定をバックアップ"
    echo "  $0 staging import -f config-dev.json   ステージング環境に設定をインポート"
    echo "  $0 dev validate                        開発環境の設定を検証"
    echo ""
}

# 引数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        dev|staging|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        export|import|backup|restore|validate|sync)
            ACTION="$1"
            shift
            ;;
        -f|--file)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
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

# 必須パラメータチェック
if [[ -z "$ENVIRONMENT" ]] || [[ -z "$ACTION" ]]; then
    echo "Environment と Action は必須です"
    show_help
    exit 1
fi

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
    log_warning "設定操作確認:"
    echo "  Environment: $ENVIRONMENT"
    echo "  Action: $ACTION"
    echo "  File: ${CONFIG_FILE:-自動生成}"
    echo ""
    
    if [[ "$ENVIRONMENT" == "prod" ]] && [[ "$ACTION" == "import" ]]; then
        log_warning "本番環境に設定をインポートしようとしています！"
        echo -n "本当に続行しますか？ (yes/no): "
        read -r response
        if [[ "$response" != "yes" ]]; then
            log_info "操作をキャンセルしました"
            exit 0
        fi
    else
        echo -n "続行しますか？ (y/N): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            log_info "操作をキャンセルしました"
            exit 0
        fi
    fi
}

# Parameter Store設定のエクスポート
export_parameter_store() {
    log_info "Parameter Store設定をエクスポート中..."
    
    local prefix="/stock-analysis-$ENVIRONMENT"
    local output_file="${CONFIG_FILE:-config-$ENVIRONMENT-$(date +%Y%m%d_%H%M%S).json}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "Parameter Store設定をエクスポートします: $prefix -> $output_file"
        return
    fi
    
    # パラメータ取得
    local parameters=$(aws ssm get-parameters-by-path \
        --path "$prefix" \
        --recursive \
        --with-decryption \
        --output json 2>/dev/null || echo '{"Parameters":[]}')
    
    # 設定ファイル生成
    cat > "$output_file" << EOF
{
  "metadata": {
    "environment": "$ENVIRONMENT",
    "exported_at": "$(date -Iseconds)",
    "prefix": "$prefix",
    "total_parameters": $(echo "$parameters" | jq '.Parameters | length')
  },
  "parameters": $(echo "$parameters" | jq '.Parameters')
}
EOF
    
    local param_count=$(echo "$parameters" | jq '.Parameters | length')
    log_success "Parameter Store設定をエクスポートしました: $output_file ($param_count パラメータ)"
    
    # 機密情報の警告
    if [[ "$param_count" -gt 0 ]]; then
        log_warning "エクスポートファイルには機密情報が含まれています。適切に管理してください。"
    fi
}

# Parameter Store設定のインポート
import_parameter_store() {
    log_info "Parameter Store設定をインポート中..."
    
    if [[ -z "$CONFIG_FILE" ]] || [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "設定ファイルが指定されていないか、ファイルが見つかりません: $CONFIG_FILE"
        exit 1
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "Parameter Store設定をインポートします: $CONFIG_FILE"
        local param_count=$(jq '.parameters | length' "$CONFIG_FILE" 2>/dev/null || echo "0")
        log_dry_run "インポート対象: $param_count パラメータ"
        return
    fi
    
    # 設定ファイル検証
    if ! jq empty "$CONFIG_FILE" 2>/dev/null; then
        log_error "設定ファイルが不正なJSON形式です: $CONFIG_FILE"
        exit 1
    fi
    
    # パラメータをインポート
    local import_count=0
    local error_count=0
    
    while IFS=$'\t' read -r name value type; do
        if [[ -z "$name" ]]; then
            continue
        fi
        
        # 環境プレフィックスを変更
        local target_name=$(echo "$name" | sed "s|/stock-analysis-[^/]*|/stock-analysis-$ENVIRONMENT|")
        
        log_verbose "パラメータをインポート中: $target_name"
        
        if aws ssm put-parameter \
            --name "$target_name" \
            --value "$value" \
            --type "$type" \
            --overwrite \
            --output json >/dev/null 2>&1; then
            import_count=$((import_count + 1))
        else
            log_warning "パラメータのインポートに失敗: $target_name"
            error_count=$((error_count + 1))
        fi
    done < <(jq -r '.parameters[] | [.Name, .Value, .Type] | @tsv' "$CONFIG_FILE")
    
    log_success "Parameter Store設定をインポートしました: $import_count パラメータ"
    if [[ "$error_count" -gt 0 ]]; then
        log_warning "エラーが発生したパラメータ: $error_count"
    fi
}

# 設定のバックアップ
backup_configuration() {
    log_info "設定をバックアップ中..."
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="backups/config_${ENVIRONMENT}_${timestamp}"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "設定をバックアップします: $backup_dir"
        return
    fi
    
    mkdir -p "$backup_dir"
    
    # Parameter Store
    local prefix="/stock-analysis-$ENVIRONMENT"
    aws ssm get-parameters-by-path \
        --path "$prefix" \
        --recursive \
        --with-decryption \
        --output json > "$backup_dir/parameter-store.json" 2>/dev/null || echo '{"Parameters":[]}' > "$backup_dir/parameter-store.json"
    
    # Lambda環境変数
    local function_name="stock-analysis-$ENVIRONMENT"
    aws lambda get-function-configuration \
        --function-name "$function_name" \
        --output json > "$backup_dir/lambda-env.json" 2>/dev/null || echo '{}' > "$backup_dir/lambda-env.json"
    
    # EventBridge設定
    local rules=(
        "stock-analysis-daily-$ENVIRONMENT"
        "stock-analysis-weekly-$ENVIRONMENT"
        "stock-analysis-monthly-$ENVIRONMENT"
    )
    
    echo "[]" > "$backup_dir/eventbridge-rules.json"
    for rule in "${rules[@]}"; do
        if aws events describe-rule --name "$rule" --output json > "/tmp/rule.json" 2>/dev/null; then
            jq ". + [$(cat /tmp/rule.json)]" "$backup_dir/eventbridge-rules.json" > "/tmp/rules-combined.json"
            mv "/tmp/rules-combined.json" "$backup_dir/eventbridge-rules.json"
        fi
    done
    rm -f /tmp/rule.json
    
    # バックアップサマリー
    cat > "$backup_dir/backup-info.json" << EOF
{
  "environment": "$ENVIRONMENT",
  "timestamp": "$timestamp",
  "backup_date": "$(date -Iseconds)",
  "parameter_count": $(jq '.Parameters | length' "$backup_dir/parameter-store.json"),
  "has_lambda_config": $([ -s "$backup_dir/lambda-env.json" ] && echo "true" || echo "false"),
  "eventbridge_rules": $(jq '. | length' "$backup_dir/eventbridge-rules.json")
}
EOF
    
    log_success "設定をバックアップしました: $backup_dir"
}

# 設定の復元
restore_configuration() {
    log_info "設定を復元中..."
    
    if [[ -z "$CONFIG_FILE" ]]; then
        # 最新のバックアップを検索
        local latest_backup=$(find backups -name "config_${ENVIRONMENT}_*" -type d | sort -r | head -1)
        if [[ -z "$latest_backup" ]]; then
            log_error "復元するバックアップが見つかりません"
            exit 1
        fi
        CONFIG_FILE="$latest_backup"
        log_info "最新のバックアップを使用します: $CONFIG_FILE"
    fi
    
    if [[ ! -d "$CONFIG_FILE" ]]; then
        log_error "バックアップディレクトリが見つかりません: $CONFIG_FILE"
        exit 1
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_dry_run "設定を復元します: $CONFIG_FILE"
        return
    fi
    
    # Parameter Storeの復元
    if [[ -f "$CONFIG_FILE/parameter-store.json" ]]; then
        log_info "Parameter Storeを復元中..."
        local restore_count=0
        
        while IFS=$'\t' read -r name value type; do
            if [[ -z "$name" ]]; then
                continue
            fi
            
            log_verbose "パラメータを復元中: $name"
            
            if aws ssm put-parameter \
                --name "$name" \
                --value "$value" \
                --type "$type" \
                --overwrite \
                --output json >/dev/null 2>&1; then
                restore_count=$((restore_count + 1))
            else
                log_warning "パラメータの復元に失敗: $name"
            fi
        done < <(jq -r '.Parameters[] | [.Name, .Value, .Type] | @tsv' "$CONFIG_FILE/parameter-store.json")
        
        log_success "Parameter Storeを復元しました: $restore_count パラメータ"
    fi
    
    log_success "設定の復元が完了しました"
}

# 設定の検証
validate_configuration() {
    log_info "設定を検証中..."
    
    local validation_errors=0
    local prefix="/stock-analysis-$ENVIRONMENT"
    
    # 必須パラメータのチェック
    local required_params=(
        "slack/webhook-url"
        "google-sheets/spreadsheet-id"
        "google-sheets/credentials"
        "gemini/api-key"
        "analysis/enable-daily"
        "analysis/enable-weekly"
        "analysis/enable-monthly"
    )
    
    log_info "必須パラメータを確認中..."
    for param in "${required_params[@]}"; do
        local param_name="$prefix/$param"
        
        if aws ssm get-parameter --name "$param_name" --output json >/dev/null 2>&1; then
            log_verbose "パラメータ確認: $param ✓"
        else
            log_error "必須パラメータが見つかりません: $param"
            validation_errors=$((validation_errors + 1))
        fi
    done
    
    # Lambda関数の確認
    log_info "Lambda関数を確認中..."
    local function_name="stock-analysis-$ENVIRONMENT"
    
    if aws lambda get-function --function-name "$function_name" --output json >/dev/null 2>&1; then
        log_verbose "Lambda関数確認: $function_name ✓"
        
        # 環境変数の確認
        local env_vars=$(aws lambda get-function-configuration --function-name "$function_name" --query 'Environment.Variables' --output json 2>/dev/null || echo '{}')
        local required_env_vars=("ENVIRONMENT" "AWS_REGION" "PARAMETER_STORE_PREFIX")
        
        for env_var in "${required_env_vars[@]}"; do
            if echo "$env_vars" | jq -e "has(\"$env_var\")" >/dev/null 2>&1; then
                log_verbose "環境変数確認: $env_var ✓"
            else
                log_warning "推奨環境変数が設定されていません: $env_var"
            fi
        done
    else
        log_error "Lambda関数が見つかりません: $function_name"
        validation_errors=$((validation_errors + 1))
    fi
    
    # EventBridgeルールの確認
    log_info "EventBridgeルールを確認中..."
    local rules=(
        "stock-analysis-daily-$ENVIRONMENT"
        "stock-analysis-weekly-$ENVIRONMENT"
        "stock-analysis-monthly-$ENVIRONMENT"
    )
    
    for rule in "${rules[@]}"; do
        if aws events describe-rule --name "$rule" --output json >/dev/null 2>&1; then
            local rule_state=$(aws events describe-rule --name "$rule" --query 'State' --output text 2>/dev/null)
            if [[ "$rule_state" == "ENABLED" ]]; then
                log_verbose "EventBridgeルール確認: $rule ✓ (ENABLED)"
            else
                log_warning "EventBridgeルールが無効です: $rule ($rule_state)"
            fi
        else
            log_error "EventBridgeルールが見つかりません: $rule"
            validation_errors=$((validation_errors + 1))
        fi
    done
    
    # 結果サマリー
    if [[ "$validation_errors" -eq 0 ]]; then
        log_success "設定検証が完了しました。問題は見つかりませんでした。"
        return 0
    else
        log_error "設定検証で $validation_errors 個の問題が見つかりました。"
        return 1
    fi
}

# 環境間設定同期
sync_configuration() {
    log_info "環境間設定同期は未実装です"
    log_info "手動でexport/importを使用してください："
    echo "  1. $0 SOURCE_ENV export -f config-temp.json"
    echo "  2. $0 TARGET_ENV import -f config-temp.json"
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム 設定管理"
    echo "============================================"
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Action: $ACTION"
    echo ""
    
    # AWS接続確認
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS認証情報が設定されていません"
        exit 1
    fi
    
    confirm_action
    
    case $ACTION in
        export)
            export_parameter_store
            ;;
        import)
            import_parameter_store
            ;;
        backup)
            backup_configuration
            ;;
        restore)
            restore_configuration
            ;;
        validate)
            validate_configuration
            ;;
        sync)
            sync_configuration
            ;;
        *)
            log_error "不明なアクション: $ACTION"
            show_help
            exit 1
            ;;
    esac
}

# スクリプト実行
main "$@"