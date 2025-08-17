#!/bin/bash

# ローカルテスト実行スクリプト
# Usage: ./scripts/local-test.sh [test-type] [options]

set -e

# デフォルト値
TEST_TYPE="all"
VERBOSE=false
COVERAGE=false
PARALLEL=false
WATCH=false

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ヘルプ表示
show_help() {
    echo "ローカルテスト実行スクリプト"
    echo ""
    echo "Usage: $0 [TEST_TYPE] [OPTIONS]"
    echo ""
    echo "TEST_TYPE:"
    echo "  all        全てのテスト (default)"
    echo "  unit       単体テストのみ"
    echo "  integration 統合テストのみ"
    echo "  lint       リンティングのみ"
    echo "  security   セキュリティチェックのみ"
    echo ""
    echo "OPTIONS:"
    echo "  -v, --verbose     詳細出力"
    echo "  -c, --coverage    カバレッジレポート生成"
    echo "  -p, --parallel    並列実行"
    echo "  -w, --watch       ファイル変更監視"
    echo "  -h, --help        このヘルプを表示"
    echo ""
    echo "Examples:"
    echo "  $0 unit --coverage       単体テストをカバレッジ付きで実行"
    echo "  $0 all --parallel        全テストを並列実行"
    echo "  $0 lint                  リンティングのみ実行"
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
        all|unit|integration|lint|security)
            TEST_TYPE="$1"
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -w|--watch)
            WATCH=true
            shift
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

# 仮想環境の確認
check_virtual_env() {
    if [[ -z "$VIRTUAL_ENV" ]]; then
        log_warning "仮想環境が有効化されていません"
        if [[ -d "venv" ]]; then
            log_info "仮想環境を有効化中..."
            source venv/bin/activate || source venv/Scripts/activate
        elif [[ -d ".venv" ]]; then
            log_info "仮想環境を有効化中..."
            source .venv/bin/activate || source .venv/Scripts/activate
        else
            log_error "仮想環境が見つかりません。setup.sh を実行してください。"
            exit 1
        fi
    fi
    log_success "仮想環境: $VIRTUAL_ENV"
}

# 依存関係チェック
check_dependencies() {
    log_info "依存関係をチェック中..."
    
    if ! python -c "import pytest" 2>/dev/null; then
        log_warning "pytest がインストールされていません。インストール中..."
        pip install -r requirements-dev.txt
    fi
    
    log_success "依存関係チェック完了"
}

# 環境変数設定
setup_test_env() {
    log_info "テスト環境を設定中..."
    
    export ENVIRONMENT=test
    export LOG_LEVEL=DEBUG
    export TEST_DEBUG=true
    export DISABLE_MOCKS=false
    export AWS_DEFAULT_REGION=us-east-1
    export AWS_ACCESS_KEY_ID=test-access-key
    export AWS_SECRET_ACCESS_KEY=test-secret-key
    
    # テストディレクトリを作成
    mkdir -p tests/reports
    mkdir -p tests/coverage
    
    log_success "テスト環境設定完了"
}

# 単体テスト実行
run_unit_tests() {
    log_info "単体テストを実行中..."
    
    local test_cmd="python -m pytest tests/unit/"
    local test_args=""
    
    if [[ "$VERBOSE" == "true" ]]; then
        test_args="$test_args --verbose"
    fi
    
    if [[ "$COVERAGE" == "true" ]]; then
        test_args="$test_args --cov=src --cov-report=html:tests/coverage/unit-html --cov-report=xml:tests/coverage/unit-coverage.xml --cov-report=term"
    fi
    
    if [[ "$PARALLEL" == "true" ]]; then
        test_args="$test_args -n auto"
    fi
    
    test_args="$test_args --junitxml=tests/reports/unit-results.xml --tb=short"
    
    if eval "$test_cmd $test_args"; then
        log_success "単体テスト完了"
        return 0
    else
        log_error "単体テストに失敗しました"
        return 1
    fi
}

# 統合テスト実行
run_integration_tests() {
    log_info "統合テストを実行中..."
    
    local test_cmd="python -m pytest tests/integration/"
    local test_args="--junitxml=tests/reports/integration-results.xml --tb=short -m integration"
    
    if [[ "$VERBOSE" == "true" ]]; then
        test_args="$test_args --verbose"
    fi
    
    if eval "$test_cmd $test_args"; then
        log_success "統合テスト完了"
        return 0
    else
        log_error "統合テストに失敗しました"
        return 1
    fi
}

