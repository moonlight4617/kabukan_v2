# -*- coding: utf-8 -*-
"""
AI分析エラーハンドリングサービス
API呼び出し失敗時のリトライ機能、分析結果の品質チェック機能を提供
"""

import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import random

from src.models.analysis_models import AnalysisResult, AnalysisType
from src.services.gemini_service import GeminiService, GeminiResponse, AnalysisMode
from src.services.analysis_result_parser import AnalysisResultParser, ParseResult, ParseStatus
from src.services.retry_manager import RetryManager, RetryConfig, RetryReason


logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """エラータイプ"""
    API_FAILURE = "api_failure"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    QUALITY_CHECK_FAILURE = "quality_check_failure"
    INVALID_RESPONSE = "invalid_response"
    AUTHENTICATION_ERROR = "authentication_error"
    SERVICE_UNAVAILABLE = "service_unavailable"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ErrorType.API_FAILURE: "API呼び出し失敗",
            ErrorType.RATE_LIMIT: "レート制限",
            ErrorType.TIMEOUT: "タイムアウト",
            ErrorType.PARSE_ERROR: "パースエラー",
            ErrorType.QUALITY_CHECK_FAILURE: "品質チェック失敗",
            ErrorType.INVALID_RESPONSE: "無効なレスポンス",
            ErrorType.AUTHENTICATION_ERROR: "認証エラー",
            ErrorType.SERVICE_UNAVAILABLE: "サービス利用不可"
        }[self]


class RecoveryStrategy(Enum):
    """復旧戦略"""
    RETRY = "retry"
    FALLBACK = "fallback"
    SKIP = "skip"
    CIRCUIT_BREAKER = "circuit_breaker"
    EXPONENTIAL_BACKOFF = "exponential_backoff"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            RecoveryStrategy.RETRY: "リトライ",
            RecoveryStrategy.FALLBACK: "フォールバック",
            RecoveryStrategy.SKIP: "スキップ",
            RecoveryStrategy.CIRCUIT_BREAKER: "サーキットブレーカー",
            RecoveryStrategy.EXPONENTIAL_BACKOFF: "指数バックオフ"
        }[self]


@dataclass
class ErrorContext:
    """エラーコンテキスト"""
    error_type: ErrorType
    error_message: str
    timestamp: datetime
    analysis_type: AnalysisType
    analysis_mode: AnalysisMode
    attempt_count: int
    original_request: Dict[str, Any]
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "error_type": self.error_type.value,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "analysis_type": self.analysis_type.value,
            "analysis_mode": self.analysis_mode.value,
            "attempt_count": self.attempt_count,
            "original_request": self.original_request,
            "stack_trace": self.stack_trace
        }


