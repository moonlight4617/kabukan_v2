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

## 🚀 AWS デプロイ

### 自動デプロイ（GitHub Actions）

このプロジェクトでは、GitHub Actionsを使用した完全自動化されたCI/CDパイプラインを提供しています。

#### 自動デプロイフロー
- **develop ブランチ** → 開発環境（dev）
- **main ブランチ** → ステージング環境（staging）
- **手動承認後** → 本番環境（prod）

#### GitHub Actionsワークフロー
- `ci.yml`: 継続的インテグレーション（テスト、リント、セキュリティスキャン）
- `deploy.yml`: 自動デプロイメント
- `security.yml`: 週次セキュリティスキャン
- `schedule-test.yml`: 日次のLambda関数動作確認

### 手動デプロイ

#### 開発環境
```bash
# 環境設定
scripts/setup-env.sh dev

# デプロイ
sam build --use-container
sam deploy --config-env dev
```

#### ステージング環境
```bash
# ステージング環境へのデプロイ
scripts/setup-env.sh staging
sam deploy --config-env staging
```

#### 本番環境
```bash
# 本番環境へのデプロイ（要注意）
scripts/setup-env.sh prod
sam deploy --config-env prod
```

### デプロイ後の確認
```bash
# ヘルスチェック実行
scripts/health-check.sh [環境名]

# CloudWatchログの確認
aws logs tail /aws/lambda/stock-analysis-[環境名]

# EventBridgeルールの状態確認
aws events list-rules --name-prefix stock-analysis
```

### ロールバック
```bash
# 前のバージョンへのロールバック
scripts/rollback.sh [環境名] [バージョン]
```

## 🔒 セキュリティ

### セキュリティ機能
- AWS IAM による最小権限の原則
- Parameter Store（SecureString）による機密情報暗号化
- 自動セキュリティスキャン（Bandit、Safety、Semgrep、CodeQL）
- 依存関係脆弱性チェック（Dependabot）
- シークレット検出（TruffleHog）

### セキュリティスキャン実行
```bash
# 手動セキュリティスキャン
.github/workflows/security.yml（GitHub Actionsで自動実行）

# 依存関係チェック
safety check
bandit -r src/
```

### セキュリティ問題の報告
セキュリティ脆弱性を発見した場合は、`.github/SECURITY.md`の手順に従って報告してください。

## 📊 モニタリング・ログ

### CloudWatch監視
- Lambda関数の実行メトリクス
- エラー率・実行時間の監視
- カスタムメトリクス（分析成功率、通知送信率）

### ログ確認
```bash
# リアルタイムログ監視
aws logs tail /aws/lambda/stock-analysis-[環境名] --follow

# エラーログフィルタ
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-analysis-[環境名] \
  --filter-pattern "ERROR"

# 特定期間のログ
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-analysis-[環境名] \
  --start-time $(date -d '1 hour ago' +%s)000
```

### アラート設定
- 関数実行エラー率の監視
- 実行時間の異常値検出
- Slack通知の送信失敗アラート

## 🤝 コントリビューション

### 開発フロー
1. Issueの作成（バグ報告・機能要求）
2. ブランチの作成（`feature/xxx` または `bugfix/xxx`）
3. コード実装・テスト作成
4. プルリクエストの作成
5. コードレビュー・CI通過
6. マージ・自動デプロイ

### コードスタイル
- Black（コードフォーマッター）
- isort（import整理）
- mypy（型チェック）
- flake8（リンター）

### テスト要件
- 単体テストカバレッジ > 80%
- 統合テストの実装
- モック使用による外部API依存の分離

## 📝 ライセンス

MIT License
