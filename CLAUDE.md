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

## Important Implementation Notes

- Google Sheets structure: "保有銘柄" sheet (holdings) and "ウォッチリスト" sheet (watchlist)
- Holdings sheet columns: symbol, name, quantity, purchase_price
- Watchlist sheet columns: symbol, name
- All external API calls include retry logic with exponential backoff
- Technical indicators use 25/75 period moving averages and 14-period RSI
- Analysis prompts include technical indicators and portfolio context
- Error handling distinguishes between temporary, configuration, and critical errors
- CloudWatch metrics track API response times and success rates