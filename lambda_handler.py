# -*- coding: utf-8 -*-
"""
AWS Lambda メインハンドラー
Event Bridgeイベントの処理、日次・週次・月次スケジュールの管理
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
import os

from src.models.analysis_models import AnalysisType
from src.services.gemini_service import AnalysisMode
from src.services.parameter_store_service import ParameterStoreService, ParameterStoreConfig
from src.services.cloudwatch_service import CloudWatchService, StructuredLogger, LogLevel
from src.services.google_sheets_service import GoogleSheetsService
from src.services.stock_data_service import StockDataService
from src.services.historical_data_manager import HistoricalDataManager
from src.services.data_validation_service import DataValidationService
from src.services.retry_manager import RetryManager, RetryConfig
from src.services.technical_analysis_service import TechnicalAnalysisService
from src.services.gemini_service import GeminiService, GeminiConfig
from src.services.daily_analysis_service import DailyAnalysisService
from src.services.weekly_analysis_service import WeeklyAnalysisService
from src.services.monthly_analysis_service import MonthlyAnalysisService
from src.services.slack_service import SlackService, SlackConfig
from src.services.slack_notification_formatter import SlackNotificationFormatter
from src.services.slack_notification_error_handler import SlackNotificationErrorHandler, NotificationConfig
from src.services.slack_priority_notification_manager import SlackPriorityNotificationManager
from src.services.performance_optimizer import PerformanceOptimizer, OptimizationConfig, OptimizationLevel, get_optimizer, optimize_execution


# ロガー設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class LambdaContext:
    """Lambda実行コンテキスト"""
    
    def __init__(self, event: Dict[str, Any], context: Any):
        self.event = event
        self.aws_context = context
        self.execution_id = context.aws_request_id if context else "local"
        self.start_time = datetime.now()
        
        # イベント情報の抽出
        self.analysis_type = self._extract_analysis_type(event)
        self.analysis_mode = self._extract_analysis_mode(event)
        self.source = event.get('source', 'unknown')
        self.detail_type = event.get('detail-type', 'unknown')
        self.custom_params = event.get('detail', {})
    
    def _extract_analysis_type(self, event: Dict[str, Any]) -> AnalysisType:
        """イベントから分析タイプを抽出"""
        # Event Bridgeのルール名から判定
        rule_name = event.get('detail', {}).get('rule-name', '')
        detail_type = event.get('detail-type', '')
        
        if 'daily' in rule_name.lower() or 'daily' in detail_type.lower():
            return AnalysisType.DAILY
        elif 'weekly' in rule_name.lower() or 'weekly' in detail_type.lower():
            return AnalysisType.WEEKLY
        elif 'monthly' in rule_name.lower() or 'monthly' in detail_type.lower():
            return AnalysisType.MONTHLY
        
        # カスタムパラメータから判定
        analysis_type_str = event.get('detail', {}).get('analysis_type', 'daily')
        try:
            return AnalysisType(analysis_type_str.lower())
        except ValueError:
            logger.warning(f"不明な分析タイプ: {analysis_type_str}, デフォルトでDAILYを使用")
            return AnalysisType.DAILY
    
    def _extract_analysis_mode(self, event: Dict[str, Any]) -> AnalysisMode:
        """イベントから分析モードを抽出"""
        mode_str = event.get('detail', {}).get('analysis_mode', 'balanced')
        try:
            return AnalysisMode(mode_str.lower())
        except ValueError:
            logger.warning(f"不明な分析モード: {mode_str}, デフォルトでBALANCEDを使用")
            return AnalysisMode.BALANCED
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "execution_id": self.execution_id,
            "analysis_type": self.analysis_type.value,
            "analysis_mode": self.analysis_mode.value,
            "source": self.source,
            "detail_type": self.detail_type,
            "start_time": self.start_time.isoformat(),
            "custom_params": self.custom_params
        }


class ServiceManager:
    """サービス管理クラス"""
    
    def __init__(self):
        self.logger = logger
        self.services = {}
        self._initialized = False
    
    async def initialize_services(self) -> bool:
        """サービスを初期化"""
        try:
            self.logger.info("サービス初期化開始")
            
            # パフォーマンス最適化設定
            optimization_config = OptimizationConfig(
                level=OptimizationLevel.MODERATE,
                enable_memory_monitoring=True,
                enable_gc_optimization=True,
                memory_threshold_mb=400.0,  # Lambda環境に適した値
                execution_timeout_seconds=900.0  # 15分
            )
            optimizer = get_optimizer(optimization_config)
            self.services['performance_optimizer'] = optimizer
            
            # Parameter Store設定
            parameter_config = ParameterStoreConfig()
            parameter_service = ParameterStoreService(parameter_config)
            self.services['parameter_store'] = parameter_service
            
            # CloudWatch設定
            cloudwatch_service = CloudWatchService()
            structured_logger = StructuredLogger(cloudwatch_service)
            self.services['cloudwatch'] = cloudwatch_service
            self.services['structured_logger'] = structured_logger
            
            # Google Sheets設定
            sheets_service = GoogleSheetsService()
            self.services['google_sheets'] = sheets_service
            
            # 株価データサービス設定
            stock_service = StockDataService()
            self.services['stock_data'] = stock_service
            
            # 履歴データマネージャー設定
            historical_manager = HistoricalDataManager(stock_service)
            self.services['historical_data'] = historical_manager
            
            # データ検証サービス設定
            validation_service = DataValidationService()
            self.services['data_validation'] = validation_service
            
            # リトライマネージャー設定
            retry_config = RetryConfig(max_attempts=3, initial_delay=1.0, max_delay=30.0)
            retry_manager = RetryManager(retry_config)
            self.services['retry_manager'] = retry_manager
            
            # テクニカル分析サービス設定
            technical_service = TechnicalAnalysisService()
            self.services['technical_analysis'] = technical_service
            
            # Gemini AIサービス設定
            gemini_config = await self._get_gemini_config()
            gemini_service = GeminiService(gemini_config)
            self.services['gemini'] = gemini_service
            
            # 分析サービス設定
            daily_service = DailyAnalysisService(
                stock_service, historical_manager, technical_service, 
                gemini_service, sheets_service
            )
            self.services['daily_analysis'] = daily_service
            
            weekly_service = WeeklyAnalysisService(
                stock_service, historical_manager, technical_service,
                gemini_service, sheets_service
            )
            self.services['weekly_analysis'] = weekly_service
            
            monthly_service = MonthlyAnalysisService(
                stock_service, historical_manager, technical_service,
                gemini_service, sheets_service
            )
            self.services['monthly_analysis'] = monthly_service
            
            # Slack通知サービス設定
            slack_config = await self._get_slack_config()
            if slack_config:
                slack_service = SlackService(slack_config, retry_manager)
                formatter = SlackNotificationFormatter()
                error_handler = SlackNotificationErrorHandler(
                    slack_service, NotificationConfig(), retry_manager
                )
                priority_manager = SlackPriorityNotificationManager(
                    slack_service, formatter, error_handler
                )
                
                self.services['slack'] = slack_service
                self.services['slack_formatter'] = formatter
                self.services['slack_error_handler'] = error_handler
                self.services['slack_priority_manager'] = priority_manager
            
            self._initialized = True
            self.logger.info("サービス初期化完了")
            return True
            
        except Exception as e:
            self.logger.error(f"サービス初期化失敗: {e}")
            self.logger.error(traceback.format_exc())
            return False
    
    async def _get_gemini_config(self) -> GeminiConfig:
        """Gemini設定を取得"""
        try:
            parameter_service = self.services.get('parameter_store')
            if parameter_service:
                api_key = await parameter_service.get_parameter('/stock-analysis/gemini/api-key')
                if api_key:
                    return GeminiConfig(api_key=api_key)
            
            # 環境変数からフォールバック
            api_key = os.environ.get('GEMINI_API_KEY')
            if api_key:
                return GeminiConfig(api_key=api_key)
            
            # デフォルト設定
            self.logger.warning("Gemini API キーが見つかりません。モックモードを使用します")
            return GeminiConfig(api_key="mock", model_type="gemini-pro", mock_mode=True)
            
        except Exception as e:
            self.logger.error(f"Gemini設定取得エラー: {e}")
            return GeminiConfig(api_key="mock", model_type="gemini-pro", mock_mode=True)
    
    async def _get_slack_config(self) -> Optional[SlackConfig]:
        """Slack設定を取得"""
        try:
            parameter_service = self.services.get('parameter_store')
            if parameter_service:
                webhook_url = await parameter_service.get_parameter('/stock-analysis/slack/webhook-url')
                if webhook_url:
                    return SlackConfig(webhook_url=webhook_url)
            
            # 環境変数からフォールバック
            webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
            if webhook_url:
                return SlackConfig(webhook_url=webhook_url)
            
            self.logger.warning("Slack Webhook URLが設定されていません。通知機能は無効です")
            return None
            
        except Exception as e:
            self.logger.error(f"Slack設定取得エラー: {e}")
            return None
    
    def get_service(self, service_name: str):
        """サービスを取得"""
        if not self._initialized:
            raise RuntimeError("サービスが初期化されていません")
        return self.services.get(service_name)
    
    def is_initialized(self) -> bool:
        """初期化済みか確認"""
        return self._initialized


class AnalysisExecutor:
    """分析実行クラス"""
    
    def __init__(self, service_manager: ServiceManager):
        self.service_manager = service_manager
        self.logger = logger
    
    @optimize_execution
    async def execute_analysis(self, context: LambdaContext) -> Dict[str, Any]:
        """分析を実行"""
        self.logger.info(f"分析実行開始: {context.analysis_type.value}")
        
        # パフォーマンス監視開始
        optimizer = self.service_manager.get_service('performance_optimizer')
        if optimizer:
            optimizer.memory_monitor.start_monitoring()
        
        try:
            # 分析タイプ別の実行
            if context.analysis_type == AnalysisType.DAILY:
                result = await self._execute_daily_analysis(context)
            elif context.analysis_type == AnalysisType.WEEKLY:
                result = await self._execute_weekly_analysis(context)
            elif context.analysis_type == AnalysisType.MONTHLY:
                result = await self._execute_monthly_analysis(context)
            else:
                raise ValueError(f"サポートされていない分析タイプ: {context.analysis_type}")
            
            # 通知送信
            await self._send_notification(result, context)
            
            # パフォーマンス情報収集
            performance_summary = {}
            if optimizer:
                memory_stats = optimizer.memory_monitor.stop_monitoring()
                performance_summary = optimizer.get_performance_summary()
                performance_summary.update(memory_stats)
            
            self.logger.info(f"分析実行完了: {context.analysis_type.value}")
            return {
                "success": True,
                "analysis_type": context.analysis_type.value,
                "execution_time": result.execution_time if hasattr(result, 'execution_time') else 0,
                "result_summary": getattr(result, 'summary', 'Analysis completed'),
                "performance": performance_summary
            }
            
        except Exception as e:
            self.logger.error(f"分析実行エラー: {e}")
            self.logger.error(traceback.format_exc())
            
            # エラー通知
            await self._send_error_notification(str(e), context)
            
            return {
                "success": False,
                "error": str(e),
                "analysis_type": context.analysis_type.value
            }
    
    async def _execute_daily_analysis(self, context: LambdaContext):
        """日次分析を実行"""
        daily_service = self.service_manager.get_service('daily_analysis')
        if not daily_service:
            raise RuntimeError("日次分析サービスが利用できません")
        
        return await daily_service.execute_daily_analysis(
            analysis_mode=context.analysis_mode,
            enable_ai_analysis=True
        )
    
    async def _execute_weekly_analysis(self, context: LambdaContext):
        """週次分析を実行"""
        weekly_service = self.service_manager.get_service('weekly_analysis')
        if not weekly_service:
            raise RuntimeError("週次分析サービスが利用できません")
        
        return await weekly_service.execute_weekly_analysis(
            analysis_mode=context.analysis_mode,
            enable_ai_analysis=True
        )
    
    async def _execute_monthly_analysis(self, context: LambdaContext):
        """月次分析を実行"""
        monthly_service = self.service_manager.get_service('monthly_analysis')
        if not monthly_service:
            raise RuntimeError("月次分析サービスが利用できません")
        
        return await monthly_service.execute_monthly_analysis(
            analysis_mode=context.analysis_mode,
            enable_ai_analysis=True
        )
    
    async def _send_notification(self, analysis_result, context: LambdaContext):
        """分析結果の通知を送信"""
        try:
            priority_manager = self.service_manager.get_service('slack_priority_manager')
            if priority_manager:
                success = await priority_manager.send_analysis_notification(analysis_result)
                if success:
                    self.logger.info("分析結果通知送信成功")
                else:
                    self.logger.warning("分析結果通知送信失敗")
            else:
                self.logger.info("Slack通知サービスが利用できません")
                
        except Exception as e:
            self.logger.error(f"通知送信エラー: {e}")
    
    async def _send_error_notification(self, error_message: str, context: LambdaContext):
        """エラー通知を送信"""
        try:
            slack_service = self.service_manager.get_service('slack')
            if slack_service:
                error_context = {
                    "execution_id": context.execution_id,
                    "analysis_type": context.analysis_type.value,
                    "error_time": datetime.now().isoformat()
                }
                
                response = slack_service.send_error_notification(
                    error_message, error_context
                )
                
                if response.success:
                    self.logger.info("エラー通知送信成功")
                else:
                    self.logger.warning("エラー通知送信失敗")
                    
        except Exception as e:
            self.logger.error(f"エラー通知送信失敗: {e}")


# グローバルサービスマネージャー（Lambda環境での再利用のため）
service_manager = ServiceManager()


async def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda メインハンドラー関数
    
    Args:
        event: Event Bridgeからのイベントデータ
        context: Lambda実行コンテキスト
        
    Returns:
        Dict[str, Any]: 実行結果
    """
    lambda_context = LambdaContext(event, context)
    
    # 構造化ログの開始
    logger.info("Lambda実行開始", extra={
        "execution_id": lambda_context.execution_id,
        "event": event,
        "context_info": lambda_context.to_dict()
    })
    
    try:
        # サービス初期化（初回のみ）
        if not service_manager.is_initialized():
            initialization_success = await service_manager.initialize_services()
            if not initialization_success:
                return {
                    "statusCode": 500,
                    "body": json.dumps({
                        "success": False,
                        "error": "サービス初期化失敗",
                        "execution_id": lambda_context.execution_id
                    })
                }
        
        # CloudWatch構造化ログ記録
        structured_logger = service_manager.get_service('structured_logger')
        if structured_logger:
            await structured_logger.log_structured(
                level=LogLevel.INFO,
                message="株価分析実行開始",
                context=lambda_context.to_dict()
            )
        
        # 分析実行
        executor = AnalysisExecutor(service_manager)
        result = await executor.execute_analysis(lambda_context)
        
        # 実行時間計算
        execution_time = (datetime.now() - lambda_context.start_time).total_seconds()
        result["total_execution_time"] = execution_time
        result["execution_id"] = lambda_context.execution_id
        
        # 成功ログ
        if structured_logger:
            await structured_logger.log_structured(
                level=LogLevel.INFO,
                message="株価分析実行完了",
                context={
                    **lambda_context.to_dict(),
                    "result": result,
                    "execution_time": execution_time
                }
            )
        
        logger.info("Lambda実行完了", extra={
            "execution_id": lambda_context.execution_id,
            "execution_time": execution_time,
            "success": result.get("success", False)
        })
        
        return {
            "statusCode": 200,
            "body": json.dumps(result, ensure_ascii=False, default=str)
        }
        
    except Exception as e:
        error_message = str(e)
        error_traceback = traceback.format_exc()
        
        logger.error("Lambda実行エラー", extra={
            "execution_id": lambda_context.execution_id,
            "error": error_message,
            "traceback": error_traceback
        })
        
        # エラーログ記録
        structured_logger = service_manager.get_service('structured_logger')
        if structured_logger:
            try:
                await structured_logger.log_structured(
                    level=LogLevel.ERROR,
                    message="株価分析実行エラー",
                    context={
                        **lambda_context.to_dict(),
                        "error": error_message,
                        "traceback": error_traceback
                    }
                )
            except:
                pass  # ログ記録エラーは無視
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": error_message,
                "execution_id": lambda_context.execution_id,
                "analysis_type": lambda_context.analysis_type.value
            }, ensure_ascii=False)
        }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    同期ラッパー関数（AWS Lambdaエントリーポイント）
    
    Args:
        event: Event Bridgeからのイベントデータ
        context: Lambda実行コンテキスト
        
    Returns:
        Dict[str, Any]: 実行結果
    """
    import asyncio
    
    # イベントループ作成・実行
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(lambda_handler(event, context))
    except Exception as e:
        logger.error(f"Handler実行エラー: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": str(e)
            })
        }
    finally:
        # ループのクリーンアップは不要（Lambda環境では再利用される）
        pass


# ローカル実行用のエントリーポイント
if __name__ == "__main__":
    # テスト用のイベントデータ
    test_event = {
        "source": "aws.events",
        "detail-type": "Scheduled Event",
        "detail": {
            "rule-name": "stock-analysis-daily",
            "analysis_type": "daily",
            "analysis_mode": "balanced"
        }
    }
    
    # テスト用のコンテキスト
    class TestContext:
        def __init__(self):
            self.aws_request_id = "test-execution-id"
            self.function_name = "stock-analysis-function"
            self.function_version = "$LATEST"
    
    # ローカル実行
    result = handler(test_event, TestContext())
    print(json.dumps(result, indent=2, ensure_ascii=False))