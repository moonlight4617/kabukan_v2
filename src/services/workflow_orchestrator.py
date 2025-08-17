# -*- coding: utf-8 -*-
"""
ワークフローオーケストレーターサービス
各サービスを統合したメイン処理フロー、エラーハンドリングと復旧機能を提供
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

from src.models.analysis_models import AnalysisType
from src.services.gemini_service import AnalysisMode
from src.services.google_sheets_service import GoogleSheetsService, DataExtractionResult
from src.services.stock_data_service import StockDataService, BatchDataResult
from src.services.historical_data_manager import HistoricalDataManager
from src.services.data_validation_service import DataValidationService
from src.services.technical_analysis_service import TechnicalAnalysisService
from src.services.gemini_service import GeminiService
from src.services.daily_analysis_service import DailyAnalysisService
from src.services.weekly_analysis_service import WeeklyAnalysisService
from src.services.monthly_analysis_service import MonthlyAnalysisService
from src.services.slack_priority_notification_manager import SlackPriorityNotificationManager
from src.services.cloudwatch_service import CloudWatchService, StructuredLogger, LogLevel


logger = logging.getLogger(__name__)


class WorkflowStage(Enum):
    """ワークフロー段階"""
    INITIALIZATION = "initialization"
    DATA_EXTRACTION = "data_extraction"
    DATA_VALIDATION = "data_validation"
    STOCK_DATA_RETRIEVAL = "stock_data_retrieval"
    HISTORICAL_DATA_RETRIEVAL = "historical_data_retrieval"
    TECHNICAL_ANALYSIS = "technical_analysis"
    AI_ANALYSIS = "ai_analysis"
    NOTIFICATION = "notification"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            WorkflowStage.INITIALIZATION: "初期化",
            WorkflowStage.DATA_EXTRACTION: "データ抽出",
            WorkflowStage.DATA_VALIDATION: "データ検証",
            WorkflowStage.STOCK_DATA_RETRIEVAL: "株価データ取得",
            WorkflowStage.HISTORICAL_DATA_RETRIEVAL: "履歴データ取得",
            WorkflowStage.TECHNICAL_ANALYSIS: "テクニカル分析",
            WorkflowStage.AI_ANALYSIS: "AI分析",
            WorkflowStage.NOTIFICATION: "通知送信",
            WorkflowStage.CLEANUP: "クリーンアップ",
            WorkflowStage.COMPLETED: "完了",
            WorkflowStage.FAILED: "失敗"
        }[self]


class RecoveryAction(Enum):
    """復旧アクション"""
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    ABORT = "abort"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            RecoveryAction.RETRY: "リトライ",
            RecoveryAction.SKIP: "スキップ",
            RecoveryAction.FALLBACK: "フォールバック",
            RecoveryAction.ABORT: "中止"
        }[self]


@dataclass
class WorkflowError:
    """ワークフローエラー"""
    stage: WorkflowStage
    error_message: str
    error_type: str
    timestamp: datetime
    recoverable: bool = True
    recovery_action: Optional[RecoveryAction] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "stage": self.stage.value,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "timestamp": self.timestamp.isoformat(),
            "recoverable": self.recoverable,
            "recovery_action": self.recovery_action.value if self.recovery_action else None,
            "context": self.context
        }


@dataclass
class WorkflowMetrics:
    """ワークフロー実行メトリクス"""
    start_time: datetime
    end_time: Optional[datetime] = None
    current_stage: WorkflowStage = WorkflowStage.INITIALIZATION
    completed_stages: List[WorkflowStage] = field(default_factory=list)
    errors: List[WorkflowError] = field(default_factory=list)
    stage_durations: Dict[str, float] = field(default_factory=dict)
    data_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def total_duration(self) -> float:
        """総実行時間"""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def is_completed(self) -> bool:
        """完了したか"""
        return self.current_stage in [WorkflowStage.COMPLETED, WorkflowStage.FAILED]

    @property
    def success_rate(self) -> float:
        """成功率"""
        if not self.completed_stages:
            return 0.0
        total_stages = len([s for s in WorkflowStage if s not in [WorkflowStage.COMPLETED, WorkflowStage.FAILED]])
        return len(self.completed_stages) / total_stages

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "current_stage": self.current_stage.value,
            "completed_stages": [s.value for s in self.completed_stages],
            "total_duration": self.total_duration,
            "success_rate": self.success_rate,
            "error_count": len(self.errors),
            "stage_durations": self.stage_durations,
            "data_counts": self.data_counts
        }


@dataclass
class WorkflowContext:
    """ワークフロー実行コンテキスト"""
    analysis_type: AnalysisType
    analysis_mode: AnalysisMode
    execution_id: str
    enable_ai_analysis: bool = True
    enable_notifications: bool = True
    fallback_on_errors: bool = True
    custom_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "analysis_type": self.analysis_type.value,
            "analysis_mode": self.analysis_mode.value,
            "execution_id": self.execution_id,
            "enable_ai_analysis": self.enable_ai_analysis,
            "enable_notifications": self.enable_notifications,
            "fallback_on_errors": self.fallback_on_errors,
            "custom_params": self.custom_params
        }


class WorkflowOrchestrator:
    """ワークフローオーケストレーターサービス"""
    
    def __init__(self,
                 sheets_service: GoogleSheetsService,
                 stock_service: StockDataService,
                 historical_manager: HistoricalDataManager,
                 validation_service: DataValidationService,
                 technical_service: TechnicalAnalysisService,
                 gemini_service: GeminiService,
                 daily_service: DailyAnalysisService,
                 weekly_service: WeeklyAnalysisService,
                 monthly_service: MonthlyAnalysisService,
                 notification_manager: Optional[SlackPriorityNotificationManager] = None,
                 structured_logger: Optional[StructuredLogger] = None):
        """
        Args:
            sheets_service: Google Sheetsサービス
            stock_service: 株価データサービス
            historical_manager: 履歴データマネージャー
            validation_service: データ検証サービス
            technical_service: テクニカル分析サービス
            gemini_service: Gemini AIサービス
            daily_service: 日次分析サービス
            weekly_service: 週次分析サービス
            monthly_service: 月次分析サービス
            notification_manager: 通知マネージャー
            structured_logger: 構造化ログ
        """
        self.sheets_service = sheets_service
        self.stock_service = stock_service
        self.historical_manager = historical_manager
        self.validation_service = validation_service
        self.technical_service = technical_service
        self.gemini_service = gemini_service
        self.daily_service = daily_service
        self.weekly_service = weekly_service
        self.monthly_service = monthly_service
        self.notification_manager = notification_manager
        self.structured_logger = structured_logger
        self.logger = logging.getLogger(__name__)
        
        # 復旧戦略設定
        self.recovery_strategies = self._initialize_recovery_strategies()
        
        # 段階別タイムアウト設定（秒）
        self.stage_timeouts = {
            WorkflowStage.DATA_EXTRACTION: 120,
            WorkflowStage.STOCK_DATA_RETRIEVAL: 300,
            WorkflowStage.HISTORICAL_DATA_RETRIEVAL: 600,
            WorkflowStage.TECHNICAL_ANALYSIS: 180,
            WorkflowStage.AI_ANALYSIS: 300,
            WorkflowStage.NOTIFICATION: 60
        }
    
    def _initialize_recovery_strategies(self) -> Dict[WorkflowStage, Dict[str, RecoveryAction]]:
        """復旧戦略を初期化"""
        return {
            WorkflowStage.DATA_EXTRACTION: {
                "ConnectionError": RecoveryAction.RETRY,
                "TimeoutError": RecoveryAction.RETRY,
                "ValidationError": RecoveryAction.ABORT,
                "default": RecoveryAction.RETRY
            },
            WorkflowStage.STOCK_DATA_RETRIEVAL: {
                "RateLimitError": RecoveryAction.RETRY,
                "NetworkError": RecoveryAction.RETRY,
                "APIError": RecoveryAction.FALLBACK,
                "default": RecoveryAction.SKIP
            },
            WorkflowStage.HISTORICAL_DATA_RETRIEVAL: {
                "NetworkError": RecoveryAction.RETRY,
                "CacheError": RecoveryAction.SKIP,
                "default": RecoveryAction.SKIP
            },
            WorkflowStage.TECHNICAL_ANALYSIS: {
                "DataInsufficient": RecoveryAction.FALLBACK,
                "CalculationError": RecoveryAction.SKIP,
                "default": RecoveryAction.SKIP
            },
            WorkflowStage.AI_ANALYSIS: {
                "APIError": RecoveryAction.RETRY,
                "RateLimitError": RecoveryAction.RETRY,
                "ParseError": RecoveryAction.FALLBACK,
                "default": RecoveryAction.FALLBACK
            },
            WorkflowStage.NOTIFICATION: {
                "NetworkError": RecoveryAction.RETRY,
                "RateLimitError": RecoveryAction.RETRY,
                "default": RecoveryAction.SKIP
            }
        }
    
    async def execute_workflow(self, context: WorkflowContext) -> Tuple[bool, Any, WorkflowMetrics]:
        """
        ワークフローを実行
        
        Args:
            context: ワークフロー実行コンテキスト
            
        Returns:
            Tuple[bool, Any, WorkflowMetrics]: (成功フラグ, 分析結果, メトリクス)
        """
        metrics = WorkflowMetrics(start_time=datetime.now())
        
        await self._log_workflow_start(context, metrics)
        
        try:
            # 段階別実行
            data_extraction_result = await self._execute_stage(
                WorkflowStage.DATA_EXTRACTION,
                self._extract_data,
                context, metrics
            )
            
            validation_result = await self._execute_stage(
                WorkflowStage.DATA_VALIDATION,
                self._validate_data,
                context, metrics, data_extraction_result
            )
            
            stock_data_result = await self._execute_stage(
                WorkflowStage.STOCK_DATA_RETRIEVAL,
                self._retrieve_stock_data,
                context, metrics, validation_result
            )
            
            historical_data_result = await self._execute_stage(
                WorkflowStage.HISTORICAL_DATA_RETRIEVAL,
                self._retrieve_historical_data,
                context, metrics, stock_data_result
            )
            
            technical_analysis_result = await self._execute_stage(
                WorkflowStage.TECHNICAL_ANALYSIS,
                self._perform_technical_analysis,
                context, metrics, stock_data_result, historical_data_result
            )
            
            analysis_result = await self._execute_stage(
                WorkflowStage.AI_ANALYSIS,
                self._perform_ai_analysis,
                context, metrics, validation_result, stock_data_result, technical_analysis_result
            )
            
            if context.enable_notifications:
                await self._execute_stage(
                    WorkflowStage.NOTIFICATION,
                    self._send_notifications,
                    context, metrics, analysis_result
                )
            
            # クリーンアップ
            await self._execute_stage(
                WorkflowStage.CLEANUP,
                self._cleanup_resources,
                context, metrics
            )
            
            # 完了
            metrics.current_stage = WorkflowStage.COMPLETED
            metrics.end_time = datetime.now()
            
            await self._log_workflow_completion(context, metrics, True)
            
            return True, analysis_result, metrics
            
        except Exception as e:
            metrics.current_stage = WorkflowStage.FAILED
            metrics.end_time = datetime.now()
            
            error = WorkflowError(
                stage=metrics.current_stage,
                error_message=str(e),
                error_type=type(e).__name__,
                timestamp=datetime.now(),
                recoverable=False
            )
            metrics.errors.append(error)
            
            await self._log_workflow_completion(context, metrics, False, str(e))
            
            return False, None, metrics
    
    async def _execute_stage(self, 
                           stage: WorkflowStage, 
                           stage_func, 
                           context: WorkflowContext, 
                           metrics: WorkflowMetrics, 
                           *args) -> Any:
        """段階を実行"""
        stage_start = datetime.now()
        metrics.current_stage = stage
        
        self.logger.info(f"ワークフロー段階開始: {stage.display_name}")
        
        try:
            # タイムアウト設定
            timeout = self.stage_timeouts.get(stage, 300)
            
            # 段階実行
            result = await asyncio.wait_for(
                stage_func(context, metrics, *args),
                timeout=timeout
            )
            
            # 成功記録
            stage_duration = (datetime.now() - stage_start).total_seconds()
            metrics.stage_durations[stage.value] = stage_duration
            metrics.completed_stages.append(stage)
            
            self.logger.info(f"ワークフロー段階完了: {stage.display_name} ({stage_duration:.2f}秒)")
            
            return result
            
        except asyncio.TimeoutError:
            error = WorkflowError(
                stage=stage,
                error_message=f"段階がタイムアウトしました: {timeout}秒",
                error_type="TimeoutError",
                timestamp=datetime.now()
            )
            
            # 復旧試行
            recovery_result = await self._attempt_recovery(error, context, metrics)
            if recovery_result is not None:
                return recovery_result
            
            raise
            
        except Exception as e:
            error = WorkflowError(
                stage=stage,
                error_message=str(e),
                error_type=type(e).__name__,
                timestamp=datetime.now()
            )
            
            # 復旧試行
            recovery_result = await self._attempt_recovery(error, context, metrics)
            if recovery_result is not None:
                return recovery_result
            
            raise
    
    async def _attempt_recovery(self, 
                              error: WorkflowError, 
                              context: WorkflowContext, 
                              metrics: WorkflowMetrics) -> Optional[Any]:
        """復旧を試行"""
        if not context.fallback_on_errors:
            return None
        
        stage_strategies = self.recovery_strategies.get(error.stage, {})
        recovery_action = stage_strategies.get(error.error_type, stage_strategies.get("default"))
        
        if not recovery_action:
            return None
        
        error.recovery_action = recovery_action
        metrics.errors.append(error)
        
        self.logger.warning(f"段階エラー発生、復旧試行: {error.stage.display_name} - {recovery_action.display_name}")
        
        if recovery_action == RecoveryAction.RETRY:
            # リトライ（簡単な実装）
            await asyncio.sleep(2)
            return await self._create_fallback_result(error.stage)
        
        elif recovery_action == RecoveryAction.SKIP:
            # スキップ
            return await self._create_fallback_result(error.stage)
        
        elif recovery_action == RecoveryAction.FALLBACK:
            # フォールバック
            return await self._create_fallback_result(error.stage)
        
        elif recovery_action == RecoveryAction.ABORT:
            # 中止
            return None
        
        return None
    
    async def _create_fallback_result(self, stage: WorkflowStage) -> Any:
        """フォールバック結果を作成"""
        if stage == WorkflowStage.DATA_EXTRACTION:
            return DataExtractionResult(success=False, data=[], errors=["フォールバック結果"])
        
        elif stage == WorkflowStage.STOCK_DATA_RETRIEVAL:
            return BatchDataResult(success=False, stock_data={}, errors=["フォールバック結果"])
        
        elif stage == WorkflowStage.AI_ANALYSIS:
            # 簡単な分析結果を返す
            from src.models.analysis_models import AnalysisResult
            return AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                timestamp=datetime.now(),
                summary="フォールバック分析結果",
                recommendation=None,
                risk_assessment=None,
                confidence_score=0.1
            )
        
        return None
    
    # 段階別実装メソッド
    async def _extract_data(self, context: WorkflowContext, metrics: WorkflowMetrics) -> DataExtractionResult:
        """データ抽出段階"""
        holdings_result = self.sheets_service.get_holdings_data()
        watchlist_result = self.sheets_service.get_watchlist_data()
        
        if not holdings_result.success and not watchlist_result.success:
            raise Exception("保有銘柄とウォッチリストの両方の取得に失敗")
        
        # データ数記録
        metrics.data_counts["holdings"] = len(holdings_result.data) if holdings_result.success else 0
        metrics.data_counts["watchlist"] = len(watchlist_result.data) if watchlist_result.success else 0
        
        return holdings_result if holdings_result.success else watchlist_result
    
    async def _validate_data(self, context: WorkflowContext, metrics: WorkflowMetrics, 
                           data_result: DataExtractionResult) -> DataExtractionResult:
        """データ検証段階"""
        if not data_result.success:
            return data_result
        
        # データ検証実行
        validated_data = []
        for item in data_result.data:
            validation_result = self.validation_service.validate_stock_config(item)
            if validation_result.is_valid:
                validated_data.append(item)
        
        return DataExtractionResult(
            success=len(validated_data) > 0,
            data=validated_data,
            errors=data_result.errors
        )
    
    async def _retrieve_stock_data(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                 validated_data: DataExtractionResult) -> BatchDataResult:
        """株価データ取得段階"""
        if not validated_data.success:
            raise Exception("検証済みデータが利用できません")
        
        symbols = [item.symbol for item in validated_data.data]
        result = self.stock_service.get_batch_stock_data(symbols)
        
        metrics.data_counts["stock_data"] = len(result.stock_data) if result.success else 0
        
        return result
    
    async def _retrieve_historical_data(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                      stock_data_result: BatchDataResult) -> Dict[str, Any]:
        """履歴データ取得段階"""
        if not stock_data_result.success:
            return {}
        
        historical_data = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)  # 過去30日間
        
        for symbol in stock_data_result.stock_data.keys():
            try:
                hist_result = self.historical_manager.get_historical_data(symbol, start_date, end_date)
                if hist_result.success:
                    historical_data[symbol] = hist_result.dataset
            except Exception as e:
                self.logger.warning(f"履歴データ取得失敗 ({symbol}): {e}")
        
        metrics.data_counts["historical_data"] = len(historical_data)
        
        return historical_data
    
    async def _perform_technical_analysis(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                        stock_data_result: BatchDataResult,
                                        historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """テクニカル分析段階"""
        technical_results = {}
        
        for symbol, stock_data in stock_data_result.stock_data.items():
            try:
                if symbol in historical_data:
                    hist_dataset = historical_data[symbol]
                    tech_result = self.technical_service.analyze_stock(stock_data, hist_dataset)
                    technical_results[symbol] = tech_result
            except Exception as e:
                self.logger.warning(f"テクニカル分析失敗 ({symbol}): {e}")
        
        metrics.data_counts["technical_analysis"] = len(technical_results)
        
        return technical_results
    
    async def _perform_ai_analysis(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                 validated_data: DataExtractionResult,
                                 stock_data_result: BatchDataResult,
                                 technical_results: Dict[str, Any]) -> Any:
        """AI分析段階"""
        if not context.enable_ai_analysis:
            return await self._create_fallback_result(WorkflowStage.AI_ANALYSIS)
        
        # 分析タイプ別実行
        if context.analysis_type == AnalysisType.DAILY:
            return self.daily_service.execute_daily_analysis(
                analysis_mode=context.analysis_mode,
                enable_ai_analysis=True
            )
        elif context.analysis_type == AnalysisType.WEEKLY:
            return self.weekly_service.execute_weekly_analysis(
                analysis_mode=context.analysis_mode,
                enable_ai_analysis=True
            )
        elif context.analysis_type == AnalysisType.MONTHLY:
            return self.monthly_service.execute_monthly_analysis(
                analysis_mode=context.analysis_mode,
                enable_ai_analysis=True
            )
        else:
            raise ValueError(f"サポートされていない分析タイプ: {context.analysis_type}")
    
    async def _send_notifications(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                analysis_result: Any) -> bool:
        """通知送信段階"""
        if not self.notification_manager:
            self.logger.info("通知マネージャーが利用できません")
            return False
        
        success = await self.notification_manager.send_analysis_notification(analysis_result)
        metrics.data_counts["notifications_sent"] = 1 if success else 0
        
        return success
    
    async def _cleanup_resources(self, context: WorkflowContext, metrics: WorkflowMetrics):
        """リソースクリーンアップ段階"""
        # 必要に応じてリソースのクリーンアップを実行
        # 現在の実装では特別なクリーンアップは不要
        pass
    
    async def _log_workflow_start(self, context: WorkflowContext, metrics: WorkflowMetrics):
        """ワークフロー開始ログ"""
        if self.structured_logger:
            await self.structured_logger.log_structured(
                level=LogLevel.INFO,
                message="ワークフロー実行開始",
                context={
                    "workflow_context": context.to_dict(),
                    "start_time": metrics.start_time.isoformat()
                }
            )
    
    async def _log_workflow_completion(self, context: WorkflowContext, metrics: WorkflowMetrics,
                                     success: bool, error_message: Optional[str] = None):
        """ワークフロー完了ログ"""
        if self.structured_logger:
            log_context = {
                "workflow_context": context.to_dict(),
                "metrics": metrics.to_dict(),
                "success": success
            }
            
            if error_message:
                log_context["error"] = error_message
            
            await self.structured_logger.log_structured(
                level=LogLevel.INFO if success else LogLevel.ERROR,
                message="ワークフロー実行完了" if success else "ワークフロー実行失敗",
                context=log_context
            )