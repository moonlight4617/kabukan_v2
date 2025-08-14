#!/usr/bin/env python3
"""
ローカル実行用メインスクリプト
開発時のテスト実行やデバッグに使用
"""

import os
import sys
import logging
from typing import Dict, Any
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.config_manager import ConfigManager
from src.handlers.lambda_handler import LambdaHandler


def setup_logging(log_level: str = "INFO") -> None:
    """ログ設定を初期化"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def create_test_event(analysis_type: str = "daily") -> Dict[str, Any]:
    """テスト用のEvent Bridgeイベントを作成"""
    return {
        "source": ["aws.events"],
        "detail-type": ["Scheduled Event"],
        "detail": {
            "analysis_type": analysis_type,
            "scheduled": True
        },
        "resources": [f"arn:aws:events:ap-northeast-1:123456789012:rule/{analysis_type}-analysis"]
    }


def main() -> None:
    """メイン実行関数"""
    try:
        # 環境変数から設定を読み込み
        log_level = os.getenv("LOG_LEVEL", "INFO")
        setup_logging(log_level)
        
        logger = logging.getLogger(__name__)
        logger.info("🚀 株式分析アプリケーションを開始します...")
        
        # 設定管理の初期化
        config_manager = ConfigManager()
        logger.info("✅ 設定管理が初期化されました")
        
        # Lambda ハンドラーの初期化
        lambda_handler = LambdaHandler()
        logger.info("✅ Lambda ハンドラーが初期化されました")
        
        # 引数から分析タイプを取得
        analysis_type = "daily"
        if len(sys.argv) > 1:
            analysis_type = sys.argv[1].lower()
            if analysis_type not in ["daily", "weekly", "monthly"]:
                logger.error(f"❌ 無効な分析タイプ: {analysis_type}")
                logger.info("有効な分析タイプ: daily, weekly, monthly")
                sys.exit(1)
        
        logger.info(f"📊 {analysis_type} 分析を実行します...")
        
        # テストイベントを作成
        test_event = create_test_event(analysis_type)
        test_context = type('Context', (), {
            'function_name': 'stock-analysis-local',
            'function_version': '$LATEST',
            'invoked_function_arn': 'arn:aws:lambda:local',
            'memory_limit_in_mb': '512',
            'remaining_time_in_millis': lambda: 300000,
            'log_group_name': '/aws/lambda/stock-analysis-local',
            'log_stream_name': '2023/01/01/[$LATEST]test'
        })()
        
        # Lambda関数を実行
        result = lambda_handler.lambda_handler(test_event, test_context)
        
        logger.info("✅ 分析が完了しました")
        logger.info(f"結果: {result}")
        
    except KeyboardInterrupt:
        logger.info("⏹️  実行が中断されました")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ エラーが発生しました: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # 環境変数ファイルを読み込み
    env_file = project_root / ".env.local"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print(f"📁 環境設定を読み込みました: {env_file}")
        except ImportError:
            print("⚠️  python-dotenvがインストールされていません。")
            print("pip install python-dotenv を実行してください。")
    else:
        print(f"⚠️  環境設定ファイルが見つかりません: {env_file}")
        print("setup.batを実行して開発環境をセットアップしてください。")
    
    main()