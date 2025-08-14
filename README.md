# 株式分析・通知システム

Google Gemini AIを使用した株式ポートフォリオ分析と通知システムです。Google Sheetsで管理する保有銘柄・ウォッチリストを自動分析し、Slackで結果を通知します。

## 🚀 クイックスタート

### 1. 開発環境のセットアップ

```bash
# 開発環境を自動セットアップ
setup.bat

# 仮想環境を有効化
venv\Scripts\activate

# 設定ファイルを編集
notepad .env.local
```

### 2. 設定ファイルの準備

`.env.local`ファイルに以下の設定を入力してください：

```env
GOOGLE_SHEETS_ID=your_google_spreadsheet_id_here
GEMINI_API_KEY=your_gemini_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 3. ローカル実行

```bash
# 日次分析を実行
dev.bat run daily

# 週次分析を実行
dev.bat run weekly

# 月次分析を実行
dev.bat run monthly
```

## 📊 機能概要

### 分析タイプ
- **日次分析**: テクニカル指標に基づく売買推奨
- **週次分析**: ポートフォリオのパフォーマンス分析
- **月次分析**: 国・業種別分析とリバランス提案

### テクニカル指標
- 移動平均線（ゴールデンクロス/デッドクロス）
- RSI（買われすぎ/売られすぎ判定）
- MACD（トレンド転換シグナル）
- 新高値/新安値ブレイク
- サポート・レジスタンス分析

## 🛠️ 開発コマンド

```bash
# ヘルプを表示
dev.bat

# テスト実行
dev.bat test

# コードフォーマット
dev.bat format

# リンティング
dev.bat lint

# 全チェック（フォーマット + リント + テスト）
dev.bat dev

# キャッシュクリア
dev.bat clean
```

## 📋 Google Sheets設定

### 保有銘柄シート
| 列 | 内容 |
|---|---|
| A | 銘柄コード |
| B | 銘柄名 |
| C | 保有数量 |
| D | 購入価格 |

### ウォッチリストシート
| 列 | 内容 |
|---|---|
| A | 銘柄コード |
| B | 銘柄名 |

## 🔧 技術スタック

- **ランタイム**: Python 3.11
- **クラウド**: AWS Lambda
- **データ管理**: Google Sheets API
- **AI分析**: Google Gemini API
- **通知**: Slack Webhook
- **株式データ**: yfinance (Yahoo Finance)

## 📁 プロジェクト構造

```
stock-analysis-notification/
├── src/
│   ├── main.py                    # ローカル実行用
│   ├── config/
│   │   └── config_manager.py      # 設定管理
│   ├── handlers/
│   │   └── lambda_handler.py      # Lambda関数
│   ├── services/                  # 各種サービス（実装予定）
│   └── models/                    # データモデル（実装予定）
├── tests/                         # テストファイル
├── setup.bat                      # 開発環境セットアップ
├── dev.bat                        # 開発用コマンド
├── requirements.txt               # Python依存関係
├── pyproject.toml                 # プロジェクト設定
└── .env.example                   # 環境変数テンプレート
```

## 🚀 AWS デプロイ（予定）

AWS SAMを使用してLambda関数としてデプロイします。

```bash
# SAM ビルド
sam build

# デプロイ
sam deploy --guided
```

## 📝 ライセンス

MIT License
