# -*- coding: utf-8 -*-
"""
分析プロンプト生成サービス
分析タイプ別のプロンプト生成、テクニカル指標を含むプロンプト作成、ポートフォリオコンテキストの統合機能を提供
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.models.data_models import StockData, StockConfig, WatchlistStock
from src.models.analysis_models import AnalysisType
from src.services.technical_analysis_service import TechnicalAnalysisResult, TrendDirection, SignalType
from src.services.gemini_service import AnalysisMode


logger = logging.getLogger(__name__)


class PromptTemplate(Enum):
    """プロンプトテンプレート種別"""
    STOCK_ANALYSIS = "stock_analysis"
    PORTFOLIO_ANALYSIS = "portfolio_analysis"
    WATCHLIST_ANALYSIS = "watchlist_analysis"
    MARKET_OVERVIEW = "market_overview"
    RISK_ASSESSMENT = "risk_assessment"
    REBALANCE_ADVICE = "rebalance_advice"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            PromptTemplate.STOCK_ANALYSIS: "個別株式分析",
            PromptTemplate.PORTFOLIO_ANALYSIS: "ポートフォリオ分析",
            PromptTemplate.WATCHLIST_ANALYSIS: "ウォッチリスト分析",
            PromptTemplate.MARKET_OVERVIEW: "市場概況",
            PromptTemplate.RISK_ASSESSMENT: "リスク評価",
            PromptTemplate.REBALANCE_ADVICE: "リバランス助言"
        }[self]


@dataclass
class PromptContext:
    """プロンプトコンテキスト"""
    analysis_type: AnalysisType
    analysis_mode: AnalysisMode
    template_type: PromptTemplate
    market_context: Dict[str, Any]
    user_preferences: Dict[str, Any]
    risk_tolerance: str
    investment_horizon: str
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "analysis_type": self.analysis_type.value,
            "analysis_mode": self.analysis_mode.value,
            "template_type": self.template_type.value,
            "market_context": self.market_context,
            "user_preferences": self.user_preferences,
            "risk_tolerance": self.risk_tolerance,
            "investment_horizon": self.investment_horizon
        }


@dataclass
class GeneratedPrompt:
    """生成されたプロンプト"""
    template_type: PromptTemplate
    prompt_text: str
    context_data: Dict[str, Any]
    technical_indicators: List[str]
    market_factors: List[str]
    instructions: List[str]
    output_format: str
    
    @property
    def full_prompt(self) -> str:
        """完全なプロンプト文字列"""
        return f"{self.prompt_text}\n\n出力形式:\n{self.output_format}"


class PromptGenerationService:
    """分析プロンプト生成サービス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialize_templates()
    
    def _initialize_templates(self):
        """プロンプトテンプレートを初期化"""
        self.base_templates = {
            PromptTemplate.STOCK_ANALYSIS: self._get_stock_analysis_template(),
            PromptTemplate.PORTFOLIO_ANALYSIS: self._get_portfolio_analysis_template(),
            PromptTemplate.WATCHLIST_ANALYSIS: self._get_watchlist_analysis_template(),
            PromptTemplate.MARKET_OVERVIEW: self._get_market_overview_template(),
            PromptTemplate.RISK_ASSESSMENT: self._get_risk_assessment_template(),
            PromptTemplate.REBALANCE_ADVICE: self._get_rebalance_advice_template()
        }
    
    def generate_stock_analysis_prompt(self,
                                     stock_data: StockData,
                                     technical_analysis: TechnicalAnalysisResult,
                                     analysis_type: AnalysisType,
                                     analysis_mode: AnalysisMode,
                                     portfolio_context: Optional[Dict[str, Any]] = None) -> GeneratedPrompt:
        """
        個別株式分析プロンプトを生成
        
        Args:
            stock_data: 株価データ
            technical_analysis: テクニカル分析結果
            analysis_type: 分析タイプ
            analysis_mode: 分析モード
            portfolio_context: ポートフォリオコンテキスト
            
        Returns:
            GeneratedPrompt: 生成されたプロンプト
        """
        context = PromptContext(
            analysis_type=analysis_type,
            analysis_mode=analysis_mode,
            template_type=PromptTemplate.STOCK_ANALYSIS,
            market_context=self._get_market_context(),
            user_preferences=self._get_user_preferences(analysis_mode),
            risk_tolerance=self._get_risk_tolerance(analysis_mode),
            investment_horizon=self._get_investment_horizon(analysis_type)
        )
        
        # テクニカル指標の文字列化
        technical_summary = self._format_technical_analysis(technical_analysis)
        
        # 株価データの文字列化
        stock_summary = self._format_stock_data(stock_data)
        
        # ポートフォリオコンテキストの統合
        portfolio_info = self._format_portfolio_context(portfolio_context) if portfolio_context else ""
        
        # プロンプト生成
        template = self.base_templates[PromptTemplate.STOCK_ANALYSIS]
        
        prompt_text = template.format(
            symbol=stock_data.symbol,
            analysis_type=analysis_type.value,
            analysis_mode=analysis_mode.value,
            stock_summary=stock_summary,
            technical_summary=technical_summary,
            portfolio_context=portfolio_info,
            risk_tolerance=context.risk_tolerance,
            investment_horizon=context.investment_horizon,
            market_context=self._format_market_context(context.market_context)
        )
        
        return GeneratedPrompt(
            template_type=PromptTemplate.STOCK_ANALYSIS,
            prompt_text=prompt_text,
            context_data=context.to_dict(),
            technical_indicators=self._extract_technical_indicators(technical_analysis),
            market_factors=self._extract_market_factors(context.market_context),
            instructions=self._get_analysis_instructions(analysis_type, analysis_mode),
            output_format=self._get_output_format(PromptTemplate.STOCK_ANALYSIS)
        )
    
    def generate_portfolio_analysis_prompt(self,
                                         holdings: List[StockConfig],
                                         stock_data_list: List[StockData],
                                         technical_analyses: List[TechnicalAnalysisResult],
                                         analysis_type: AnalysisType,
                                         analysis_mode: AnalysisMode) -> GeneratedPrompt:
        """
        ポートフォリオ分析プロンプトを生成
        
        Args:
            holdings: 保有銘柄リスト
            stock_data_list: 株価データリスト
            technical_analyses: テクニカル分析結果リスト
            analysis_type: 分析タイプ
            analysis_mode: 分析モード
            
        Returns:
            GeneratedPrompt: 生成されたプロンプト
        """
        context = PromptContext(
            analysis_type=analysis_type,
            analysis_mode=analysis_mode,
            template_type=PromptTemplate.PORTFOLIO_ANALYSIS,
            market_context=self._get_market_context(),
            user_preferences=self._get_user_preferences(analysis_mode),
            risk_tolerance=self._get_risk_tolerance(analysis_mode),
            investment_horizon=self._get_investment_horizon(analysis_type)
        )
        
        # ポートフォリオサマリー生成
        portfolio_summary = self._format_portfolio_summary(holdings, stock_data_list)
        
        # 集約テクニカル分析
        aggregated_technical = self._aggregate_technical_analyses(technical_analyses)
        
        # プロンプト生成
        template = self.base_templates[PromptTemplate.PORTFOLIO_ANALYSIS]
        
        prompt_text = template.format(
            analysis_type=analysis_type.value,
            analysis_mode=analysis_mode.value,
            portfolio_summary=portfolio_summary,
            technical_summary=aggregated_technical,
            holdings_count=len(holdings),
            risk_tolerance=context.risk_tolerance,
            investment_horizon=context.investment_horizon,
            market_context=self._format_market_context(context.market_context)
        )
        
        return GeneratedPrompt(
            template_type=PromptTemplate.PORTFOLIO_ANALYSIS,
            prompt_text=prompt_text,
            context_data=context.to_dict(),
            technical_indicators=self._extract_multiple_technical_indicators(technical_analyses),
            market_factors=self._extract_market_factors(context.market_context),
            instructions=self._get_analysis_instructions(analysis_type, analysis_mode),
            output_format=self._get_output_format(PromptTemplate.PORTFOLIO_ANALYSIS)
        )
    
    def generate_watchlist_analysis_prompt(self,
                                         watchlist: List[WatchlistStock],
                                         stock_data_list: List[StockData],
                                         technical_analyses: List[TechnicalAnalysisResult],
                                         analysis_mode: AnalysisMode) -> GeneratedPrompt:
        """
        ウォッチリスト分析プロンプトを生成
        
        Args:
            watchlist: ウォッチリスト
            stock_data_list: 株価データリスト
            technical_analyses: テクニカル分析結果リスト
            analysis_mode: 分析モード
            
        Returns:
            GeneratedPrompt: 生成されたプロンプト
        """
        context = PromptContext(
            analysis_type=AnalysisType.DAILY,  # ウォッチリストは通常日次
            analysis_mode=analysis_mode,
            template_type=PromptTemplate.WATCHLIST_ANALYSIS,
            market_context=self._get_market_context(),
            user_preferences=self._get_user_preferences(analysis_mode),
            risk_tolerance=self._get_risk_tolerance(analysis_mode),
            investment_horizon="短期"
        )
        
        # ウォッチリストサマリー生成
        watchlist_summary = self._format_watchlist_summary(watchlist, stock_data_list)
        
        # 集約テクニカル分析
        aggregated_technical = self._aggregate_technical_analyses(technical_analyses)
        
        # プロンプト生成
        template = self.base_templates[PromptTemplate.WATCHLIST_ANALYSIS]
        
        prompt_text = template.format(
            analysis_mode=analysis_mode.value,
            watchlist_summary=watchlist_summary,
            technical_summary=aggregated_technical,
            watchlist_count=len(watchlist),
            risk_tolerance=context.risk_tolerance,
            market_context=self._format_market_context(context.market_context)
        )
        
        return GeneratedPrompt(
            template_type=PromptTemplate.WATCHLIST_ANALYSIS,
            prompt_text=prompt_text,
            context_data=context.to_dict(),
            technical_indicators=self._extract_multiple_technical_indicators(technical_analyses),
            market_factors=self._extract_market_factors(context.market_context),
            instructions=self._get_analysis_instructions(AnalysisType.DAILY, analysis_mode),
            output_format=self._get_output_format(PromptTemplate.WATCHLIST_ANALYSIS)
        )
    
    def generate_risk_assessment_prompt(self,
                                      portfolio_data: Dict[str, Any],
                                      analysis_mode: AnalysisMode) -> GeneratedPrompt:
        """
        リスク評価プロンプトを生成
        
        Args:
            portfolio_data: ポートフォリオデータ
            analysis_mode: 分析モード
            
        Returns:
            GeneratedPrompt: 生成されたプロンプト
        """
        context = PromptContext(
            analysis_type=AnalysisType.MONTHLY,
            analysis_mode=analysis_mode,
            template_type=PromptTemplate.RISK_ASSESSMENT,
            market_context=self._get_market_context(),
            user_preferences=self._get_user_preferences(analysis_mode),
            risk_tolerance=self._get_risk_tolerance(analysis_mode),
            investment_horizon="長期"
        )
        
        # ポートフォリオリスクデータ整理
        risk_summary = self._format_risk_data(portfolio_data)
        
        # プロンプト生成
        template = self.base_templates[PromptTemplate.RISK_ASSESSMENT]
        
        prompt_text = template.format(
            analysis_mode=analysis_mode.value,
            risk_summary=risk_summary,
            risk_tolerance=context.risk_tolerance,
            market_context=self._format_market_context(context.market_context)
        )
        
        return GeneratedPrompt(
            template_type=PromptTemplate.RISK_ASSESSMENT,
            prompt_text=prompt_text,
            context_data=context.to_dict(),
            technical_indicators=[],
            market_factors=self._extract_market_factors(context.market_context),
            instructions=self._get_risk_assessment_instructions(analysis_mode),
            output_format=self._get_output_format(PromptTemplate.RISK_ASSESSMENT)
        )
    
    def _get_stock_analysis_template(self) -> str:
        """個別株式分析テンプレート"""
        return """専門的な金融アナリストとして、以下の株式について包括的な{analysis_type}分析を実行してください。

分析対象: {symbol}
分析モード: {analysis_mode}
投資期間: {investment_horizon}
リスク許容度: {risk_tolerance}

現在の株価情報:
{stock_summary}

テクニカル分析結果:
{technical_summary}

ポートフォリオコンテキスト:
{portfolio_context}

市場環境:
{market_context}

分析要求:
1. 現在の株価水準とトレンドの評価
2. テクニカル指標に基づく短期・中期見通し
3. リスク要因と機会の特定
4. 具体的な投資推奨（買い/売り/保持）と根拠
5. 目標価格とストップロス水準の提案
6. ポートフォリオ内での位置づけと適切な配分比率

特に以下の点を重視してください:
- データに基づく客観的な分析
- リスク・リターンのバランス評価
- 市場環境との整合性
- 投資期間に応じた戦略提案"""
    
    def _get_portfolio_analysis_template(self) -> str:
        """ポートフォリオ分析テンプレート"""
        return """ポートフォリオマネージャーとして、以下のポートフォリオについて{analysis_type}分析を実行してください。

分析モード: {analysis_mode}
投資期間: {investment_horizon}
リスク許容度: {risk_tolerance}
保有銘柄数: {holdings_count}

ポートフォリオ概要:
{portfolio_summary}

統合テクニカル分析:
{technical_summary}

市場環境:
{market_context}

分析要求:
1. ポートフォリオ全体のパフォーマンス評価
2. 銘柄間の相関関係とリスク分散状況
3. セクター・地域配分の適切性
4. 個別銘柄の貢献度分析
5. リバランスの必要性と具体的提案
6. リスク調整後リターンの評価
7. 今後の戦略的方向性

重点評価項目:
- 分散投資の効果性
- リスク集中の特定
- パフォーマンス向上の機会
- 市場環境変化への対応力"""
    
    def _get_watchlist_analysis_template(self) -> str:
        """ウォッチリスト分析テンプレート"""
        return """投資機会発掘の専門家として、以下のウォッチリストについて分析してください。

分析モード: {analysis_mode}
リスク許容度: {risk_tolerance}
監視銘柄数: {watchlist_count}

ウォッチリスト概要:
{watchlist_summary}

統合テクニカル分析:
{technical_summary}

市場環境:
{market_context}

分析要求:
1. 各銘柄の投資魅力度ランキング
2. エントリータイミングの評価
3. 短期・中期の価格目標設定
4. リスク要因と注意点の特定
5. 優先度付きの投資推奨順序
6. 適切な投資比率の提案

評価基準:
- テクニカル指標の優位性
- 市場トレンドとの整合性
- リスク・リターン比率
- 流動性とボラティリティ"""
    
    def _get_market_overview_template(self) -> str:
        """市場概況テンプレート"""
        return """市場アナリストとして、現在の市場環境について包括的な分析を提供してください。

分析要求:
1. 主要指数の動向と要因分析
2. セクター別パフォーマンス評価
3. マクロ経済指標の影響評価
4. 地政学的リスクの考慮
5. 投資家センチメントの分析
6. 今後の市場見通しと注意点"""
    
    def _get_risk_assessment_template(self) -> str:
        """リスク評価テンプレート"""
        return """リスク管理の専門家として、以下のポートフォリオのリスク評価を実行してください。

分析モード: {analysis_mode}
リスク許容度: {risk_tolerance}

リスクデータ:
{risk_summary}

市場環境:
{market_context}

評価要求:
1. 各種リスク指標の分析
2. 集中リスクの特定
3. 市場リスクへの感応度評価
4. ストレステストシナリオ
5. リスク軽減策の提案
6. 最適なリスク・リターン配分"""
    
    def _get_rebalance_advice_template(self) -> str:
        """リバランス助言テンプレート"""
        return """ポートフォリオ最適化の専門家として、リバランス戦略を提案してください。

分析要求:
1. 現在の配分と目標配分の比較
2. リバランスの必要性評価
3. 具体的な売買提案
4. 実行タイミングの推奨
5. 税務効率の考慮
6. 取引コストの最適化"""
    
    def _format_technical_analysis(self, technical_analysis: TechnicalAnalysisResult) -> str:
        """テクニカル分析を文字列化"""
        trend_name = {
            TrendDirection.BULLISH: "上昇トレンド",
            TrendDirection.BEARISH: "下降トレンド", 
            TrendDirection.NEUTRAL: "横ばいトレンド"
        }.get(technical_analysis.trend_direction, "不明")
        
        signal_name = {
            SignalType.STRONG_BUY: "強い買いシグナル",
            SignalType.BUY: "買いシグナル",
            SignalType.HOLD: "保持シグナル",
            SignalType.SELL: "売りシグナル",
            SignalType.STRONG_SELL: "強い売りシグナル"
        }.get(technical_analysis.overall_signal, "不明")
        
        rsi_status = ""
        if technical_analysis.rsi:
            rsi_value = technical_analysis.rsi.values[-1] if technical_analysis.rsi.values else 0
            if rsi_value > 70:
                rsi_status = "買われすぎ"
            elif rsi_value < 30:
                rsi_status = "売られすぎ"
            else:
                rsi_status = "中立"
            rsi_status = f"RSI: {rsi_value:.1f} ({rsi_status})"
        
        return f"""
トレンド方向: {trend_name}
総合シグナル: {signal_name}
シグナル強度: {technical_analysis.signal_strength:.2f}
ボラティリティ: {technical_analysis.volatility:.2f}%
{rsi_status}
新高値更新: {'はい' if technical_analysis.is_new_high else 'いいえ'}
新安値更新: {'はい' if technical_analysis.is_new_low else 'いいえ'}
        """.strip()
    
    def _format_stock_data(self, stock_data: StockData) -> str:
        """株価データを文字列化"""
        return f"""
銘柄コード: {stock_data.symbol}
現在価格: ${stock_data.current_price:.2f}
前日終値: ${stock_data.previous_close:.2f}
変化額: ${stock_data.change:.2f} ({stock_data.change_percent:.2f}%)
出来高: {stock_data.volume:,}
更新時刻: {stock_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
    
    def _format_portfolio_context(self, portfolio_context: Dict[str, Any]) -> str:
        """ポートフォリオコンテキストを文字列化"""
        if not portfolio_context:
            return "ポートフォリオコンテキストは利用できません。"
        
        total_value = portfolio_context.get('total_value', 0)
        holdings_count = portfolio_context.get('holdings_count', 0)
        top_holdings = portfolio_context.get('top_holdings', [])
        
        context = f"ポートフォリオ総額: ${total_value:,.2f}\n"
        context += f"保有銘柄数: {holdings_count}\n"
        
        if top_holdings:
            context += "主要保有銘柄:\n"
            for holding in top_holdings[:3]:
                context += f"- {holding.get('symbol', 'N/A')}: {holding.get('percentage', 0):.1f}%\n"
        
        return context
    
    def _format_portfolio_summary(self, holdings: List[StockConfig], stock_data_list: List[StockData]) -> str:
        """ポートフォリオサマリーを文字列化"""
        stock_data_dict = {data.symbol: data for data in stock_data_list}
        
        summary = f"保有銘柄数: {len(holdings)}\n\n"
        total_value = 0
        
        for holding in holdings:
            stock_data = stock_data_dict.get(holding.symbol)
            if stock_data:
                value = stock_data.current_price * holding.quantity
                total_value += value
                pnl = (stock_data.current_price - (holding.purchase_price or stock_data.current_price)) * holding.quantity
                pnl_pct = (pnl / (holding.purchase_price * holding.quantity)) * 100 if holding.purchase_price else 0
                
                summary += f"{holding.symbol} ({holding.name}): "
                summary += f"{holding.quantity}株, ${value:,.2f}, "
                summary += f"損益: ${pnl:,.2f} ({pnl_pct:.1f}%)\n"
        
        summary = f"ポートフォリオ総額: ${total_value:,.2f}\n\n" + summary
        return summary
    
    def _format_watchlist_summary(self, watchlist: List[WatchlistStock], stock_data_list: List[StockData]) -> str:
        """ウォッチリストサマリーを文字列化"""
        stock_data_dict = {data.symbol: data for data in stock_data_list}
        
        summary = f"監視銘柄数: {len(watchlist)}\n\n"
        
        for stock in watchlist:
            stock_data = stock_data_dict.get(stock.symbol)
            if stock_data:
                summary += f"{stock.symbol} ({stock.name}): "
                summary += f"${stock_data.current_price:.2f} "
                summary += f"({stock_data.change_percent:+.2f}%)\n"
        
        return summary
    
    def _aggregate_technical_analyses(self, technical_analyses: List[TechnicalAnalysisResult]) -> str:
        """複数のテクニカル分析を集約"""
        if not technical_analyses:
            return "テクニカル分析データなし"
        
        # 平均値計算
        avg_signal_strength = sum(ta.signal_strength for ta in technical_analyses) / len(technical_analyses)
        avg_volatility = sum(ta.volatility for ta in technical_analyses) / len(technical_analyses)
        
        # トレンド集計
        trend_counts = {}
        signal_counts = {}
        
        for ta in technical_analyses:
            trend_counts[ta.trend_direction] = trend_counts.get(ta.trend_direction, 0) + 1
            signal_counts[ta.overall_signal] = signal_counts.get(ta.overall_signal, 0) + 1
        
        dominant_trend = max(trend_counts.items(), key=lambda x: x[1])[0]
        dominant_signal = max(signal_counts.items(), key=lambda x: x[1])[0]
        
        return f"""
