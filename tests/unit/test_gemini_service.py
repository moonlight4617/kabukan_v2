# -*- coding: utf-8 -*-
"""
Gemini AIサービスのテスト
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.services.gemini_service import (
    GeminiService,
    GeminiConfig,
    GeminiRequest,
    GeminiResponse,
    ModelType,
    AnalysisMode
)
from src.models.data_models import StockData, WatchlistStock
from src.models.analysis_models import AnalysisResult, AnalysisType, RecommendationType, RiskLevel
from src.services.technical_analysis_service import (
    TechnicalAnalysisResult,
    TrendDirection,
    SignalType,
    RSIData,
    MovingAverage
)


class TestModelType:
    """ModelTypeクラスのテスト"""
    
    def test_model_type_values(self):
        """モデルタイプの値確認"""
        assert ModelType.GEMINI_1_5_FLASH.value == "gemini-1.5-flash"
        assert ModelType.GEMINI_1_5_PRO.value == "gemini-1.5-pro"
        assert ModelType.GEMINI_1_0_PRO.value == "gemini-1.0-pro"


class TestAnalysisMode:
    """AnalysisModeクラスのテスト"""
    
    def test_analysis_mode_values(self):
        """分析モードの値確認"""
        assert AnalysisMode.CONSERVATIVE.value == "conservative"
        assert AnalysisMode.BALANCED.value == "balanced"
        assert AnalysisMode.AGGRESSIVE.value == "aggressive"


class TestGeminiConfig:
    """GeminiConfigクラスのテスト"""
    
    def test_default_config(self):
        """デフォルト設定"""
        config = GeminiConfig(api_key="test_key")
        
        assert config.api_key == "test_key"
        assert config.model_type == ModelType.GEMINI_1_5_FLASH
        assert config.temperature == 0.1
        assert config.top_p == 0.8
        assert config.top_k == 40
        assert config.max_output_tokens == 8192
        assert config.timeout_seconds == 60
        assert config.enable_safety_settings is True
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
    
    def test_custom_config(self):
        """カスタム設定"""
        config = GeminiConfig(
            api_key="custom_key",
            model_type=ModelType.GEMINI_1_5_PRO,
            temperature=0.3,
            top_p=0.9,
            max_output_tokens=4096,
            timeout_seconds=30,
            enable_safety_settings=False,
            max_retries=5,
            retry_delay=2.0
        )
        
        assert config.api_key == "custom_key"
        assert config.model_type == ModelType.GEMINI_1_5_PRO
        assert config.temperature == 0.3
        assert config.top_p == 0.9
        assert config.max_output_tokens == 4096
        assert config.timeout_seconds == 30
        assert config.enable_safety_settings is False
        assert config.max_retries == 5
        assert config.retry_delay == 2.0


class TestGeminiRequest:
    """GeminiRequestクラスのテスト"""
    
    def test_request_creation(self):
        """リクエスト作成"""
        request = GeminiRequest(
            prompt="Test prompt",
            analysis_type=AnalysisType.DAILY,
            symbol="AAPL",
            context_data={"test": "data"},
            model_override=ModelType.GEMINI_1_5_PRO,
            temperature_override=0.5
        )
        
        assert request.prompt == "Test prompt"
        assert request.analysis_type == AnalysisType.DAILY
        assert request.symbol == "AAPL"
        assert request.context_data == {"test": "data"}
        assert request.model_override == ModelType.GEMINI_1_5_PRO
        assert request.temperature_override == 0.5
    
    def test_default_values(self):
        """デフォルト値"""
        request = GeminiRequest(
            prompt="Test prompt",
            analysis_type=AnalysisType.WEEKLY
        )
        
        assert request.symbol is None
        assert request.context_data == {}
        assert request.model_override is None
        assert request.temperature_override is None


class TestGeminiResponse:
    """GeminiResponseクラスのテスト"""
    
    def test_successful_response(self):
        """成功レスポンス"""
        analysis_result = AnalysisResult(
            analysis_type=AnalysisType.DAILY,
            summary="Test reasoning",
            recommendations=[],
            timestamp=datetime.now()
        )
        
        response = GeminiResponse(
            success=True,
            content="Test content",
            analysis_result=analysis_result,
            response_time=1.5,
            token_usage={"prompt_tokens": 100, "completion_tokens": 200},
            model_used="gemini-1.5-flash",
            request_id="req_123"
        )
        
        assert response.success is True
        assert response.content == "Test content"
        assert response.analysis_result == analysis_result
        assert response.response_time == 1.5
        assert response.token_usage["prompt_tokens"] == 100
        assert response.model_used == "gemini-1.5-flash"
        assert response.request_id == "req_123"
    
    def test_failed_response(self):
        """失敗レスポンス"""
        response = GeminiResponse(
            success=False,
            error_message="API error occurred",
            response_time=0.5
        )
        
        assert response.success is False
        assert response.error_message == "API error occurred"
        assert response.content is None
        assert response.analysis_result is None
        assert response.response_time == 0.5


class TestGeminiService:
    """GeminiServiceクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = GeminiConfig(
            api_key="test_api_key",
            model_type=ModelType.GEMINI_1_5_FLASH,
            temperature=0.1,
            max_retries=2,
            retry_delay=0.1
        )
        
        # モックデータの準備
        self.stock_data = StockData(
            symbol="AAPL",
            current_price=150.0,
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        self.technical_analysis = TechnicalAnalysisResult(
            symbol="AAPL",
            analysis_date=datetime.now(),
            current_price=150.0,
            trend_direction=TrendDirection.BULLISH,
            overall_signal=SignalType.BUY,
            signal_strength=0.8,
            volatility=15.5,
            rsi=RSIData(values=[65.0]),
            sma_5=MovingAverage(period=5, values=[149.0]),
            sma_25=MovingAverage(period=25, values=[145.0]),
            crossover_signals=[],
            breakout_signals=[],
            support_resistance=[],
            is_new_high=False,
            is_new_low=False
        )
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_service_initialization(self, mock_model_class, mock_configure):
        """サービス初期化"""
        mock_model = Mock()
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        # Gemini APIの設定が呼び出されたか確認
        mock_configure.assert_called_once_with(api_key="test_api_key")
        
        # モデルが初期化されたか確認
        mock_model_class.assert_called_once()
        
        assert service.config == self.config
        assert service._model == mock_model
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_model_initialization_with_safety_settings(self, mock_model_class, mock_configure):
        """セーフティ設定付きモデル初期化"""
        mock_model = Mock()
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        # セーフティ設定が含まれているか確認
        call_args = mock_model_class.call_args
        assert 'safety_settings' in call_args.kwargs
        assert call_args.kwargs['safety_settings'] is not None
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_model_initialization_without_safety_settings(self, mock_model_class, mock_configure):
        """セーフティ設定なしモデル初期化"""
        config = GeminiConfig(api_key="test_key", enable_safety_settings=False)
        mock_model = Mock()
        mock_model_class.return_value = mock_model
        
        service = GeminiService(config)
        
        # セーフティ設定がNoneであることを確認
        call_args = mock_model_class.call_args
        assert call_args.kwargs['safety_settings'] is None
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_analyze_stock_success(self, mock_model_class, mock_configure):
        """株式分析成功"""
        # モックレスポンスの設定
        mock_response = Mock()
        mock_response.text = json.dumps({
            "recommendation": "BUY",
            "confidence": 0.8,
            "target_price": 160.0,
            "stop_loss": 140.0,
            "reasoning": "Strong technical indicators",
            "risk_level": "MEDIUM"
        })
        mock_response.usage_metadata = Mock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 50
        mock_response.usage_metadata.total_token_count = 150
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        # 株式分析を実行
        response = service.analyze_stock(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.BALANCED
        )
        
        assert response.success is True
        assert response.analysis_result is not None
        assert response.analysis_result.recommendations[0].type == RecommendationType.BUY
        assert response.analysis_result.recommendations[0].confidence == 0.8
        assert response.analysis_result.recommendations[0].target_price == 160.0
        assert response.token_usage["prompt_tokens"] == 100
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_analyze_stock_api_error(self, mock_model_class, mock_configure):
        """株式分析API エラー"""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("API Error")
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        response = service.analyze_stock(
            self.stock_data,
            self.technical_analysis
        )
        
        assert response.success is False
        assert "API Error" in response.error_message
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_analyze_portfolio_success(self, mock_model_class, mock_configure):
        """ポートフォリオ分析成功"""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "overall_score": 75,
            "risk_level": "MEDIUM",
            "diversification_score": 80,
            "performance_outlook": "POSITIVE"
        })
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        holdings = [self.stock_data]
        technical_analyses = [self.technical_analysis]
        
        response = service.analyze_portfolio(
            holdings,
            technical_analyses,
            AnalysisType.WEEKLY,
            AnalysisMode.BALANCED
        )
        
        assert response.success is True
        assert response.analysis_result is not None
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_analyze_watchlist_success(self, mock_model_class, mock_configure):
        """ウォッチリスト分析成功"""
        mock_response = Mock()
        mock_response.text = json.dumps({
            "top_picks": [{"symbol": "AAPL", "priority": 8, "reason": "Strong momentum"}],
            "market_timing": "NOW",
            "investment_strategy": "Buy on dips"
        })
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        watchlist = [WatchlistStock(
            symbol="AAPL",
            name="Apple Inc."
        )]
        technical_analyses = [self.technical_analysis]
        
        response = service.analyze_watchlist(
            watchlist,
            technical_analyses,
            AnalysisMode.AGGRESSIVE
        )
        
        assert response.success is True
        assert response.analysis_result is not None
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_model_override(self, mock_model_class, mock_configure):
        """モデルオーバーライド"""
        mock_response = Mock()
        mock_response.text = '{"recommendation": "HOLD", "confidence": 0.5}'
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        # 直接_execute_requestをテスト
        request = GeminiRequest(
            prompt="Test prompt",
            analysis_type=AnalysisType.DAILY,
            model_override=ModelType.GEMINI_1_5_PRO,
            temperature_override=0.5
        )
        
        response = service._execute_request(request)
        
        # モデルが2回作成されることを確認（初期化 + オーバーライド）
        assert mock_model_class.call_count >= 2
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_empty_response_handling(self, mock_model_class, mock_configure):
        """空レスポンス処理"""
        mock_response = Mock()
        mock_response.text = None
        
        mock_model = Mock()
        mock_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        request = GeminiRequest(
            prompt="Test prompt",
            analysis_type=AnalysisType.DAILY
        )
        
        response = service._execute_request(request)
        
        assert response.success is False
        assert "空のレスポンス" in response.error_message
    
    def test_prompt_generation_stock_analysis(self):
        """株式分析プロンプト生成"""
        service = GeminiService(self.config)
        
        prompt = service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.BALANCED
        )
        
        assert "AAPL" in prompt
        assert "150.00" in prompt
        assert "bullish" in prompt
        assert "65.0" in prompt  # RSI値
        assert "日次分析" in prompt
        assert "balanced" in prompt
    
    def test_prompt_generation_portfolio_analysis(self):
        """ポートフォリオ分析プロンプト生成"""
        service = GeminiService(self.config)
        
        holdings = [self.stock_data]
        technical_analyses = [self.technical_analysis]
        
        prompt = service._generate_portfolio_analysis_prompt(
            holdings,
            technical_analyses,
            AnalysisType.WEEKLY,
            AnalysisMode.CONSERVATIVE
        )
        
        assert "ポートフォリオ分析" in prompt
        assert "保有銘柄数: 1" in prompt
        assert "AAPL" in prompt
        assert "conservative" in prompt
    
    def test_prompt_generation_watchlist_analysis(self):
        """ウォッチリスト分析プロンプト生成"""
        service = GeminiService(self.config)
        
        watchlist = [WatchlistStock(
            symbol="AAPL",
            name="Apple Inc."
        )]
        technical_analyses = [self.technical_analysis]
        
        prompt = service._generate_watchlist_analysis_prompt(
            watchlist,
            technical_analyses,
            AnalysisMode.AGGRESSIVE
        )
        
        assert "ウォッチリスト分析" in prompt
        assert "1銘柄" in prompt
        assert "AAPL" in prompt
        assert "aggressive" in prompt
    
    def test_parse_analysis_response_valid_json(self):
        """分析結果パース（有効なJSON）"""
        service = GeminiService(self.config)
        
        response_text = """
        Here is the analysis:
        {
            "recommendation": "BUY",
            "confidence": 0.75,
            "target_price": 160.0,
            "stop_loss": 140.0,
            "reasoning": "Strong technical signals",
            "risk_level": "MEDIUM"
        }
        Additional notes...
        """
        
        result = service._parse_analysis_response(
            response_text,
            AnalysisType.DAILY,
            "AAPL"
        )
        
        assert result is not None
        assert result.recommendations[0].symbol == "AAPL"
        assert result.recommendations[0].type == RecommendationType.BUY
        assert result.recommendations[0].confidence == 0.75
        assert result.recommendations[0].target_price == 160.0
        assert result.confidence_score == 0.75
    
    def test_parse_analysis_response_invalid_json(self):
        """分析結果パース（無効なJSON）"""
        service = GeminiService(self.config)
        
        response_text = "This is not a valid JSON response"
        
        result = service._parse_analysis_response(
            response_text,
            AnalysisType.DAILY,
            "AAPL"
        )
        
        assert result is not None
        assert result.confidence_score == 0.5  # JSONが見つからない場合は0.5
        assert response_text in result.summary
    
    def test_parse_analysis_response_no_json(self):
        """分析結果パース（JSONなし）"""
        service = GeminiService(self.config)
        
        response_text = "Plain text analysis without JSON"
        
        result = service._parse_analysis_response(
            response_text,
            AnalysisType.DAILY,
            "AAPL"
        )
        
        assert result is not None
        assert result.confidence_score == 0.5
        assert result.summary == response_text
    
    def test_serialize_stock_data(self):
        """株式データシリアライズ"""
        service = GeminiService(self.config)
        
        serialized = service._serialize_stock_data(self.stock_data)
        
        assert serialized["symbol"] == "AAPL"
        assert serialized["current_price"] == 150.0
        assert serialized["previous_close"] == 148.0
        assert serialized["change"] == 2.0
        assert serialized["change_percent"] == 1.35
        assert serialized["volume"] == 1000000
        assert "timestamp" in serialized
    
    def test_serialize_technical_analysis(self):
        """テクニカル分析シリアライズ"""
        service = GeminiService(self.config)
        
        serialized = service._serialize_technical_analysis(self.technical_analysis)
        
        assert serialized["trend_direction"] == "bullish"
        assert serialized["overall_signal"] == "buy"
        assert serialized["signal_strength"] == 0.8
        assert serialized["rsi_value"] == 65.0
        assert serialized["rsi_overbought"] is False
        assert serialized["rsi_oversold"] is False
        assert serialized["volatility"] == 15.5
        assert serialized["is_new_high"] is False
        assert serialized["is_new_low"] is False
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_get_service_status_available(self, mock_model_class, mock_configure):
        """サービス状態取得（利用可能）"""
        mock_response = Mock()
        mock_response.text = "OK"
        
        mock_test_model = Mock()
        mock_test_model.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_test_model
        
        service = GeminiService(self.config)
        
        status = service.get_service_status()
        
        assert status["service_name"] == "GeminiService"
        assert status["available"] is True
        assert status["model_type"] == "gemini-1.5-flash"
        assert status["api_configured"] is True
        assert "retry_manager_status" in status
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_get_service_status_unavailable(self, mock_model_class, mock_configure):
        """サービス状態取得（利用不可）"""
        mock_test_model = Mock()
        mock_test_model.generate_content.side_effect = Exception("Service unavailable")
        mock_model_class.return_value = mock_test_model
        
        service = GeminiService(self.config)
        
        status = service.get_service_status()
        
        assert status["service_name"] == "GeminiService"
        assert status["available"] is False
        assert status["api_configured"] is True


