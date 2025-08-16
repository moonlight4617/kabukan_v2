# デプロイメントガイド

## 依存関係管理

### ファイル構成
- `requirements.txt`: 本番環境（Lambda）用の依存関係
- `requirements-dev.txt`: 開発・テスト環境用の依存関係

### ローカル開発環境セットアップ
```bash
# 全ての依存関係をインストール（開発用）
dev.bat setup
# または
dev.bat install
```

### Lambda デプロイ用
```bash
# 本番用依存関係のみインストール
pip install -r requirements.txt
```

## Lambda デプロイ時の注意点

### パッケージサイズ最適化
- `requirements.txt`には本番で必要なライブラリのみを含める
- 開発・テスト用ツール（pytest, black, flake8等）は含めない
- Lambda のサイズ制限（250MB unzipped, 50MB zipped）を考慮

### 推奨Lambda Layer
以下のライブラリはLambda Layerとして分離することを推奨：
- `boto3`, `botocore` (AWS管理Layer使用可能)
- `pandas`, `numpy` (重いデータ処理ライブラリ)
- `google-api-python-client` (Google API関連)

### 環境変数
本番環境では以下の環境変数をLambdaで設定：
- AWS Parameter Store設定
- Google Sheets API認証情報
- その他の設定値

## AWS SAM デプロイ
```bash
sam build
sam deploy --guided
```