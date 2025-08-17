# 株式分析システム Makefile

.PHONY: help setup build test deploy clean lint format install dev-install
.DEFAULT_GOAL := help

# 変数
ENVIRONMENT ?= dev
PYTHON ?= python3
PIP ?= pip3
SAM ?= sam
AWS ?= aws

# カラー定義
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m

# ヘルプ
help: ## ヘルプを表示
	@echo "$(BLUE)株式分析システム Makefile$(NC)"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make <target> [ENVIRONMENT=dev|staging|prod]"
	@echo ""
	@echo "$(YELLOW)Targets:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make setup                    # 初期セットアップ"
	@echo "  make test                     # テスト実行"
	@echo "  make deploy ENVIRONMENT=dev   # 開発環境にデプロイ"
	@echo "  make deploy ENVIRONMENT=prod  # 本番環境にデプロイ"

# セットアップ
setup: ## 開発環境をセットアップ
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@if [ -f scripts/setup-env.sh ]; then \
		chmod +x scripts/setup-env.sh; \
		./scripts/setup-env.sh $(ENVIRONMENT); \
	else \
		echo "$(RED)Setup script not found$(NC)"; \
		exit 1; \
	fi

# 依存関係インストール
install: ## 本番依存関係をインストール
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# 開発依存関係インストール
dev-install: install ## 開発依存関係をインストール
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install -r requirements-dev.txt

# 仮想環境作成
venv: ## 仮想環境を作成
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv venv
	@echo "$(GREEN)Virtual environment created. Activate with:$(NC)"
	@echo "  source venv/bin/activate  # Linux/Mac"
	@echo "  venv\\Scripts\\activate    # Windows"

# ビルド
build: ## SAMビルドを実行
	@echo "$(BLUE)Building SAM application...$(NC)"
	$(SAM) build

# テスト
test: ## 全テストを実行
	@echo "$(BLUE)Running tests...$(NC)"
	@if [ -f scripts/local-test.sh ]; then \
		chmod +x scripts/local-test.sh; \
		./scripts/local-test.sh all; \
	else \
		$(PYTHON) -m pytest tests/ -v; \
	fi

# 単体テスト
test-unit: ## 単体テストを実行
	@echo "$(BLUE)Running unit tests...$(NC)"
	@if [ -f scripts/local-test.sh ]; then \
		chmod +x scripts/local-test.sh; \
		./scripts/local-test.sh unit --coverage; \
	else \
		$(PYTHON) -m pytest tests/unit/ -v --cov=src; \
	fi

# 統合テスト
test-integration: ## 統合テストを実行
	@echo "$(BLUE)Running integration tests...$(NC)"
	@if [ -f scripts/local-test.sh ]; then \
		chmod +x scripts/local-test.sh; \
		./scripts/local-test.sh integration; \
	else \
		$(PYTHON) -m pytest tests/integration/ -v; \
	fi

# リンティング
lint: ## コード品質チェックを実行
	@echo "$(BLUE)Running linting...$(NC)"
	@if [ -f scripts/local-test.sh ]; then \
		chmod +x scripts/local-test.sh; \
		./scripts/local-test.sh lint; \
	else \
		black --check src/ tests/; \
		isort --check-only src/ tests/; \
		flake8 src/ tests/; \
		mypy src/; \
	fi

# フォーマット
format: ## コードフォーマットを実行
	@echo "$(BLUE)Formatting code...$(NC)"
	black src/ tests/
	isort src/ tests/
	@echo "$(GREEN)Code formatting completed$(NC)"

# セキュリティチェック
security: ## セキュリティチェックを実行
	@echo "$(BLUE)Running security checks...$(NC)"
	bandit -r src/
	safety check

# ローカル実行
local-api: ## SAM Local APIを起動
	@echo "$(BLUE)Starting SAM Local API...$(NC)"
	$(SAM) local start-api --env-vars env.json

# Lambda関数のローカル実行
local-invoke: ## Lambda関数をローカル実行
	@echo "$(BLUE)Invoking Lambda function locally...$(NC)"
	$(SAM) local invoke StockAnalysisFunction --event events/daily-event.json

