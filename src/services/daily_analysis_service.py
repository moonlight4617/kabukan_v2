# -*- coding: utf-8 -*-
"""
日次分析サービス
テクニカル指標に基づく日次分析ロジックと売買推奨機能を提供
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from src.models.data_models import StockData, StockConfig, WatchlistStock
from src.models.analysis_models import AnalysisResult, AnalysisType, RecommendationType, RiskLevel, Recommendation
from src.services.stock_data_service import StockDataService, BatchDataResult
from src.services.historical_data_manager import HistoricalDataManager, HistoricalDataset
from src.services.technical_analysis_service import TechnicalAnalysisService, TechnicalAnalysisResult
from src.services.gemini_service import GeminiService, AnalysisMode
from src.services.google_sheets_service import GoogleSheetsService


logger = logging.getLogger(__name__)


class HoldingAction(Enum):
    """保有銘柄に対するアクション"""
    BUY_MORE = "buy_more"          # 追加購入
    SELL_PARTIAL = "sell_partial"  # 部分売却
    SELL_ALL = "sell_all"          # 全売却
    HOLD = "hold"                  # 保持
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            HoldingAction.BUY_MORE: "追加購入",
            HoldingAction.SELL_PARTIAL: "部分売却", 
            HoldingAction.SELL_ALL: "全売却",
            HoldingAction.HOLD: "保持"
        }
        return mapping[self]


class WatchlistAction(Enum):
    """ウォッチリスト銘柄に対するアクション"""
    BUY_NOW = "buy_now"            # 即座に購入
    BUY_ON_DIP = "buy_on_dip"      # 押し目買い
    WAIT = "wait"                  # 待機
    REMOVE = "remove"              # リストから削除
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            WatchlistAction.BUY_NOW: "即座に購入",
            WatchlistAction.BUY_ON_DIP: "押し目買い",
            WatchlistAction.WAIT: "待機",
            WatchlistAction.REMOVE: "リストから削除"
        }
        return mapping[self]


@dataclass
class HoldingRecommendation:
    """保有銘柄推奨"""
    symbol: str
    name: str
    current_price: float
    current_quantity: int
    action: HoldingAction
    confidence: float  # 0.0-1.0
    reasoning: str
    
    # アクション詳細
    recommended_quantity: Optional[int] = None  # 売買推奨数量
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str = "短期"  # 短期、中期、長期
    
    # リスク評価
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_factors: List[str] = field(default_factory=list)
    
    # 財務情報
    current_value: Optional[float] = None  # 現在評価額
    unrealized_pnl: Optional[float] = None  # 含み損益
    unrealized_pnl_pct: Optional[float] = None  # 含み損益率
    
    def __post_init__(self):
        """データ検証と自動計算"""
        if self.current_quantity > 0:
            self.current_value = self.current_price * self.current_quantity
        
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("信頼度は0.0-1.0の範囲である必要があります")


@dataclass
class WatchlistRecommendation:
    """ウォッチリスト推奨"""
    symbol: str
    name: str
    current_price: float
    action: WatchlistAction
    confidence: float  # 0.0-1.0
    reasoning: str
    
    # エントリー戦略
    entry_price: Optional[float] = None  # エントリー推奨価格
    entry_quantity: Optional[int] = None  # 推奨購入数量
    entry_timing: str = "即座"  # 即座、押し目待ち、ブレイク待ち
    
    # 価格目標
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    
    # リスク評価
    risk_level: RiskLevel = RiskLevel.MEDIUM
    priority: int = 5  # 1-10の優先度（10が最高）
    
    def __post_init__(self):
        """データ検証"""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("信頼度は0.0-1.0の範囲である必要があります")
        if not (1 <= self.priority <= 10):
            raise ValueError("優先度は1-10の範囲である必要があります")


@dataclass
class DailyAnalysisResult:
    """日次分析結果"""
    analysis_date: datetime
    market_summary: str
    
    # 保有銘柄分析
    holding_recommendations: List[HoldingRecommendation] = field(default_factory=list)
    holdings_summary: str = ""
    total_portfolio_value: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_unrealized_pnl_pct: float = 0.0
    
    # ウォッチリスト分析
    watchlist_recommendations: List[WatchlistRecommendation] = field(default_factory=list)
    watchlist_summary: str = ""
    
    # 総合評価
    overall_market_sentiment: str = "中立"  # 強気、弱気、中立
    risk_assessment: str = ""
    daily_strategy: str = ""
    
    # 統計情報
    holdings_analyzed: int = 0
    watchlist_analyzed: int = 0
    execution_time: float = 0.0
    
    @property
    def buy_recommendations_count(self) -> int:
        """購入推奨数"""
        return len([rec for rec in self.watchlist_recommendations 
                   if rec.action in [WatchlistAction.BUY_NOW, WatchlistAction.BUY_ON_DIP]])
    
    @property
    def sell_recommendations_count(self) -> int:
        """売却推奨数"""
        return len([rec for rec in self.holding_recommendations 
                   if rec.action in [HoldingAction.SELL_PARTIAL, HoldingAction.SELL_ALL]])
    
    @property
    def high_priority_watchlist(self) -> List[WatchlistRecommendation]:
        """高優先度ウォッチリスト"""
        return [rec for rec in self.watchlist_recommendations if rec.priority >= 8]


class DailyAnalysisService:
    """日次分析サービス"""
    
    def __init__(self,
                 stock_service: StockDataService,
                 historical_manager: HistoricalDataManager,
                 technical_service: TechnicalAnalysisService,
                 gemini_service: GeminiService,
                 sheets_service: GoogleSheetsService):
        """
        Args:
            stock_service: 株式データサービス
            historical_manager: 履歴データマネージャー
            technical_service: テクニカル分析サービス
            gemini_service: Gemini AIサービス
            sheets_service: Google Sheetsサービス
        """
        self.stock_service = stock_service
        self.historical_manager = historical_manager
        self.technical_service = technical_service
        self.gemini_service = gemini_service
        self.sheets_service = sheets_service
        self.logger = logging.getLogger(__name__)
    
    def execute_daily_analysis(self,
                             analysis_mode: AnalysisMode = AnalysisMode.BALANCED,
                             enable_ai_analysis: bool = True) -> DailyAnalysisResult:
        """
        日次分析を実行
        
        Args:
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            DailyAnalysisResult: 日次分析結果
        """
        start_time = datetime.now()
        self.logger.info("日次分析開始")
        
        try:
            # Google Sheetsから保有銘柄とウォッチリストを取得
            holdings_data = self.sheets_service.get_holdings_data()
            watchlist_data = self.sheets_service.get_watchlist_data()
            
            if not holdings_data.success:
                error_msg = ", ".join(holdings_data.errors) if holdings_data.errors else "Unknown error"
                raise Exception(f"Google Sheetsからのデータ取得に失敗: {error_msg}")
            
            if not watchlist_data.success:
                error_msg = ", ".join(watchlist_data.errors) if watchlist_data.errors else "Unknown error"
                raise Exception(f"Google Sheetsからのデータ取得に失敗: {error_msg}")
            
            # 分析結果オブジェクトを初期化
            result = DailyAnalysisResult(
                analysis_date=datetime.now(),
                market_summary="",
                holdings_analyzed=len(holdings_data.data),
                watchlist_analyzed=len(watchlist_data.data)
            )
            
            # 保有銘柄分析
            if holdings_data.data:
                self.logger.info(f"保有銘柄分析開始: {len(holdings_data.data)}銘柄")
                holding_recommendations = self._analyze_holdings(
                    holdings_data.data, analysis_mode, enable_ai_analysis
                )
                result.holding_recommendations = holding_recommendations
                result.holdings_summary = self._generate_holdings_summary(holding_recommendations)
                result.total_portfolio_value = sum(rec.current_value or 0 for rec in holding_recommendations)
                result.total_unrealized_pnl = sum(rec.unrealized_pnl or 0 for rec in holding_recommendations)
                if result.total_portfolio_value > 0:
                    result.total_unrealized_pnl_pct = (result.total_unrealized_pnl / result.total_portfolio_value) * 100
            
            # ウォッチリスト分析
            if watchlist_data.data:
                self.logger.info(f"ウォッチリスト分析開始: {len(watchlist_data.data)}銘柄")
                watchlist_recommendations = self._analyze_watchlist(
                    watchlist_data.data, analysis_mode, enable_ai_analysis
                )
                result.watchlist_recommendations = watchlist_recommendations
                result.watchlist_summary = self._generate_watchlist_summary(watchlist_recommendations)
            
            # 総合市場分析
            result.market_summary = self._generate_market_summary(result, analysis_mode)
            result.overall_market_sentiment = self._assess_market_sentiment(result)
            result.risk_assessment = self._generate_risk_assessment(result)
            result.daily_strategy = self._generate_daily_strategy(result, analysis_mode)
            
            # 実行時間を記録
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            self.logger.info(f"日次分析完了: 実行時間 {execution_time:.2f}秒")
            return result
            
        except Exception as e:
            self.logger.error(f"日次分析中にエラーが発生: {e}")
            raise
    
    def _analyze_holdings(self,
                         holdings: List[StockConfig],
                         analysis_mode: AnalysisMode,
                         enable_ai_analysis: bool) -> List[HoldingRecommendation]:
        """
        保有銘柄を分析
        
        Args:
            holdings: 保有銘柄リスト
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            List[HoldingRecommendation]: 保有銘柄推奨リスト
        """
        recommendations = []
        
        # 株価データを一括取得
        symbols = [holding.symbol for holding in holdings]
        stock_data_result = self.stock_service.get_batch_stock_data(symbols)
        
        if not stock_data_result.success:
            self.logger.warning(f"株価データ取得で一部失敗: {stock_data_result.error_message}")
        
        for holding in holdings:
            try:
                recommendation = self._analyze_single_holding(
                    holding, stock_data_result.stock_data.get(holding.symbol),
                    analysis_mode, enable_ai_analysis
                )
                if recommendation:
                    recommendations.append(recommendation)
                    
            except Exception as e:
                self.logger.error(f"保有銘柄分析エラー ({holding.symbol}): {e}")
                # エラーが発生した場合もデフォルト推奨を作成
                recommendations.append(self._create_default_holding_recommendation(holding))
        
        return recommendations
    
    def _analyze_single_holding(self,
                               holding: StockConfig,
                               stock_data: Optional[StockData],
                               analysis_mode: AnalysisMode,
                               enable_ai_analysis: bool) -> Optional[HoldingRecommendation]:
        """
        個別保有銘柄を分析
        
        Args:
            holding: 保有銘柄設定
            stock_data: 株価データ
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            HoldingRecommendation: 保有銘柄推奨
        """
        if not stock_data:
            self.logger.warning(f"株価データなし: {holding.symbol}")
            return self._create_default_holding_recommendation(holding)
        
        # 履歴データを取得
        try:
            historical_data = self.historical_manager.get_historical_data(
                holding.symbol, period_days=60
            )
            
            if not historical_data.success or historical_data.dataset.is_empty:
                self.logger.warning(f"履歴データ取得失敗: {holding.symbol}")
                return self._create_basic_holding_recommendation(holding, stock_data)
            
            # テクニカル分析を実行
            technical_result = self.technical_service.analyze(historical_data.dataset)
            
            # AI分析（オプション）
            ai_recommendation = None
            if enable_ai_analysis:
                try:
                    gemini_response = self.gemini_service.analyze_stock(
                        stock_data, technical_result, AnalysisType.DAILY, analysis_mode
                    )
                    if gemini_response.success and gemini_response.analysis_result:
                        ai_recommendation = gemini_response.analysis_result
                except Exception as e:
                    self.logger.warning(f"AI分析失敗 ({holding.symbol}): {e}")
            
            # 推奨を生成
            return self._generate_holding_recommendation(
                holding, stock_data, technical_result, ai_recommendation, analysis_mode
            )
            
        except Exception as e:
            self.logger.error(f"保有銘柄分析エラー ({holding.symbol}): {e}")
            return self._create_basic_holding_recommendation(holding, stock_data)
    
    def _generate_holding_recommendation(self,
                                       holding: StockConfig,
                                       stock_data: StockData,
                                       technical_result: TechnicalAnalysisResult,
                                       ai_recommendation: Optional[AnalysisResult],
                                       analysis_mode: AnalysisMode) -> HoldingRecommendation:
        """
        保有銘柄推奨を生成
        
        Args:
            holding: 保有銘柄設定
            stock_data: 株価データ
            technical_result: テクニカル分析結果
            ai_recommendation: AI推奨
            analysis_mode: 分析モード
            
        Returns:
            HoldingRecommendation: 保有銘柄推奨
        """
        # 基本アクションをテクニカル分析から決定
        action, confidence = self._determine_holding_action(technical_result, analysis_mode)
        
        # AI推奨がある場合は調整
        if ai_recommendation and ai_recommendation.recommendations:
            ai_rec = ai_recommendation.recommendations[0]
            action, confidence = self._adjust_action_with_ai(
                action, confidence, ai_rec, analysis_mode
            )
        
        # 含み損益計算
        purchase_price = holding.purchase_price or stock_data.current_price
        unrealized_pnl = (stock_data.current_price - purchase_price) * holding.quantity
        unrealized_pnl_pct = ((stock_data.current_price - purchase_price) / purchase_price) * 100 if purchase_price > 0 else 0
        
        # リスク評価
        risk_level = self._assess_holding_risk(stock_data, technical_result, unrealized_pnl_pct)
        risk_factors = self._identify_risk_factors(stock_data, technical_result)
        
        # 推奨数量の計算
        recommended_quantity = self._calculate_recommended_quantity(
            action, holding.quantity, stock_data, technical_result, analysis_mode
        )
        
        # 価格目標の設定
        target_price, stop_loss = self._calculate_price_targets(
            stock_data, technical_result, action, analysis_mode
        )
        
        # 理由の生成
        reasoning = self._generate_holding_reasoning(
            action, technical_result, ai_recommendation, unrealized_pnl_pct
        )
        
        return HoldingRecommendation(
            symbol=holding.symbol,
            name=holding.name,
            current_price=stock_data.current_price,
            current_quantity=holding.quantity,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            recommended_quantity=recommended_quantity,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_level=risk_level,
            risk_factors=risk_factors,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct
        )
    
    def _determine_holding_action(self,
                                technical_result: TechnicalAnalysisResult,
                                analysis_mode: AnalysisMode) -> Tuple[HoldingAction, float]:
        """
        テクニカル分析に基づいてアクションを決定
        
        Args:
            technical_result: テクニカル分析結果
            analysis_mode: 分析モード
            
        Returns:
            Tuple[HoldingAction, float]: アクションと信頼度
        """
        signal_strength = technical_result.signal_strength
        trend_direction = technical_result.trend_direction
        overall_signal = technical_result.overall_signal
        
        # 分析モードによる閾値調整
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            buy_threshold = 0.7
            sell_threshold = 0.3
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            buy_threshold = 0.5
            sell_threshold = 0.5
        else:  # BALANCED
            buy_threshold = 0.6
            sell_threshold = 0.4
        
        # RSI による過熱判定
        is_overbought = technical_result.rsi and technical_result.rsi.is_overbought
        is_oversold = technical_result.rsi and technical_result.rsi.is_oversold
        
        # 新高値/新安値判定
        is_new_high = technical_result.is_new_high
        is_new_low = technical_result.is_new_low
        
        # アクション決定ロジック
        if signal_strength >= buy_threshold and not is_overbought:
            if is_oversold or is_new_low:
                return HoldingAction.BUY_MORE, min(0.9, signal_strength + 0.1)
            else:
                return HoldingAction.BUY_MORE, signal_strength
                
        elif signal_strength <= sell_threshold or is_overbought:
            if is_new_high and signal_strength < 0.3:
                return HoldingAction.SELL_ALL, min(0.9, 1.0 - signal_strength)
            elif signal_strength <= 0.2:
                return HoldingAction.SELL_PARTIAL, min(0.8, 1.0 - signal_strength)
            else:
                return HoldingAction.SELL_PARTIAL, 0.6
                
        else:
            return HoldingAction.HOLD, 0.5
    
    def _adjust_action_with_ai(self,
                             current_action: HoldingAction,
                             current_confidence: float,
                             ai_recommendation: Recommendation,
                             analysis_mode: AnalysisMode) -> Tuple[HoldingAction, float]:
        """
        AI推奨でアクションを調整
        
        Args:
            current_action: 現在のアクション
            current_confidence: 現在の信頼度
            ai_recommendation: AI推奨
            analysis_mode: 分析モード
            
        Returns:
            Tuple[HoldingAction, float]: 調整後のアクションと信頼度
        """
        ai_confidence = ai_recommendation.confidence
        
        # AI推奨の重み（分析モードによって調整）
        ai_weight = {
            AnalysisMode.CONSERVATIVE: 0.3,
            AnalysisMode.BALANCED: 0.5,
            AnalysisMode.AGGRESSIVE: 0.7
        }.get(analysis_mode, 0.5)
        
        # AI推奨に基づくアクション調整
        if ai_recommendation.type == RecommendationType.STRONG_BUY:
            if current_action == HoldingAction.HOLD:
                adjusted_confidence = min(0.95, current_confidence + ai_confidence * ai_weight)
                return HoldingAction.BUY_MORE, adjusted_confidence
            elif current_action == HoldingAction.SELL_PARTIAL:
                adjusted_confidence = (current_confidence + ai_confidence * ai_weight) / 2
                return HoldingAction.HOLD, adjusted_confidence
                
        elif ai_recommendation.type == RecommendationType.STRONG_SELL:
            if current_action == HoldingAction.HOLD:
                adjusted_confidence = min(0.95, current_confidence + ai_confidence * ai_weight)
                return HoldingAction.SELL_PARTIAL, adjusted_confidence
            elif current_action == HoldingAction.BUY_MORE:
                adjusted_confidence = (current_confidence + ai_confidence * ai_weight) / 2
                return HoldingAction.HOLD, adjusted_confidence
        
        # 信頼度の調整
        adjusted_confidence = (current_confidence + ai_confidence * ai_weight) / (1 + ai_weight)
        return current_action, min(0.95, adjusted_confidence)
    
    def _analyze_watchlist(self,
                          watchlist: List[WatchlistStock],
                          analysis_mode: AnalysisMode,
                          enable_ai_analysis: bool) -> List[WatchlistRecommendation]:
        """
        ウォッチリストを分析
        
        Args:
            watchlist: ウォッチリスト
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            List[WatchlistRecommendation]: ウォッチリスト推奨リスト
        """
        recommendations = []
        
        # 株価データを一括取得
        symbols = [stock.symbol for stock in watchlist]
        stock_data_result = self.stock_service.get_batch_stock_data(symbols)
        
        if not stock_data_result.success:
            self.logger.warning(f"ウォッチリスト株価データ取得で一部失敗: {stock_data_result.error_message}")
        
        for stock in watchlist:
            try:
                recommendation = self._analyze_single_watchlist_stock(
                    stock, stock_data_result.stock_data.get(stock.symbol),
                    analysis_mode, enable_ai_analysis
                )
                if recommendation:
                    recommendations.append(recommendation)
                    
            except Exception as e:
                self.logger.error(f"ウォッチリスト分析エラー ({stock.symbol}): {e}")
        
        # 優先度でソート
        recommendations.sort(key=lambda x: x.priority, reverse=True)
        return recommendations
    
    def _analyze_single_watchlist_stock(self,
                                      stock: WatchlistStock,
                                      stock_data: Optional[StockData],
                                      analysis_mode: AnalysisMode,
                                      enable_ai_analysis: bool) -> Optional[WatchlistRecommendation]:
        """
        個別ウォッチリスト銘柄を分析
        
        Args:
            stock: ウォッチリスト銘柄
            stock_data: 株価データ
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            WatchlistRecommendation: ウォッチリスト推奨
        """
        if not stock_data:
            self.logger.warning(f"株価データなし: {stock.symbol}")
            return None
        
        try:
            # 履歴データを取得
            historical_data = self.historical_manager.get_historical_data(
                stock.symbol, period_days=60
            )
            
            if not historical_data.success or historical_data.dataset.is_empty:
                self.logger.warning(f"履歴データ取得失敗: {stock.symbol}")
                return self._create_basic_watchlist_recommendation(stock, stock_data)
            
            # テクニカル分析を実行
            technical_result = self.technical_service.analyze(historical_data.dataset)
            
            # AI分析（オプション）
            ai_recommendation = None
            if enable_ai_analysis:
                try:
                    gemini_response = self.gemini_service.analyze_stock(
                        stock_data, technical_result, AnalysisType.DAILY, analysis_mode
                    )
                    if gemini_response.success and gemini_response.analysis_result:
                        ai_recommendation = gemini_response.analysis_result
                except Exception as e:
                    self.logger.warning(f"AI分析失敗 ({stock.symbol}): {e}")
            
            # 推奨を生成
            return self._generate_watchlist_recommendation(
                stock, stock_data, technical_result, ai_recommendation, analysis_mode
            )
            
        except Exception as e:
            self.logger.error(f"ウォッチリスト分析エラー ({stock.symbol}): {e}")
            return self._create_basic_watchlist_recommendation(stock, stock_data)
    
    def _generate_watchlist_recommendation(self,
                                         stock: WatchlistStock,
                                         stock_data: StockData,
                                         technical_result: TechnicalAnalysisResult,
                                         ai_recommendation: Optional[AnalysisResult],
                                         analysis_mode: AnalysisMode) -> WatchlistRecommendation:
        """
        ウォッチリスト推奨を生成
        
        Args:
            stock: ウォッチリスト銘柄
            stock_data: 株価データ
            technical_result: テクニカル分析結果
            ai_recommendation: AI推奨
            analysis_mode: 分析モード
            
        Returns:
            WatchlistRecommendation: ウォッチリスト推奨
        """
        # 基本アクションをテクニカル分析から決定
        action, confidence, priority = self._determine_watchlist_action(
            technical_result, analysis_mode
        )
        
        # AI推奨がある場合は調整
        if ai_recommendation and ai_recommendation.recommendations:
            ai_rec = ai_recommendation.recommendations[0]
            action, confidence, priority = self._adjust_watchlist_action_with_ai(
                action, confidence, priority, ai_rec, analysis_mode
            )
        
        # エントリー価格とタイミング
        entry_price, entry_timing = self._calculate_entry_strategy(
            stock_data, technical_result, action
        )
        
        # 価格目標
        target_price, stop_loss = self._calculate_price_targets(
            stock_data, technical_result, action, analysis_mode
        )
        
        # リスク評価
        risk_level = self._assess_watchlist_risk(stock_data, technical_result)
        
        # 理由の生成
        reasoning = self._generate_watchlist_reasoning(
            action, technical_result, ai_recommendation
        )
        
        return WatchlistRecommendation(
            symbol=stock.symbol,
            name=stock.name,
            current_price=stock_data.current_price,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            entry_price=entry_price,
            entry_timing=entry_timing,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_level=risk_level,
            priority=priority
        )
    
    def _determine_watchlist_action(self,
                                  technical_result: TechnicalAnalysisResult,
                                  analysis_mode: AnalysisMode) -> Tuple[WatchlistAction, float, int]:
        """
        ウォッチリストアクションを決定
        
        Args:
            technical_result: テクニカル分析結果
            analysis_mode: 分析モード
            
        Returns:
            Tuple[WatchlistAction, float, int]: アクション、信頼度、優先度
        """
        signal_strength = technical_result.signal_strength
        is_oversold = technical_result.rsi and technical_result.rsi.is_oversold
        is_new_low = technical_result.is_new_low
        volatility = technical_result.volatility
        
        # 分析モードによる閾値調整
        buy_threshold = 0.75 if analysis_mode == AnalysisMode.CONSERVATIVE else 0.65
        
        if signal_strength >= buy_threshold:
            if is_oversold or is_new_low:
                return WatchlistAction.BUY_NOW, signal_strength, 9
            else:
                return WatchlistAction.BUY_NOW, signal_strength, 7
                
        elif signal_strength >= 0.5:
            if volatility > 20:  # 高ボラティリティ
                return WatchlistAction.BUY_ON_DIP, signal_strength, 6
            else:
                return WatchlistAction.BUY_ON_DIP, signal_strength, 5
                
        elif signal_strength <= 0.3:
            return WatchlistAction.REMOVE, 1.0 - signal_strength, 1
            
        else:
            return WatchlistAction.WAIT, 0.5, 3
    
    def _adjust_watchlist_action_with_ai(self,
                                       current_action: WatchlistAction,
                                       current_confidence: float,
                                       current_priority: int,
                                       ai_recommendation: Recommendation,
                                       analysis_mode: AnalysisMode) -> Tuple[WatchlistAction, float, int]:
        """
        AI推奨でウォッチリストアクションを調整
        
        Args:
            current_action: 現在のアクション
            current_confidence: 現在の信頼度
            current_priority: 現在の優先度
            ai_recommendation: AI推奨
            analysis_mode: 分析モード
            
        Returns:
            Tuple[WatchlistAction, float, int]: 調整後のアクション、信頼度、優先度
        """
        ai_confidence = ai_recommendation.confidence
        ai_weight = {
            AnalysisMode.CONSERVATIVE: 0.3,
            AnalysisMode.BALANCED: 0.5,
            AnalysisMode.AGGRESSIVE: 0.7
        }.get(analysis_mode, 0.5)
        
        # AI推奨に基づく調整
        if ai_recommendation.type == RecommendationType.STRONG_BUY:
            if current_action == WatchlistAction.WAIT:
                return WatchlistAction.BUY_ON_DIP, (current_confidence + ai_confidence * ai_weight) / 2, min(10, current_priority + 2)
            elif current_action == WatchlistAction.BUY_ON_DIP:
                return WatchlistAction.BUY_NOW, (current_confidence + ai_confidence * ai_weight) / 2, min(10, current_priority + 1)
                
        elif ai_recommendation.type == RecommendationType.SELL:
            if current_action in [WatchlistAction.BUY_NOW, WatchlistAction.BUY_ON_DIP]:
                return WatchlistAction.WAIT, 0.4, max(1, current_priority - 2)
        
        # 信頼度と優先度の調整
        adjusted_confidence = (current_confidence + ai_confidence * ai_weight) / (1 + ai_weight)
        adjusted_priority = current_priority
        
        if ai_confidence > 0.8:
            adjusted_priority = min(10, current_priority + 1)
        
        return current_action, min(0.95, adjusted_confidence), adjusted_priority
    
    # ヘルパーメソッド群
    def _create_default_holding_recommendation(self, holding: StockConfig) -> HoldingRecommendation:
        """デフォルト保有銘柄推奨を作成"""
        return HoldingRecommendation(
            symbol=holding.symbol,
            name=holding.name,
            current_price=0.0,
            current_quantity=holding.quantity,
            action=HoldingAction.HOLD,
            confidence=0.3,
            reasoning="データ不足のため保持推奨",
            risk_level=RiskLevel.HIGH,
            risk_factors=["データ不足"]
        )
    
    def _create_basic_holding_recommendation(self, holding: StockConfig, stock_data: StockData) -> HoldingRecommendation:
        """基本的な保有銘柄推奨を作成"""
        return HoldingRecommendation(
            symbol=holding.symbol,
            name=holding.name,
            current_price=stock_data.current_price,
            current_quantity=holding.quantity,
            action=HoldingAction.HOLD,
            confidence=0.5,
            reasoning="限定的なデータに基づく保持推奨"
        )
    
    def _create_basic_watchlist_recommendation(self, stock: WatchlistStock, stock_data: StockData) -> WatchlistRecommendation:
        """基本的なウォッチリスト推奨を作成"""
        return WatchlistRecommendation(
            symbol=stock.symbol,
            name=stock.name,
            current_price=stock_data.current_price,
            action=WatchlistAction.WAIT,
            confidence=0.5,
            reasoning="限定的なデータに基づく待機推奨",
            priority=5
        )
    
    def _assess_holding_risk(self, stock_data: StockData, technical_result: TechnicalAnalysisResult, unrealized_pnl_pct: float) -> RiskLevel:
        """保有銘柄リスク評価"""
        risk_score = 0
        
        # ボラティリティ
        if technical_result.volatility > 30:
            risk_score += 2
        elif technical_result.volatility > 20:
            risk_score += 1
        
        # 含み損益
        if unrealized_pnl_pct < -20:
            risk_score += 2
        elif unrealized_pnl_pct < -10:
            risk_score += 1
        
        # テクニカル指標
        if technical_result.rsi and technical_result.rsi.current_value:
            if technical_result.rsi.current_value > 80 or technical_result.rsi.current_value < 20:
                risk_score += 1
        
        if risk_score >= 3:
            return RiskLevel.HIGH
        elif risk_score >= 1:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _assess_watchlist_risk(self, stock_data: StockData, technical_result: TechnicalAnalysisResult) -> RiskLevel:
        """ウォッチリストリスク評価"""
        risk_score = 0
        
        # ボラティリティ
        if technical_result.volatility > 25:
            risk_score += 2
        elif technical_result.volatility > 15:
            risk_score += 1
        
        # シグナル強度（低い場合はリスク）
        if technical_result.signal_strength < 0.4:
            risk_score += 1
        
        if risk_score >= 2:
            return RiskLevel.HIGH
        elif risk_score >= 1:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _identify_risk_factors(self, stock_data: StockData, technical_result: TechnicalAnalysisResult) -> List[str]:
        """リスク要因を特定"""
        factors = []
        
        if technical_result.volatility > 25:
            factors.append("高ボラティリティ")
        
        if technical_result.rsi and technical_result.rsi.is_overbought:
            factors.append("買われすぎ")
        
        if technical_result.is_new_low:
            factors.append("新安値更新")
        
        if stock_data.volume < 10000:  # 低出来高
            factors.append("低流動性")
        
        return factors
    
    def _calculate_recommended_quantity(self, action: HoldingAction, current_quantity: int, stock_data: StockData, technical_result: TechnicalAnalysisResult, analysis_mode: AnalysisMode) -> Optional[int]:
        """推奨数量を計算"""
        if action == HoldingAction.BUY_MORE:
            # 信頼度に基づいて追加購入数量を決定
            base_quantity = max(1, current_quantity // 10)  # 現在の10%程度
            if technical_result.signal_strength > 0.8:
                return base_quantity * 2
            else:
                return base_quantity
                
        elif action == HoldingAction.SELL_PARTIAL:
            # 部分売却数量
            if technical_result.signal_strength < 0.3:
                return current_quantity // 2  # 半分売却
            else:
                return current_quantity // 4  # 4分の1売却
                
        elif action == HoldingAction.SELL_ALL:
            return current_quantity
            
        return None
    
    def _calculate_price_targets(self, stock_data: StockData, technical_result: TechnicalAnalysisResult, action, analysis_mode: AnalysisMode) -> Tuple[Optional[float], Optional[float]]:
        """価格目標を計算"""
        current_price = stock_data.current_price
        volatility = technical_result.volatility / 100
        
        # 保守的/積極的な調整
        multiplier = {
            AnalysisMode.CONSERVATIVE: 0.8,
            AnalysisMode.BALANCED: 1.0,
            AnalysisMode.AGGRESSIVE: 1.2
        }.get(analysis_mode, 1.0)
        
        if isinstance(action, HoldingAction) and action in [HoldingAction.BUY_MORE, HoldingAction.HOLD]:
            target_price = current_price * (1 + volatility * 2 * multiplier)
            stop_loss = current_price * (1 - volatility * 1.5)
            
        elif isinstance(action, WatchlistAction) and action in [WatchlistAction.BUY_NOW, WatchlistAction.BUY_ON_DIP]:
            target_price = current_price * (1 + volatility * 1.5 * multiplier)
            stop_loss = current_price * (1 - volatility * 1.2)
            
        else:
            target_price = None
            stop_loss = current_price * 0.95  # 基本的なストップロス
        
        return target_price, stop_loss
    
    def _calculate_entry_strategy(self, stock_data: StockData, technical_result: TechnicalAnalysisResult, action: WatchlistAction) -> Tuple[Optional[float], str]:
        """エントリー戦略を計算"""
        current_price = stock_data.current_price
        
        if action == WatchlistAction.BUY_NOW:
            return current_price, "即座"
        elif action == WatchlistAction.BUY_ON_DIP:
            # 5-10%の押し目を狙う
            entry_price = current_price * 0.95
            return entry_price, "押し目待ち"
        else:
            return None, "待機"
    
    def _generate_holding_reasoning(self, action: HoldingAction, technical_result: TechnicalAnalysisResult, ai_recommendation: Optional[AnalysisResult], unrealized_pnl_pct: float) -> str:
        """保有銘柄推奨理由を生成"""
        reasons = []
        
        # テクニカル要因
        if technical_result.signal_strength > 0.7:
            reasons.append("強いテクニカル買いシグナル")
        elif technical_result.signal_strength < 0.3:
            reasons.append("弱いテクニカル指標")
        
        # RSI
        if technical_result.rsi:
            if technical_result.rsi.is_oversold:
                reasons.append("RSI売られすぎ")
            elif technical_result.rsi.is_overbought:
                reasons.append("RSI買われすぎ")
        
        # 含み損益
        if unrealized_pnl_pct > 20:
            reasons.append("大幅含み益")
        elif unrealized_pnl_pct < -15:
            reasons.append("含み損拡大")
        
        # AI推奨
        if ai_recommendation and ai_recommendation.recommendations:
            ai_rec = ai_recommendation.recommendations[0]
            if ai_rec.confidence > 0.7:
                reasons.append(f"AI高信頼度推奨({ai_rec.type.value})")
        
        return "、".join(reasons) if reasons else f"{action.display_name}を推奨"
    
    def _generate_watchlist_reasoning(self, action: WatchlistAction, technical_result: TechnicalAnalysisResult, ai_recommendation: Optional[AnalysisResult]) -> str:
        """ウォッチリスト推奨理由を生成"""
        reasons = []
        
        # テクニカル要因
        if technical_result.signal_strength > 0.7:
            reasons.append("強い買いシグナル")
        elif technical_result.signal_strength < 0.3:
            reasons.append("弱いシグナル")
        
        # トレンド
        if technical_result.trend_direction.value == "bullish":
            reasons.append("上昇トレンド")
        elif technical_result.trend_direction.value == "bearish":
            reasons.append("下降トレンド")
        
        # 特殊状況
        if technical_result.is_new_high:
            reasons.append("新高値ブレイク")
        elif technical_result.is_new_low:
            reasons.append("新安値機会")
        
        # AI推奨
        if ai_recommendation and ai_recommendation.recommendations:
            ai_rec = ai_recommendation.recommendations[0]
            if ai_rec.confidence > 0.7:
                reasons.append(f"AI推奨({ai_rec.type.value})")
        
        return "、".join(reasons) if reasons else f"{action.display_name}を推奨"
    
    def _generate_holdings_summary(self, recommendations: List[HoldingRecommendation]) -> str:
        """保有銘柄サマリーを生成"""
        if not recommendations:
            return "保有銘柄なし"
        
        total_value = sum(rec.current_value or 0 for rec in recommendations)
        buy_more_count = len([rec for rec in recommendations if rec.action == HoldingAction.BUY_MORE])
        sell_count = len([rec for rec in recommendations if rec.action in [HoldingAction.SELL_PARTIAL, HoldingAction.SELL_ALL]])
        
        return f"保有{len(recommendations)}銘柄、評価額{total_value:,.0f}円、追加購入推奨{buy_more_count}銘柄、売却推奨{sell_count}銘柄"
    
    def _generate_watchlist_summary(self, recommendations: List[WatchlistRecommendation]) -> str:
        """ウォッチリストサマリーを生成"""
        if not recommendations:
            return "ウォッチリストなし"
        
        buy_count = len([rec for rec in recommendations if rec.action in [WatchlistAction.BUY_NOW, WatchlistAction.BUY_ON_DIP]])
        high_priority_count = len([rec for rec in recommendations if rec.priority >= 8])
        
        return f"ウォッチ{len(recommendations)}銘柄、購入推奨{buy_count}銘柄、高優先度{high_priority_count}銘柄"
    
    def _generate_market_summary(self, result: DailyAnalysisResult, analysis_mode: AnalysisMode) -> str:
        """市場サマリーを生成"""
        total_buy_signals = result.buy_recommendations_count + len([rec for rec in result.holding_recommendations if rec.action == HoldingAction.BUY_MORE])
        total_sell_signals = result.sell_recommendations_count
        
        if total_buy_signals > total_sell_signals:
            return f"買い優勢市場。買い推奨{total_buy_signals}、売り推奨{total_sell_signals}"
        elif total_sell_signals > total_buy_signals:
            return f"売り優勢市場。買い推奨{total_buy_signals}、売り推奨{total_sell_signals}"
        else:
            return f"中立市場。買い推奨{total_buy_signals}、売り推奨{total_sell_signals}"
    
    def _assess_market_sentiment(self, result: DailyAnalysisResult) -> str:
        """市場センチメントを評価"""
        buy_signals = result.buy_recommendations_count + len([rec for rec in result.holding_recommendations if rec.action == HoldingAction.BUY_MORE])
        sell_signals = result.sell_recommendations_count
        total_signals = buy_signals + sell_signals
        
        if total_signals == 0:
            return "中立"
        
        buy_ratio = buy_signals / total_signals
        
        if buy_ratio > 0.6:
            return "強気"
        elif buy_ratio < 0.4:
            return "弱気"
        else:
            return "中立"
    
    def _generate_risk_assessment(self, result: DailyAnalysisResult) -> str:
        """リスク評価を生成"""
        high_risk_holdings = len([rec for rec in result.holding_recommendations if rec.risk_level == RiskLevel.HIGH])
        high_risk_watchlist = len([rec for rec in result.watchlist_recommendations if rec.risk_level == RiskLevel.HIGH])
        
        total_high_risk = high_risk_holdings + high_risk_watchlist
        
        if total_high_risk == 0:
            return "低リスク環境"
        elif total_high_risk <= 2:
            return f"中程度リスク環境（高リスク{total_high_risk}銘柄）"
        else:
            return f"高リスク環境（高リスク{total_high_risk}銘柄）"
    
    def _generate_daily_strategy(self, result: DailyAnalysisResult, analysis_mode: AnalysisMode) -> str:
        """日次戦略を生成"""
        strategies = []
        
        # 保有銘柄戦略
        if result.holding_recommendations:
            buy_more_count = len([rec for rec in result.holding_recommendations if rec.action == HoldingAction.BUY_MORE])
            if buy_more_count > 0:
                strategies.append(f"保有銘柄{buy_more_count}銘柄の追加購入検討")
            
            sell_count = len([rec for rec in result.holding_recommendations if rec.action in [HoldingAction.SELL_PARTIAL, HoldingAction.SELL_ALL]])
            if sell_count > 0:
                strategies.append(f"保有銘柄{sell_count}銘柄の売却検討")
        
        # ウォッチリスト戦略
        if result.high_priority_watchlist:
            strategies.append(f"高優先度{len(result.high_priority_watchlist)}銘柄の新規購入検討")
        
        # 分析モード別戦略
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            strategies.append("リスク管理重視の保守的アプローチ")
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            strategies.append("成長機会重視の積極的アプローチ")
        else:
            strategies.append("バランス重視のアプローチ")
        
        return "。".join(strategies) if strategies else "現状維持戦略"