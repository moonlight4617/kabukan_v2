# CLAUDE.md

日本語で応答すること
guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based stock analysis and notification application built for AWS Lambda. The system:
- Fetches stock data from Google Sheets (holdings and watchlist)
- Performs AI-powered analysis using Google Gemini API
- Sends notifications via Slack
- Runs on scheduled intervals (daily, weekly, monthly)

## Architecture

**Tech Stack:**
- AWS Lambda (Python 3.11) with Event Bridge scheduling
- Google Sheets API for data source
- Google Gemini AI for analysis
- Slack webhooks for notifications
- AWS Parameter Store for configuration
- CloudWatch for logging and metrics

**Core Components:**
- `ConfigManager` - AWS Parameter Store integration and Google Sheets configuration
- `GoogleSheetsService` - Fetches holdings and watchlist data
- `StockDataService` - Yahoo Finance integration with historical data
- `TechnicalIndicatorService` - RSI, MACD, moving averages, breakout detection
- `AnalysisService` - Gemini API integration with daily/weekly/monthly analysis types
- `NotificationService` - Slack webhook integration
- `LambdaHandler` - Event Bridge event processing and service orchestration

## Analysis Types

**Daily Analysis:** Technical indicators, buy/sell/hold recommendations for holdings, buy recommendations for watchlist
**Weekly Analysis:** Portfolio performance analysis, returns, volatility, benchmark comparison  
**Monthly Analysis:** Country/sector analysis, rebalancing advice, diversification assessment

## Development Commands

**Testing:**
```bash
pytest --cov=src --cov-report=xml --cov-report=term tests/
```

**Linting:**
```bash
flake8 src tests
black --check src tests
```

**Dependencies:**
```bash
pip install -r requirements.txt
pip install pytest pytest-cov pytest-mock flake8 black
```

**AWS Deployment:**
```bash
sam build
sam deploy --config-env [staging|production]
```

## Key Configuration

**Parameter Store paths:**
- `/stock-analysis/google-sheets-id` - Spreadsheet ID
- `/stock-analysis/google-credentials` - Service account JSON (SecureString)
- `/stock-analysis/gemini-api-key` - Gemini API key (SecureString)
- `/stock-analysis/slack-webhook` - Slack webhook URL (SecureString)

**Event Bridge schedules:**
- Daily: `0 22 ? * MON-FRI *` (22:00 weekdays)
- Weekly: `0 23 ? * FRI *` (Friday 23:00)
- Monthly: `0 23 L * ? *` (Last day of month 23:00)

## Data Models

**Core Classes:**
- `StockConfig` - 保有銘柄設定（symbol, name, quantity, purchase_price）
- `WatchlistStock` - ウォッチリスト銘柄（symbol, name）
- `StockData` - 市場データ（prices, volume, timestamp, 履歴データ）
- `StockHolding` - 保有株式（設定+市場データ+計算値）
- `Portfolio` - ポートフォリオ全体（holdings, 合計値, パフォーマンス指標）
- `GoogleSheetsConfig` - Google Sheets設定

**Analysis Models:**
- `AnalysisType` - 分析タイプ（DAILY, WEEKLY, MONTHLY）
- `RecommendationType` - 推奨タイプ（BUY, SELL, HOLD, STRONG_BUY, STRONG_SELL）
- `RiskLevel` - リスクレベル（LOW, MEDIUM, HIGH, VERY_HIGH）
- `TechnicalSignal` - テクニカルシグナル（BULLISH, BEARISH, NEUTRAL）
- `TechnicalIndicators` - テクニカル指標（RSI, MACD, 移動平均、ブレイクアウト等）
- `Recommendation` - AI推奨（type, symbol, confidence, reasoning, target_price等）
- `RiskAssessment` - リスク評価（overall_risk, diversification_score, 業種/国別集中度等）
- `AnalysisResult` - 分析結果（summary, recommendations, risk_assessment, market_outlook等）

**Validation:**
- `StockValidator` - 株式データ検証（銘柄コード、価格、数量等）
- `ConfigValidator` - 設定データ検証（API keys, URLs等）
- `DataCollectionValidator` - 一括データ検証
- `AnalysisValidator` - 分析結果検証（推奨の整合性、テクニカル指標等）
- `AnalysisCollectionValidator` - 複数分析結果の一貫性検証
- すべてのデータクラスに組み込みvalidation機能

## Development Setup

**Local Development:**
```bash
setup.bat                    # 開発環境自動セットアップ
dev.bat run daily           # 日次分析実行
dev.bat test                # テスト実行
dev.bat format              # コードフォーマット
dev.bat lint                # リンティング
```

## Important Implementation Notes

- Google Sheets structure: "保有銘柄" sheet (holdings) and "ウォッチリスト" sheet (watchlist)
- Holdings sheet columns: symbol, name, quantity, purchase_price
- Watchlist sheet columns: symbol, name  
- Data validation at multiple levels: input validation, business logic validation, configuration validation
- Comprehensive error handling with ValidationError for user-friendly messages
- All external API calls include retry logic with exponential backoff
- Technical indicators use 25/75 period moving averages and 14-period RSI
- Analysis prompts include technical indicators and portfolio context
- Error handling distinguishes between temporary, configuration, and critical errors
- CloudWatch metrics track API response times and success rates
- Portfolio calculations include unrealized gains/losses, daily changes, performance metrics