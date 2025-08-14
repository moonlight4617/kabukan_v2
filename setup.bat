@echo off
chcp 65001 >nul
echo 🚀 開発環境をセットアップ中...
echo.

REM 仮想環境作成
echo Python仮想環境を作成中...
python -m venv venv
if %errorlevel% neq 0 (
    echo ❌ 仮想環境の作成に失敗しました。Pythonが正しくインストールされているか確認してください。
    pause
    exit /b 1
)

REM 仮想環境を有効化
echo 仮想環境を有効化中...
call venv\Scripts\activate.bat

REM 依存関係インストール
echo 依存関係をインストール中...
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-cov black flake8 python-dotenv

REM 開発用依存関係
echo 開発用ツールをインストール中...
pip install pytest-mock mypy aws-sam-cli

REM 環境設定ファイルのコピー
if not exist .env.local (
    echo 環境設定ファイルを作成中...
    copy .env.example .env.local
    echo ⚠️  .env.localファイルに実際の設定値を入力してください。
) else (
    echo ℹ️  .env.localファイルは既に存在します。
)

echo.
echo ✅ セットアップ完了！
echo.
echo 📋 次の手順:
echo 1. .env.localファイルを編集して実際の設定値を入力
echo 2. 仮想環境を有効化: venv\Scripts\activate.bat
echo 3. ローカル実行: python src\main.py
echo 4. テスト実行: pytest tests\ -v
echo.
pause