# デプロイ
deploy: build ## 指定環境にデプロイ
	@echo "$(BLUE)Deploying to $(ENVIRONMENT) environment...$(NC)"
	@if [ -f scripts/deploy.sh ]; then \
		chmod +x scripts/deploy.sh; \
		./scripts/deploy.sh $(ENVIRONMENT); \
	else \
		$(SAM) deploy --config-env $(ENVIRONMENT); \
	fi

# ガイド付きデプロイ
deploy-guided: build ## ガイド付きデプロイ
	@echo "$(BLUE)Guided deployment to $(ENVIRONMENT) environment...$(NC)"
	@if [ -f scripts/deploy.sh ]; then \
		chmod +x scripts/deploy.sh; \
		./scripts/deploy.sh $(ENVIRONMENT) --guided; \
	else \
		$(SAM) deploy --guided --config-env $(ENVIRONMENT); \
	fi

# ヘルスチェック
health-check: ## デプロイ後のヘルスチェック
	@echo "$(BLUE)Running health check for $(ENVIRONMENT)...$(NC)"
	@if [ -f scripts/health-check.sh ]; then \
		chmod +x scripts/health-check.sh; \
		./scripts/health-check.sh $(ENVIRONMENT); \
	else \
		echo "$(YELLOW)Health check script not found$(NC)"; \
	fi

# ロールバック
rollback: ## 前のバージョンにロールバック
	@echo "$(BLUE)Rolling back $(ENVIRONMENT) environment...$(NC)"
	@if [ -f scripts/rollback.sh ]; then \
		chmod +x scripts/rollback.sh; \
		./scripts/rollback.sh $(ENVIRONMENT); \
	else \
		echo "$(RED)Rollback script not found$(NC)"; \
		exit 1; \
	fi

# 設定エクスポート
config-export: ## 設定をエクスポート
	@echo "$(BLUE)Exporting configuration for $(ENVIRONMENT)...$(NC)"
	@if [ -f scripts/manage-config.sh ]; then \
		chmod +x scripts/manage-config.sh; \
		./scripts/manage-config.sh $(ENVIRONMENT) export; \
	else \
		echo "$(RED)Config management script not found$(NC)"; \
		exit 1; \
	fi

# 設定バックアップ
config-backup: ## 設定をバックアップ
	@echo "$(BLUE)Backing up configuration for $(ENVIRONMENT)...$(NC)"
	@if [ -f scripts/manage-config.sh ]; then \
		chmod +x scripts/manage-config.sh; \
		./scripts/manage-config.sh $(ENVIRONMENT) backup; \
	else \
		echo "$(RED)Config management script not found$(NC)"; \
		exit 1; \
	fi

# 設定検証
config-validate: ## 設定を検証
	@echo "$(BLUE)Validating configuration for $(ENVIRONMENT)...$(NC)"
	@if [ -f scripts/manage-config.sh ]; then \
		chmod +x scripts/manage-config.sh; \
		./scripts/manage-config.sh $(ENVIRONMENT) validate; \
	else \
		echo "$(RED)Config management script not found$(NC)"; \
		exit 1; \
	fi

# ログ確認
logs: ## CloudWatchログを確認
	@echo "$(BLUE)Fetching logs for $(ENVIRONMENT)...$(NC)"
	$(AWS) logs tail /aws/lambda/stock-analysis-$(ENVIRONMENT) --follow

# ログファイル取得
logs-file: ## ログをファイルに保存
	@echo "$(BLUE)Saving logs to file for $(ENVIRONMENT)...$(NC)"
	$(AWS) logs filter-log-events \
		--log-group-name /aws/lambda/stock-analysis-$(ENVIRONMENT) \
		--start-time $$(date -d '1 hour ago' +%s)000 \
		--output text > logs/$(ENVIRONMENT)-$$(date +%Y%m%d_%H%M%S).log
	@echo "$(GREEN)Logs saved to logs/ directory$(NC)"

