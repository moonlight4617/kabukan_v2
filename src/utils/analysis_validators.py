"""
分析結果データの検証ユーティリティ
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from src.models.analysis_models import (
    AnalysisType,
    RecommendationType,
    RiskLevel,
    TechnicalSignal,
    TechnicalIndicators,
    Recommendation,
    RiskAssessment,
    AnalysisResult
)
from src.utils.validators import ValidationError

logger = logging.getLogger(__name__)


class AnalysisValidator:
    """分析結果データの検証クラス"""
    
    @classmethod
    def validate_confidence_score(cls, confidence: float, field_name: str = "信頼度") -> bool:
        """
        信頼度スコアの妥当性をチェック
        
        Args:
            confidence: 信頼度（0.0-1.0）
            field_name: フィールド名（エラーメッセージ用）
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な信頼度の場合
        """
        if confidence is None:
            raise ValidationError(f"{field_name}が設定されていません")
        
        try:
            confidence_float = float(confidence)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name}は数値である必要があります")
        
        if not (0.0 <= confidence_float <= 1.0):
            raise ValidationError(f"{field_name}は0.0-1.0の範囲である必要があります")
        
        return True
    
    @classmethod
    def validate_technical_indicators(cls, indicators: TechnicalIndicators) -> List[str]:
        """
        テクニカル指標の整合性をチェック
        
        Args:
            indicators: テクニカル指標
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        # RSI値の妥当性チェック
        if indicators.rsi is not None:
            if not (0 <= indicators.rsi <= 100):
                errors.append("RSIは0-100の範囲である必要があります")
        
        # 移動平均の整合性チェック
        if indicators.short_ma is not None and indicators.long_ma is not None:
            if indicators.golden_cross and indicators.short_ma <= indicators.long_ma:
                errors.append("ゴールデンクロス時は短期移動平均が長期移動平均を上回る必要があります")
            
            if indicators.dead_cross and indicators.short_ma >= indicators.long_ma:
                errors.append("デッドクロス時は短期移動平均が長期移動平均を下回る必要があります")
        
        # 相関係数の妥当性チェック
        if indicators.market_correlation is not None:
            if not (-1.0 <= indicators.market_correlation <= 1.0):
                errors.append("市場相関係数は-1.0から1.0の範囲である必要があります")
        
        # サポート・レジスタンスの関係チェック
        if (indicators.support_level is not None and 
            indicators.resistance_level is not None):
            if indicators.support_level >= indicators.resistance_level:
                errors.append("サポートレベルはレジスタンスレベルより低い必要があります")
        
        return errors
    
    @classmethod
    def validate_recommendation(cls, recommendation: Recommendation) -> List[str]:
        """
        推奨データの整合性をチェック
        
        Args:
            recommendation: 推奨データ
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        try:
            # 基本的なデータクラス検証は__post_init__で実行済み
            pass
        except ValueError as e:
            errors.append(str(e))
        
        # 目標価格とストップロスの整合性チェック
        if (recommendation.target_price is not None and 
            recommendation.stop_loss is not None):
            
            if recommendation.type in [RecommendationType.BUY, RecommendationType.STRONG_BUY]:
                if recommendation.stop_loss >= recommendation.target_price:
                    errors.append("購入推奨の場合、ストップロスは目標価格より低く設定する必要があります")
            
            elif recommendation.type in [RecommendationType.SELL, RecommendationType.STRONG_SELL]:
                if recommendation.stop_loss <= recommendation.target_price:
                    errors.append("売却推奨の場合、ストップロスは目標価格より高く設定する必要があります")
        
        # 期待リターンの妥当性チェック
        if recommendation.expected_return is not None:
            if recommendation.expected_return < -100:
                errors.append("期待リターンは-100%以上である必要があります")
            if recommendation.expected_return > 1000:
                errors.append("期待リターンは1000%以下が現実的です")
        
        # 推奨タイプと信頼度の整合性チェック
        if recommendation.type in [RecommendationType.STRONG_BUY, RecommendationType.STRONG_SELL]:
            if recommendation.confidence < 0.6:
                errors.append("強い推奨の場合、信頼度は60%以上が適切です")
        
        return errors
    
    @classmethod
    def validate_risk_assessment(cls, risk_assessment: RiskAssessment) -> List[str]:
        """
        リスク評価の整合性をチェック
        
        Args:
            risk_assessment: リスク評価
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        try:
            # 基本的なデータクラス検証は__post_init__で実行済み
            pass
        except ValueError as e:
            errors.append(str(e))
        
        # 業種集中度の妥当性チェック
        if risk_assessment.sector_concentration:
            total_weight = sum(risk_assessment.sector_concentration.values())
            if not (0.9 <= total_weight <= 1.1):  # 多少の誤差を許容
                errors.append(f"業種別集中度の合計が100%と一致しません（{total_weight*100:.1f}%）")
        
        # 国別集中度の妥当性チェック
        if risk_assessment.country_concentration:
            total_weight = sum(risk_assessment.country_concentration.values())
            if not (0.9 <= total_weight <= 1.1):
                errors.append(f"国別集中度の合計が100%と一致しません（{total_weight*100:.1f}%）")
        
        # リスクレベルと分散度の整合性チェック
        if (risk_assessment.overall_risk == RiskLevel.LOW and 
            risk_assessment.diversification_score < 0.6):
            errors.append("低リスクと評価するには分散度が不足しています")
        
        if (risk_assessment.overall_risk == RiskLevel.VERY_HIGH and 
            risk_assessment.diversification_score > 0.4):
            errors.append("高分散なのに非常に高リスクの評価は矛盾しています")
        
        return errors
    
    @classmethod
    def validate_analysis_result(cls, result: AnalysisResult) -> List[str]:
        """
        分析結果全体の整合性をチェック
        
        Args:
            result: 分析結果
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        try:
            # 基本的なデータクラス検証は__post_init__で実行済み
            pass
        except ValueError as e:
            errors.append(str(e))
        
        # 推奨数の妥当性チェック
        if len(result.recommendations) > 50:
            errors.append("推奨数が多すぎます（50以下が推奨）")
        
        # 各推奨の個別検証
        for i, recommendation in enumerate(result.recommendations):
            rec_errors = cls.validate_recommendation(recommendation)
            for error in rec_errors:
                errors.append(f"推奨{i+1}: {error}")
        
        # リスク評価の検証
        if result.risk_assessment:
            risk_errors = cls.validate_risk_assessment(result.risk_assessment)
            errors.extend(risk_errors)
        
        # テクニカル分析の検証
        if result.technical_analysis:
            for symbol, indicators in result.technical_analysis.items():
                tech_errors = cls.validate_technical_indicators(indicators)
                for error in tech_errors:
                    errors.append(f"{symbol}のテクニカル指標: {error}")
        
        # 分析タイプと推奨の整合性チェック
        if result.analysis_type == AnalysisType.DAILY:
            # 日次分析では短期的な推奨が期待される
            long_term_count = sum(1 for rec in result.recommendations 
                                 if rec.time_horizon == "長期")
            if long_term_count > len(result.recommendations) * 0.3:
                errors.append("日次分析で長期推奨の比率が高すぎます")
        
        elif result.analysis_type == AnalysisType.MONTHLY:
            # 月次分析では長期的な推奨が期待される
            short_term_count = sum(1 for rec in result.recommendations 
                                  if rec.time_horizon == "短期")
            if short_term_count > len(result.recommendations) * 0.3:
                errors.append("月次分析で短期推奨の比率が高すぎます")
        
        # 実行時間の妥当性チェック
        if result.execution_time is not None:
            if result.execution_time < 0:
                errors.append("実行時間は0以上である必要があります")
            if result.execution_time > 300:  # 5分
                errors.append("実行時間が長すぎます（5分以下が推奨）")
        
        return errors


class AnalysisCollectionValidator:
    """分析結果コレクションの検証クラス"""
    
    @classmethod
    def validate_analysis_consistency(cls, results: List[AnalysisResult]) -> List[str]:
        """
        複数の分析結果の一貫性をチェック
        
        Args:
            results: 分析結果のリスト
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        if not results:
            return ["分析結果が空です"]
        
        # 同一銘柄の推奨の一貫性チェック
        symbol_recommendations = {}
        for result in results:
            for rec in result.recommendations:
                if rec.symbol not in symbol_recommendations:
                    symbol_recommendations[rec.symbol] = []
                symbol_recommendations[rec.symbol].append(rec)
        
        # 同一銘柄で矛盾する推奨がないかチェック
        for symbol, recs in symbol_recommendations.items():
            if len(recs) > 1:
                buy_count = sum(1 for rec in recs 
                               if rec.type in [RecommendationType.BUY, RecommendationType.STRONG_BUY])
                sell_count = sum(1 for rec in recs 
                                if rec.type in [RecommendationType.SELL, RecommendationType.STRONG_SELL])
                
                if buy_count > 0 and sell_count > 0:
                    errors.append(f"{symbol}: 購入と売却の推奨が混在しています")
        
        # 時系列での一貫性チェック
        sorted_results = sorted(results, key=lambda x: x.timestamp)
        for i in range(1, len(sorted_results)):
            prev_result = sorted_results[i-1]
            curr_result = sorted_results[i]
            
            # 短期間での大幅な評価変更をチェック
            time_diff = curr_result.timestamp - prev_result.timestamp
            if time_diff.total_seconds() < 3600:  # 1時間以内
                if (prev_result.confidence_score and curr_result.confidence_score and
                    abs(prev_result.confidence_score - curr_result.confidence_score) > 0.5):
                    errors.append("短時間で信頼度スコアが大幅に変化しています")
        
        return errors
    
    @classmethod
    def validate_portfolio_analysis_completeness(cls, 
                                                portfolio_symbols: List[str],
                                                analysis_results: List[AnalysisResult]) -> List[str]:
        """
        ポートフォリオ分析の完全性をチェック
        
        Args:
            portfolio_symbols: ポートフォリオの銘柄リスト
            analysis_results: 分析結果のリスト
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        # 分析された銘柄を収集
        analyzed_symbols = set()
        for result in analysis_results:
            for rec in result.recommendations:
                analyzed_symbols.add(rec.symbol)
        
        # 未分析の銘柄をチェック
        missing_symbols = set(portfolio_symbols) - analyzed_symbols
        if missing_symbols:
            errors.append(f"以下の保有銘柄が分析されていません: {', '.join(missing_symbols)}")
        
        # 関係ない銘柄の分析をチェック
        extra_symbols = analyzed_symbols - set(portfolio_symbols)
        if extra_symbols:
            # ウォッチリストの可能性があるので警告レベル
            logger.warning(f"ポートフォリオ外の銘柄が分析されています: {', '.join(extra_symbols)}")
        
        return errors