# -*- coding: utf-8 -*-
"""
Google Gemini AI分析サービス
株式データとテクニカル分析結果を基にAI分析を実行
"""

import logging
import json
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from src.models.data_models import StockData, StockConfig, WatchlistStock
from src.models.analysis_models import AnalysisResult, AnalysisType, RecommendationType, RiskLevel, Recommendation
from src.services.technical_analysis_service import TechnicalAnalysisResult
from src.services.retry_manager import RetryManager, RetryConfig


logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Geminiモデルタイプ"""
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_0_PRO = "gemini-1.0-pro"


class AnalysisMode(Enum):
    """分析モード"""
    CONSERVATIVE = "conservative"      # 保守的分析
    BALANCED = "balanced"             # バランス分析
    AGGRESSIVE = "aggressive"         # 積極的分析


@dataclass
class GeminiConfig:
    """Gemini AI設定"""
    api_key: str
    model_type: ModelType = ModelType.GEMINI_1_5_FLASH
    temperature: float = 0.1  # 創造性レベル（0-1）
    top_p: float = 0.8
    top_k: int = 40
    max_output_tokens: int = 8192
    timeout_seconds: int = 60
    
    # セーフティ設定
    enable_safety_settings: bool = True
    
    # リトライ設定
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class GeminiRequest:
    """Gemini APIリクエスト"""
    prompt: str
    analysis_type: AnalysisType
    symbol: Optional[str] = None
    context_data: Dict[str, Any] = field(default_factory=dict)
    model_override: Optional[ModelType] = None
    temperature_override: Optional[float] = None


@dataclass
class GeminiResponse:
    """Gemini APIレスポンス"""
    success: bool
    content: Optional[str] = None
    analysis_result: Optional[AnalysisResult] = None
    error_message: Optional[str] = None
    response_time: float = 0.0
    token_usage: Dict[str, int] = field(default_factory=dict)
    model_used: Optional[str] = None
    request_id: Optional[str] = None


class GeminiService:
    """Google Gemini AI分析サービス"""
    
    def __init__(self, config: GeminiConfig):
        """
        Args:
            config: Gemini設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Gemini APIの初期化
        genai.configure(api_key=config.api_key)
        
        # リトライマネージャーの初期化
        retry_config = RetryConfig(
            max_attempts=config.max_retries,
            base_delay=config.retry_delay,
            max_delay=30.0,
            retryable_exceptions=[Exception]  # 一般的な例外をリトライ対象とする
        )
        self.retry_manager = RetryManager(
            retry_config=retry_config,
            enable_circuit_breaker=True,
            enable_rate_limiting=True
        )
        
        # モデルの初期化
        self._model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Geminiモデルを初期化"""
        try:
            generation_config = {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "top_k": self.config.top_k,
                "max_output_tokens": self.config.max_output_tokens,
            }
            
            safety_settings = None
            if self.config.enable_safety_settings:
                safety_settings = {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }
            
            self._model = genai.GenerativeModel(
                model_name=self.config.model_type.value,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            self.logger.info(f"Geminiモデル初期化完了: {self.config.model_type.value}")
            
        except Exception as e:
            self.logger.error(f"Geminiモデル初期化エラー: {e}")
            raise
    
    def analyze_stock(self, 
                     stock_data: StockData, 
                     technical_analysis: TechnicalAnalysisResult,
                     analysis_type: AnalysisType = AnalysisType.DAILY,
                     analysis_mode: AnalysisMode = AnalysisMode.BALANCED,
                     additional_context: Optional[Dict[str, Any]] = None) -> GeminiResponse:
        """
        個別株式のAI分析を実行
        
        Args:
            stock_data: 株式データ
            technical_analysis: テクニカル分析結果
            analysis_type: 分析タイプ
            analysis_mode: 分析モード
            additional_context: 追加コンテキスト
            
        Returns:
            GeminiResponse: 分析結果
        """
        try:
            # プロンプトを生成
            prompt = self._generate_stock_analysis_prompt(
                stock_data, technical_analysis, analysis_type, analysis_mode, additional_context
            )
            
            request = GeminiRequest(
                prompt=prompt,
                analysis_type=analysis_type,
                symbol=stock_data.symbol,
                context_data={
                    "stock_data": self._serialize_stock_data(stock_data),
                    "technical_analysis": self._serialize_technical_analysis(technical_analysis),
                    "analysis_mode": analysis_mode.value
                }
            )
            
            return self._execute_request(request)
            
        except Exception as e:
            self.logger.error(f"株式分析エラー ({stock_data.symbol}): {e}")
            return GeminiResponse(
                success=False,
                error_message=f"株式分析中にエラーが発生: {e}"
            )
    
    def analyze_portfolio(self,
                         holdings: List[StockData],
                         technical_analyses: List[TechnicalAnalysisResult],
                         analysis_type: AnalysisType = AnalysisType.WEEKLY,
                         analysis_mode: AnalysisMode = AnalysisMode.BALANCED) -> GeminiResponse:
        """
        ポートフォリオ全体のAI分析を実行
        
        Args:
            holdings: 保有株式データのリスト
            technical_analyses: テクニカル分析結果のリスト
            analysis_type: 分析タイプ
            analysis_mode: 分析モード
            
        Returns:
            GeminiResponse: 分析結果
        """
        try:
            # プロンプトを生成
            prompt = self._generate_portfolio_analysis_prompt(
                holdings, technical_analyses, analysis_type, analysis_mode
            )
            
            request = GeminiRequest(
                prompt=prompt,
                analysis_type=analysis_type,
                context_data={
                    "portfolio_size": len(holdings),
                    "total_symbols": [stock.symbol for stock in holdings],
                    "analysis_mode": analysis_mode.value
                }
            )
            
            return self._execute_request(request)
            
        except Exception as e:
            self.logger.error(f"ポートフォリオ分析エラー: {e}")
            return GeminiResponse(
                success=False,
                error_message=f"ポートフォリオ分析中にエラーが発生: {e}"
            )
    
    def analyze_watchlist(self,
                         watchlist: List[WatchlistStock],
                         technical_analyses: List[TechnicalAnalysisResult],
                         analysis_mode: AnalysisMode = AnalysisMode.BALANCED) -> GeminiResponse:
        """
        ウォッチリストのAI分析を実行
        
        Args:
            watchlist: ウォッチリスト
            technical_analyses: テクニカル分析結果
            analysis_mode: 分析モード
            
        Returns:
            GeminiResponse: 分析結果
        """
        try:
            # プロンプトを生成
            prompt = self._generate_watchlist_analysis_prompt(
                watchlist, technical_analyses, analysis_mode
            )
            
            request = GeminiRequest(
                prompt=prompt,
                analysis_type=AnalysisType.DAILY,
                context_data={
                    "watchlist_size": len(watchlist),
                    "symbols": [stock.symbol for stock in watchlist],
                    "analysis_mode": analysis_mode.value
                }
            )
            
            return self._execute_request(request)
            
        except Exception as e:
            self.logger.error(f"ウォッチリスト分析エラー: {e}")
            return GeminiResponse(
                success=False,
                error_message=f"ウォッチリスト分析中にエラーが発生: {e}"
            )
    
    def _execute_request(self, request: GeminiRequest) -> GeminiResponse:
        """
        Gemini APIリクエストを実行
        
        Args:
            request: リクエスト
            
        Returns:
            GeminiResponse: レスポンス
        """
        def _make_api_call():
            start_time = time.time()
            
            # モデル設定のオーバーライド
            model = self._model
            if request.model_override or request.temperature_override:
                generation_config = {
                    "temperature": request.temperature_override or self.config.temperature,
                    "top_p": self.config.top_p,
                    "top_k": self.config.top_k,
                    "max_output_tokens": self.config.max_output_tokens,
                }
                
                model_name = request.model_override.value if request.model_override else self.config.model_type.value
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                    safety_settings=self._model.safety_settings if hasattr(self._model, 'safety_settings') else None
                )
            
            # APIリクエストを送信
            response = model.generate_content(
                request.prompt,
                request_options={"timeout": self.config.timeout_seconds}
            )
            
            response_time = time.time() - start_time
            
            # レスポンスの処理
            if response.text:
                # 分析結果を構造化
                analysis_result = self._parse_analysis_response(
                    response.text, request.analysis_type, request.symbol
                )
                
                # トークン使用量の取得（可能な場合）
                token_usage = {}
                if hasattr(response, 'usage_metadata'):
                    token_usage = {
                        "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                        "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                        "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
                    }
                
                return GeminiResponse(
                    success=True,
                    content=response.text,
                    analysis_result=analysis_result,
                    response_time=response_time,
                    token_usage=token_usage,
                    model_used=model.model_name if hasattr(model, 'model_name') else None,
                    request_id=f"req_{int(time.time())}"
                )
            else:
                return GeminiResponse(
                    success=False,
                    error_message="Gemini APIから空のレスポンスが返されました",
                    response_time=response_time
                )
        
        # リトライ機能付きでAPIコールを実行
        try:
            result = self.retry_manager.execute_with_retry(_make_api_call)
            if result.success:
                return result.result
            else:
                return GeminiResponse(
                    success=False,
                    error_message=f"API呼び出し失敗: {result.exception}"
                )
        
        except Exception as e:
            self.logger.error(f"Gemini APIリクエスト実行エラー: {e}")
            return GeminiResponse(
                success=False,
                error_message=f"APIリクエスト実行中にエラーが発生: {e}"
            )
    
    def _generate_stock_analysis_prompt(self,
                                      stock_data: StockData,
                                      technical_analysis: TechnicalAnalysisResult,
                                      analysis_type: AnalysisType,
                                      analysis_mode: AnalysisMode,
                                      additional_context: Optional[Dict[str, Any]] = None) -> str:
        """個別株式分析用プロンプトを生成"""
        
        # 基本情報
        prompt_parts = [
            f"## 株式分析レポート作成 ({analysis_type.value})",
            f"分析モード: {analysis_mode.value}",
            f"",
            f"### 銘柄情報",
            f"- シンボル: {stock_data.symbol}",
            f"- 現在価格: {stock_data.current_price:,.2f}",
            f"- 前日終値: {stock_data.previous_close:,.2f}",
            f"- 変化: {stock_data.change:+.2f} ({stock_data.change_percent:+.2f}%)",
            f"- 出来高: {stock_data.volume:,}",
            f""
        ]
        
        # テクニカル分析結果
        if technical_analysis:
            prompt_parts.extend([
                f"### テクニカル分析結果",
                f"- トレンド方向: {technical_analysis.trend_direction.value}",
                f"- 総合シグナル: {technical_analysis.overall_signal.value}",
                f"- シグナル強度: {technical_analysis.signal_strength:.2f}",
                f"- ボラティリティ: {technical_analysis.volatility:.2f}%",
                f""
            ])
            
            # RSI情報
            if technical_analysis.rsi and technical_analysis.rsi.current_value:
                prompt_parts.append(f"- RSI(14): {technical_analysis.rsi.current_value:.1f}")
                if technical_analysis.rsi.is_overbought:
                    prompt_parts.append(f"  → 買われすぎ状態")
                elif technical_analysis.rsi.is_oversold:
                    prompt_parts.append(f"  → 売られすぎ状態")
            
            # 移動平均情報
            if technical_analysis.sma_5 and technical_analysis.sma_25:
                sma5 = technical_analysis.sma_5.current_value
                sma25 = technical_analysis.sma_25.current_value
                if sma5 and sma25:
                    prompt_parts.append(f"- SMA5: {sma5:.2f}, SMA25: {sma25:.2f}")
                    if sma5 > sma25:
                        prompt_parts.append(f"  → 短期移動平均が長期を上回る（強気傾向）")
                    else:
                        prompt_parts.append(f"  → 短期移動平均が長期を下回る（弱気傾向）")
            
            # シグナル情報
            if technical_analysis.crossover_signals:
                prompt_parts.append(f"- 最近のクロスオーバーシグナル:")
                for signal in technical_analysis.crossover_signals[-3:]:  # 直近3つ
                    prompt_parts.append(f"  - {signal.date}: {signal.description}")
            
            # 新高値・新安値情報
            if technical_analysis.is_new_high:
                prompt_parts.append(f"- {technical_analysis.new_high_period}日ぶりの新高値を更新")
            elif technical_analysis.is_new_low:
                prompt_parts.append(f"- {technical_analysis.new_low_period}日ぶりの新安値を更新")
        
        prompt_parts.append("")
        
        # 分析指示
        analysis_instruction = {
            AnalysisType.DAILY: "日次分析として、短期的な売買判断と推奨アクションを提供してください。",
            AnalysisType.WEEKLY: "週次分析として、中期的なポジション調整と戦略を提案してください。",
            AnalysisType.MONTHLY: "月次分析として、長期的な投資戦略とポートフォリオ調整を検討してください。"
        }.get(analysis_type, "総合的な分析を行ってください。")
        
        mode_instruction = {
            AnalysisMode.CONSERVATIVE: "保守的な投資アプローチで、リスクを抑えた分析を重視してください。",
            AnalysisMode.BALANCED: "バランスの取れた分析で、リスクとリターンを適切に評価してください。",
            AnalysisMode.AGGRESSIVE: "積極的な投資アプローチで、成長機会を重視した分析を行ってください。"
        }.get(analysis_mode, "")
        
        prompt_parts.extend([
            f"### 分析依頼",
            analysis_instruction,
            mode_instruction,
            f"",
            f"以下の形式でJSONレスポンスを提供してください:",
            f"{{",
            f'  "recommendation": "BUY|SELL|HOLD",',
            f'  "confidence": 0.0-1.0,',
            f'  "target_price": 数値,',
            f'  "stop_loss": 数値,',
            f'  "time_horizon": "短期|中期|長期",',
            f'  "risk_level": "LOW|MEDIUM|HIGH",',
            f'  "reasoning": "分析理由の詳細説明",',
            f'  "key_factors": ["要因1", "要因2", "要因3"],',
            f'  "market_outlook": "市場見通し"',
            f"}}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _generate_portfolio_analysis_prompt(self,
                                          holdings: List[StockData],
                                          technical_analyses: List[TechnicalAnalysisResult],
                                          analysis_type: AnalysisType,
                                          analysis_mode: AnalysisMode) -> str:
        """ポートフォリオ分析用プロンプトを生成"""
        
        prompt_parts = [
            f"## ポートフォリオ分析レポート ({analysis_type.value})",
            f"分析モード: {analysis_mode.value}",
            f"",
            f"### ポートフォリオサマリー",
            f"- 保有銘柄数: {len(holdings)}",
            f""
        ]
        
        # 保有銘柄一覧
        prompt_parts.append("### 保有銘柄詳細")
        total_value = 0
        
        for i, (stock, ta) in enumerate(zip(holdings, technical_analyses)):
            market_value = stock.current_price * 100  # デフォルト100株
            total_value += market_value
            
            prompt_parts.extend([
                f"{i+1}. {stock.symbol}",
                f"   - 現在価格: {stock.current_price:,.2f}",
                f"   - 前日比: {stock.change_percent:+.2f}%",
                f"   - シグナル: {ta.overall_signal.value if ta else 'N/A'}",
                f"   - RSI: {ta.rsi.current_value:.1f}" if ta and ta.rsi and ta.rsi.current_value else "",
                f""
            ])
        
        prompt_parts.append(f"推定ポートフォリオ総額: {total_value:,.0f} USD")
        prompt_parts.append("")
        
        # 分析指示
        prompt_parts.extend([
            f"### ポートフォリオ分析依頼",
            f"上記のポートフォリオについて、{analysis_type.value}の視点で総合的な分析を行ってください。",
            f"",
            f"以下の形式でJSONレスポンスを提供してください:",
            f"{{",
            f'  "overall_score": 0-100,',
            f'  "risk_level": "LOW|MEDIUM|HIGH",',
            f'  "diversification_score": 0-100,',
            f'  "performance_outlook": "POSITIVE|NEUTRAL|NEGATIVE",',
            f'  "recommended_actions": [',
            f'    {{"action": "BUY|SELL|HOLD", "symbol": "銘柄", "reason": "理由"}},',
            f'  ],',
            f'  "portfolio_balance": "バランス評価",',
            f'  "risk_assessment": "リスク評価",',
            f'  "improvement_suggestions": ["改善提案1", "改善提案2"]',
            f"}}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _generate_watchlist_analysis_prompt(self,
                                          watchlist: List[WatchlistStock],
                                          technical_analyses: List[TechnicalAnalysisResult],
                                          analysis_mode: AnalysisMode) -> str:
        """ウォッチリスト分析用プロンプトを生成"""
        
        prompt_parts = [
            f"## ウォッチリスト分析レポート",
            f"分析モード: {analysis_mode.value}",
            f"",
            f"### ウォッチリスト ({len(watchlist)}銘柄)",
            f""
        ]
        
        # ウォッチリスト銘柄詳細
        for i, (stock, ta) in enumerate(zip(watchlist, technical_analyses)):
            prompt_parts.extend([
                f"{i+1}. {stock.symbol} ({stock.name})",
                f"   - 現在価格: {ta.current_price:,.2f}" if ta else "",
                f"   - シグナル: {ta.overall_signal.value}" if ta else "",
                f"   - 新高値: はい" if ta and ta.is_new_high else "",
                f"   - 新安値: はい" if ta and ta.is_new_low else "",
                f""
            ])
        
        # 分析指示
        prompt_parts.extend([
            f"### ウォッチリスト分析依頼",
            f"上記のウォッチリストについて、投資機会の優先順位付けを行ってください。",
            f"",
            f"以下の形式でJSONレスポンスを提供してください:",
            f"{{",
            f'  "top_picks": [',
            f'    {{"symbol": "銘柄", "priority": 1-10, "reason": "選定理由", "entry_point": 数値}},',
            f'  ],',
            f'  "avoid_list": ["回避推奨銘柄"],',
            f'  "market_timing": "NOW|WAIT|CAUTION",',
            f'  "sector_outlook": "セクター見通し",',
            f'  "investment_strategy": "推奨戦略"',
            f"}}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _parse_analysis_response(self, 
                               response_text: str, 
                               analysis_type: AnalysisType,
                               symbol: Optional[str] = None) -> Optional[AnalysisResult]:
        """
        Geminiのレスポンスを分析結果オブジェクトに変換
        
        Args:
            response_text: Geminiのレスポンステキスト
            analysis_type: 分析タイプ
            symbol: 銘柄シンボル
            
        Returns:
            AnalysisResult: 構造化された分析結果
        """
        try:
            # JSONブロックを抽出
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                # JSONが見つからない場合は、テキスト全体を説明として使用
                return AnalysisResult(
                    analysis_type=analysis_type,
                    summary=response_text,
                    recommendations=[],
                    timestamp=datetime.now(),
                    confidence_score=0.5,
                    technical_analysis={symbol or "PORTFOLIO": {"raw_response": response_text}}
                )
            
            json_text = response_text[json_start:json_end]
            parsed_data = json.loads(json_text)
            
            # 推奨タイプの変換
            recommendation_map = {
                "BUY": RecommendationType.BUY,
                "SELL": RecommendationType.SELL,
                "HOLD": RecommendationType.HOLD,
                "STRONG_BUY": RecommendationType.STRONG_BUY,
                "STRONG_SELL": RecommendationType.STRONG_SELL
            }
            recommendation = recommendation_map.get(
                parsed_data.get("recommendation", "HOLD"), 
                RecommendationType.HOLD
            )
            
            # リスクレベルの変換
            risk_map = {
                "LOW": RiskLevel.LOW,
                "MEDIUM": RiskLevel.MEDIUM,
                "HIGH": RiskLevel.HIGH
            }
            risk_level = risk_map.get(
                parsed_data.get("risk_level", "MEDIUM"),
                RiskLevel.MEDIUM
            )
            
            # 推奨オブジェクトを作成
            recommendation_obj = Recommendation(
                type=recommendation,
                symbol=symbol or "PORTFOLIO",
                confidence=float(parsed_data.get("confidence", 0.5)),
                reasoning=parsed_data.get("reasoning", ""),
                target_price=parsed_data.get("target_price"),
                stop_loss=parsed_data.get("stop_loss"),
                time_horizon=parsed_data.get("time_horizon")
            )
            
            return AnalysisResult(
                analysis_type=analysis_type,
                summary=parsed_data.get("reasoning", ""),
                recommendations=[recommendation_obj],
                market_outlook=parsed_data.get("market_outlook", ""),
                timestamp=datetime.now(),
                confidence_score=float(parsed_data.get("confidence", 0.5)),
                technical_analysis={symbol or "PORTFOLIO": {"raw_response": response_text}}
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"分析結果のパースに失敗: {e}")
            # パースに失敗した場合はデフォルト結果を返す
            return AnalysisResult(
                analysis_type=analysis_type,
                summary=f"AI分析結果の解析に失敗しました。生レスポンス: {response_text[:500]}...",
                recommendations=[],
                timestamp=datetime.now(),
                confidence_score=0.3,
                technical_analysis={symbol or "UNKNOWN": {"raw_response": response_text, "parse_error": str(e)}}
            )
    
    def _serialize_stock_data(self, stock_data: StockData) -> Dict[str, Any]:
        """株式データをシリアライズ"""
        return {
            "symbol": stock_data.symbol,
            "current_price": stock_data.current_price,
            "previous_close": stock_data.previous_close,
            "change": stock_data.change,
            "change_percent": stock_data.change_percent,
            "volume": stock_data.volume,
            "timestamp": stock_data.timestamp.isoformat()
        }
    
    def _serialize_technical_analysis(self, ta: TechnicalAnalysisResult) -> Dict[str, Any]:
        """テクニカル分析結果をシリアライズ"""
        return {
            "trend_direction": ta.trend_direction.value,
            "overall_signal": ta.overall_signal.value,
            "signal_strength": ta.signal_strength,
            "rsi_value": ta.rsi.current_value if ta.rsi else None,
            "rsi_overbought": ta.rsi.is_overbought if ta.rsi else False,
            "rsi_oversold": ta.rsi.is_oversold if ta.rsi else False,
            "volatility": ta.volatility,
            "is_new_high": ta.is_new_high,
            "is_new_low": ta.is_new_low,
            "crossover_signals_count": len(ta.crossover_signals),
            "breakout_signals_count": len(ta.breakout_signals)
        }
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状態を取得"""
        try:
            # 簡単なテストリクエストでサービス状態を確認
            test_prompt = "Hello, please respond with 'OK'"
            test_model = genai.GenerativeModel(model_name=self.config.model_type.value)
            response = test_model.generate_content(test_prompt)
            
            service_available = bool(response.text)
            
        except Exception as e:
            service_available = False
            self.logger.warning(f"Geminiサービス状態確認エラー: {e}")
        
        return {
            "service_name": "GeminiService",
            "available": service_available,
            "model_type": self.config.model_type.value,
            "api_configured": bool(self.config.api_key),
            "retry_manager_status": self.retry_manager.get_status() if self.retry_manager else None
        }