# メトリクス確認
metrics: ## CloudWatchメトリクスを確認
	@echo "$(BLUE)Fetching metrics for $(ENVIRONMENT)...$(NC)"
	$(AWS) cloudwatch get-metric-statistics \
		--namespace AWS/Lambda \
		--metric-name Duration \
		--dimensions Name=FunctionName,Value=stock-analysis-$(ENVIRONMENT) \
		--start-time $$(date -d '1 hour ago' --iso-8601) \
		--end-time $$(date --iso-8601) \
		--period 300 \
		--statistics Average,Maximum \
		--output table

# Lambda関数の実行
invoke: ## Lambda関数を実行
	@echo "$(BLUE)Invoking Lambda function for $(ENVIRONMENT)...$(NC)"
	$(AWS) lambda invoke \
		--function-name stock-analysis-$(ENVIRONMENT) \
		--payload '{"source": "manual", "detail-type": "Manual Trigger", "detail": {"analysis_type": "daily"}}' \
		--output json \
		response.json
	@cat response.json | jq .
	@rm -f response.json

# スタック削除
destroy: ## CloudFormationスタックを削除
	@echo "$(RED)WARNING: This will delete the entire stack for $(ENVIRONMENT)!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		$(AWS) cloudformation delete-stack --stack-name stock-analysis-$(ENVIRONMENT); \
		echo "$(YELLOW)Stack deletion initiated. Check AWS Console for progress.$(NC)"; \
	else \
		echo "$(GREEN)Operation cancelled.$(NC)"; \
	fi

# クリーンアップ
clean: ## 一時ファイルをクリーンアップ
	@echo "$(BLUE)Cleaning up temporary files...$(NC)"
	rm -rf .aws-sam/build/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf tests/coverage/
	rm -rf tests/reports/
	rm -f .coverage
	rm -f response.json
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleanup completed$(NC)"

# 開発者向けワークフロー
dev-setup: venv dev-install setup ## 開発環境の完全セットアップ
	@echo "$(GREEN)Development environment is ready!$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Activate virtual environment: source venv/bin/activate"
	@echo "  2. Edit .env.dev with your configuration"
	@echo "  3. Run tests: make test"
	@echo "  4. Deploy: make deploy ENVIRONMENT=dev"

# CI/CD用ワークフロー
ci: lint security test ## CI用の全チェックを実行
	@echo "$(GREEN)All CI checks passed!$(NC)"

# リリース準備
release-prepare: ci build ## リリース準備（全チェック + ビルド）
	@echo "$(GREEN)Release preparation completed!$(NC)"

# 開発サーバー
dev-server: ## 開発用サーバーを起動
	@echo "$(BLUE)Starting development server...$(NC)"
	@echo "$(YELLOW)This will start SAM Local API and watch for changes$(NC)"
	$(SAM) local start-api --env-vars env.json --warm-containers EAGER

# 環境情報表示
info: ## 環境情報を表示
	@echo "$(BLUE)Environment Information:$(NC)"
	@echo "  Environment: $(ENVIRONMENT)"
	@echo "  Python: $$($(PYTHON) --version 2>&1 || echo 'Not found')"
	@echo "  SAM CLI: $$($(SAM) --version 2>&1 || echo 'Not found')"
	@echo "  AWS CLI: $$($(AWS) --version 2>&1 || echo 'Not found')"
	@echo "  Git: $$(git --version 2>&1 || echo 'Not found')"
	@if [ -f .env.$(ENVIRONMENT) ]; then \
		echo "  Config file: .env.$(ENVIRONMENT) ✓"; \
	else \
		echo "  Config file: .env.$(ENVIRONMENT) ✗"; \
	fi

# ファイル監視モード
watch: ## ファイル変更を監視してテストを自動実行
	@echo "$(BLUE)Watching for file changes...$(NC)"
	@if [ -f scripts/local-test.sh ]; then \
		chmod +x scripts/local-test.sh; \
		./scripts/local-test.sh unit --watch; \
	else \
		echo "$(YELLOW)File watching requires local-test.sh script$(NC)"; \
	fi