class TestGeminiServiceRetryIntegration:
    """GeminiServiceとRetryManagerの統合テスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = GeminiConfig(
            api_key="test_key",
            max_retries=2,
            retry_delay=0.01  # テスト用に短く設定
        )
        
        self.stock_data = StockData(
            symbol="AAPL",
            current_price=150.0,
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        self.technical_analysis = TechnicalAnalysisResult(
            symbol="AAPL",
            analysis_date=datetime.now(),
            current_price=150.0,
            trend_direction=TrendDirection.BULLISH,
            overall_signal=SignalType.BUY,
            signal_strength=0.8,
            volatility=15.5,
            crossover_signals=[],
            breakout_signals=[],
            support_resistance=[],
            is_new_high=False,
            is_new_low=False
        )
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_retry_on_temporary_failure(self, mock_model_class, mock_configure):
        """一時的な失敗でのリトライ"""
        call_count = 0
        
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary network error")
            
            mock_response = Mock()
            mock_response.text = '{"recommendation": "BUY", "confidence": 0.8}'
            return mock_response
        
        mock_model = Mock()
        mock_model.generate_content.side_effect = side_effect
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        response = service.analyze_stock(self.stock_data, self.technical_analysis)
        
        assert response.success is True
        assert call_count == 2  # 1回失敗、2回目で成功
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_max_retries_exceeded(self, mock_model_class, mock_configure):
        """最大リトライ回数超過"""
        mock_model = Mock()
        mock_model.generate_content.side_effect = Exception("Persistent error")
        mock_model_class.return_value = mock_model
        
        service = GeminiService(self.config)
        
        response = service.analyze_stock(self.stock_data, self.technical_analysis)
        
        assert response.success is False
        assert "Persistent error" in response.error_message


class TestGeminiServicePromptCustomization:
    """プロンプトカスタマイズのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = GeminiConfig(api_key="test_key")
        self.service = GeminiService(self.config)
        
        # 完全なテクニカル分析データ
        self.technical_analysis = TechnicalAnalysisResult(
            symbol="AAPL",
            analysis_date=datetime.now(),
            current_price=150.0,
            trend_direction=TrendDirection.BULLISH,
            overall_signal=SignalType.BUY,
            signal_strength=0.85,
            volatility=12.5,
            rsi=RSIData(values=[72.0]),
            sma_5=MovingAverage(period=5, values=[149.5]),
            sma_25=MovingAverage(period=25, values=[145.0]),
            crossover_signals=[],
            breakout_signals=[],
            support_resistance=[],
            is_new_high=True,
            new_high_period=20,
            is_new_low=False
        )
        
        self.stock_data = StockData(
            symbol="AAPL",
            current_price=150.0,
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            volume=1000000,
            timestamp=datetime.now()
        )
    
    def test_prompt_includes_technical_details(self):
        """プロンプトにテクニカル詳細が含まれることの確認"""
        prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.BALANCED
        )
        
        # テクニカル分析の詳細が含まれているか確認
        assert "RSI(14): 72.0" in prompt
        assert "買われすぎ状態" in prompt
        assert "SMA5: 149.50, SMA25: 145.00" in prompt
        assert "短期移動平均が長期を上回る" in prompt
        assert "20日ぶりの新高値を更新" in prompt
    
    def test_prompt_analysis_mode_differences(self):
        """分析モードによるプロンプトの違い"""
        conservative_prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.CONSERVATIVE
        )
        
        aggressive_prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.AGGRESSIVE
        )
        
        assert "保守的な投資アプローチ" in conservative_prompt
        assert "積極的な投資アプローチ" in aggressive_prompt
        assert "リスクを抑えた" in conservative_prompt
        assert "成長機会を重視" in aggressive_prompt
    
    def test_prompt_analysis_type_differences(self):
        """分析タイプによるプロンプトの違い"""
        daily_prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.DAILY,
            AnalysisMode.BALANCED
        )
        
        weekly_prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.WEEKLY,
            AnalysisMode.BALANCED
        )
        
        monthly_prompt = self.service._generate_stock_analysis_prompt(
            self.stock_data,
            self.technical_analysis,
            AnalysisType.MONTHLY,
            AnalysisMode.BALANCED
        )
        
        assert "日次分析" in daily_prompt
        assert "短期的な売買判断" in daily_prompt
        assert "週次分析" in weekly_prompt
        assert "中期的なポジション調整" in weekly_prompt
        assert "月次分析" in monthly_prompt
        assert "長期的な投資戦略" in monthly_prompt


class TestGeminiServiceErrorHandling:
    """エラーハンドリングのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = GeminiConfig(api_key="test_key")
    
    @patch('google.generativeai.configure')
    @patch('google.generativeai.GenerativeModel')
    def test_initialization_error_handling(self, mock_model_class, mock_configure):
        """初期化エラーハンドリング"""
        mock_model_class.side_effect = Exception("Model initialization failed")
        
        with pytest.raises(Exception, match="Model initialization failed"):
            GeminiService(self.config)
    
    @patch('google.generativeai.configure')
    def test_configuration_error_handling(self, mock_configure):
        """設定エラーハンドリング"""
        mock_configure.side_effect = Exception("API configuration failed")
        
        with pytest.raises(Exception, match="API configuration failed"):
            GeminiService(self.config)