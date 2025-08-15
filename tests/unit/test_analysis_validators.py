"""
分析バリデーション機能のテスト
"""

import pytest
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
from src.utils.analysis_validators import (
    AnalysisValidator,
    AnalysisCollectionValidator,
    ValidationError
)


class TestAnalysisValidator:
    """AnalysisValidatorクラスのテスト"""
    
    def test_valid_confidence_score(self):
        """有効な信頼度スコア"""
        assert AnalysisValidator.validate_confidence_score(0.0)
        assert AnalysisValidator.validate_confidence_score(0.5)
        assert AnalysisValidator.validate_confidence_score(1.0)
        assert AnalysisValidator.validate_confidence_score("0.8")  # 文字列数値
    
    def test_invalid_confidence_scores(self):
        """無効な信頼度スコア"""
        with pytest.raises(ValidationError, match="信頼度が設定されていません"):
            AnalysisValidator.validate_confidence_score(None)
        
        with pytest.raises(ValidationError, match="信頼度は数値である必要があります"):
            AnalysisValidator.validate_confidence_score("abc")
        
        with pytest.raises(ValidationError, match="信頼度は0.0-1.0の範囲である必要があります"):
            AnalysisValidator.validate_confidence_score(-0.1)
        
        with pytest.raises(ValidationError, match="信頼度は0.0-1.0の範囲である必要があります"):
            AnalysisValidator.validate_confidence_score(1.1)
    
    def test_valid_technical_indicators(self):
        """有効なテクニカル指標"""
        indicators = TechnicalIndicators(
            golden_cross=True,
            short_ma=2600.0,
            long_ma=2500.0,
            rsi=30.0,
            market_correlation=0.7,
            support_level=2400.0,
            resistance_level=2700.0
        )
        
        errors = AnalysisValidator.validate_technical_indicators(indicators)
        assert len(errors) == 0
    
    def test_invalid_technical_indicators(self):
        """無効なテクニカル指標"""
        # 無効なRSI
        invalid_rsi = TechnicalIndicators(rsi=150.0)
        errors = AnalysisValidator.validate_technical_indicators(invalid_rsi)
        assert any("RSIは0-100の範囲" in error for error in errors)
        
        # 移動平均の矛盾
        contradictory_ma = TechnicalIndicators(
            golden_cross=True,
            short_ma=2400.0,  # 長期MAより低い
            long_ma=2500.0
        )
        errors = AnalysisValidator.validate_technical_indicators(contradictory_ma)
        assert any("ゴールデンクロス時は" in error for error in errors)
        
        # 無効な相関係数
        invalid_correlation = TechnicalIndicators(market_correlation=1.5)
        errors = AnalysisValidator.validate_technical_indicators(invalid_correlation)
        assert any("市場相関係数は-1.0から1.0" in error for error in errors)
        
        # サポート・レジスタンスの逆転
        invalid_sr = TechnicalIndicators(
            support_level=2700.0,
            resistance_level=2600.0  # サポートより低い
        )
        errors = AnalysisValidator.validate_technical_indicators(invalid_sr)
        assert any("サポートレベルはレジスタンスレベルより低い" in error for error in errors)
    
    def test_valid_recommendation(self):
        """有効な推奨"""
        recommendation = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.8,
            reasoning="強気のテクニカルシグナル",
            target_price=2800.0,
            stop_loss=2400.0,  # 目標価格より低い
            expected_return=15.0
        )
        
        errors = AnalysisValidator.validate_recommendation(recommendation)
        assert len(errors) == 0
    
    def test_invalid_recommendations(self):
        """無効な推奨"""
        # 購入推奨でストップロスが目標価格より高い
        invalid_buy = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.8,
            reasoning="テスト",
            target_price=2600.0,
            stop_loss=2800.0  # 目標価格より高い
        )
        errors = AnalysisValidator.validate_recommendation(invalid_buy)
        assert any("ストップロスは目標価格より低く" in error for error in errors)
        
        # 売却推奨でストップロスが目標価格より低い
        invalid_sell = Recommendation(
            type=RecommendationType.SELL,
            symbol="7203",
            confidence=0.8,
            reasoning="テスト",
            target_price=2400.0,
            stop_loss=2200.0  # 目標価格より低い
        )
        errors = AnalysisValidator.validate_recommendation(invalid_sell)
        assert any("ストップロスは目標価格より高く" in error for error in errors)
        
        # 非現実的な期待リターン
        unrealistic_return = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.8,
            reasoning="テスト",
            expected_return=2000.0  # 2000%
        )
        errors = AnalysisValidator.validate_recommendation(unrealistic_return)
        assert any("期待リターンは1000%以下" in error for error in errors)
        
        # 強い推奨なのに低い信頼度
        low_confidence_strong = Recommendation(
            type=RecommendationType.STRONG_BUY,
            symbol="7203",
            confidence=0.3,  # 低い信頼度
            reasoning="テスト"
        )
        errors = AnalysisValidator.validate_recommendation(low_confidence_strong)
        assert any("強い推奨の場合、信頼度は60%以上" in error for error in errors)
    
    def test_valid_risk_assessment(self):
        """有効なリスク評価"""
        risk_assessment = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.7,
            volatility_analysis="中程度のボラティリティ",
            sector_concentration={"Tech": 0.4, "Finance": 0.6},
            country_concentration={"US": 0.7, "JP": 0.3}
        )
        
        errors = AnalysisValidator.validate_risk_assessment(risk_assessment)
        assert len(errors) == 0
    
    def test_invalid_risk_assessments(self):
        """無効なリスク評価"""
        # 業種集中度の合計が100%でない
        invalid_sector = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.7,
            volatility_analysis="テスト",
            sector_concentration={"Tech": 0.3, "Finance": 0.5}  # 合計80%
        )
        errors = AnalysisValidator.validate_risk_assessment(invalid_sector)
        assert any("業種別集中度の合計が100%" in error for error in errors)
        
        # リスクレベルと分散度の矛盾
        contradictory_risk = RiskAssessment(
            overall_risk=RiskLevel.LOW,
            diversification_score=0.3,  # 低分散なのに低リスク
            volatility_analysis="テスト"
        )
        errors = AnalysisValidator.validate_risk_assessment(contradictory_risk)
        assert any("低リスクと評価するには分散度が不足" in error for error in errors)
    
    def test_valid_analysis_result(self):
        """有効な分析結果"""
        recommendations = [
            Recommendation(
                type=RecommendationType.BUY,
                symbol="7203",
                confidence=0.8,
                reasoning="強気シグナル",
                time_horizon="短期"
            )
        ]
        
        result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="日次分析結果",
            recommendations=recommendations,
            execution_time=2.5
        )
        
        errors = AnalysisValidator.validate_analysis_result(result)
        assert len(errors) == 0
    
    def test_invalid_analysis_results(self):
        """無効な分析結果"""
        # 推奨数が多すぎる
        too_many_recs = [
            Recommendation(
                type=RecommendationType.HOLD,
                symbol=f"STOCK{i}",
                confidence=0.5,
                reasoning="テスト"
            )
            for i in range(60)  # 60個の推奨
        ]
        
        result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="テスト",
            recommendations=too_many_recs
        )
        
        errors = AnalysisValidator.validate_analysis_result(result)
        assert any("推奨数が多すぎます" in error for error in errors)
        
        # 日次分析で長期推奨が多い
        long_term_recs = [
            Recommendation(
                type=RecommendationType.BUY,
                symbol=f"STOCK{i}",
                confidence=0.7,
                reasoning="テスト",
                time_horizon="長期"
            )
            for i in range(5)  # 5個の長期推奨
        ]
        
        daily_result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="テスト",
            recommendations=long_term_recs
        )
        
        errors = AnalysisValidator.validate_analysis_result(daily_result)
        assert any("日次分析で長期推奨の比率が高すぎます" in error for error in errors)


