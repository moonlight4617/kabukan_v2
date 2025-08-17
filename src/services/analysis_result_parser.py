# -*- coding: utf-8 -*-
"""
分析結果パーサーサービス
Gemini APIレスポンスのパースと構造化、分析結果の検証と正規化機能を提供
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.models.analysis_models import AnalysisResult, AnalysisType, Recommendation, RiskAssessment, RiskLevel


logger = logging.getLogger(__name__)


class ParseStatus(Enum):
    """パース状態"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    INVALID_FORMAT = "invalid_format"
    VALIDATION_ERROR = "validation_error"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ParseStatus.SUCCESS: "成功",
            ParseStatus.PARTIAL_SUCCESS: "部分的成功", 
            ParseStatus.FAILED: "失敗",
            ParseStatus.INVALID_FORMAT: "フォーマット無効",
            ParseStatus.VALIDATION_ERROR: "検証エラー"
        }[self]


class ValidationSeverity(Enum):
    """検証重要度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ValidationSeverity.INFO: "情報",
            ValidationSeverity.WARNING: "警告",
            ValidationSeverity.ERROR: "エラー",
            ValidationSeverity.CRITICAL: "重大"
        }[self]


@dataclass
class ValidationIssue:
    """検証問題"""
    field: str
    severity: ValidationSeverity
    message: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "field": self.field,
            "severity": self.severity.value,
            "message": self.message,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value
        }


@dataclass
class ParseResult:
    """パース結果"""
    status: ParseStatus
    parsed_data: Optional[Dict[str, Any]]
    analysis_result: Optional[AnalysisResult]
    validation_issues: List[ValidationIssue]
    confidence_score: float
    processing_time: float
    raw_response: str
    error_message: Optional[str] = None
    
    @property
    def is_successful(self) -> bool:
        """成功したか"""
        return self.status in [ParseStatus.SUCCESS, ParseStatus.PARTIAL_SUCCESS]
    
    @property
    def has_critical_issues(self) -> bool:
        """重大な問題があるか"""
        return any(issue.severity == ValidationSeverity.CRITICAL for issue in self.validation_issues)


class AnalysisResultParser:
    """分析結果パーサーサービス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialize_validators()
    
    def _initialize_validators(self):
        """バリデーターを初期化"""
        self.required_fields = {
            "stock_analysis": ["recommendation", "confidence", "reasoning"],
            "portfolio_analysis": ["overall_score", "risk_level", "diversification_score"],
            "watchlist_analysis": ["top_picks", "market_timing"],
            "risk_assessment": ["risk_level", "risk_factors"]
        }
        
        self.field_types = {
            "confidence": float,
            "target_price": float,
            "stop_loss": float,
            "overall_score": int,
            "diversification_score": int,
            "priority": int
        }
        
        self.enum_fields = {
            "recommendation": ["BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"],
            "risk_level": ["LOW", "MEDIUM", "HIGH"],
            "performance_outlook": ["POSITIVE", "NEUTRAL", "NEGATIVE"],
            "market_timing": ["NOW", "WAIT", "DIP"],
            "entry_timing": ["NOW", "WAIT", "DIP"]
        }
    
    def parse_gemini_response(self, 
                            raw_response: str,
                            analysis_type: AnalysisType,
                            expected_format: str = "json") -> ParseResult:
        """
        Geminiレスポンスをパース
        
        Args:
            raw_response: 生のレスポンス文字列
            analysis_type: 分析タイプ
            expected_format: 期待するフォーマット
            
        Returns:
            ParseResult: パース結果
        """
        start_time = datetime.now()
        self.logger.info(f"分析結果パース開始: {analysis_type.value}")
        
        try:
            # JSON抽出を試行
            json_data = self._extract_json_from_response(raw_response)
            
            if not json_data:
                return ParseResult(
                    status=ParseStatus.INVALID_FORMAT,
                    parsed_data=None,
                    analysis_result=None,
                    validation_issues=[ValidationIssue(
                        field="response",
                        severity=ValidationSeverity.CRITICAL,
                        message="JSONフォーマットが見つかりません",
                        actual_value=raw_response[:100] + "..." if len(raw_response) > 100 else raw_response
                    )],
                    confidence_score=0.0,
                    processing_time=0.0,
                    raw_response=raw_response,
                    error_message="JSONフォーマットが見つかりません"
                )
            
            # データ検証
            validation_issues = self._validate_parsed_data(json_data, analysis_type)
            
            # 信頼度スコア計算
            confidence_score = self._calculate_confidence_score(json_data, validation_issues)
            
            # AnalysisResultオブジェクトに変換
            analysis_result = self._convert_to_analysis_result(json_data, analysis_type)
            
            # ステータス決定
            status = self._determine_parse_status(validation_issues, analysis_result)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            result = ParseResult(
                status=status,
                parsed_data=json_data,
                analysis_result=analysis_result,
                validation_issues=validation_issues,
                confidence_score=confidence_score,
                processing_time=processing_time,
                raw_response=raw_response
            )
            
            self.logger.info(f"パース完了: {status.value}, 信頼度: {confidence_score:.2f}")
            return result
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            self.logger.error(f"パース中にエラーが発生: {e}")
            
            return ParseResult(
                status=ParseStatus.FAILED,
                parsed_data=None,
                analysis_result=None,
                validation_issues=[ValidationIssue(
                    field="parser",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"パースエラー: {str(e)}"
                )],
                confidence_score=0.0,
                processing_time=processing_time,
                raw_response=raw_response,
                error_message=str(e)
            )
    
    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """レスポンスからJSONを抽出"""
        try:
            # まず直接JSON解析を試行
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # JSON部分を正規表現で抽出
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',  # マークダウン形式
            r'```\s*(\{.*?\})\s*```',      # 汎用マークダウン
            r'(\{.*?\})',                  # 単純なJSONブロック
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _validate_parsed_data(self, data: Dict[str, Any], analysis_type: AnalysisType) -> List[ValidationIssue]:
        """パース済みデータを検証"""
        issues = []
        analysis_key = analysis_type.value.lower() + "_analysis"
        
        # 必須フィールドチェック
        required_fields = self.required_fields.get(analysis_key, [])
        for field in required_fields:
            if field not in data:
                issues.append(ValidationIssue(
                    field=field,
                    severity=ValidationSeverity.ERROR,
                    message=f"必須フィールド '{field}' がありません"
                ))
        
        # データ型チェック
        for field, expected_type in self.field_types.items():
            if field in data:
                if not isinstance(data[field], expected_type):
                    issues.append(ValidationIssue(
                        field=field,
                        severity=ValidationSeverity.WARNING,
                        message=f"フィールド '{field}' の型が期待値と異なります",
                        expected_value=str(expected_type.__name__),
                        actual_value=str(type(data[field]).__name__)
                    ))
        
        # 列挙値チェック
        for field, valid_values in self.enum_fields.items():
            if field in data:
                if data[field] not in valid_values:
                    issues.append(ValidationIssue(
                        field=field,
                        severity=ValidationSeverity.ERROR,
                        message=f"フィールド '{field}' の値が無効です",
                        expected_value=", ".join(valid_values),
                        actual_value=str(data[field])
                    ))
        
        # 範囲チェック
        if "confidence" in data:
            confidence = data["confidence"]
            if not (0.0 <= confidence <= 1.0):
                issues.append(ValidationIssue(
                    field="confidence",
                    severity=ValidationSeverity.ERROR,
                    message="信頼度は0.0-1.0の範囲内である必要があります",
                    expected_value="0.0-1.0",
                    actual_value=str(confidence)
                ))
        
        if "overall_score" in data:
            score = data["overall_score"]
            if not (0 <= score <= 100):
                issues.append(ValidationIssue(
                    field="overall_score",
                    severity=ValidationSeverity.ERROR,
                    message="総合スコアは0-100の範囲内である必要があります",
                    expected_value="0-100",
                    actual_value=str(score)
                ))
        
        return issues
    
    def _calculate_confidence_score(self, data: Dict[str, Any], validation_issues: List[ValidationIssue]) -> float:
        """信頼度スコアを計算"""
        base_score = 1.0
        
        # 検証問題による減点
        for issue in validation_issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                base_score -= 0.3
            elif issue.severity == ValidationSeverity.ERROR:
                base_score -= 0.2
            elif issue.severity == ValidationSeverity.WARNING:
                base_score -= 0.1
        
        # データ完全性による加点
        if "reasoning" in data and len(str(data["reasoning"])) > 50:
            base_score += 0.1
        
        if "key_factors" in data and isinstance(data["key_factors"], list) and len(data["key_factors"]) >= 3:
            base_score += 0.1
        
        return max(0.0, min(1.0, base_score))
    
    def _convert_to_analysis_result(self, data: Dict[str, Any], analysis_type: AnalysisType) -> Optional[AnalysisResult]:
        """辞書データをAnalysisResultオブジェクトに変換"""
        try:
            # 推奨事項の作成
            recommendation = None
            if "recommendation" in data:
                recommendation = Recommendation(
                    action=data["recommendation"],
                    confidence=data.get("confidence", 0.5),
                    reasoning=data.get("reasoning", ""),
                    target_price=data.get("target_price"),
                    stop_loss=data.get("stop_loss"),
                    expected_return=data.get("expected_return"),
                    risk_level=RiskLevel(data.get("risk_level", "MEDIUM"))
                )
            
            # リスク評価の作成
            risk_assessment = None
            if "risk_level" in data or "risk_factors" in data:
                risk_assessment = RiskAssessment(
                    level=RiskLevel(data.get("risk_level", "MEDIUM")),
                    factors=data.get("risk_factors", []),
                    score=data.get("risk_score", 50),
                    description=data.get("risk_description", ""),
                    mitigation_strategies=data.get("mitigation_strategies", [])
                )
            
            # AnalysisResultの作成
            return AnalysisResult(
                analysis_type=analysis_type,
                timestamp=datetime.now(),
                summary=data.get("summary", self._generate_default_summary(data)),
                recommendation=recommendation,
                risk_assessment=risk_assessment,
                confidence_score=data.get("confidence", 0.5),
                metadata={
                    "ai_generated": True,
                    "original_response": data,
                    "processed_at": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"AnalysisResult変換エラー: {e}")
            return None
    
    def _generate_default_summary(self, data: Dict[str, Any]) -> str:
        """デフォルトサマリーを生成"""
        summary_parts = []
        
        if "recommendation" in data:
            summary_parts.append(f"推奨アクション: {data['recommendation']}")
        
        if "confidence" in data:
            summary_parts.append(f"信頼度: {data['confidence']:.1%}")
        
        if "overall_score" in data:
            summary_parts.append(f"総合スコア: {data['overall_score']}/100")
        
        if "risk_level" in data:
            summary_parts.append(f"リスクレベル: {data['risk_level']}")
        
        return "; ".join(summary_parts) if summary_parts else "分析結果が生成されました"
    
    def _determine_parse_status(self, validation_issues: List[ValidationIssue], analysis_result: Optional[AnalysisResult]) -> ParseStatus:
        """パース状態を決定"""
        critical_issues = [issue for issue in validation_issues if issue.severity == ValidationSeverity.CRITICAL]
        error_issues = [issue for issue in validation_issues if issue.severity == ValidationSeverity.ERROR]
        
        if critical_issues:
            return ParseStatus.FAILED
        elif error_issues:
            return ParseStatus.PARTIAL_SUCCESS if analysis_result else ParseStatus.VALIDATION_ERROR
        elif analysis_result:
            return ParseStatus.SUCCESS
        else:
            return ParseStatus.FAILED
    
    def validate_analysis_quality(self, analysis_result: AnalysisResult) -> List[ValidationIssue]:
        """分析品質を検証"""
        issues = []
        
        # 推奨事項の品質チェック
        if analysis_result.recommendation:
            rec = analysis_result.recommendation
            
            if not rec.reasoning or len(rec.reasoning) < 20:
                issues.append(ValidationIssue(
                    field="recommendation.reasoning",
                    severity=ValidationSeverity.WARNING,
                    message="推奨理由が短すぎます（20文字以上推奨）"
                ))
            
            if rec.confidence < 0.3:
                issues.append(ValidationIssue(
                    field="recommendation.confidence",
                    severity=ValidationSeverity.WARNING,
                    message="信頼度が低すぎます"
                ))
        
        # リスク評価の品質チェック
        if analysis_result.risk_assessment:
            risk = analysis_result.risk_assessment
            
            if not risk.factors or len(risk.factors) == 0:
                issues.append(ValidationIssue(
                    field="risk_assessment.factors",
                    severity=ValidationSeverity.WARNING,
                    message="リスク要因が特定されていません"
                ))
        
        # サマリーの品質チェック
        if not analysis_result.summary or len(analysis_result.summary) < 10:
            issues.append(ValidationIssue(
                field="summary",
                severity=ValidationSeverity.WARNING,
                message="サマリーが短すぎます"
            ))
        
        return issues
    
    def normalize_analysis_result(self, analysis_result: AnalysisResult) -> AnalysisResult:
        """分析結果を正規化"""
        # 推奨事項の正規化
        if analysis_result.recommendation:
            rec = analysis_result.recommendation
            
            # 信頼度の正規化
            if rec.confidence > 1.0:
                rec.confidence = rec.confidence / 100.0
            
            # 価格の正規化（負の値を除去）
            if rec.target_price and rec.target_price < 0:
                rec.target_price = None
            
            if rec.stop_loss and rec.stop_loss < 0:
                rec.stop_loss = None
        
        # リスク評価の正規化
        if analysis_result.risk_assessment:
            risk = analysis_result.risk_assessment
            
            # スコアの正規化
            if risk.score > 100:
                risk.score = 100
            elif risk.score < 0:
                risk.score = 0
        
        # 信頼度スコアの正規化
        if analysis_result.confidence_score > 1.0:
            analysis_result.confidence_score = analysis_result.confidence_score / 100.0
        
        return analysis_result