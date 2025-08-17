# -*- coding: utf-8 -*-
"""
月次分析サービス
国別・業種別パフォーマンス分析、長期リバランスアドバイス、分散投資状況の評価機能を提供
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import statistics

from src.models.data_models import StockConfig, StockData
from src.models.analysis_models import AnalysisResult, AnalysisType
from src.services.google_sheets_service import GoogleSheetsService, DataExtractionResult
from src.services.stock_data_service import StockDataService, BatchDataResult
from src.services.historical_data_manager import HistoricalDataManager, DataRetrievalResult
from src.services.technical_analysis_service import TechnicalAnalysisService, TechnicalAnalysisResult
from src.services.gemini_service import GeminiService, AnalysisMode


logger = logging.getLogger(__name__)


class RegionType(Enum):
    """地域区分"""
    US = "us"
    EUROPE = "europe"
    ASIA = "asia"
    JAPAN = "japan"
    EMERGING = "emerging"
    DEVELOPED = "developed"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            RegionType.US: "米国",
            RegionType.EUROPE: "ヨーロッパ",
            RegionType.ASIA: "アジア",
            RegionType.JAPAN: "日本",
            RegionType.EMERGING: "新興国",
            RegionType.DEVELOPED: "先進国"
        }[self]


class SectorType(Enum):
    """業種区分"""
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    FINANCIALS = "financials"
    CONSUMER_DISCRETIONARY = "consumer_discretionary"
    CONSUMER_STAPLES = "consumer_staples"
    INDUSTRIALS = "industrials"
    ENERGY = "energy"
    UTILITIES = "utilities"
    MATERIALS = "materials"
    REAL_ESTATE = "real_estate"
    COMMUNICATIONS = "communications"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            SectorType.TECHNOLOGY: "テクノロジー",
            SectorType.HEALTHCARE: "ヘルスケア",
            SectorType.FINANCIALS: "金融",
            SectorType.CONSUMER_DISCRETIONARY: "一般消費財",
            SectorType.CONSUMER_STAPLES: "生活必需品",
            SectorType.INDUSTRIALS: "資本財",
            SectorType.ENERGY: "エネルギー",
            SectorType.UTILITIES: "公益事業",
            SectorType.MATERIALS: "素材",
            SectorType.REAL_ESTATE: "不動産",
            SectorType.COMMUNICATIONS: "通信"
        }[self]


class DiversificationLevel(Enum):
    """分散レベル"""
    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    VERY_POOR = "very_poor"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            DiversificationLevel.EXCELLENT: "優秀",
            DiversificationLevel.GOOD: "良好", 
            DiversificationLevel.MODERATE: "普通",
            DiversificationLevel.POOR: "不十分",
            DiversificationLevel.VERY_POOR: "非常に不十分"
        }[self]


@dataclass
class RegionalPerformance:
    """地域別パフォーマンス"""
    region: RegionType
    allocation_percentage: float
    monthly_return: float
    monthly_return_pct: float
    volatility: float
    sharpe_ratio: float
    holdings_count: int
    total_value: float
    contribution_to_portfolio: float  # ポートフォリオ貢献度


@dataclass
class SectorPerformance:
    """業種別パフォーマンス"""
    sector: SectorType
    allocation_percentage: float
    monthly_return: float
    monthly_return_pct: float
    volatility: float
    sharpe_ratio: float
    holdings_count: int
    total_value: float
    contribution_to_portfolio: float


@dataclass
class DiversificationMetrics:
    """分散投資指標"""
    herfindahl_index: float  # ハーフィンダール指数（集中度）
    effective_holdings: float  # 実効保有銘柄数
    region_diversification: DiversificationLevel
    sector_diversification: DiversificationLevel
    concentration_risk_score: float  # 集中リスクスコア
    top_holdings_percentage: float  # 上位銘柄の占有率
    correlation_score: float  # 銘柄間相関スコア


@dataclass
class RebalanceRecommendation:
    """リバランス推奨"""
    type: str  # "increase", "decrease", "maintain"
    category: str  # region or sector
    name: str  # 具体的な地域名・業種名
    current_allocation: float
    target_allocation: float
    recommended_change: float
    reasoning: str
    priority: int  # 1-10


@dataclass
class MonthlyAnalysisResult:
    """月次分析結果"""
    analysis_date: datetime
    analysis_period_start: datetime
    analysis_period_end: datetime
    total_portfolio_value: float
    monthly_return: float
    monthly_return_pct: float
    
    # 地域・業種別分析
    regional_performances: List[RegionalPerformance]
    sector_performances: List[SectorPerformance]
    
    # 分散投資分析
    diversification_metrics: DiversificationMetrics
    
    # リバランス推奨
    rebalance_recommendations: List[RebalanceRecommendation]
    
    # サマリー
    performance_summary: str
    diversification_summary: str
    rebalance_summary: str
    risk_assessment: str
    long_term_outlook: str
    
    execution_time: float = 0
    
    @property
    def best_performing_region(self) -> Optional[RegionalPerformance]:
        """最高パフォーマンス地域"""
        return max(self.regional_performances, 
                  key=lambda x: x.monthly_return_pct, default=None)
    
    @property
    def worst_performing_region(self) -> Optional[RegionalPerformance]:
        """最低パフォーマンス地域"""
        return min(self.regional_performances, 
                  key=lambda x: x.monthly_return_pct, default=None)
    
    @property
    def best_performing_sector(self) -> Optional[SectorPerformance]:
        """最高パフォーマンス業種"""
        return max(self.sector_performances, 
                  key=lambda x: x.monthly_return_pct, default=None)
    
    @property
    def worst_performing_sector(self) -> Optional[SectorPerformance]:
        """最低パフォーマンス業種"""
        return min(self.sector_performances, 
                  key=lambda x: x.monthly_return_pct, default=None)


class MonthlyAnalysisService:
    """月次分析サービス"""
    
    # 銘柄シンボルから地域・業種を推定するマッピング（簡略版）
    SYMBOL_TO_REGION = {
        # 米国株
        "AAPL": RegionType.US, "GOOGL": RegionType.US, "MSFT": RegionType.US,
        "AMZN": RegionType.US, "TSLA": RegionType.US, "NVDA": RegionType.US,
        "META": RegionType.US, "NFLX": RegionType.US, "SPY": RegionType.US,
        "QQQ": RegionType.US, "VOO": RegionType.US,
    }
    
    SYMBOL_TO_SECTOR = {
        # テクノロジー
        "AAPL": SectorType.TECHNOLOGY, "GOOGL": SectorType.TECHNOLOGY, 
        "MSFT": SectorType.TECHNOLOGY, "NVDA": SectorType.TECHNOLOGY,
        "META": SectorType.COMMUNICATIONS, "NFLX": SectorType.COMMUNICATIONS,
        # その他
        "AMZN": SectorType.CONSUMER_DISCRETIONARY,
        "TSLA": SectorType.CONSUMER_DISCRETIONARY,
    }
    
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
    
    def execute_monthly_analysis(self,
                               analysis_mode: AnalysisMode = AnalysisMode.BALANCED,
                               enable_ai_analysis: bool = True) -> MonthlyAnalysisResult:
        """
        月次分析を実行
        
        Args:
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            
        Returns:
            MonthlyAnalysisResult: 月次分析結果
        """
        start_time = datetime.now()
        self.logger.info("月次分析開始")
        
        try:
            # 分析期間の設定（過去1ヶ月）
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            # Google Sheetsから保有銘柄を取得
            holdings_data = self.sheets_service.get_holdings_data()
            if not holdings_data.success:
                error_msg = ", ".join(holdings_data.errors) if holdings_data.errors else "Unknown error"
                raise Exception(f"Google Sheetsからのデータ取得に失敗: {error_msg}")
            
            holdings = holdings_data.data
            if not holdings:
                raise Exception("保有銘柄が見つかりません")
            
            # 現在の株価データを取得
            symbols = [holding.symbol for holding in holdings]
            current_data_result = self.stock_service.get_batch_stock_data(symbols)
            
            # 月間履歴データを取得
            monthly_data = self._get_monthly_historical_data(symbols, start_date, end_date)
            
            # ポートフォリオ価値計算
            total_portfolio_value = sum(
                current_data_result.stock_data.get(holding.symbol, Mock()).current_price * holding.quantity
                for holding in holdings
                if current_data_result.stock_data.get(holding.symbol)
            )
            
            # 月間リターン計算
            monthly_return, monthly_return_pct = self._calculate_portfolio_monthly_return(
                holdings, current_data_result.stock_data, monthly_data
            )
            
            # 地域別分析
            regional_performances = self._analyze_regional_performance(
                holdings, current_data_result.stock_data, monthly_data, total_portfolio_value
            )
            
            # 業種別分析
            sector_performances = self._analyze_sector_performance(
                holdings, current_data_result.stock_data, monthly_data, total_portfolio_value
            )
            
            # 分散投資指標計算
            diversification_metrics = self._calculate_diversification_metrics(
                holdings, current_data_result.stock_data, total_portfolio_value
            )
            
            # リバランス推奨生成
            rebalance_recommendations = self._generate_rebalance_recommendations(
                regional_performances, sector_performances, diversification_metrics, analysis_mode
            )
            
            # 分析結果を生成
            result = MonthlyAnalysisResult(
                analysis_date=datetime.now(),
                analysis_period_start=start_date,
                analysis_period_end=end_date,
                total_portfolio_value=total_portfolio_value,
                monthly_return=monthly_return,
                monthly_return_pct=monthly_return_pct,
                regional_performances=regional_performances,
                sector_performances=sector_performances,
                diversification_metrics=diversification_metrics,
                rebalance_recommendations=rebalance_recommendations,
                performance_summary=self._generate_performance_summary(
                    monthly_return_pct, regional_performances, sector_performances
                ),
                diversification_summary=self._generate_diversification_summary(diversification_metrics),
                rebalance_summary=self._generate_rebalance_summary(rebalance_recommendations),
                risk_assessment=self._generate_risk_assessment(
                    diversification_metrics, regional_performances, sector_performances
                ),
                long_term_outlook=self._generate_long_term_outlook(
                    regional_performances, sector_performances, analysis_mode
                )
            )
            
            # AI分析で追加インサイトを取得（オプション）
            if enable_ai_analysis:
                try:
                    ai_insights = self._get_ai_insights(result, analysis_mode)
                    result.long_term_outlook += f"\n\nAI分析:\n{ai_insights}"
                except Exception as e:
                    self.logger.warning(f"AI分析失敗: {e}")
            
            # 実行時間を記録
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            self.logger.info(f"月次分析完了: 実行時間 {execution_time:.2f}秒")
            return result
            
        except Exception as e:
            self.logger.error(f"月次分析中にエラーが発生: {e}")
            raise
    
    def _get_monthly_historical_data(self, 
                                   symbols: List[str], 
                                   start_date: datetime, 
                                   end_date: datetime) -> Dict[str, List[float]]:
        """月間履歴データを取得"""
        monthly_data = {}
        
        for symbol in symbols:
            try:
                historical_result = self.historical_manager.get_historical_data(
                    symbol, start_date, end_date
                )
                
                if historical_result.success and not historical_result.dataset.is_empty:
                    # 日次終値を取得
                    prices = [data.close for data in historical_result.dataset.price_data]
                    monthly_data[symbol] = prices
                else:
                    self.logger.warning(f"履歴データ取得失敗: {symbol}")
                    monthly_data[symbol] = []
                    
            except Exception as e:
                self.logger.error(f"履歴データ取得エラー ({symbol}): {e}")
                monthly_data[symbol] = []
        
        return monthly_data
    
    def _calculate_portfolio_monthly_return(self,
                                          holdings: List[StockConfig],
                                          current_data: Dict[str, StockData],
                                          monthly_data: Dict[str, List[float]]) -> Tuple[float, float]:
        """ポートフォリオ月間リターンを計算"""
        current_value = 0
        month_start_value = 0
        
        for holding in holdings:
            symbol = holding.symbol
            current_stock_data = current_data.get(symbol)
            prices = monthly_data.get(symbol, [])
            
            if not current_stock_data or len(prices) < 2:
                continue
            
            current_price = current_stock_data.current_price
            month_start_price = prices[0]
            
            current_value += current_price * holding.quantity
            month_start_value += month_start_price * holding.quantity
        
        monthly_return = current_value - month_start_value
        monthly_return_pct = (monthly_return / month_start_value) * 100 if month_start_value > 0 else 0
        
        return monthly_return, monthly_return_pct
    
    def _analyze_regional_performance(self,
                                    holdings: List[StockConfig],
                                    current_data: Dict[str, StockData],
                                    monthly_data: Dict[str, List[float]],
                                    total_portfolio_value: float) -> List[RegionalPerformance]:
        """地域別パフォーマンスを分析"""
        regional_data = {}
        
        # 地域別にデータを集約
        for holding in holdings:
            symbol = holding.symbol
            region = self.SYMBOL_TO_REGION.get(symbol, RegionType.US)  # デフォルトは米国
            
            current_stock_data = current_data.get(symbol)
            prices = monthly_data.get(symbol, [])
            
            if not current_stock_data or len(prices) < 2:
                continue
            
            current_price = current_stock_data.current_price
            month_start_price = prices[0]
            holding_value = current_price * holding.quantity
            
            if region not in regional_data:
                regional_data[region] = {
                    'holdings': [],
                    'total_value': 0,
                    'monthly_returns': [],
                    'volatilities': []
                }
            
            # 月間リターン計算
            monthly_return = ((current_price / month_start_price) - 1) * 100 if month_start_price > 0 else 0
            
            # ボラティリティ計算
            if len(prices) >= 2:
                daily_returns = [(prices[i] / prices[i-1] - 1) * 100 
                               for i in range(1, len(prices))]
                volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
            else:
                volatility = 0
            
            regional_data[region]['holdings'].append(holding)
            regional_data[region]['total_value'] += holding_value
            regional_data[region]['monthly_returns'].append(monthly_return)
            regional_data[region]['volatilities'].append(volatility)
        
        # 地域別パフォーマンスオブジェクト作成
        performances = []
        for region, data in regional_data.items():
            allocation_pct = (data['total_value'] / total_portfolio_value) * 100 if total_portfolio_value > 0 else 0
            avg_return = statistics.mean(data['monthly_returns']) if data['monthly_returns'] else 0
            avg_volatility = statistics.mean(data['volatilities']) if data['volatilities'] else 0
            sharpe_ratio = avg_return / avg_volatility if avg_volatility > 0 else 0
            
            performance = RegionalPerformance(
                region=region,
                allocation_percentage=allocation_pct,
                monthly_return=data['total_value'] * (avg_return / 100),
                monthly_return_pct=avg_return,
                volatility=avg_volatility,
                sharpe_ratio=sharpe_ratio,
                holdings_count=len(data['holdings']),
                total_value=data['total_value'],
                contribution_to_portfolio=allocation_pct * avg_return / 100
            )
            performances.append(performance)
        
        return performances
    
    def _analyze_sector_performance(self,
                                  holdings: List[StockConfig],
                                  current_data: Dict[str, StockData],
                                  monthly_data: Dict[str, List[float]],
                                  total_portfolio_value: float) -> List[SectorPerformance]:
        """業種別パフォーマンスを分析"""
        sector_data = {}
        
        # 業種別にデータを集約
        for holding in holdings:
            symbol = holding.symbol
            sector = self.SYMBOL_TO_SECTOR.get(symbol, SectorType.TECHNOLOGY)  # デフォルトはテクノロジー
            
            current_stock_data = current_data.get(symbol)
            prices = monthly_data.get(symbol, [])
            
            if not current_stock_data or len(prices) < 2:
                continue
            
            current_price = current_stock_data.current_price
            month_start_price = prices[0]
            holding_value = current_price * holding.quantity
            
            if sector not in sector_data:
                sector_data[sector] = {
                    'holdings': [],
                    'total_value': 0,
                    'monthly_returns': [],
                    'volatilities': []
                }
            
            # 月間リターン計算
            monthly_return = ((current_price / month_start_price) - 1) * 100 if month_start_price > 0 else 0
            
            # ボラティリティ計算
            if len(prices) >= 2:
                daily_returns = [(prices[i] / prices[i-1] - 1) * 100 
                               for i in range(1, len(prices))]
                volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
            else:
                volatility = 0
            
            sector_data[sector]['holdings'].append(holding)
            sector_data[sector]['total_value'] += holding_value
            sector_data[sector]['monthly_returns'].append(monthly_return)
            sector_data[sector]['volatilities'].append(volatility)
        
        # 業種別パフォーマンスオブジェクト作成
        performances = []
        for sector, data in sector_data.items():
            allocation_pct = (data['total_value'] / total_portfolio_value) * 100 if total_portfolio_value > 0 else 0
            avg_return = statistics.mean(data['monthly_returns']) if data['monthly_returns'] else 0
            avg_volatility = statistics.mean(data['volatilities']) if data['volatilities'] else 0
            sharpe_ratio = avg_return / avg_volatility if avg_volatility > 0 else 0
            
            performance = SectorPerformance(
                sector=sector,
                allocation_percentage=allocation_pct,
                monthly_return=data['total_value'] * (avg_return / 100),
                monthly_return_pct=avg_return,
                volatility=avg_volatility,
                sharpe_ratio=sharpe_ratio,
                holdings_count=len(data['holdings']),
                total_value=data['total_value'],
                contribution_to_portfolio=allocation_pct * avg_return / 100
            )
            performances.append(performance)
        
        return performances
    
    def _calculate_diversification_metrics(self,
                                         holdings: List[StockConfig],
                                         current_data: Dict[str, StockData],
                                         total_portfolio_value: float) -> DiversificationMetrics:
        """分散投資指標を計算"""
        # 各銘柄の重み計算
        weights = []
        values = []
        
        for holding in holdings:
            current_stock_data = current_data.get(holding.symbol)
            if current_stock_data:
                value = current_stock_data.current_price * holding.quantity
                weight = value / total_portfolio_value if total_portfolio_value > 0 else 0
                weights.append(weight)
                values.append(value)
        
        if not weights:
            return DiversificationMetrics(
                herfindahl_index=1.0,
                effective_holdings=1,
                region_diversification=DiversificationLevel.VERY_POOR,
                sector_diversification=DiversificationLevel.VERY_POOR,
                concentration_risk_score=100,
                top_holdings_percentage=100,
                correlation_score=1.0
            )
        
        # ハーフィンダール指数（集中度）
        herfindahl_index = sum(w ** 2 for w in weights)
        
        # 実効保有銘柄数
        effective_holdings = 1 / herfindahl_index if herfindahl_index > 0 else 1
        
        # 上位銘柄の占有率（上位3銘柄）
        sorted_weights = sorted(weights, reverse=True)
        top_holdings_percentage = sum(sorted_weights[:3]) * 100
        
        # 地域・業種の分散レベル評価
        unique_regions = len(set(self.SYMBOL_TO_REGION.get(h.symbol, RegionType.US) for h in holdings))
        unique_sectors = len(set(self.SYMBOL_TO_SECTOR.get(h.symbol, SectorType.TECHNOLOGY) for h in holdings))
        
        region_diversification = self._evaluate_diversification_level(unique_regions, "region")
        sector_diversification = self._evaluate_diversification_level(unique_sectors, "sector")
        
        # 集中リスクスコア（0-100、高いほどリスク大）
        concentration_risk_score = herfindahl_index * 100
        
        # 相関スコア（簡略化）
        correlation_score = min(1.0, max(0.0, (len(holdings) - effective_holdings) / len(holdings)))
        
        return DiversificationMetrics(
            herfindahl_index=herfindahl_index,
            effective_holdings=effective_holdings,
            region_diversification=region_diversification,
            sector_diversification=sector_diversification,
            concentration_risk_score=concentration_risk_score,
            top_holdings_percentage=top_holdings_percentage,
            correlation_score=correlation_score
        )
    
    def _evaluate_diversification_level(self, count: int, category: str) -> DiversificationLevel:
        """分散レベルを評価"""
        if category == "region":
            if count >= 4:
                return DiversificationLevel.EXCELLENT
            elif count >= 3:
                return DiversificationLevel.GOOD
            elif count >= 2:
                return DiversificationLevel.MODERATE
            else:
                return DiversificationLevel.POOR
        else:  # sector
            if count >= 8:
                return DiversificationLevel.EXCELLENT
            elif count >= 6:
                return DiversificationLevel.GOOD
            elif count >= 4:
                return DiversificationLevel.MODERATE
            elif count >= 2:
                return DiversificationLevel.POOR
            else:
                return DiversificationLevel.VERY_POOR
    
    def _generate_rebalance_recommendations(self,
                                          regional_performances: List[RegionalPerformance],
                                          sector_performances: List[SectorPerformance],
                                          diversification_metrics: DiversificationMetrics,
                                          analysis_mode: AnalysisMode) -> List[RebalanceRecommendation]:
        """リバランス推奨を生成"""
        recommendations = []
        
        # 地域別リバランス推奨
        target_regional_allocation = self._get_target_regional_allocation(analysis_mode)
        for region_perf in regional_performances:
            target = target_regional_allocation.get(region_perf.region, 25.0)  # デフォルト25%
            current = region_perf.allocation_percentage
            diff = target - current
            
            if abs(diff) > 5.0:  # 5%以上の差がある場合
                rec_type = "increase" if diff > 0 else "decrease"
                priority = min(10, max(1, int(abs(diff) / 2)))
                
                recommendation = RebalanceRecommendation(
                    type=rec_type,
                    category="region",
                    name=region_perf.region.display_name,
                    current_allocation=current,
                    target_allocation=target,
                    recommended_change=abs(diff),
                    reasoning=f"目標配分{target:.1f}%に対して{abs(diff):.1f}%の{'過少' if diff > 0 else '過多'}",
                    priority=priority
                )
                recommendations.append(recommendation)
        
        # 業種別リバランス推奨
        target_sector_allocation = self._get_target_sector_allocation(analysis_mode)
        for sector_perf in sector_performances:
            target = target_sector_allocation.get(sector_perf.sector, 15.0)  # デフォルト15%
            current = sector_perf.allocation_percentage
            diff = target - current
            
            if abs(diff) > 10.0:  # 10%以上の差がある場合
                rec_type = "increase" if diff > 0 else "decrease"
                priority = min(10, max(1, int(abs(diff) / 3)))
                
                recommendation = RebalanceRecommendation(
                    type=rec_type,
                    category="sector",
                    name=sector_perf.sector.display_name,
                    current_allocation=current,
                    target_allocation=target,
                    recommended_change=abs(diff),
                    reasoning=f"目標配分{target:.1f}%に対して{abs(diff):.1f}%の{'過少' if diff > 0 else '過多'}",
                    priority=priority
                )
                recommendations.append(recommendation)
        
        # 集中リスク対応
        if diversification_metrics.concentration_risk_score > 50:
            recommendation = RebalanceRecommendation(
                type="decrease",
                category="concentration",
                name="上位銘柄",
                current_allocation=diversification_metrics.top_holdings_percentage,
                target_allocation=40.0,
                recommended_change=diversification_metrics.top_holdings_percentage - 40.0,
                reasoning="上位銘柄への集中度が高すぎるため分散を推奨",
                priority=8
            )
            recommendations.append(recommendation)
        
        # 優先度順にソート
        recommendations.sort(key=lambda x: x.priority, reverse=True)
        
        return recommendations
    
    def _get_target_regional_allocation(self, analysis_mode: AnalysisMode) -> Dict[RegionType, float]:
        """分析モード別の目標地域配分"""
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            return {
                RegionType.US: 40.0,
                RegionType.DEVELOPED: 30.0,
                RegionType.ASIA: 20.0,
                RegionType.EMERGING: 10.0
            }
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            return {
                RegionType.US: 50.0,
                RegionType.ASIA: 25.0,
                RegionType.EMERGING: 20.0,
                RegionType.DEVELOPED: 5.0
            }
        else:  # BALANCED
            return {
                RegionType.US: 45.0,
                RegionType.DEVELOPED: 25.0,
                RegionType.ASIA: 20.0,
                RegionType.EMERGING: 10.0
            }
    
    def _get_target_sector_allocation(self, analysis_mode: AnalysisMode) -> Dict[SectorType, float]:
        """分析モード別の目標業種配分"""
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            return {
                SectorType.TECHNOLOGY: 20.0,
                SectorType.HEALTHCARE: 15.0,
                SectorType.FINANCIALS: 15.0,
                SectorType.CONSUMER_STAPLES: 15.0,
                SectorType.UTILITIES: 10.0,
                SectorType.INDUSTRIALS: 10.0,
                SectorType.MATERIALS: 5.0,
                SectorType.ENERGY: 5.0,
                SectorType.REAL_ESTATE: 5.0
            }
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            return {
                SectorType.TECHNOLOGY: 35.0,
                SectorType.HEALTHCARE: 15.0,
                SectorType.CONSUMER_DISCRETIONARY: 15.0,
                SectorType.COMMUNICATIONS: 10.0,
                SectorType.FINANCIALS: 10.0,
                SectorType.INDUSTRIALS: 10.0,
                SectorType.ENERGY: 5.0
            }
        else:  # BALANCED
            return {
                SectorType.TECHNOLOGY: 25.0,
                SectorType.HEALTHCARE: 15.0,
                SectorType.FINANCIALS: 12.0,
                SectorType.CONSUMER_DISCRETIONARY: 12.0,
                SectorType.CONSUMER_STAPLES: 10.0,
                SectorType.INDUSTRIALS: 10.0,
                SectorType.COMMUNICATIONS: 8.0,
                SectorType.UTILITIES: 4.0,
                SectorType.MATERIALS: 4.0
            }
    
    def _generate_performance_summary(self,
                                    monthly_return_pct: float,
                                    regional_performances: List[RegionalPerformance],
                                    sector_performances: List[SectorPerformance]) -> str:
        """パフォーマンスサマリーを生成"""
        best_region = max(regional_performances, key=lambda x: x.monthly_return_pct, default=None)
        worst_region = min(regional_performances, key=lambda x: x.monthly_return_pct, default=None)
        best_sector = max(sector_performances, key=lambda x: x.monthly_return_pct, default=None)
        worst_sector = min(sector_performances, key=lambda x: x.monthly_return_pct, default=None)
        
        summary = f"""月次パフォーマンス概要：