class TestAnalysisCollectionValidator:
    """AnalysisCollectionValidatorクラスのテスト"""
    
    def test_consistent_analysis_results(self):
        """一貫性のある分析結果"""
        results = [
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果1",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.BUY,
                        symbol="7203",
                        confidence=0.8,
                        reasoning="強気"
                    )
                ],
                confidence_score=0.8
            ),
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果2",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.BUY,
                        symbol="AAPL",
                        confidence=0.7,
                        reasoning="好調"
                    )
                ],
                confidence_score=0.85
            )
        ]
        
        errors = AnalysisCollectionValidator.validate_analysis_consistency(results)
        assert len(errors) == 0
    
    def test_inconsistent_analysis_results(self):
        """非一貫性のある分析結果"""
        # 同一銘柄で矛盾する推奨
        contradictory_results = [
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果1",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.BUY,
                        symbol="7203",
                        confidence=0.8,
                        reasoning="強気"
                    )
                ]
            ),
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果2",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.SELL,
                        symbol="7203",  # 同一銘柄で売却推奨
                        confidence=0.7,
                        reasoning="弱気"
                    )
                ]
            )
        ]
        
        errors = AnalysisCollectionValidator.validate_analysis_consistency(contradictory_results)
        assert any("購入と売却の推奨が混在" in error for error in errors)
        
        # 短時間での信頼度大幅変化
        base_time = datetime.now()
        rapid_change_results = [
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果1",
                recommendations=[],
                confidence_score=0.9,
                timestamp=base_time
            ),
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="結果2",
                recommendations=[],
                confidence_score=0.3,  # 0.6ポイント減少
                timestamp=base_time + timedelta(minutes=30)  # 30分後
            )
        ]
        
        errors = AnalysisCollectionValidator.validate_analysis_consistency(rapid_change_results)
        assert any("短時間で信頼度スコアが大幅に変化" in error for error in errors)
    
    def test_portfolio_analysis_completeness(self):
        """ポートフォリオ分析の完全性"""
        portfolio_symbols = ["7203", "AAPL", "MSFT"]
        
        # 完全な分析
        complete_results = [
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="完全分析",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.BUY,
                        symbol="7203",
                        confidence=0.8,
                        reasoning="テスト"
                    ),
                    Recommendation(
                        type=RecommendationType.HOLD,
                        symbol="AAPL",
                        confidence=0.6,
                        reasoning="テスト"
                    ),
                    Recommendation(
                        type=RecommendationType.SELL,
                        symbol="MSFT",
                        confidence=0.7,
                        reasoning="テスト"
                    )
                ]
            )
        ]
        
        errors = AnalysisCollectionValidator.validate_portfolio_analysis_completeness(
            portfolio_symbols, complete_results
        )
        assert len(errors) == 0
        
        # 不完全な分析（一部銘柄が欠落）
        incomplete_results = [
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="不完全分析",
                recommendations=[
                    Recommendation(
                        type=RecommendationType.BUY,
                        symbol="7203",
                        confidence=0.8,
                        reasoning="テスト"
                    )
                    # AAPLとMSFTが欠落
                ]
            )
        ]
        
        errors = AnalysisCollectionValidator.validate_portfolio_analysis_completeness(
            portfolio_symbols, incomplete_results
        )
        assert any("以下の保有銘柄が分析されていません" in error for error in errors)
        assert any("AAPL" in error for error in errors)
        assert any("MSFT" in error for error in errors)