# リンティング実行
run_lint() {
    log_info "リンティングを実行中..."
    
    local lint_failed=false
    
    # Black (フォーマットチェック)
    log_info "Black フォーマットチェック..."
    if ! black --check --diff src/ tests/; then
        log_warning "Black フォーマットチェックに失敗"
        lint_failed=true
    fi
    
    # isort (インポートソート)
    log_info "isort インポートソートチェック..."
    if ! isort --check-only --diff src/ tests/; then
        log_warning "isort チェックに失敗"
        lint_failed=true
    fi
    
    # flake8 (リンティング)
    log_info "flake8 リンティング..."
    if ! flake8 src/ tests/ --max-line-length=100 --extend-ignore=E203,W503; then
        log_warning "flake8 リンティングに失敗"
        lint_failed=true
    fi
    
    # mypy (型チェック)
    log_info "mypy 型チェック..."
    if ! mypy src/ --ignore-missing-imports --no-strict-optional; then
        log_warning "mypy 型チェックに失敗"
        lint_failed=true
    fi
    
    if [[ "$lint_failed" == "true" ]]; then
        log_error "リンティングチェックに失敗しました"
        return 1
    else
        log_success "リンティングチェック完了"
        return 0
    fi
}

# セキュリティチェック実行
run_security_check() {
    log_info "セキュリティチェックを実行中..."
    
    local security_failed=false
    
    # bandit (セキュリティリンティング)
    log_info "bandit セキュリティリンティング..."
    if ! bandit -r src/ --severity-level medium; then
        log_warning "bandit セキュリティチェックで警告があります"
        security_failed=true
    fi
    
    # safety (依存関係脆弱性チェック)
    log_info "safety 依存関係脆弱性チェック..."
    if ! safety check; then
        log_warning "safety チェックで脆弱性が検出されました"
        security_failed=true
    fi
    
    if [[ "$security_failed" == "true" ]]; then
        log_error "セキュリティチェックで問題が検出されました"
        return 1
    else
        log_success "セキュリティチェック完了"
        return 0
    fi
}

# ファイル監視モード
run_watch_mode() {
    log_info "ファイル変更監視モードを開始..."
    log_info "ファイルが変更されると自動でテストが実行されます"
    log_info "終了するには Ctrl+C を押してください"
    
    if command -v inotifywait &> /dev/null; then
        while true; do
            inotifywait -r -e modify,create,delete src/ tests/ 2>/dev/null
            log_info "ファイル変更を検出。テストを実行中..."
            run_tests
            echo ""
            log_info "監視を継続中..."
        done
    elif command -v fswatch &> /dev/null; then
        fswatch -o src/ tests/ | while read num; do
            log_info "ファイル変更を検出。テストを実行中..."
            run_tests
            echo ""
            log_info "監視を継続中..."
        done
    else
        log_warning "ファイル監視ツール (inotifywait or fswatch) がインストールされていません"
        log_info "手動でテストを実行します..."
        run_tests
    fi
}

# テスト実行
run_tests() {
    local test_failed=false
    
    case $TEST_TYPE in
        "unit")
            if ! run_unit_tests; then
                test_failed=true
            fi
            ;;
        "integration")
            if ! run_integration_tests; then
                test_failed=true
            fi
            ;;
        "lint")
            if ! run_lint; then
                test_failed=true
            fi
            ;;
        "security")
            if ! run_security_check; then
                test_failed=true
            fi
            ;;
        "all")
            if ! run_lint; then
                test_failed=true
            fi
            if ! run_security_check; then
                test_failed=true
            fi
            if ! run_unit_tests; then
                test_failed=true
            fi
            if ! run_integration_tests; then
                test_failed=true
            fi
            ;;
    esac
    
    return $([ "$test_failed" == "true" ] && echo 1 || echo 0)
}

# カバレッジレポート表示
show_coverage_report() {
    if [[ "$COVERAGE" == "true" && "$TEST_TYPE" != "lint" && "$TEST_TYPE" != "security" ]]; then
        log_info "カバレッジレポート:"
        if [[ -f "tests/coverage/unit-coverage.xml" ]]; then
            log_info "カバレッジレポートが生成されました: tests/coverage/unit-html/index.html"
        fi
    fi
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム ローカルテスト"
    echo "============================================"
    echo ""
    
    check_virtual_env
    check_dependencies
    setup_test_env
    
    if [[ "$WATCH" == "true" ]]; then
        run_watch_mode
    else
        if run_tests; then
            show_coverage_report
            log_success "全てのテストが完了しました！"
            exit 0
        else
            log_error "一部のテストに失敗しました"
            exit 1
        fi
    fi
}

# スクリプト実行
main "$@"