# 監視システム運用ガイド

株式分析システムの包括的な監視・アラート・パフォーマンス管理システムの使用方法を説明します。

## 🎯 概要

このシステムは以下の監視機能を提供します：

- **リアルタイム監視**: Lambda関数、API、通知システムの状態監視
- **パフォーマンス分析**: 実行時間、メモリ使用率、エラー率の分析
- **コスト最適化**: AWS利用料金の監視と最適化提案
- **自動アラート**: 問題発生時のSlack/メール通知
- **運用レポート**: 定期的なシステム状態レポート

## 📊 監視コンポーネント

### 1. CloudWatch Dashboard

- **URL**: `https://console.aws.amazon.com/cloudwatch/home#dashboards:`
- **ダッシュボード名**: `StockAnalysis-{environment}`

#### 主要メトリクス
- Lambda関数実行回数・エラー数・実行時間
- EventBridge ルールの実行状況
- カスタムメトリクス（分析成功率、API呼び出し、通知送信）
- メモリ使用率とパフォーマンス指標

### 2. CloudWatch Alarms

#### 設定済みアラーム
- **Lambda Error Rate**: エラー率 > 5%で警告、> 10%で重大
- **Lambda Duration**: 実行時間 > 60秒で警告、> 120秒で重大
- **Lambda Throttles**: スロットリング発生時に即座にアラート
- **Memory Utilization**: メモリ使用率 > 80%で警告
- **No Invocations**: 24時間実行されない場合にアラート

#### アラート通知先
- **Slack**: 即座にチャンネルに通知
- **SNS**: 重大なアラートはメール/SMS通知

### 3. カスタムメトリクス

#### ビジネスメトリクス
- `AnalysisSuccess`: 分析成功数
- `AnalysisFailure`: 分析失敗数
- `AnalysisDuration`: 分析処理時間
- `PortfolioValue`: ポートフォリオ評価額
- `AnalyzedStocks`: 分析対象銘柄数

#### 技術メトリクス
- `GoogleSheetsAPICall`: Google Sheets API呼び出し数
- `GeminiAPICall`: Gemini AI API呼び出し数
- `SlackNotificationSent`: Slack通知送信数
- `SlackNotificationFailed`: Slack通知失敗数

## 🔧 監視スクリプトの使用方法

### インストール

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 実行権限の付与（Linux/macOS）
chmod +x scripts/monitoring.py
```

### 基本的な使用方法

#### 1. ヘルスチェック

```bash
# 開発環境のヘルスチェック
python scripts/monitoring.py health-check --environment dev

# 詳細出力で本番環境をチェック
python scripts/monitoring.py health-check --environment prod --verbose
```

**出力例:**
```
=== Health Check Report - PROD ===
Timestamp: 2024-01-15 10:30:00
Overall Status: HEALTHY
Active Alerts: 0

--- Component Health ---
✅ lambda_function: healthy (0.45s)
✅ eventbridge_rules: healthy (0.23s)
✅ parameter_store: healthy (0.12s)
⚠️ google_sheets_api: warning (2.15s)
✅ gemini_api: healthy (0.89s)
✅ slack_webhook: healthy (0.34s)

--- Recommendations ---
1. Google Sheets API response time is high. Check API quotas.
2. System is operating normally. Continue monitoring.
```

#### 2. パフォーマンス分析

```bash
# 過去24時間のパフォーマンス分析
python scripts/monitoring.py performance --environment prod --hours 24

# 過去1週間の分析
python scripts/monitoring.py performance --environment prod --hours 168
```

**出力例:**
```
=== Performance Analysis Report - PROD ===
Analysis Period: Last 24 hours
Metrics Count: 144

--- Performance Metrics ---
Average Duration: 45,320.5ms
P95 Duration: 67,890.2ms
P99 Duration: 89,432.1ms
Max Duration: 112,345.0ms
Average Memory Utilization: 67.3%
Max Memory Utilization: 85.7%
Error Rate: 2.1%
Cold Start Rate: 8.5%

--- Optimization Recommendations ---
1. P95 duration (67.9s) is acceptable but monitor trends
2. Memory utilization (67%) is optimal
3. Consider connection pooling to reduce execution time
```

#### 3. コスト分析

```bash
# 過去7日間のコスト分析
python scripts/monitoring.py cost --environment prod --days 7

# 過去30日間のコスト分析
python scripts/monitoring.py cost --environment prod --days 30
```

**出力例:**
```
=== Cost Analysis Report - PROD ===
Analysis Period: Last 7 days

--- Cost Metrics ---
Estimated Cost: $12.4567
Cost per Request: $0.000124
Total Requests: 100,456
Total Duration: 4,567,890ms
Memory GB-Seconds: 123.45

Cost Change: 📈 +5.2%

--- Cost Optimization Opportunities ---
1. Memory utilization is low (67%). Consider reducing allocated memory to save costs.
   Recommendation: Reduce memory from 512MB to 384MB
   Potential Savings: 20-30%
```

#### 4. テストアラート送信

```bash
# 中程度のテストアラートを送信
python scripts/monitoring.py test-alert --environment dev --severity medium

