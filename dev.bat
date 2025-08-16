@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%1"=="" (
    echo 📋 使用可能なコマンド:
    echo   setup     - 開発環境をセットアップ
    echo   install   - 依存関係をインストール
    echo   run       - アプリケーションをローカル実行
    echo   test      - テストを実行
    echo   lint      - コードの静的解析
    echo   format    - コードフォーマット
    echo   clean     - キャッシュファイルを削除
    echo   activate  - 仮想環境を有効化
    echo.
    echo 使用例:
    echo   dev.bat run
    echo   dev.bat test
    echo   dev.bat run daily    - 日次分析を実行
    echo   dev.bat run weekly   - 週次分析を実行
    echo   dev.bat run monthly  - 月次分析を実行
    goto :eof
)

REM 仮想環境の確認
if not exist "venv\Scripts\activate.bat" (
    echo ❌ 仮想環境が見つかりません。
    echo まず 'dev.bat setup' を実行してください。
    exit /b 1
)

REM 仮想環境を有効化
call venv\Scripts\activate.bat

if "%1"=="setup" (
    echo 🚀 開発環境をセットアップ中...
    call setup.bat
    goto :eof
)

if "%1"=="install" (
    echo 📦 依存関係をインストール中...
    pip install --upgrade pip
    echo 本番依存関係をインストール中...
    pip install -r requirements.txt
    echo 開発依存関係をインストール中...
    pip install -r requirements-dev.txt
    echo ✅ インストール完了
    goto :eof
)

if "%1"=="run" (
    echo 🚀 アプリケーションを実行中...
    if "%2"=="" (
        python src\main.py
    ) else (
        python src\main.py %2
    )
    goto :eof
)

if "%1"=="test" (
    echo 🧪 テストを実行中...
    if exist "tests\" (
        pytest tests\ -v --cov=src --cov-report=term-missing
    ) else (
        echo ⚠️  testsディレクトリが見つかりません。
    )
    goto :eof
)

if "%1"=="lint" (
    echo 🔍 コードの静的解析中...
    if exist "src\" (
        flake8 src
        if !errorlevel!==0 (
            echo ✅ flake8チェック完了
        )
    )
    if exist "tests\" (
        flake8 tests
    )
    goto :eof
)

if "%1"=="format" (
    echo 🎨 コードフォーマット中...
    if exist "src\" (
        black src
    )
    if exist "tests\" (
        black tests
    )
    echo ✅ フォーマット完了
    goto :eof
)

if "%1"=="clean" (
    echo 🧹 キャッシュファイルを削除中...
    for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
    for /r . %%f in (*.pyc) do @if exist "%%f" del "%%f"
    if exist ".pytest_cache" rd /s /q ".pytest_cache"
    if exist ".coverage" del ".coverage"
    if exist "stock_cache.json" del "stock_cache.json"
    echo ✅ クリーンアップ完了
    goto :eof
)

if "%1"=="activate" (
    echo 💡 仮想環境を有効化するには以下のコマンドを実行してください:
    echo venv\Scripts\activate.bat
    goto :eof
)

if "%1"=="dev" (
    echo 🛠️  開発チェックを実行中...
    call dev.bat format
    call dev.bat lint
    call dev.bat test
    echo ✅ 開発チェック完了
    goto :eof
)

echo ❌ 不明なコマンド: %1
echo 'dev.bat' でヘルプを表示