分析銘柄数: {len(technical_analyses)}
平均シグナル強度: {avg_signal_strength:.2f}
平均ボラティリティ: {avg_volatility:.2f}%
支配的トレンド: {dominant_trend.value}
支配的シグナル: {dominant_signal.value}
        """.strip()
    
    def _format_risk_data(self, portfolio_data: Dict[str, Any]) -> str:
        """リスクデータを文字列化"""
        risk_metrics = portfolio_data.get('risk_metrics', {})
        
        return f"""
ポートフォリオVaR: {risk_metrics.get('var', 0):.2f}%
最大ドローダウン: {risk_metrics.get('max_drawdown', 0):.2f}%
シャープレシオ: {risk_metrics.get('sharpe_ratio', 0):.2f}
ベータ値: {risk_metrics.get('beta', 1):.2f}
相関係数: {risk_metrics.get('correlation', 0):.2f}
        """.strip()
    
    def _get_market_context(self) -> Dict[str, Any]:
        """市場コンテキストを取得"""
        return {
            "market_trend": "上昇基調",
            "volatility_level": "中程度",
            "interest_rate_environment": "低金利",
            "economic_outlook": "緩やかな成長",
            "geopolitical_risks": "中程度"
        }
    
    def _format_market_context(self, market_context: Dict[str, Any]) -> str:
        """市場コンテキストを文字列化"""
        return f"""
