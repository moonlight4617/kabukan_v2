"""
分析結果モデルのテスト
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
    MarketContext,
    AnalysisRequest,
    AnalysisResult
)


class TestEnums:
    """Enumクラスのテスト"""
    
    def test_analysis_type(self):
        """AnalysisTypeのテスト"""
        assert AnalysisType.DAILY.display_name == "日次分析"
        assert AnalysisType.WEEKLY.display_name == "週次分析"
        assert AnalysisType.MONTHLY.display_name == "月次分析"
        assert str(AnalysisType.DAILY) == "daily"
    
    def test_recommendation_type(self):
        """RecommendationTypeのテスト"""
        assert RecommendationType.BUY.display_name == "購入"
        assert RecommendationType.SELL.display_name == "売却"
        assert RecommendationType.HOLD.display_name == "保持"
        assert RecommendationType.STRONG_BUY.display_name == "強い購入"
        assert RecommendationType.STRONG_SELL.display_name == "強い売却"
        
        # 優先度テスト
        assert RecommendationType.STRONG_SELL.priority == 5
        assert RecommendationType.STRONG_BUY.priority == 4
        assert RecommendationType.SELL.priority == 3
        assert RecommendationType.BUY.priority == 2
        assert RecommendationType.HOLD.priority == 1
    
    def test_risk_level(self):
        """RiskLevelのテスト"""
        assert RiskLevel.LOW.display_name == "低リスク"
        assert RiskLevel.MEDIUM.display_name == "中リスク"
        assert RiskLevel.HIGH.display_name == "高リスク"
        assert RiskLevel.VERY_HIGH.display_name == "非常に高リスク"
        
        # スコアテスト
        assert RiskLevel.LOW.score == 1
        assert RiskLevel.MEDIUM.score == 2
        assert RiskLevel.HIGH.score == 3
        assert RiskLevel.VERY_HIGH.score == 4
    
    def test_technical_signal(self):
        """TechnicalSignalのテスト"""
        assert TechnicalSignal.BULLISH.display_name == "強気"
        assert TechnicalSignal.BEARISH.display_name == "弱気"
        assert TechnicalSignal.NEUTRAL.display_name == "中立"


class TestTechnicalIndicators:
    """TechnicalIndicatorsクラスのテスト"""
    
    def test_basic_indicators(self):
        """基本的なテクニカル指標"""
        indicators = TechnicalIndicators(
            golden_cross=True,
            rsi=25.0,
            macd_line=1.5,
            macd_signal=1.2,
            volume_change_rate=30.0
        )
        
        # 自動計算された値をチェック
        assert indicators.rsi_signal == TechnicalSignal.BULLISH  # RSI < 30
        assert indicators.macd_trend == TechnicalSignal.BULLISH  # MACD > Signal
        assert indicators.volume_trend == TechnicalSignal.BULLISH  # Volume > 20%
    
    def test_rsi_signals(self):
        """RSIシグナルの自動判定"""
        # 買われすぎ
        indicators_overbought = TechnicalIndicators(rsi=75.0)
        assert indicators_overbought.rsi_signal == TechnicalSignal.BEARISH
        
        # 売られすぎ
        indicators_oversold = TechnicalIndicators(rsi=25.0)
        assert indicators_oversold.rsi_signal == TechnicalSignal.BULLISH
        
        # 中立
        indicators_neutral = TechnicalIndicators(rsi=50.0)
        assert indicators_neutral.rsi_signal == TechnicalSignal.NEUTRAL
    
    def test_overall_signal(self):
        """総合シグナルの計算"""
        # 強気シグナル
        bullish_indicators = TechnicalIndicators(
            golden_cross=True,  # +2
            new_high_break=True,  # +1
            rsi=25.0,  # +1 (売られすぎ)
            macd_line=1.5,
            macd_signal=1.2,  # +1 (MACD > Signal)
            volume_change_rate=25.0  # +1
        )
        assert bullish_indicators.overall_signal == TechnicalSignal.BULLISH
        
        # 弱気シグナル
        bearish_indicators = TechnicalIndicators(
            dead_cross=True,  # +2
            new_low_break=True,  # +1
            rsi=75.0,  # +1 (買われすぎ)
            macd_line=1.2,
            macd_signal=1.5,  # +1 (MACD < Signal)
            volume_change_rate=-25.0  # +1
        )
        assert bearish_indicators.overall_signal == TechnicalSignal.BEARISH
        
        # 中立シグナル
        neutral_indicators = TechnicalIndicators(
            rsi=50.0,
            volume_change_rate=5.0
        )
        assert neutral_indicators.overall_signal == TechnicalSignal.NEUTRAL
    
    def test_signal_summary(self):
        """シグナルサマリーの取得"""
        indicators = TechnicalIndicators(
            golden_cross=True,
            rsi=25.0,
            short_ma=2500.0,
            long_ma=2400.0
        )
        
        summary = indicators.get_signal_summary()
        assert summary["overall_signal"] == "強気"
        assert summary["moving_average"]["golden_cross"] is True
        assert summary["moving_average"]["short_ma"] == 2500.0
        assert summary["oscillators"]["rsi"] == 25.0
        assert summary["oscillators"]["rsi_signal"] == "強気"


class TestRecommendation:
    """Recommendationクラスのテスト"""
    
    def test_valid_recommendation(self):
        """有効な推奨"""
        rec = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.8,
            reasoning="テクニカル指標が強気を示している",
            target_price=2800.0,
            time_horizon="短期"
        )
        
        assert rec.confidence_level == "高"
        assert not rec.is_high_priority  # STRONG_BUYではないため
        assert "7203: 購入" in rec.get_formatted_summary()
        assert "目標価格: ¥2,800" in rec.get_formatted_summary()
    
    def test_high_priority_recommendation(self):
        """高優先度推奨"""
        rec = Recommendation(
            type=RecommendationType.STRONG_BUY,
            symbol="AAPL",
            confidence=0.9,
            reasoning="業績好調により強い購入推奨",
            target_price=200.0
        )
        
        assert rec.is_high_priority
        assert rec.confidence_level == "高"
    
    def test_invalid_recommendations(self):
        """無効な推奨のテスト"""
        # 空の銘柄コード
        with pytest.raises(ValueError, match="銘柄コードが空です"):
            Recommendation(
                type=RecommendationType.BUY,
                symbol="",
                confidence=0.8,
                reasoning="テスト"
            )
        
        # 無効な信頼度
        with pytest.raises(ValueError, match="信頼度は0.0-1.0の範囲である必要があります"):
            Recommendation(
                type=RecommendationType.BUY,
                symbol="7203",
                confidence=1.5,
                reasoning="テスト"
            )
        
        # 空の推奨理由
        with pytest.raises(ValueError, match="推奨理由が空です"):
            Recommendation(
                type=RecommendationType.BUY,
                symbol="7203",
                confidence=0.8,
                reasoning=""
            )
    
    def test_confidence_levels(self):
        """信頼度レベルのテスト"""
        high_conf = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.9,
            reasoning="テスト"
        )
        assert high_conf.confidence_level == "高"
        
        medium_conf = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.7,
            reasoning="テスト"
        )
        assert medium_conf.confidence_level == "中"
        
        low_conf = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.5,
            reasoning="テスト"
        )
        assert low_conf.confidence_level == "低"
        
        very_low_conf = Recommendation(
            type=RecommendationType.BUY,
            symbol="7203",
            confidence=0.3,
            reasoning="テスト"
        )
        assert very_low_conf.confidence_level == "非常に低"


class TestRiskAssessment:
    """RiskAssessmentクラスのテスト"""
    
    def test_valid_risk_assessment(self):
        """有効なリスク評価"""
        risk = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.7,
            volatility_analysis="中程度のボラティリティ",
            recommendations=["分散投資を検討", "リスク管理の強化"],
            concentration_risk=0.3
        )
        
        assert risk.diversification_level == "中分散"
        assert risk.risk_score >= 1
        assert risk.risk_score <= 10
    
    def test_diversification_levels(self):
        """分散レベルのテスト"""
        high_div = RiskAssessment(
            overall_risk=RiskLevel.LOW,
            diversification_score=0.9,
            volatility_analysis="テスト"
        )
        assert high_div.diversification_level == "高分散"
        
        medium_div = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.7,
            volatility_analysis="テスト"
        )
        assert medium_div.diversification_level == "中分散"
        
        low_div = RiskAssessment(
            overall_risk=RiskLevel.HIGH,
            diversification_score=0.5,
            volatility_analysis="テスト"
        )
        assert low_div.diversification_level == "低分散"
        
        concentrated = RiskAssessment(
            overall_risk=RiskLevel.VERY_HIGH,
            diversification_score=0.2,
            volatility_analysis="テスト"
        )
        assert concentrated.diversification_level == "集中"
    
    def test_risk_score_calculation(self):
        """リスクスコア計算のテスト"""
        # 低リスク、高分散
        low_risk = RiskAssessment(
            overall_risk=RiskLevel.LOW,
            diversification_score=0.9,
            volatility_analysis="テスト",
            concentration_risk=0.1
        )
        assert low_risk.risk_score <= 5
        
        # 高リスク、低分散
        high_risk = RiskAssessment(
            overall_risk=RiskLevel.VERY_HIGH,
            diversification_score=0.2,
            volatility_analysis="テスト",
            concentration_risk=0.8
        )
        assert high_risk.risk_score >= 7
    
    def test_invalid_risk_assessment(self):
        """無効なリスク評価のテスト"""
        # 無効な分散スコア
        with pytest.raises(ValueError, match="分散スコアは0.0-1.0の範囲である必要があります"):
            RiskAssessment(
                overall_risk=RiskLevel.LOW,
                diversification_score=1.5,
                volatility_analysis="テスト"
            )
        
        # 空のボラティリティ分析
        with pytest.raises(ValueError, match="ボラティリティ分析が空です"):
            RiskAssessment(
                overall_risk=RiskLevel.LOW,
                diversification_score=0.7,
                volatility_analysis=""
            )
    
    def test_risk_summary(self):
        """リスクサマリーの取得"""
        risk = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.6,
            volatility_analysis="中程度のボラティリティ",
            sector_concentration={"Tech": 0.4, "Finance": 0.3},
            correlation_risk=0.7
        )
        
        summary = risk.get_risk_summary()
        assert summary["overall_risk"] == "中リスク"
        assert summary["diversification"]["level"] == "中分散"
        assert summary["concentration"]["sectors"]["Tech"] == 0.4


class TestMarketContext:
    """MarketContextクラスのテスト"""
    
    def test_market_context(self):
        """市場コンテキスト"""
        context = MarketContext(
            market_trend=TechnicalSignal.BULLISH,
            market_volatility=20.0,
            sector_performance={"Tech": 5.2, "Finance": -1.5},
            economic_indicators={"GDP": 2.1, "Inflation": 3.5}
        )
        
        assert not context.is_volatile_market  # 20 < 25
        assert context.market_trend == TechnicalSignal.BULLISH
    
    def test_volatile_market(self):
        """高ボラティリティ市場"""
        volatile_context = MarketContext(
            market_trend=TechnicalSignal.BEARISH,
            market_volatility=30.0
        )
        
        assert volatile_context.is_volatile_market  # 30 > 25


class TestAnalysisRequest:
    """AnalysisRequestクラスのテスト"""
    
    def test_valid_request(self):
        """有効な分析リクエスト"""
        request = AnalysisRequest(
            analysis_type=AnalysisType.DAILY,
            symbols=["7203", "AAPL", "MSFT"]
        )
        
        assert request.analysis_type == AnalysisType.DAILY
        assert len(request.symbols) == 3
    
    def test_invalid_requests(self):
        """無効な分析リクエスト"""
        # 空の銘柄リスト
        with pytest.raises(ValueError, match="分析対象銘柄が指定されていません"):
            AnalysisRequest(
                analysis_type=AnalysisType.DAILY,
                symbols=[]
            )
        
        # 銘柄数超過
        with pytest.raises(ValueError, match="分析対象銘柄は100以下である必要があります"):
            AnalysisRequest(
                analysis_type=AnalysisType.DAILY,
                symbols=[f"STOCK{i}" for i in range(101)]
            )


class TestAnalysisResult:
    """AnalysisResultクラスのテスト"""
    
    def test_valid_analysis_result(self):
        """有効な分析結果"""
        recommendations = [
            Recommendation(
                type=RecommendationType.BUY,
                symbol="7203",
                confidence=0.8,
                reasoning="強気のテクニカルシグナル"
            ),
            Recommendation(
                type=RecommendationType.STRONG_SELL,
                symbol="AAPL",
                confidence=0.9,
                reasoning="業績悪化の懸念"
            ),
            Recommendation(
                type=RecommendationType.HOLD,
                symbol="MSFT",
                confidence=0.6,
                reasoning="現状維持が適切"
            )
        ]
        
        risk_assessment = RiskAssessment(
            overall_risk=RiskLevel.MEDIUM,
            diversification_score=0.7,
            volatility_analysis="中程度のボラティリティ"
        )
        
        result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="本日の分析結果：混在したシグナル",
            recommendations=recommendations,
            risk_assessment=risk_assessment,
            market_outlook="中立的な市場見通し",
            confidence_score=0.75
        )
        
        assert len(result.recommendations) == 3
        assert len(result.high_priority_recommendations) == 1  # STRONG_SELL
        assert len(result.buy_recommendations) == 1
        assert len(result.sell_recommendations) == 1
    
    def test_recommendations_by_symbol(self):
        """銘柄別推奨の取得"""
        recommendations = [
            Recommendation(
                type=RecommendationType.BUY,
                symbol="7203",
                confidence=0.8,
                reasoning="テスト1"
            ),
            Recommendation(
                type=RecommendationType.SELL,
                symbol="7203",
                confidence=0.7,
                reasoning="テスト2"
            ),
            Recommendation(
                type=RecommendationType.HOLD,
                symbol="AAPL",
                confidence=0.6,
                reasoning="テスト3"
            )
        ]
        
        result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="テスト分析",
            recommendations=recommendations
        )
        
        toyota_recs = result.get_recommendations_by_symbol("7203")
        assert len(toyota_recs) == 2
        
        apple_recs = result.get_recommendations_by_symbol("AAPL")
        assert len(apple_recs) == 1
        
        no_recs = result.get_recommendations_by_symbol("GOOGL")
        assert len(no_recs) == 0
    
    def test_invalid_analysis_result(self):
        """無効な分析結果"""
        # 空のサマリー
        with pytest.raises(ValueError, match="分析サマリーが空です"):
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary=""
            )
        
        # 無効な信頼度スコア
        with pytest.raises(ValueError, match="信頼度スコアは0.0-1.0の範囲である必要があります"):
            AnalysisResult(
                analysis_type=AnalysisType.DAILY,
                summary="テスト",
                confidence_score=1.5
            )
    
    def test_analysis_summary(self):
        """分析サマリーの取得"""
        result = AnalysisResult(
            analysis_type=AnalysisType.WEEKLY,
            summary="週次分析結果",
            market_outlook="楽観的",
            confidence_score=0.8,
            execution_time=2.5
        )
        
        summary = result.get_analysis_summary()
        assert summary["analysis_type"] == "週次分析"
        assert summary["summary"] == "週次分析結果"
        assert summary["market_outlook"] == "楽観的"
        assert summary["confidence_score"] == 0.8
        assert summary["execution_time"] == 2.5