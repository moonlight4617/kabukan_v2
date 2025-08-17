#!/bin/bash

# 環境セットアップスクリプト
# Usage: ./scripts/setup-env.sh [environment]

set -e

ENVIRONMENT=${1:-dev}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Pythonバージョンチェック
check_python() {
    log_info "Pythonバージョンをチェック中..."
    
    if command -v python3.11 &> /dev/null; then
        PYTHON_CMD="python3.11"
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        if [[ "$PYTHON_VERSION" != "3.11" ]]; then
            log_warning "Python 3.11が推奨ですが、$PYTHON_VERSION を使用します"
        fi
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
        PYTHON_VERSION=$(python --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        if [[ "$PYTHON_VERSION" < "3.11" ]]; then
            log_error "Python 3.11以上が必要です。現在のバージョン: $PYTHON_VERSION"
            exit 1
        fi
    else
        log_error "Pythonがインストールされていません"
        exit 1
    fi
    
    log_success "Python: $($PYTHON_CMD --version)"
}

# 仮想環境セットアップ
setup_virtual_env() {
    log_info "仮想環境をセットアップ中..."
    
    cd "$PROJECT_ROOT"
    
    # 仮想環境が存在しない場合は作成
    if [[ ! -d "venv" ]]; then
        log_info "仮想環境を作成中..."
        $PYTHON_CMD -m venv venv
    fi
    
    # 仮想環境を有効化
    if [[ -f "venv/bin/activate" ]]; then
        source venv/bin/activate
    elif [[ -f "venv/Scripts/activate" ]]; then
        source venv/Scripts/activate
    else
        log_error "仮想環境の有効化に失敗しました"
        exit 1
    fi
    
    log_success "仮想環境が有効化されました: $VIRTUAL_ENV"
}

# 依存関係インストール
install_dependencies() {
    log_info "依存関係をインストール中..."
    
    # pipをアップグレード
    pip install --upgrade pip
    
    # 本番依存関係をインストール
    pip install -r requirements.txt
    
    # 開発依存関係をインストール（開発環境の場合）
    if [[ "$ENVIRONMENT" == "dev" ]]; then
        pip install -r requirements-dev.txt
    fi
    
    log_success "依存関係のインストールが完了しました"
}

# 環境設定ファイル作成
create_env_file() {
    log_info "環境設定ファイルを作成中..."
    
    local env_file=".env.$ENVIRONMENT"
    
    if [[ -f "$env_file" ]]; then
        log_info "既存の環境設定ファイルが見つかりました: $env_file"
        return
    fi
    
    cat > "$env_file" << EOF
# 株式分析システム環境設定 ($ENVIRONMENT)

# 基本設定
ENVIRONMENT=$ENVIRONMENT
LOG_LEVEL=$([ "$ENVIRONMENT" = "prod" ] && echo "INFO" || echo "DEBUG")
AWS_REGION=us-east-1

# AWS設定
PARAMETER_STORE_PREFIX=/stock-analysis-$ENVIRONMENT
CLOUDWATCH_NAMESPACE=StockAnalysis/$ENVIRONMENT
LOG_GROUP_NAME=/aws/lambda/stock-analysis-$ENVIRONMENT

# 機能設定
ENABLE_DAILY_ANALYSIS=true
ENABLE_WEEKLY_ANALYSIS=true
ENABLE_MONTHLY_ANALYSIS=$([ "$ENVIRONMENT" = "prod" ] && echo "true" || echo "false")

# テスト設定（開発環境のみ）
$([ "$ENVIRONMENT" = "dev" ] && cat << 'DEVEOF'
TEST_DEBUG=true
DISABLE_MOCKS=false
TEST_TIMEOUT=30
DEVEOF
)

# 本番設定（本番環境のみ）
$([ "$ENVIRONMENT" = "prod" ] && cat << 'PRODEOF'
ENABLE_PERFORMANCE_MONITORING=true
ENABLE_DETAILED_LOGGING=false
PRODEOF
)

# 外部サービス設定（実際の値は Parameter Store から取得）
# SLACK_WEBHOOK_URL=
# GOOGLE_SHEETS_SPREADSHEET_ID=
# GOOGLE_SHEETS_CREDENTIALS=
# GEMINI_API_KEY=
EOF
    
    log_success "環境設定ファイルを作成しました: $env_file"
    log_info "必要に応じて設定値を編集してください"
}

# AWS CLI設定チェック
check_aws_cli() {
    log_info "AWS CLI設定をチェック中..."
    
    if ! command -v aws &> /dev/null; then
        log_warning "AWS CLIがインストールされていません"
        log_info "インストール: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        return
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_warning "AWS認証情報が設定されていません"
        log_info "設定コマンド: aws configure"
        return
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local user_arn=$(aws sts get-caller-identity --query Arn --output text)
    log_success "AWS設定OK - Account: $account_id, User: $user_arn"
}

# SAM CLI設定チェック
check_sam_cli() {
    log_info "SAM CLI設定をチェック中..."
    
    if ! command -v sam &> /dev/null; then
        log_warning "SAM CLIがインストールされていません"
        log_info "インストール: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
        return
    fi
    
    local sam_version=$(sam --version)
    log_success "SAM CLI: $sam_version"
}

# 開発ツールセットアップ
setup_dev_tools() {
    if [[ "$ENVIRONMENT" != "dev" ]]; then
        return
    fi
    
    log_info "開発ツールをセットアップ中..."
    
    # pre-commit設定
    if command -v pre-commit &> /dev/null; then
        log_info "pre-commit hooksを設定中..."
        pre-commit install
        log_success "pre-commit hooksが設定されました"
    fi
    
    # VSCode設定作成
    if [[ ! -d ".vscode" ]]; then
        mkdir -p .vscode
        
        # settings.json
        cat > .vscode/settings.json << 'EOF'
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.formatting.blackArgs": ["--line-length=100"],
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        ".pytest_cache": true,
        ".coverage": true,
        "htmlcov": true,
        ".aws-sam": true
    }
}
EOF
        
        # launch.json
        cat > .vscode/launch.json << 'EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "envFile": "${workspaceFolder}/.env.dev"
        },
        {
            "name": "Python: Pytest",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["${workspaceFolder}/tests", "-v"],
            "console": "integratedTerminal",
            "envFile": "${workspaceFolder}/.env.dev"
        },
        {
            "name": "SAM Local: Daily Analysis",
            "type": "aws-sam",
            "request": "direct-invoke",
            "invokeTarget": {
                "target": "template",
                "templatePath": "${workspaceFolder}/template.yaml",
                "logicalId": "StockAnalysisFunction"
            },
            "lambda": {
                "payload": {
                    "json": {
                        "source": "aws.events",
                        "detail-type": "Scheduled Event",
                        "detail": {
                            "analysis_type": "daily"
                        }
                    }
                },
                "environmentVariables": {
                    "ENVIRONMENT": "dev"
                }
            }
        }
    ]
}
EOF
        
        log_success "VSCode設定を作成しました"
    fi
}