市場トレンド: {market_context.get('market_trend', 'N/A')}
ボラティリティ水準: {market_context.get('volatility_level', 'N/A')}
金利環境: {market_context.get('interest_rate_environment', 'N/A')}
経済見通し: {market_context.get('economic_outlook', 'N/A')}
地政学リスク: {market_context.get('geopolitical_risks', 'N/A')}
        """.strip()
    
    def _get_user_preferences(self, analysis_mode: AnalysisMode) -> Dict[str, Any]:
        """ユーザー設定を取得"""
        return {
            "investment_style": analysis_mode.value,
            "sector_preferences": [],
            "esg_priority": False,
            "dividend_focus": False
        }
    
    def _get_risk_tolerance(self, analysis_mode: AnalysisMode) -> str:
        """リスク許容度を取得"""
        return {
            AnalysisMode.CONSERVATIVE: "低リスク",
            AnalysisMode.BALANCED: "中リスク",
            AnalysisMode.AGGRESSIVE: "高リスク"
        }.get(analysis_mode, "中リスク")
    
    def _get_investment_horizon(self, analysis_type: AnalysisType) -> str:
        """投資期間を取得"""
        return {
            AnalysisType.DAILY: "短期（数日〜数週間）",
            AnalysisType.WEEKLY: "中期（数週間〜数ヶ月）",
            AnalysisType.MONTHLY: "長期（数ヶ月〜数年）"
        }.get(analysis_type, "中期")
    
    def _extract_technical_indicators(self, technical_analysis: TechnicalAnalysisResult) -> List[str]:
        """テクニカル指標を抽出"""
        indicators = []
        
        if technical_analysis.rsi:
            indicators.append("RSI")
        if technical_analysis.sma_5:
            indicators.append("SMA5")
        if technical_analysis.sma_25:
            indicators.append("SMA25")
        if technical_analysis.crossover_signals:
            indicators.append("クロスオーバー")
        if technical_analysis.breakout_signals:
            indicators.append("ブレイクアウト")
        if technical_analysis.support_resistance:
            indicators.append("サポート・レジスタンス")
        
        return indicators
    
    def _extract_multiple_technical_indicators(self, technical_analyses: List[TechnicalAnalysisResult]) -> List[str]:
        """複数のテクニカル指標を抽出"""
        all_indicators = set()
        
        for ta in technical_analyses:
            indicators = self._extract_technical_indicators(ta)
            all_indicators.update(indicators)
        
        return list(all_indicators)
    
    def _extract_market_factors(self, market_context: Dict[str, Any]) -> List[str]:
        """市場要因を抽出"""
        return list(market_context.keys())
    
    def _get_analysis_instructions(self, analysis_type: AnalysisType, analysis_mode: AnalysisMode) -> List[str]:
        """分析指示を取得"""
        base_instructions = [
            "客観的なデータに基づいて分析してください",
            "リスクとリターンのバランスを評価してください",
            "市場環境との整合性を確認してください"
        ]
        
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            base_instructions.append("リスク管理を重視してください")
        elif analysis_mode == AnalysisMode.AGGRESSIVE:
            base_instructions.append("成長機会を積極的に評価してください")
        
        if analysis_type == AnalysisType.DAILY:
            base_instructions.append("短期的な価格変動に注目してください")
        elif analysis_type == AnalysisType.MONTHLY:
            base_instructions.append("長期的なトレンドを重視してください")
        
        return base_instructions
    
    def _get_risk_assessment_instructions(self, analysis_mode: AnalysisMode) -> List[str]:
        """リスク評価指示を取得"""
        instructions = [
            "各種リスク指標を包括的に評価してください",
            "集中リスクを特定してください",
            "ストレステストを実施してください",
            "リスク軽減策を提案してください"
        ]
        
        if analysis_mode == AnalysisMode.CONSERVATIVE:
            instructions.append("特にダウンサイドリスクに注意してください")
        
        return instructions
    
    def _get_output_format(self, template_type: PromptTemplate) -> str:
        """出力フォーマットを取得"""
        if template_type == PromptTemplate.STOCK_ANALYSIS:
            return """
{
  "recommendation": "BUY/SELL/HOLD",
  "confidence": 0.0-1.0,
  "target_price": 価格,
  "stop_loss": 価格,
  "reasoning": "推奨理由",
  "risk_level": "LOW/MEDIUM/HIGH",
  "investment_horizon": "期間",
  "key_factors": ["要因1", "要因2", "要因3"]
}
            """.strip()
        
        elif template_type == PromptTemplate.PORTFOLIO_ANALYSIS:
            return """
{
  "overall_score": 0-100,
  "risk_level": "LOW/MEDIUM/HIGH",
  "diversification_score": 0-100,
  "performance_outlook": "POSITIVE/NEUTRAL/NEGATIVE",
  "rebalance_needed": true/false,
  "top_recommendations": ["推奨1", "推奨2", "推奨3"],
  "risk_factors": ["リスク1", "リスク2", "リスク3"]
}
            """.strip()
        
        elif template_type == PromptTemplate.WATCHLIST_ANALYSIS:
            return """
{
  "top_picks": [
    {
      "symbol": "銘柄コード",
      "priority": 1-10,
      "reason": "選定理由",
      "entry_timing": "NOW/WAIT/DIP"
    }
  ],
  "market_timing": "NOW/WAIT",
  "investment_strategy": "戦略説明"
}
            """.strip()
        
        else:
            return "構造化されたJSON形式で回答してください。"