# -*- coding: utf-8 -*-
"""
テスト環境用設定
"""

import os
from typing import Dict, Any

# テスト環境のベース設定
TEST_BASE_CONFIG = {
    "environment": "test",
    "debug_mode": True,
    "log_level": "DEBUG",
    "enable_mocking": True,
    "test_timeout": 30,
    "mock_external_apis": True
}

# AWS モック設定
AWS_MOCK_CONFIG = {
    "region": "us-east-1",
    "parameter_store": {
        "prefix": "/stock-analysis-test",
        "mock_parameters": {
            "/stock-analysis-test/google-sheets/spreadsheet-id": "test-spreadsheet-123",
            "/stock-analysis-test/google-sheets/credentials": '{"type": "service_account", "project_id": "test-project"}',
            "/stock-analysis-test/slack/webhook-url": "https://hooks.slack.com/test-webhook",
            "/stock-analysis-test/gemini/api-key": "test-gemini-api-key",
            "/stock-analysis-test/analysis/enable-daily": "true",
            "/stock-analysis-test/analysis/enable-weekly": "true",
            "/stock-analysis-test/analysis/enable-monthly": "false"
        }
    },
    "cloudwatch": {
        "namespace": "StockAnalysis/Test",
        "log_group": "/aws/lambda/stock-analysis-test"
    },
    "lambda": {
        "function_name": "stock-analysis-test-function",
        "memory_size": 256,
        "timeout": 300
    }
}

# Google Sheets モック設定
GOOGLE_SHEETS_MOCK_CONFIG = {
    "spreadsheet_id": "test-spreadsheet-123",
    "mock_data": {
        "portfolio": [
            ["Symbol", "Shares", "Purchase Price", "Purchase Date", "Region", "Sector"],
            ["AAPL", "100", "150.00", "2024-01-01", "US", "Technology"],
            ["GOOGL", "50", "2800.00", "2024-01-15", "US", "Technology"],
            ["MSFT", "75", "300.00", "2024-02-01", "US", "Technology"]
        ],
        "watchlist": [
            ["Symbol", "Target Price", "Region", "Sector", "Priority"],
            ["TSLA", "220.00", "US", "Automotive", "High"],
            ["AMD", "120.00", "US", "Technology", "Medium"],
            ["NVDA", "800.00", "US", "Technology", "High"]
        ]
    },
    "credentials": {
        "type": "service_account",
        "project_id": "test-project",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest-private-key\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
}

# Slack モック設定
SLACK_MOCK_CONFIG = {
    "webhook_url": "https://hooks.slack.com/services/test/webhook/url",
    "channels": {
        "default": "#stock-analysis-test",
        "alerts": "#alerts-test",
        "errors": "#errors-test"
    },
    "mock_responses": {
        "success": {
            "status_code": 200,
            "response": {"ok": True}
        },
        "failure": {
            "status_code": 400,
            "response": {"error": "invalid_payload"}
        },
        "rate_limit": {
            "status_code": 429,
            "response": {"error": "rate_limited"}
        }
    }
}

# Gemini AI モック設定
GEMINI_MOCK_CONFIG = {
    "api_key": "test-gemini-api-key",
    "model_name": "gemini-pro",
    "mock_responses": {
        "daily_analysis": {
            "analysis_id": "test-daily-001",
            "portfolio_summary": "ポートフォリオは全体的に良好なパフォーマンスを示しています。",
            "recommendations": [
                {
                    "symbol": "AAPL",
                    "action": "HOLD",
                    "confidence": 0.85,
                    "reasoning": "技術的指標が安定しており、継続保有を推奨します。",
                    "target_price": 180.0
                }
            ],
            "market_sentiment": "POSITIVE",
            "risk_assessment": "MEDIUM"
        },
        "weekly_analysis": {
            "analysis_id": "test-weekly-001",
            "portfolio_summary": "週次パフォーマンス: +3.2%の上昇を記録しました。",
            "recommendations": [],
            "market_sentiment": "POSITIVE",
            "risk_assessment": "LOW"
        },
        "monthly_analysis": {
            "analysis_id": "test-monthly-001",
            "portfolio_summary": "月次パフォーマンス: +5.8%の成長。セクター別では技術株が好調。",
            "recommendations": [
                {
                    "symbol": "Portfolio",
                    "action": "REBALANCE",
                    "confidence": 0.75,
                    "reasoning": "技術株の比重が高すぎるため、分散投資を検討してください。",
                    "target_price": None
                }
            ],
            "market_sentiment": "POSITIVE",
            "risk_assessment": "MEDIUM"
        }
    }
}

# Yahoo Finance モック設定
YAHOO_FINANCE_MOCK_CONFIG = {
    "mock_data": {
        "AAPL": {
            "symbol": "AAPL",
            "regularMarketPrice": 175.50,
            "previousClose": 174.00,
            "regularMarketOpen": 175.00,
            "regularMarketDayHigh": 176.00,
            "regularMarketDayLow": 174.50,
            "regularMarketVolume": 50000000,
            "marketCap": 2750000000000,
            "trailingPE": 28.5
        },
        "GOOGL": {
            "symbol": "GOOGL",
            "regularMarketPrice": 2950.00,
            "previousClose": 2930.00,
            "regularMarketOpen": 2940.00,
            "regularMarketDayHigh": 2960.00,
            "regularMarketDayLow": 2920.00,
            "regularMarketVolume": 1500000,
            "marketCap": 1900000000000,
            "trailingPE": 25.2
        },
        "MSFT": {
            "symbol": "MSFT",
            "regularMarketPrice": 380.00,
            "previousClose": 378.50,
            "regularMarketOpen": 379.00,
            "regularMarketDayHigh": 382.00,
            "regularMarketDayLow": 377.00,
            "regularMarketVolume": 30000000,
            "marketCap": 2800000000000,
            "trailingPE": 32.1
        },
        "TSLA": {
            "symbol": "TSLA",
            "regularMarketPrice": 220.00,
            "previousClose": 215.00,
            "regularMarketOpen": 218.00,
            "regularMarketDayHigh": 225.00,
            "regularMarketDayLow": 216.00,
            "regularMarketVolume": 80000000,
            "marketCap": 700000000000,
            "trailingPE": 65.5
        }
    },
    "historical_data_mock": {
        "periods": ["1d", "5d", "1mo", "3mo", "6mo", "1y"],
        "intervals": ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]
    }
}

