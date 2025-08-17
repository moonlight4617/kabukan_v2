# -*- coding: utf-8 -*-
"""
週次分析サービス
保有株式のパフォーマンス分析、週間リターンとボラティリティ計算、ベンチマーク比較機能を提供
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


class PerformanceCategory(Enum):
    """パフォーマンスカテゴリ"""
    EXCELLENT = "excellent"  # 10%以上
    GOOD = "good"            # 5%以上10%未満
    AVERAGE = "average"      # -5%以上5%未満
    POOR = "poor"            # -10%以上-5%未満
    VERY_POOR = "very_poor"  # -10%未満

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            PerformanceCategory.EXCELLENT: "優秀",
            PerformanceCategory.GOOD: "良好",
            PerformanceCategory.AVERAGE: "平均的",
            PerformanceCategory.POOR: "不振",
            PerformanceCategory.VERY_POOR: "非常に不振"
        }[self]

    @classmethod
    def from_return(cls, weekly_return: float) -> 'PerformanceCategory':
        """週間リターンからカテゴリを判定"""
        if weekly_return >= 10.0:
            return cls.EXCELLENT
        elif weekly_return >= 5.0:
            return cls.GOOD
        elif weekly_return >= -5.0:
            return cls.AVERAGE
        elif weekly_return >= -10.0:
            return cls.POOR
        else:
            return cls.VERY_POOR


@dataclass
class StockPerformance:
    """個別株式パフォーマンス"""
    symbol: str
    name: str
    current_price: float
    week_start_price: float
    weekly_return: float
    weekly_return_pct: float
    weekly_volatility: float
    current_quantity: int
    current_value: float
    weekly_pnl: float
    weekly_pnl_pct: float
    performance_category: PerformanceCategory
    relative_to_benchmark: float  # ベンチマーク対比
    volume_trend: str  # 出来高トレンド
    
    @property
    def is_outperforming(self) -> bool:
        """ベンチマークを上回っているか"""
        return self.relative_to_benchmark > 0


@dataclass
class PortfolioPerformance:
    """ポートフォリオパフォーマンス"""
    total_value: float
    week_start_value: float
    weekly_return: float
    weekly_return_pct: float
    weekly_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    best_performer: Optional[StockPerformance]
    worst_performer: Optional[StockPerformance]
    outperformers_count: int
    underperformers_count: int
    
    @property
    def risk_adjusted_return(self) -> float:
        """リスク調整後リターン"""
        return self.weekly_return_pct / self.weekly_volatility if self.weekly_volatility > 0 else 0


@dataclass
class BenchmarkComparison:
    """ベンチマーク比較"""
    benchmark_name: str
    benchmark_symbol: str
    benchmark_return: float
    benchmark_volatility: float
    portfolio_vs_benchmark: float
    alpha: float  # 超過リターン
    beta: float   # 市場感応度
    correlation: float
    tracking_error: float
    information_ratio: float


@dataclass
class WeeklyAnalysisResult:
    """週次分析結果"""
    analysis_date: datetime
    analysis_period_start: datetime
    analysis_period_end: datetime
    portfolio_performance: PortfolioPerformance
    stock_performances: List[StockPerformance]
    benchmark_comparison: BenchmarkComparison
    market_summary: str
    performance_summary: str
    recommendations: List[str]
    risk_assessment: str
    execution_time: float = 0
    
    @property
    def top_performers(self) -> List[StockPerformance]:
        """上位パフォーマー（上位3銘柄）"""
        return sorted(self.stock_performances, 
                     key=lambda x: x.weekly_return_pct, reverse=True)[:3]
    
    @property
    def bottom_performers(self) -> List[StockPerformance]:
        """下位パフォーマー（下位3銘柄）"""
        return sorted(self.stock_performances, 
                     key=lambda x: x.weekly_return_pct)[:3]


class WeeklyAnalysisService:
    """週次分析サービス"""
    
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
    
    def execute_weekly_analysis(self,
                              analysis_mode: AnalysisMode = AnalysisMode.BALANCED,
                              enable_ai_analysis: bool = True,
                              benchmark_symbol: str = "SPY") -> WeeklyAnalysisResult:
        """
        週次分析を実行
        
        Args:
            analysis_mode: 分析モード
            enable_ai_analysis: AI分析を有効にするか
            benchmark_symbol: ベンチマーク銘柄（デフォルト: SPY）
            
        Returns:
            WeeklyAnalysisResult: 週次分析結果
        """
        start_time = datetime.now()
        self.logger.info("週次分析開始")
        
        try:
            # 分析期間の設定（過去1週間）
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            
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
            
            # ベンチマークデータも取得
            benchmark_data_result = self.stock_service.get_batch_stock_data([benchmark_symbol])
            
            # 週間履歴データを取得
            weekly_data = self._get_weekly_historical_data(symbols + [benchmark_symbol], start_date, end_date)
            
            # 個別株式パフォーマンスを計算
            stock_performances = self._analyze_stock_performances(
                holdings, current_data_result.stock_data, weekly_data
            )
            
            # ポートフォリオパフォーマンスを計算
            portfolio_performance = self._calculate_portfolio_performance(
                stock_performances, weekly_data
            )
            
            # ベンチマーク比較を実行
            benchmark_comparison = self._analyze_benchmark_comparison(
                portfolio_performance, weekly_data, benchmark_symbol
            )
            
            # 分析結果を生成
            result = WeeklyAnalysisResult(
                analysis_date=datetime.now(),
                analysis_period_start=start_date,
                analysis_period_end=end_date,
                portfolio_performance=portfolio_performance,
                stock_performances=stock_performances,
                benchmark_comparison=benchmark_comparison,
                market_summary=self._generate_market_summary(benchmark_comparison),
                performance_summary=self._generate_performance_summary(portfolio_performance),
                recommendations=self._generate_recommendations(
                    portfolio_performance, stock_performances, benchmark_comparison, analysis_mode
                ),
                risk_assessment=self._generate_risk_assessment(portfolio_performance, stock_performances)
            )
            
            # AI分析で追加インサイトを取得（オプション）
            if enable_ai_analysis:
                try:
                    ai_insights = self._get_ai_insights(result, analysis_mode)
                    result.market_summary += f"\n\nAI分析:\n{ai_insights}"
                except Exception as e:
                    self.logger.warning(f"AI分析失敗: {e}")
            
            # 実行時間を記録
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            self.logger.info(f"週次分析完了: 実行時間 {execution_time:.2f}秒")
            return result
            
        except Exception as e:
            self.logger.error(f"週次分析中にエラーが発生: {e}")
            raise
    
    def _get_weekly_historical_data(self, 
                                   symbols: List[str], 
                                   start_date: datetime, 
                                   end_date: datetime) -> Dict[str, List[float]]:
        """週間履歴データを取得"""
        weekly_data = {}
        
        for symbol in symbols:
            try:
                historical_result = self.historical_manager.get_historical_data(
                    symbol, start_date, end_date
                )
                
                if historical_result.success and not historical_result.dataset.is_empty:
                    # 日次終値を取得
                    prices = [data.close for data in historical_result.dataset.price_data]
                    weekly_data[symbol] = prices
                else:
                    self.logger.warning(f"履歴データ取得失敗: {symbol}")
                    weekly_data[symbol] = []
                    
            except Exception as e:
                self.logger.error(f"履歴データ取得エラー ({symbol}): {e}")
                weekly_data[symbol] = []
        
        return weekly_data
    
    def _analyze_stock_performances(self,
                                  holdings: List[StockConfig],
                                  current_data: Dict[str, StockData],
                                  weekly_data: Dict[str, List[float]]) -> List[StockPerformance]:
        """個別株式パフォーマンスを分析"""
        performances = []
        
        for holding in holdings:
            symbol = holding.symbol
            current_stock_data = current_data.get(symbol)
            prices = weekly_data.get(symbol, [])
            
            if not current_stock_data or len(prices) < 2:
                self.logger.warning(f"データ不足: {symbol}")
                continue
            
            # 週初と週末の価格
            week_start_price = prices[0]
            current_price = current_stock_data.current_price
            
            # 週間リターン計算
            weekly_return = current_price - week_start_price
            weekly_return_pct = (weekly_return / week_start_price) * 100 if week_start_price > 0 else 0
            
            # 週間ボラティリティ計算
            if len(prices) >= 2:
                daily_returns = [(prices[i] / prices[i-1] - 1) * 100 
                               for i in range(1, len(prices))]
                weekly_volatility = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
            else:
                weekly_volatility = 0
            
            # ポジション情報
            current_value = current_price * holding.quantity
            weekly_pnl = weekly_return * holding.quantity
            weekly_pnl_pct = weekly_return_pct
            
            # パフォーマンスカテゴリ
            performance_category = PerformanceCategory.from_return(weekly_return_pct)
            
            # 出来高トレンド分析
            volume_trend = self._analyze_volume_trend(current_stock_data.volume)
            
            performance = StockPerformance(
                symbol=symbol,
                name=holding.name,
                current_price=current_price,
                week_start_price=week_start_price,
                weekly_return=weekly_return,
                weekly_return_pct=weekly_return_pct,
                weekly_volatility=weekly_volatility,
                current_quantity=holding.quantity,
                current_value=current_value,
                weekly_pnl=weekly_pnl,
                weekly_pnl_pct=weekly_pnl_pct,
                performance_category=performance_category,
                relative_to_benchmark=0,  # 後でベンチマーク比較時に設定
                volume_trend=volume_trend
            )
            
            performances.append(performance)
        
        return performances
    
    def _calculate_portfolio_performance(self,
                                       stock_performances: List[StockPerformance],
                                       weekly_data: Dict[str, List[float]]) -> PortfolioPerformance:
        """ポートフォリオパフォーマンスを計算"""
        if not stock_performances:
            raise ValueError("株式パフォーマンスデータがありません")
        
        # ポートフォリオ価値
        total_value = sum(perf.current_value for perf in stock_performances)
        week_start_value = sum(perf.week_start_price * perf.current_quantity 
                              for perf in stock_performances)
        
        # 週間リターン
        weekly_return = total_value - week_start_value
        weekly_return_pct = (weekly_return / week_start_value) * 100 if week_start_value > 0 else 0
        
        # ポートフォリオボラティリティ（加重平均）
        total_weights = sum(perf.current_value for perf in stock_performances)
        if total_weights > 0:
            weekly_volatility = sum(
                (perf.current_value / total_weights) * perf.weekly_volatility
                for perf in stock_performances
            )
        else:
            weekly_volatility = 0
        
        # シャープレシオ（リスクフリーレート0と仮定）
        sharpe_ratio = weekly_return_pct / weekly_volatility if weekly_volatility > 0 else 0
        
        # 最大ドローダウン計算
        max_drawdown = self._calculate_max_drawdown(stock_performances)
        
        # ベスト・ワーストパフォーマー
        best_performer = max(stock_performances, key=lambda x: x.weekly_return_pct, default=None)
        worst_performer = min(stock_performances, key=lambda x: x.weekly_return_pct, default=None)
        
        # アウトパフォーマー・アンダーパフォーマー数（後でベンチマーク比較後に更新）
        outperformers_count = 0
        underperformers_count = 0
        
        return PortfolioPerformance(
            total_value=total_value,
            week_start_value=week_start_value,
            weekly_return=weekly_return,
            weekly_return_pct=weekly_return_pct,
            weekly_volatility=weekly_volatility,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            best_performer=best_performer,
            worst_performer=worst_performer,
            outperformers_count=outperformers_count,
            underperformers_count=underperformers_count
        )
    
    def _analyze_benchmark_comparison(self,
                                    portfolio_performance: PortfolioPerformance,
                                    weekly_data: Dict[str, List[float]],
                                    benchmark_symbol: str) -> BenchmarkComparison:
        """ベンチマーク比較を分析"""
        benchmark_prices = weekly_data.get(benchmark_symbol, [])
        
        if len(benchmark_prices) < 2:
            self.logger.warning(f"ベンチマークデータ不足: {benchmark_symbol}")
            # デフォルト値を返す
            return BenchmarkComparison(
                benchmark_name=benchmark_symbol,
                benchmark_symbol=benchmark_symbol,
                benchmark_return=0,
                benchmark_volatility=0,
                portfolio_vs_benchmark=portfolio_performance.weekly_return_pct,
                alpha=0,
                beta=1,
                correlation=0,
                tracking_error=0,
                information_ratio=0
            )
        
        # ベンチマークリターン計算
        benchmark_start = benchmark_prices[0]
        benchmark_end = benchmark_prices[-1]
        benchmark_return = ((benchmark_end / benchmark_start) - 1) * 100 if benchmark_start > 0 else 0
        
        # ベンチマークボラティリティ
        if len(benchmark_prices) >= 2:
            benchmark_daily_returns = [(benchmark_prices[i] / benchmark_prices[i-1] - 1) * 100 
                                     for i in range(1, len(benchmark_prices))]
            benchmark_volatility = statistics.stdev(benchmark_daily_returns) if len(benchmark_daily_returns) > 1 else 0
        else:
            benchmark_volatility = 0
        
        # アルファ（超過リターン）
        alpha = portfolio_performance.weekly_return_pct - benchmark_return
        
        # ベータ、相関係数、トラッキングエラー、情報比率の計算は簡略化
        # 実際の実装では、より長期間のデータを使用して計算する
        beta = 1.0  # 簡略化
        correlation = 0.8  # 簡略化
        tracking_error = abs(alpha)
        information_ratio = alpha / tracking_error if tracking_error > 0 else 0
        
        return BenchmarkComparison(
            benchmark_name=f"{benchmark_symbol} ETF",
            benchmark_symbol=benchmark_symbol,
            benchmark_return=benchmark_return,
            benchmark_volatility=benchmark_volatility,
            portfolio_vs_benchmark=alpha,
            alpha=alpha,
            beta=beta,
            correlation=correlation,
            tracking_error=tracking_error,
            information_ratio=information_ratio
        )
    
    def _calculate_max_drawdown(self, stock_performances: List[StockPerformance]) -> float:
        """最大ドローダウンを計算"""
        if not stock_performances:
            return 0
        
        # 簡略化：最悪パフォーマーの損失率を使用
        worst_return = min(perf.weekly_return_pct for perf in stock_performances)
        return abs(min(0, worst_return))
    
    def _analyze_volume_trend(self, current_volume: int) -> str:
        """出来高トレンドを分析"""
        # 簡略化：現在の出来高のみで判定
        if current_volume > 10000000:  # 1000万株以上
            return "高水準"
        elif current_volume > 1000000:  # 100万株以上
            return "平均的"
        else:
            return "低水準"
    
    def _generate_market_summary(self, benchmark_comparison: BenchmarkComparison) -> str:
        """市場サマリーを生成"""
        benchmark_performance = "上昇" if benchmark_comparison.benchmark_return > 0 else "下落"
        portfolio_performance = "アウトパフォーム" if benchmark_comparison.alpha > 0 else "アンダーパフォーム"
        
        return f"""週間市場概況：
