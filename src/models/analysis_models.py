"""
分析結果モデル
AI分析、テクニカル指標、推奨アクションに関するデータクラス
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AnalysisType(Enum):
    """分析タイプ"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            AnalysisType.DAILY: "日次分析",
            AnalysisType.WEEKLY: "週次分析", 
            AnalysisType.MONTHLY: "月次分析"
        }
        return mapping[self]


class RecommendationType(Enum):
    """推奨タイプ"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            RecommendationType.BUY: "購入",
            RecommendationType.SELL: "売却",
            RecommendationType.HOLD: "保持",
            RecommendationType.STRONG_BUY: "強い購入",
            RecommendationType.STRONG_SELL: "強い売却"
        }
        return mapping[self]
    
    @property
    def priority(self) -> int:
        """優先度（数値が高いほど重要）"""
        mapping = {
            RecommendationType.STRONG_SELL: 5,
            RecommendationType.STRONG_BUY: 4,
            RecommendationType.SELL: 3,
            RecommendationType.BUY: 2,
            RecommendationType.HOLD: 1
        }
        return mapping[self]


class RiskLevel(Enum):
    """リスクレベル"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            RiskLevel.LOW: "低リスク",
            RiskLevel.MEDIUM: "中リスク",
            RiskLevel.HIGH: "高リスク",
            RiskLevel.VERY_HIGH: "非常に高リスク"
        }
        return mapping[self]
    
    @property
    def score(self) -> int:
        """リスクスコア（1-4）"""
        mapping = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.VERY_HIGH: 4
        }
        return mapping[self]


class TechnicalSignal(Enum):
    """テクニカルシグナル"""
    BULLISH = "BULLISH"  # 強気
    BEARISH = "BEARISH"  # 弱気
    NEUTRAL = "NEUTRAL"  # 中立
    
    def __str__(self) -> str:
        return self.value
    
    @property
    def display_name(self) -> str:
        """表示用名称"""
        mapping = {
            TechnicalSignal.BULLISH: "強気",
            TechnicalSignal.BEARISH: "弱気",
            TechnicalSignal.NEUTRAL: "中立"
        }
        return mapping[self]


@dataclass
class TechnicalIndicators:
    """
    テクニカル指標データクラス
    各種テクニカル分析結果を保持
    """
    # 移動平均
    golden_cross: bool = False
    dead_cross: bool = False
    short_ma: Optional[float] = None
    long_ma: Optional[float] = None
    
    # ブレイクアウト
    new_high_break: bool = False
    new_low_break: bool = False
    resistance_break: bool = False
    support_break: bool = False
    
    # オシレーター
    rsi: Optional[float] = None
    rsi_signal: Optional[TechnicalSignal] = None
    
    # MACD
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_trend: Optional[TechnicalSignal] = None
    
    # 市場相関
    market_correlation: Optional[float] = None
    
    # 出来高
    volume_change_rate: Optional[float] = None
    volume_trend: Optional[TechnicalSignal] = None
    
    # サポート・レジスタンス
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    
    def __post_init__(self):
        """データ検証と自動計算"""
        # RSIシグナルの自動判定
        if self.rsi is not None:
            if self.rsi_signal is None:
                if self.rsi > 70:
                    self.rsi_signal = TechnicalSignal.BEARISH  # 買われすぎ
                elif self.rsi < 30:
                    self.rsi_signal = TechnicalSignal.BULLISH  # 売られすぎ
                else:
                    self.rsi_signal = TechnicalSignal.NEUTRAL
        
        # MACDトレンドの自動判定
        if self.macd_line is not None and self.macd_signal is not None:
            if self.macd_trend is None:
                if self.macd_line > self.macd_signal:
                    self.macd_trend = TechnicalSignal.BULLISH
                elif self.macd_line < self.macd_signal:
                    self.macd_trend = TechnicalSignal.BEARISH
                else:
                    self.macd_trend = TechnicalSignal.NEUTRAL
        
        # 出来高トレンドの自動判定
        if self.volume_change_rate is not None:
            if self.volume_trend is None:
                if self.volume_change_rate > 20:
                    self.volume_trend = TechnicalSignal.BULLISH  # 出来高急増
                elif self.volume_change_rate < -20:
                    self.volume_trend = TechnicalSignal.BEARISH  # 出来高急減
                else:
                    self.volume_trend = TechnicalSignal.NEUTRAL
    
    @property
    def overall_signal(self) -> TechnicalSignal:
        """総合テクニカルシグナル"""
        bullish_count = 0
        bearish_count = 0
        
        # 各指標のシグナルをカウント
        if self.golden_cross:
            bullish_count += 2  # 重要指標
        if self.dead_cross:
            bearish_count += 2
        
        if self.new_high_break or self.resistance_break:
            bullish_count += 1
        if self.new_low_break or self.support_break:
            bearish_count += 1
        
        if self.rsi_signal == TechnicalSignal.BULLISH:
            bullish_count += 1
        elif self.rsi_signal == TechnicalSignal.BEARISH:
            bearish_count += 1
        
        if self.macd_trend == TechnicalSignal.BULLISH:
            bullish_count += 1
        elif self.macd_trend == TechnicalSignal.BEARISH:
            bearish_count += 1
        
        if self.volume_trend == TechnicalSignal.BULLISH:
            bullish_count += 1
        elif self.volume_trend == TechnicalSignal.BEARISH:
            bearish_count += 1
        
        # 総合判定
        if bullish_count > bearish_count + 1:
            return TechnicalSignal.BULLISH
        elif bearish_count > bullish_count + 1:
            return TechnicalSignal.BEARISH
        else:
            return TechnicalSignal.NEUTRAL
    
    def get_signal_summary(self) -> Dict[str, Any]:
        """シグナルサマリーを取得"""
        return {
            "overall_signal": self.overall_signal.display_name,
            "moving_average": {
                "golden_cross": self.golden_cross,
                "dead_cross": self.dead_cross,
                "short_ma": self.short_ma,
                "long_ma": self.long_ma
            },
            "breakout": {
                "new_high_break": self.new_high_break,
                "new_low_break": self.new_low_break,
                "resistance_break": self.resistance_break,
                "support_break": self.support_break
            },
            "oscillators": {
                "rsi": self.rsi,
                "rsi_signal": self.rsi_signal.display_name if self.rsi_signal else None,
                "macd_trend": self.macd_trend.display_name if self.macd_trend else None
            },
            "volume": {
                "change_rate": self.volume_change_rate,
                "trend": self.volume_trend.display_name if self.volume_trend else None
            },
            "support_resistance": {
                "support_level": self.support_level,
                "resistance_level": self.resistance_level
            }
        }