• ポートフォリオ全体: {monthly_return_pct:.2f}%
• 地域別最高: {best_region.region.display_name} ({best_region.monthly_return_pct:.2f}%)
• 地域別最低: {worst_region.region.display_name} ({worst_region.monthly_return_pct:.2f}%)
• 業種別最高: {best_sector.sector.display_name} ({best_sector.monthly_return_pct:.2f}%)
• 業種別最低: {worst_sector.sector.display_name} ({worst_sector.monthly_return_pct:.2f}%)"""
        
        return summary
    
    def _generate_diversification_summary(self, metrics: DiversificationMetrics) -> str:
        """分散投資サマリーを生成"""
        return f"""分散投資状況：
• 実効保有銘柄数: {metrics.effective_holdings:.1f}銘柄
• 地域分散レベル: {metrics.region_diversification.display_name}
• 業種分散レベル: {metrics.sector_diversification.display_name}
• 集中リスクスコア: {metrics.concentration_risk_score:.1f}/100
• 上位3銘柄占有率: {metrics.top_holdings_percentage:.1f}%
• 銘柄間相関スコア: {metrics.correlation_score:.2f}"""
    
    def _generate_rebalance_summary(self, recommendations: List[RebalanceRecommendation]) -> str:
        """リバランスサマリーを生成"""
        if not recommendations:
            return "現在のアロケーションは適切です。大幅なリバランスは不要です。"
        
        high_priority = [r for r in recommendations if r.priority >= 7]
        
        if high_priority:
            summary = f"重要なリバランス推奨が{len(high_priority)}件あります：\n"
            for rec in high_priority[:3]:  # 上位3件
                summary += f"• {rec.name}: {rec.current_allocation:.1f}% → {rec.target_allocation:.1f}% ({rec.type})\n"
        else:
            summary = f"軽微なリバランス推奨が{len(recommendations)}件あります。"
        
        return summary
    
    def _generate_risk_assessment(self,
                                diversification_metrics: DiversificationMetrics,
                                regional_performances: List[RegionalPerformance],
                                sector_performances: List[SectorPerformance]) -> str:
        """リスク評価を生成"""
        risk_factors = []
        
        # 集中リスク
        if diversification_metrics.concentration_risk_score > 70:
            risk_factors.append("高い集中リスク")
        
        # 地域・業種分散リスク
        if diversification_metrics.region_diversification in [DiversificationLevel.POOR, DiversificationLevel.VERY_POOR]:
            risk_factors.append("地域分散不足")
        
        if diversification_metrics.sector_diversification in [DiversificationLevel.POOR, DiversificationLevel.VERY_POOR]:
            risk_factors.append("業種分散不足")
        
        # 相関リスク
        if diversification_metrics.correlation_score > 0.7:
            risk_factors.append("銘柄間高相関")
        
        # 地域・業種の偏り
        max_regional_allocation = max(p.allocation_percentage for p in regional_performances)
        max_sector_allocation = max(p.allocation_percentage for p in sector_performances)
        
        if max_regional_allocation > 60:
            risk_factors.append("地域への過度な集中")
        
        if max_sector_allocation > 40:
            risk_factors.append("特定業種への過度な集中")
        
        if not risk_factors:
            return "現在、重大なリスク要因は検出されていません。分散投資が適切に行われています。"
        else:
            return "検出されたリスク要因: " + ", ".join(risk_factors)
    
    def _generate_long_term_outlook(self,
                                  regional_performances: List[RegionalPerformance],
                                  sector_performances: List[SectorPerformance],
                                  analysis_mode: AnalysisMode) -> str:
        """長期見通しを生成"""
        outlook = f"""長期投資戦略の提言：