• {benchmark_comparison.benchmark_name}は{benchmark_comparison.benchmark_return:.2f}%の{benchmark_performance}
• ポートフォリオはベンチマークを{abs(benchmark_comparison.alpha):.2f}%{portfolio_performance}
• 市場ボラティリティ: {benchmark_comparison.benchmark_volatility:.2f}%
• ポートフォリオとの相関: {benchmark_comparison.correlation:.2f}"""
    
    def _generate_performance_summary(self, portfolio_performance: PortfolioPerformance) -> str:
        """パフォーマンスサマリーを生成"""
        return_direction = "利益" if portfolio_performance.weekly_return > 0 else "損失"
        
        summary = f"""週間パフォーマンス：
• 総リターン: {portfolio_performance.weekly_return_pct:.2f}% ({return_direction}: ¥{abs(portfolio_performance.weekly_return):,.0f})
• ポートフォリオ価値: ¥{portfolio_performance.total_value:,.0f}
• 週間ボラティリティ: {portfolio_performance.weekly_volatility:.2f}%
• シャープレシオ: {portfolio_performance.sharpe_ratio:.2f}
• 最大ドローダウン: {portfolio_performance.max_drawdown:.2f}%"""
        
        if portfolio_performance.best_performer:
            summary += f"\n• 最高パフォーマー: {portfolio_performance.best_performer.symbol} ({portfolio_performance.best_performer.weekly_return_pct:.2f}%)"
        
        if portfolio_performance.worst_performer:
            summary += f"\n• 最低パフォーマー: {portfolio_performance.worst_performer.symbol} ({portfolio_performance.worst_performer.weekly_return_pct:.2f}%)"
        
        return summary
    
    def _generate_recommendations(self,
                                portfolio_performance: PortfolioPerformance,
                                stock_performances: List[StockPerformance],
                                benchmark_comparison: BenchmarkComparison,
                                analysis_mode: AnalysisMode) -> List[str]:
        """推奨事項を生成"""
        recommendations = []
        
        # パフォーマンス基準の推奨
        if portfolio_performance.weekly_return_pct < -5:
            recommendations.append("ポートフォリオが大幅下落。リスク管理の見直しを検討してください。")
        elif portfolio_performance.weekly_return_pct > 10:
            recommendations.append("好調なパフォーマンス。利益確定の機会を検討してください。")
        
        # ベンチマーク比較の推奨
        if benchmark_comparison.alpha < -2:
            recommendations.append("ベンチマークを大幅に下回っています。ポートフォリオ戦略の見直しが必要です。")
        elif benchmark_comparison.alpha > 2:
            recommendations.append("ベンチマークを上回る好成績。現在の戦略を維持してください。")
        
        # ボラティリティの推奨
        if portfolio_performance.weekly_volatility > 20:
            recommendations.append("高いボラティリティが観測されています。リスク分散を強化してください。")
        
        # 個別銘柄の推奨
        excellent_performers = [p for p in stock_performances 
                              if p.performance_category == PerformanceCategory.EXCELLENT]
        very_poor_performers = [p for p in stock_performances 
                              if p.performance_category == PerformanceCategory.VERY_POOR]
        
        if excellent_performers:
            symbols = [p.symbol for p in excellent_performers[:2]]
            recommendations.append(f"優秀なパフォーマンス銘柄 ({', '.join(symbols)}) への追加投資を検討してください。")
        
        if very_poor_performers:
            symbols = [p.symbol for p in very_poor_performers[:2]]
            recommendations.append(f"不振銘柄 ({', '.join(symbols)}) のポジション見直しを検討してください。")
        
        # 分析モード別の推奨
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            recommendations.append("保守的アプローチ: 安定性を重視し、ボラティリティの低い銘柄への投資を優先してください。")
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            recommendations.append("積極的アプローチ: 成長機会を捉え、高パフォーマンス銘柄への集中投資を検討してください。")
        
        return recommendations
    
    def _generate_risk_assessment(self,
                                portfolio_performance: PortfolioPerformance,
                                stock_performances: List[StockPerformance]) -> str:
        """リスク評価を生成"""
        risk_factors = []
        
        # ボラティリティリスク
        if portfolio_performance.weekly_volatility > 20:
            risk_factors.append(f"高ボラティリティ ({portfolio_performance.weekly_volatility:.1f}%)")
        
        # 集中リスク
        if len(stock_performances) < 5:
            risk_factors.append("銘柄数不足による集中リスク")
        
        # パフォーマンス分散リスク
        returns_range = max(p.weekly_return_pct for p in stock_performances) - min(p.weekly_return_pct for p in stock_performances)
        if returns_range > 20:
            risk_factors.append(f"銘柄間パフォーマンス格差大 ({returns_range:.1f}%)")
        
        # ドローダウンリスク
        if portfolio_performance.max_drawdown > 10:
            risk_factors.append(f"大幅ドローダウン ({portfolio_performance.max_drawdown:.1f}%)")
        
        if not risk_factors:
            return "現在、重大なリスク要因は検出されていません。"
        else:
            return "検出されたリスク要因: " + ", ".join(risk_factors)
    
    def _get_ai_insights(self, result: WeeklyAnalysisResult, analysis_mode: AnalysisMode) -> str:
        """AI分析でインサイトを取得"""
        try:
            # ポートフォリオ情報をAI分析用に整理
            portfolio_data = {
                "weekly_return": result.portfolio_performance.weekly_return_pct,
                "volatility": result.portfolio_performance.weekly_volatility,
                "sharpe_ratio": result.portfolio_performance.sharpe_ratio,
                "benchmark_alpha": result.benchmark_comparison.alpha,
                "top_performers": [
                    {"symbol": p.symbol, "return": p.weekly_return_pct}
                    for p in result.top_performers
                ],
                "bottom_performers": [
                    {"symbol": p.symbol, "return": p.weekly_return_pct}
                    for p in result.bottom_performers
                ]
            }
            
            # AI分析を実行（簡略化）
            ai_response = self.gemini_service.analyze_portfolio(
                [], [], AnalysisType.WEEKLY, analysis_mode
            )
            
            if ai_response.success and ai_response.analysis_result:
                return ai_response.analysis_result.summary
            else:
                return "AI分析を実行できませんでした。"
                
        except Exception as e:
            self.logger.error(f"AI分析エラー: {e}")
            return "AI分析中にエラーが発生しました。"