@dataclass
class RecoveryAction:
    """復旧アクション"""
    strategy: RecoveryStrategy
    delay_seconds: float
    max_attempts: int
    success_condition: Optional[Callable[[Any], bool]] = None
    fallback_function: Optional[Callable[[], Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "strategy": self.strategy.value,
            "delay_seconds": self.delay_seconds,
            "max_attempts": self.max_attempts
        }


@dataclass
class AIAnalysisResult:
    """AI分析結果"""
    success: bool
    analysis_result: Optional[AnalysisResult]
    error_context: Optional[ErrorContext]
    recovery_actions: List[RecoveryAction] = field(default_factory=list)
    execution_time: float = 0.0
    quality_score: float = 0.0
    
    @property
    def is_recoverable(self) -> bool:
        """復旧可能か"""
        return bool(self.recovery_actions)


class QualityChecker:
    """品質チェッカー"""
    
    def __init__(self):
        self.min_confidence_score = 0.3
        self.min_summary_length = 20
        self.required_reasoning_length = 30
    
    def check_analysis_quality(self, analysis_result: AnalysisResult) -> tuple[bool, float, List[str]]:
        """
        分析結果の品質をチェック
        
        Args:
            analysis_result: 分析結果
            
        Returns:
            tuple[bool, float, List[str]]: (品質OK, 品質スコア, 問題リスト)
        """
        issues = []
        quality_score = 1.0
        
        # 信頼度スコアチェック
        if analysis_result.confidence_score < self.min_confidence_score:
            issues.append(f"信頼度スコアが低すぎます: {analysis_result.confidence_score}")
            quality_score -= 0.3
        
        # サマリー品質チェック
        if not analysis_result.summary or len(analysis_result.summary) < self.min_summary_length:
            issues.append("サマリーが短すぎます")
            quality_score -= 0.2
        
        # 推奨事項チェック
        if analysis_result.recommendation:
            rec = analysis_result.recommendation
            if not rec.reasoning or len(rec.reasoning) < self.required_reasoning_length:
                issues.append("推奨理由が不十分です")
                quality_score -= 0.2
            
            if rec.confidence < self.min_confidence_score:
                issues.append("推奨の信頼度が低すぎます")
                quality_score -= 0.2
        else:
            issues.append("推奨事項がありません")
            quality_score -= 0.4
        
        # リスク評価チェック
        if analysis_result.risk_assessment:
            risk = analysis_result.risk_assessment
            if not risk.factors or len(risk.factors) == 0:
                issues.append("リスク要因が特定されていません")
                quality_score -= 0.1
        
        quality_score = max(0.0, quality_score)
        is_quality_ok = quality_score >= 0.6 and len(issues) <= 2
        
        return is_quality_ok, quality_score, issues


class AIAnalysisErrorHandler:
    """AI分析エラーハンドリングサービス"""
    
    def __init__(self,
                 gemini_service: GeminiService,
                 result_parser: AnalysisResultParser,
                 retry_manager: Optional[RetryManager] = None):
        """
        Args:
            gemini_service: Gemini AIサービス
            result_parser: 分析結果パーサー
            retry_manager: リトライマネージャー
        """
        self.gemini_service = gemini_service
        self.result_parser = result_parser
        self.retry_manager = retry_manager or RetryManager(RetryConfig())
        self.quality_checker = QualityChecker()
        self.logger = logging.getLogger(__name__)
        
        # エラー復旧戦略マッピング
        self.error_recovery_map = {
            ErrorType.API_FAILURE: RecoveryAction(
                strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
                delay_seconds=1.0,
                max_attempts=3
            ),
            ErrorType.RATE_LIMIT: RecoveryAction(
                strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
                delay_seconds=5.0,
                max_attempts=5
            ),
            ErrorType.TIMEOUT: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay_seconds=2.0,
                max_attempts=2
            ),
            ErrorType.PARSE_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay_seconds=0.5,
                max_attempts=2
            ),
            ErrorType.QUALITY_CHECK_FAILURE: RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                delay_seconds=1.0,
                max_attempts=2
            ),
            ErrorType.AUTHENTICATION_ERROR: RecoveryAction(
                strategy=RecoveryStrategy.CIRCUIT_BREAKER,
                delay_seconds=0.0,
                max_attempts=1
            ),
            ErrorType.SERVICE_UNAVAILABLE: RecoveryAction(
                strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
                delay_seconds=10.0,
                max_attempts=3
            )
        }
    
    async def execute_analysis_with_error_handling(self,
                                                 analysis_function: Callable,
                                                 analysis_type: AnalysisType,
                                                 analysis_mode: AnalysisMode,
                                                 **kwargs) -> AIAnalysisResult:
        """
        エラーハンドリング付きでAI分析を実行
        
        Args:
            analysis_function: 分析関数
            analysis_type: 分析タイプ
            analysis_mode: 分析モード
            **kwargs: 分析関数の引数
            
        Returns:
            AIAnalysisResult: AI分析結果
        """
        start_time = datetime.now()
        self.logger.info(f"AI分析開始: {analysis_type.value}, モード: {analysis_mode.value}")
        
        last_error_context = None
        recovery_actions = []
        
        for attempt in range(1, 4):  # 最大3回試行
            try:
                # 分析実行
                result = await self._execute_analysis_attempt(
                    analysis_function, analysis_type, analysis_mode, attempt, **kwargs
                )
                
                if result.success:
                    execution_time = (datetime.now() - start_time).total_seconds()
                    result.execution_time = execution_time
                    
                    self.logger.info(f"AI分析成功: 実行時間 {execution_time:.2f}秒, 品質スコア: {result.quality_score:.2f}")
                    return result
                
                last_error_context = result.error_context
                recovery_actions.extend(result.recovery_actions)
                
                # 復旧アクションの実行
                if result.recovery_actions:
                    recovery_action = result.recovery_actions[0]
                    await self._execute_recovery_action(recovery_action, attempt)
                
            except Exception as e:
                self.logger.error(f"AI分析試行 {attempt} で予期しないエラー: {e}")
                last_error_context = ErrorContext(
                    error_type=ErrorType.API_FAILURE,
                    error_message=str(e),
                    timestamp=datetime.now(),
                    analysis_type=analysis_type,
                    analysis_mode=analysis_mode,
                    attempt_count=attempt,
                    original_request=kwargs,
                    stack_trace=str(e)
                )
        
        # 全ての試行が失敗
        execution_time = (datetime.now() - start_time).total_seconds()
        self.logger.error(f"AI分析失敗: 全ての試行が失敗, 実行時間 {execution_time:.2f}秒")
        
        return AIAnalysisResult(
            success=False,
            analysis_result=None,
            error_context=last_error_context,
            recovery_actions=recovery_actions,
            execution_time=execution_time,
            quality_score=0.0
        )
    
    async def _execute_analysis_attempt(self,
                                      analysis_function: Callable,
                                      analysis_type: AnalysisType,
                                      analysis_mode: AnalysisMode,
                                      attempt: int,
                                      **kwargs) -> AIAnalysisResult:
        """分析試行を実行"""
        try:
            # Gemini API呼び出し
            gemini_response = await self._safe_gemini_call(analysis_function, **kwargs)
            
            if not gemini_response.success:
                error_type = self._classify_gemini_error(gemini_response.error_message)
                error_context = ErrorContext(
                    error_type=error_type,
                    error_message=gemini_response.error_message or "Unknown error",
                    timestamp=datetime.now(),
                    analysis_type=analysis_type,
                    analysis_mode=analysis_mode,
                    attempt_count=attempt,
                    original_request=kwargs
                )
                
                recovery_action = self.error_recovery_map.get(error_type)
                recovery_actions = [recovery_action] if recovery_action else []
                
                return AIAnalysisResult(
                    success=False,
                    analysis_result=None,
                    error_context=error_context,
                    recovery_actions=recovery_actions
                )
            
            # レスポンスパース
            parse_result = self.result_parser.parse_gemini_response(
                gemini_response.raw_response,
                analysis_type
            )
            
            if parse_result.status == ParseStatus.FAILED:
                error_context = ErrorContext(
                    error_type=ErrorType.PARSE_ERROR,
                    error_message=parse_result.error_message or "Parse failed",
                    timestamp=datetime.now(),
                    analysis_type=analysis_type,
                    analysis_mode=analysis_mode,
                    attempt_count=attempt,
                    original_request=kwargs
                )
                
                recovery_action = self.error_recovery_map.get(ErrorType.PARSE_ERROR)
                
                return AIAnalysisResult(
                    success=False,
                    analysis_result=None,
                    error_context=error_context,
                    recovery_actions=[recovery_action] if recovery_action else []
                )
            
            # 品質チェック
            if parse_result.analysis_result:
                is_quality_ok, quality_score, issues = self.quality_checker.check_analysis_quality(
                    parse_result.analysis_result
                )
                
                if not is_quality_ok:
                    error_context = ErrorContext(
                        error_type=ErrorType.QUALITY_CHECK_FAILURE,
                        error_message=f"品質チェック失敗: {', '.join(issues)}",
                        timestamp=datetime.now(),
                        analysis_type=analysis_type,
                        analysis_mode=analysis_mode,
                        attempt_count=attempt,
                        original_request=kwargs
                    )
                    
                    recovery_action = self.error_recovery_map.get(ErrorType.QUALITY_CHECK_FAILURE)
                    
                    return AIAnalysisResult(
                        success=False,
                        analysis_result=parse_result.analysis_result,
                        error_context=error_context,
                        recovery_actions=[recovery_action] if recovery_action else [],
                        quality_score=quality_score
                    )
                
                return AIAnalysisResult(
                    success=True,
                    analysis_result=parse_result.analysis_result,
                    error_context=None,
                    quality_score=quality_score
                )
            
            # パース結果が空
            error_context = ErrorContext(
                error_type=ErrorType.INVALID_RESPONSE,
                error_message="パース結果が空です",
                timestamp=datetime.now(),
                analysis_type=analysis_type,
                analysis_mode=analysis_mode,
                attempt_count=attempt,
                original_request=kwargs
            )
            
            return AIAnalysisResult(
                success=False,
                analysis_result=None,
                error_context=error_context,
                recovery_actions=[]
            )
            
        except Exception as e:
            error_context = ErrorContext(
                error_type=ErrorType.API_FAILURE,
                error_message=str(e),
                timestamp=datetime.now(),
                analysis_type=analysis_type,
                analysis_mode=analysis_mode,
                attempt_count=attempt,
                original_request=kwargs,
                stack_trace=str(e)
            )
            
            recovery_action = self.error_recovery_map.get(ErrorType.API_FAILURE)
            
            return AIAnalysisResult(
                success=False,
                analysis_result=None,
                error_context=error_context,
                recovery_actions=[recovery_action] if recovery_action else []
            )
    
    async def _safe_gemini_call(self, analysis_function: Callable, **kwargs) -> GeminiResponse:
        """安全なGemini API呼び出し"""
        try:
            if asyncio.iscoroutinefunction(analysis_function):
                return await analysis_function(**kwargs)
            else:
                return analysis_function(**kwargs)
        except Exception as e:
            return GeminiResponse(
                success=False,
                raw_response="",
                analysis_result=None,
                error_message=str(e),
                execution_time=0.0
            )
    
    def _classify_gemini_error(self, error_message: Optional[str]) -> ErrorType:
        """Geminiエラーを分類"""
        if not error_message:
            return ErrorType.API_FAILURE
        
        error_lower = error_message.lower()
        
        if "rate limit" in error_lower or "quota" in error_lower:
            return ErrorType.RATE_LIMIT
        elif "timeout" in error_lower:
            return ErrorType.TIMEOUT
        elif "auth" in error_lower or "permission" in error_lower:
            return ErrorType.AUTHENTICATION_ERROR
        elif "unavailable" in error_lower or "503" in error_lower:
            return ErrorType.SERVICE_UNAVAILABLE
        else:
            return ErrorType.API_FAILURE
    
    async def _execute_recovery_action(self, recovery_action: RecoveryAction, attempt: int):
        """復旧アクションを実行"""
        if recovery_action.strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
            delay = recovery_action.delay_seconds * (2 ** (attempt - 1))
            jitter = random.uniform(0, 0.1 * delay)  # ジッター追加
            total_delay = delay + jitter
            
            self.logger.info(f"指数バックオフ待機: {total_delay:.2f}秒")
            await asyncio.sleep(total_delay)
            
        elif recovery_action.strategy == RecoveryStrategy.RETRY:
            if recovery_action.delay_seconds > 0:
                self.logger.info(f"リトライ前待機: {recovery_action.delay_seconds}秒")
                await asyncio.sleep(recovery_action.delay_seconds)
        
        elif recovery_action.strategy == RecoveryStrategy.CIRCUIT_BREAKER:
            self.logger.warning("サーキットブレーカー発動: 復旧処理をスキップ")
    
    def create_fallback_analysis_result(self,
                                      analysis_type: AnalysisType,
                                      error_context: ErrorContext) -> AnalysisResult:
        """フォールバック分析結果を作成"""
        from src.models.analysis_models import Recommendation, RiskAssessment, RiskLevel
        
        # 基本的なフォールバック推奨
        fallback_recommendation = Recommendation(
            action="HOLD",
            confidence=0.3,
            reasoning=f"AI分析が失敗したため、保守的なアプローチを推奨します。エラー: {error_context.error_message}",
            risk_level=RiskLevel.MEDIUM
        )
        
        # 基本的なリスク評価
        fallback_risk_assessment = RiskAssessment(
            level=RiskLevel.MEDIUM,
            factors=["AI分析失敗によるリスク", "不確実性の増大"],
            score=50,
            description="AI分析が利用できないため、標準的なリスクレベルを設定",
            mitigation_strategies=["手動分析の実施", "専門家への相談"]
        )
        
        return AnalysisResult(
            analysis_type=analysis_type,
            timestamp=datetime.now(),
            summary=f"AI分析が利用できないため、フォールバック結果を提供します。{error_context.error_type.display_name}が発生しました。",
            recommendation=fallback_recommendation,
            risk_assessment=fallback_risk_assessment,
            confidence_score=0.3,
            metadata={
                "fallback": True,
                "error_type": error_context.error_type.value,
                "error_message": error_context.error_message,
                "generated_at": datetime.now().isoformat()
            }
        )