地域配分戦略:
• {analysis_mode.value}モードに基づく地域分散の最適化
• 新興国への適度なエクスポージャー維持
• 地政学リスクを考慮した分散投資

業種配分戦略:
• テクノロジーセクターの長期成長性を重視
• ディフェンシブセクターでのリスク軽減
• ESG要因を考慮した持続可能な投資

リバランス頻度:
• 四半期ごとの配分見直し
• 年1-2回の大幅リバランス実施
• 市場変動時の機動的対応"""
        
        return outlook
    
    def _get_ai_insights(self, result: MonthlyAnalysisResult, analysis_mode: AnalysisMode) -> str:
        """AI分析でインサイトを取得"""
        try:
            # 簡略化されたAI分析
            ai_response = self.gemini_service.analyze_portfolio(
                [], [], AnalysisType.MONTHLY, analysis_mode
            )
            
            if ai_response.success and ai_response.analysis_result:
                return ai_response.analysis_result.summary
            else:
                return "AI分析を実行できませんでした。"
                
        except Exception as e:
            self.logger.error(f"AI分析エラー: {e}")
            return "AI分析中にエラーが発生しました。"


# Mock クラス（現在のデータ取得時にエラーハンドリング用）
class Mock:
    def __init__(self):
        self.current_price = 0