# テストディレクトリ作成
create_test_directories() {
    log_info "テストディレクトリを作成中..."
    
    local test_dirs=(
        "tests/reports"
        "tests/coverage"
        "tests/fixtures/data"
        "logs"
        ".aws-sam/build"
    )
    
    for dir in "${test_dirs[@]}"; do
        mkdir -p "$dir"
    done
    
    log_success "テストディレクトリを作成しました"
}

# 設定検証
validate_setup() {
    log_info "セットアップ検証中..."
    
    local validation_failed=false
    
    # Python importテスト
    if ! python -c "import src.models.data_models" 2>/dev/null; then
        log_warning "Pythonモジュールのimportに失敗しました"
        validation_failed=true
    fi
    
    # 必要なファイル確認
    local required_files=(
        "template.yaml"
        "samconfig.toml"
        "requirements.txt"
        "pytest.ini"
    )
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_warning "必要なファイルが見つかりません: $file"
            validation_failed=true
        fi
    done
    
    if [[ "$validation_failed" == "true" ]]; then
        log_error "セットアップ検証で問題が見つかりました"
        return 1
    else
        log_success "セットアップ検証が完了しました"
        return 0
    fi
}

# 使用方法表示
show_usage() {
    echo ""
    echo "============================================"
    echo "  セットアップ完了！"
    echo "============================================"
    echo ""
    echo "次のステップ:"
    echo ""
    
    if [[ "$ENVIRONMENT" == "dev" ]]; then
        echo "1. 開発用設定:"
        echo "   export ENVIRONMENT=$ENVIRONMENT"
        echo "   source venv/bin/activate  # または venv/Scripts/activate"
        echo ""
        echo "2. テスト実行:"
        echo "   ./scripts/local-test.sh unit"
        echo "   ./scripts/local-test.sh all --coverage"
        echo ""
        echo "3. ローカル開発:"
        echo "   sam local start-api"
        echo "   sam local invoke StockAnalysisFunction"
        echo ""
    fi
    
    echo "4. デプロイ:"
    echo "   ./scripts/deploy.sh $ENVIRONMENT --guided"
    echo ""
    echo "5. 設定ファイル編集:"
    echo "   vi .env.$ENVIRONMENT"
    echo ""
    echo "詳細な手順: README-deployment.md を参照してください"
    echo ""
}

# メイン処理
main() {
    echo "============================================"
    echo "  株式分析システム 環境セットアップ"
    echo "============================================"
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo ""
    
    check_python
    setup_virtual_env
    install_dependencies
    create_env_file
    check_aws_cli
    check_sam_cli
    setup_dev_tools
    create_test_directories
    
    if validate_setup; then
        show_usage
    else
        log_error "セットアップに失敗しました"
        exit 1
    fi
}

# スクリプト実行
main "$@"