# 緊急テストアラート
python scripts/monitoring.py test-alert --environment staging --severity critical
```

## 🚨 アラート対応手順

### 1. Lambda Function Errors

**アラート例**: "Lambda Error Rate Critical"

**対応手順**:
1. CloudWatch Logsで詳細なエラーログを確認
2. Google Sheets/Gemini API/Slack APIの接続状況確認
3. Parameter Storeの設定値確認
4. 必要に応じてLambda関数の再デプロイ

```bash
# エラーログの確認
aws logs tail /aws/lambda/stock-analysis-prod --follow

# 最近のエラーを検索
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-analysis-prod \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### 2. Performance Issues

**アラート例**: "Lambda Duration Warning"

**対応手順**:
1. パフォーマンス分析を実行して傾向を確認
2. 外部API応答時間の確認
3. メモリ設定の見直し
4. コードの最適化検討

```bash
# パフォーマンス詳細分析
python scripts/monitoring.py performance --environment prod --hours 48

# メモリ使用率の確認
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name MemoryUtilization \
  --dimensions Name=FunctionName,Value=stock-analysis-prod \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

### 3. API Failures

**アラート例**: "Google Sheets API Failures"

**対応手順**:
1. API認証情報の確認
2. APIクォータ・制限の確認
3. ネットワーク接続の確認
4. API仕様変更の調査

```bash
# Parameter Store設定の確認
aws ssm get-parameters-by-path \
  --path "/stock-analysis-prod" \
  --recursive \
  --with-decryption
```

### 4. Cost Anomalies

**アラート例**: "Lambda Cost Increase Critical"

**対応手順**:
1. 実行回数の異常増加確認
2. 実行時間の増加原因調査
3. 不正な呼び出しの有無確認
4. 必要に応じて一時的な実行停止

```bash
# 実行回数の確認
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=stock-analysis-prod \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

## 📋 定期運用タスク

### 日次タスク

1. **ヘルスチェック実行**
```bash
python scripts/monitoring.py health-check --environment prod
```

2. **エラーログ確認**
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/stock-analysis-prod \
  --filter-pattern "ERROR" \
  --start-time $(date -d '24 hours ago' +%s)000
```

### 週次タスク

1. **パフォーマンス分析**
```bash
python scripts/monitoring.py performance --environment prod --hours 168
```

2. **セキュリティスキャン結果確認**
   - GitHub Actions の Security Scan ワークフロー結果確認

### 月次タスク

1. **コスト分析**
```bash
python scripts/monitoring.py cost --environment prod --days 30
```

2. **設定レビュー**
   - アラート閾値の見直し
   - 監視対象の追加・削除
   - 通知先の更新

## 🛠️ カスタマイズ

### 閾値の調整

`src/monitoring/performance_monitor.py` の `thresholds` 設定を変更：

```python
self.thresholds = {
    'duration_warning': 60,     # 60秒 → 変更
    'duration_critical': 120,   # 120秒 → 変更
    'memory_usage_warning': 80, # 80% → 変更
    'error_rate_warning': 5,    # 5% → 変更
}
```

### 新しいカスタムメトリクスの追加

```python
# メトリクス送信例
metrics_publisher.add_to_batch('CustomMetricName', value, 'Unit')
metrics_publisher.flush_batch()
```

### 新しいアラートの追加

```python
# アラート作成例
alert_manager.create_alert(
    title="Custom Alert",
    description="Description of the issue",
    severity=AlertSeverity.MEDIUM,
    source="CustomSource",
    metadata={"key": "value"}
)
```

## 🔍 トラブルシューティング

### 監視スクリプトが実行できない

**エラー**: `ModuleNotFoundError: No module named 'monitoring'`

**解決方法**:
```bash
# プロジェクトルートから実行
cd /path/to/kabukan_v2
python scripts/monitoring.py health-check
```

### CloudWatch メトリクスが表示されない

**原因**: 
- メトリクス送信の権限不足
- 名前空間の設定ミス

**解決方法**:
```bash
# IAM権限確認
aws iam get-role-policy --role-name stock-analysis-execution-role-prod --policy-name CloudWatchMetricsPolicy

# カスタムメトリクス確認
aws cloudwatch list-metrics --namespace Custom/StockAnalysis
```

### Slack通知が届かない

**確認項目**:
1. Webhook URLの設定確認
2. Parameter Storeの値確認
3. ネットワーク接続確認

```bash
# Parameter Store確認
aws ssm get-parameter --name "/stock-analysis-prod/slack-webhook-url" --with-decryption

# テスト通知送信
python scripts/monitoring.py test-alert --environment prod --severity low
```

## 📞 サポート

### ログ収集

問題発生時は以下のログを収集してください：

1. **Lambda実行ログ**
```bash
aws logs download /aws/lambda/stock-analysis-prod lambda-logs.txt
```

2. **監視スクリプトログ**
```bash
# monitoring-YYYYMMDD.log ファイル
```

3. **CloudWatch アラーム履歴**
```bash
aws cloudwatch describe-alarm-history --alarm-name stock-analysis-lambda-errors-prod
```

### エスカレーション

1. **レベル1**: 開発チーム
   - 一般的なアプリケーションエラー
   - パフォーマンス問題

2. **レベル2**: インフラチーム  
   - AWS リソースの問題
   - ネットワーク関連問題

3. **レベル3**: セキュリティチーム
   - セキュリティアラート
   - 不正アクセスの疑い

---

このガイドに従って、株式分析システムの安定運用を実現してください。質問や改善提案がありましたら、GitHubのIssueで報告をお願いします。