@dataclass
class Recommendation:
    """
    推奨アクションデータクラス
    AI分析による推奨事項を保持
    """
    type: RecommendationType
    symbol: str
    confidence: float  # 0.0-1.0の信頼度
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: Optional[str] = None  # "短期", "中期", "長期"
    expected_return: Optional[float] = None  # 期待リターン（%）
    risk_factors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """データ検証"""
        if not self.symbol:
            raise ValueError("銘柄コードが空です")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("信頼度は0.0-1.0の範囲である必要があります")
        if not self.reasoning:
            raise ValueError("推奨理由が空です")
        if self.target_price is not None and self.target_price <= 0:
            raise ValueError("目標価格は0より大きい値である必要があります")
        if self.stop_loss is not None and self.stop_loss <= 0:
            raise ValueError("ストップロス価格は0より大きい値である必要があります")
    
    @property
    def confidence_level(self) -> str:
        """信頼度レベル"""
        if self.confidence >= 0.8:
            return "高"
        elif self.confidence >= 0.6:
            return "中"
        elif self.confidence >= 0.4:
            return "低"
        else:
            return "非常に低"
    
    @property
    def is_high_priority(self) -> bool:
        """高優先度推奨かチェック"""
        return (self.type in [RecommendationType.STRONG_BUY, RecommendationType.STRONG_SELL] 
                and self.confidence >= 0.7)
    
    def get_formatted_summary(self) -> str:
        """推奨内容のフォーマット済みサマリー"""
        summary = f"{self.symbol}: {self.type.display_name}"
        
        if self.target_price:
            summary += f" (目標価格: ¥{self.target_price:,.0f})"
        
        summary += f" [信頼度: {self.confidence_level}]"
        
        if self.time_horizon:
            summary += f" [{self.time_horizon}]"
        
        return summary