# データベース/ストレージ モック設定
STORAGE_MOCK_CONFIG = {
    "cache": {
        "type": "memory",
        "ttl": 300,  # 5分
        "max_size": 1000
    },
    "persistence": {
        "type": "file",
        "base_path": "tests/fixtures/data"
    }
}

# テスト実行設定
TEST_EXECUTION_CONFIG = {
    "parallel_execution": True,
    "max_workers": 4,
    "test_data_cleanup": True,
    "mock_reset_between_tests": True,
    "performance_monitoring": True,
    "memory_leak_detection": True
}

# CI/CD 環境設定
CI_CD_CONFIG = {
    "github_actions": {
        "python_versions": ["3.11"],
        "test_matrix": [
            {"name": "unit", "path": "tests/unit", "coverage": True},
            {"name": "integration", "path": "tests/integration", "coverage": False},
            {"name": "performance", "path": "tests/performance", "coverage": False}
        ],
        "artifacts": ["coverage-reports", "test-reports", "logs"],
        "notifications": {
            "slack_webhook": "${SLACK_CI_WEBHOOK}",
            "on_failure": True,
            "on_success": False
        }
    },
    "environments": {
        "test": {
            "aws_region": "us-east-1",
            "parameter_store_prefix": "/stock-analysis-test",
            "cloudwatch_namespace": "StockAnalysis/Test"
        },
        "staging": {
            "aws_region": "us-east-1",
            "parameter_store_prefix": "/stock-analysis-staging",
            "cloudwatch_namespace": "StockAnalysis/Staging"
        },
        "production": {
            "aws_region": "us-east-1",
            "parameter_store_prefix": "/stock-analysis",
            "cloudwatch_namespace": "StockAnalysis"
        }
    }
}

# 統合設定
TEST_CONFIG = {
    **TEST_BASE_CONFIG,
    "aws": AWS_MOCK_CONFIG,
    "google_sheets": GOOGLE_SHEETS_MOCK_CONFIG,
    "slack": SLACK_MOCK_CONFIG,
    "gemini": GEMINI_MOCK_CONFIG,
    "yahoo_finance": YAHOO_FINANCE_MOCK_CONFIG,
    "storage": STORAGE_MOCK_CONFIG,
    "execution": TEST_EXECUTION_CONFIG,
    "ci_cd": CI_CD_CONFIG
}


class TestConfig:
    """テスト設定管理クラス"""
    
    def __init__(self, config_override: Dict[str, Any] = None):
        self.config = TEST_CONFIG.copy()
        if config_override:
            self._deep_update(self.config, config_override)
    
    def _deep_update(self, base_dict: Dict[str, Any], update_dict: Dict[str, Any]):
        """辞書の深い更新"""
        for key, value in update_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def get(self, key_path: str, default=None):
        """ドット記法でのキー取得"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any):
        """ドット記法でのキー設定"""
        keys = key_path.split('.')
        target = self.config
        
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        target[keys[-1]] = value
    
    def get_aws_config(self) -> Dict[str, Any]:
        """AWS設定を取得"""
        return self.config["aws"]
    
    def get_mock_config(self, service: str) -> Dict[str, Any]:
        """指定されたサービスのモック設定を取得"""
        return self.config.get(service, {})
    
    def is_mocking_enabled(self) -> bool:
        """モックが有効かどうか"""
        return self.config.get("enable_mocking", True)
    
    def get_ci_cd_config(self) -> Dict[str, Any]:
        """CI/CD設定を取得"""
        return self.config["ci_cd"]


# グローバル設定インスタンス
test_config = TestConfig()


# 環境変数からのオーバーライド
def load_test_config_from_env():
    """環境変数からテスト設定をロード"""
    overrides = {}
    
    # CI/CD環境検出
    if os.getenv("GITHUB_ACTIONS"):
        overrides["ci_cd.environment"] = "github_actions"
        overrides["execution.parallel_execution"] = True
    
    # デバッグモード
    if os.getenv("TEST_DEBUG"):
        overrides["debug_mode"] = True
        overrides["log_level"] = "DEBUG"
    
    # モック無効化
    if os.getenv("DISABLE_MOCKS"):
        overrides["enable_mocking"] = False
        overrides["mock_external_apis"] = False
    
    # テストタイムアウト
    if os.getenv("TEST_TIMEOUT"):
        overrides["test_timeout"] = int(os.getenv("TEST_TIMEOUT"))
    
    return TestConfig(overrides)


# 使用例
if __name__ == "__main__":
    config = load_test_config_from_env()
    
    print("Test Configuration:")
    print(f"Environment: {config.get('environment')}")
    print(f"Debug Mode: {config.get('debug_mode')}")
    print(f"Mocking Enabled: {config.is_mocking_enabled()}")
    print(f"AWS Region: {config.get('aws.region')}")
    print(f"Slack Webhook: {config.get('slack.webhook_url')}")