@dataclass
class RiskAssessment:
    """
    リスク評価データクラス
    ポートフォリオや個別銘柄のリスク分析結果を保持
    """
    overall_risk: RiskLevel
    diversification_score: float  # 0.0-1.0（1.0が最も分散）
    volatility_analysis: str
    recommendations: List[str] = field(default_factory=list)
    
    # 詳細リスク指標
    concentration_risk: Optional[float] = None  # 集中リスク（0.0-1.0）
    sector_concentration: Optional[Dict[str, float]] = None  # 業種別集中度
    country_concentration: Optional[Dict[str, float]] = None  # 国別集中度
    correlation_risk: Optional[float] = None  # 相関リスク
    liquidity_risk: Optional[float] = None  # 流動性リスク
    
    def __post_init__(self):
        """データ検証"""
        if not (0.0 <= self.diversification_score <= 1.0):
            raise ValueError("分散スコアは0.0-1.0の範囲である必要があります")
        if not self.volatility_analysis:
            raise ValueError("ボラティリティ分析が空です")
        
        # 集中リスクの検証
        if self.concentration_risk is not None:
            if not (0.0 <= self.concentration_risk <= 1.0):
                raise ValueError("集中リスクは0.0-1.0の範囲である必要があります")
    
    @property
    def diversification_level(self) -> str:
        """分散レベル"""
        if self.diversification_score >= 0.8:
            return "高分散"
        elif self.diversification_score >= 0.6:
            return "中分散"
        elif self.diversification_score >= 0.4:
            return "低分散"
        else:
            return "集中"
    
    @property
    def risk_score(self) -> int:
        """総合リスクスコア（1-10）"""
        base_score = self.overall_risk.score * 2  # 2-8
        
        # 分散度による調整
        diversification_adjustment = (1 - self.diversification_score) * 2  # 0-2
        
        # 集中リスクによる調整
        concentration_adjustment = 0
        if self.concentration_risk is not None:
            concentration_adjustment = self.concentration_risk * 2  # 0-2
        
        total_score = base_score + diversification_adjustment + concentration_adjustment
        return min(10, max(1, int(total_score)))
    
    def get_risk_summary(self) -> Dict[str, Any]:
        """リスクサマリーを取得"""
        return {
            "overall_risk": self.overall_risk.display_name,
            "risk_score": self.risk_score,
            "diversification": {
                "score": self.diversification_score,
                "level": self.diversification_level
            },
            "concentration": {
                "risk": self.concentration_risk,
                "sectors": self.sector_concentration,
                "countries": self.country_concentration
            },
            "other_risks": {
                "correlation": self.correlation_risk,
                "liquidity": self.liquidity_risk
            },
            "recommendations": self.recommendations
        }


@dataclass
class MarketContext:
    """
    市場コンテキストデータクラス
    分析時点での市場状況を保持
    """
    market_trend: TechnicalSignal
    market_volatility: float  # VIX等
    sector_performance: Dict[str, float] = field(default_factory=dict)
    economic_indicators: Dict[str, float] = field(default_factory=dict)
    news_sentiment: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_volatile_market(self) -> bool:
        """高ボラティリティ市場かチェック"""
        return self.market_volatility > 25.0  # VIX > 25


@dataclass
class AnalysisRequest:
    """
    分析リクエストデータクラス
    分析実行時のパラメータを保持
    """
    analysis_type: AnalysisType
    symbols: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    technical_indicators: Optional[TechnicalIndicators] = None
    market_context: Optional[MarketContext] = None
    custom_parameters: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """データ検証"""
        if not self.symbols:
            raise ValueError("分析対象銘柄が指定されていません")
        if len(self.symbols) > 100:
            raise ValueError("分析対象銘柄は100以下である必要があります")


@dataclass
class AnalysisResult:
    """
    分析結果データクラス
    AI分析の最終結果を保持
    """
    analysis_type: AnalysisType
    summary: str
    recommendations: List[Recommendation] = field(default_factory=list)
    risk_assessment: Optional[RiskAssessment] = None
    market_outlook: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 分析詳細
    technical_analysis: Optional[Dict[str, TechnicalIndicators]] = None
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    sector_analysis: Dict[str, Any] = field(default_factory=dict)
    country_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # メタデータ
    execution_time: Optional[float] = None
    ai_model: Optional[str] = None
    confidence_score: Optional[float] = None
    
    def __post_init__(self):
        """データ検証"""
        if not self.summary:
            raise ValueError("分析サマリーが空です")
        if self.confidence_score is not None:
            if not (0.0 <= self.confidence_score <= 1.0):
                raise ValueError("信頼度スコアは0.0-1.0の範囲である必要があります")
    
    @property
    def high_priority_recommendations(self) -> List[Recommendation]:
        """高優先度推奨を取得"""
        return [rec for rec in self.recommendations if rec.is_high_priority]
    
    @property
    def buy_recommendations(self) -> List[Recommendation]:
        """購入推奨を取得"""
        return [rec for rec in self.recommendations 
                if rec.type in [RecommendationType.BUY, RecommendationType.STRONG_BUY]]
    
    @property
    def sell_recommendations(self) -> List[Recommendation]:
        """売却推奨を取得"""
        return [rec for rec in self.recommendations 
                if rec.type in [RecommendationType.SELL, RecommendationType.STRONG_SELL]]
    
    def get_recommendations_by_symbol(self, symbol: str) -> List[Recommendation]:
        """指定銘柄の推奨を取得"""
        return [rec for rec in self.recommendations if rec.symbol == symbol]
    
    def get_analysis_summary(self) -> Dict[str, Any]:
        """分析結果サマリーを取得"""
        return {
            "analysis_type": self.analysis_type.display_name,
            "timestamp": self.timestamp.isoformat(),
            "summary": self.summary,
            "market_outlook": self.market_outlook,
            "recommendations_count": len(self.recommendations),
            "high_priority_count": len(self.high_priority_recommendations),
            "buy_count": len(self.buy_recommendations),
            "sell_count": len(self.sell_recommendations),
            "risk_assessment": self.risk_assessment.get_risk_summary() if self.risk_assessment else None,
            "confidence_score": self.confidence_score,
            "execution_time": self.execution_time
        }