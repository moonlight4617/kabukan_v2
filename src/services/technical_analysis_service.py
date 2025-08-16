# -*- coding: utf-8 -*-
"""
テクニカル分析サービス
株価データからテクニカル指標を計算し、パターン検出を行う
"""

import logging
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics

from src.services.historical_data_manager import HistoricalDataset, PriceData, VolumeData


logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    """トレンド方向"""
    BULLISH = "bullish"      # 上昇トレンド
    BEARISH = "bearish"      # 下降トレンド
    NEUTRAL = "neutral"      # 横ばい
    UNKNOWN = "unknown"      # 不明


class SignalType(Enum):
    """シグナルタイプ"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"


class CrossoverType(Enum):
    """クロスオーバータイプ"""
    GOLDEN_CROSS = "golden_cross"      # ゴールデンクロス
    DEAD_CROSS = "dead_cross"          # デッドクロス
    BULLISH_SIGNAL = "bullish_signal"  # 強気シグナル
    BEARISH_SIGNAL = "bearish_signal"  # 弱気シグナル


@dataclass
class MovingAverage:
    """移動平均データ"""
    period: int
    values: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    
    @property
    def current_value(self) -> Optional[float]:
        """現在値"""
        return self.values[-1] if self.values else None
    
    @property
    def previous_value(self) -> Optional[float]:
        """前回値"""
        return self.values[-2] if len(self.values) >= 2 else None


@dataclass
class RSIData:
    """RSI（相対力指数）データ"""
    period: int = 14
    values: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    gains: List[float] = field(default_factory=list)
    losses: List[float] = field(default_factory=list)
    
    @property
    def current_value(self) -> Optional[float]:
        """現在のRSI値"""
        return self.values[-1] if self.values else None
    
    @property
    def is_overbought(self) -> bool:
        """買われすぎ判定（RSI > 70）"""
        return self.current_value is not None and self.current_value > 70
    
    @property
    def is_oversold(self) -> bool:
        """売られすぎ判定（RSI < 30）"""
        return self.current_value is not None and self.current_value < 30


@dataclass
class MACDData:
    """MACD（移動平均収束拡散法）データ"""
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    macd_line: List[float] = field(default_factory=list)
    signal_line: List[float] = field(default_factory=list)
    histogram: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    
    @property
    def current_macd(self) -> Optional[float]:
        """現在のMACDライン値"""
        return self.macd_line[-1] if self.macd_line else None
    
    @property
    def current_signal(self) -> Optional[float]:
        """現在のシグナルライン値"""
        return self.signal_line[-1] if self.signal_line else None
    
    @property
    def current_histogram(self) -> Optional[float]:
        """現在のヒストグラム値"""
        return self.histogram[-1] if self.histogram else None


@dataclass
class BollingerBandsData:
    """ボリンジャーバンドデータ"""
    period: int = 20
    std_dev: float = 2.0
    upper_band: List[float] = field(default_factory=list)
    middle_band: List[float] = field(default_factory=list)  # SMA
    lower_band: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    
    @property
    def current_upper(self) -> Optional[float]:
        return self.upper_band[-1] if self.upper_band else None
    
    @property
    def current_middle(self) -> Optional[float]:
        return self.middle_band[-1] if self.middle_band else None
    
    @property
    def current_lower(self) -> Optional[float]:
        return self.lower_band[-1] if self.lower_band else None


@dataclass
class CrossoverSignal:
    """クロスオーバーシグナル"""
    date: str
    crossover_type: CrossoverType
    price: float
    signal_strength: float  # 0-1のシグナル強度
    description: str
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupportResistanceLevel:
    """サポート・レジスタンスレベル"""
    level: float
    level_type: str  # "support" or "resistance"
    strength: float  # 強度（0-1）
    touch_count: int  # タッチ回数
    last_touch_date: str
    confidence: float  # 信頼度（0-1）


@dataclass
class BreakoutSignal:
    """ブレイクアウトシグナル"""
    date: str
    breakout_type: str  # "new_high", "new_low", "resistance_break", "support_break"
    price: float
    reference_level: float  # 基準レベル（前回高値など）
    strength: float  # 強度（0-1）
    volume_surge: bool  # 出来高急増の有無
    description: str
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketCorrelation:
    """市場相関データ"""
    correlation_coefficient: float  # 相関係数
    period_days: int
    reference_symbol: str  # 基準銘柄（例：日経平均）
    confidence_level: float  # 信頼度
    description: str


@dataclass
class TechnicalAnalysisResult:
    """テクニカル分析結果"""
    symbol: str
    analysis_date: datetime
    current_price: float
    
    # 移動平均
    sma_5: Optional[MovingAverage] = None
    sma_25: Optional[MovingAverage] = None
    sma_75: Optional[MovingAverage] = None
    ema_12: Optional[MovingAverage] = None
    ema_26: Optional[MovingAverage] = None
    
    # テクニカル指標
    rsi: Optional[RSIData] = None
    macd: Optional[MACDData] = None
    bollinger_bands: Optional[BollingerBandsData] = None
    
    # シグナル
    crossover_signals: List[CrossoverSignal] = field(default_factory=list)
    breakout_signals: List[BreakoutSignal] = field(default_factory=list)
    support_resistance: List[SupportResistanceLevel] = field(default_factory=list)
    
    # 市場分析
    market_correlation: Optional[MarketCorrelation] = None
    
    # 総合判定
    trend_direction: TrendDirection = TrendDirection.UNKNOWN
    overall_signal: SignalType = SignalType.HOLD
    signal_strength: float = 0.0  # 0-1
    
    # 追加情報
    price_change_pct: float = 0.0
    volume_change_pct: float = 0.0
    volatility: float = 0.0
    
    # 新高値・新安値情報
    is_new_high: bool = False
    is_new_low: bool = False
    new_high_period: int = 0  # 何日ぶりの高値か
    new_low_period: int = 0   # 何日ぶりの安値か


class TechnicalAnalysisService:
    """テクニカル分析サービス"""
    
    def __init__(self, 
                 enable_advanced_patterns: bool = True,
                 enable_volume_analysis: bool = True):
        """
        Args:
            enable_advanced_patterns: 高度なパターン分析を有効にする
            enable_volume_analysis: 出来高分析を有効にする
        """
        self.enable_advanced_patterns = enable_advanced_patterns
        self.enable_volume_analysis = enable_volume_analysis
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, dataset: HistoricalDataset) -> TechnicalAnalysisResult:
        """
        包括的なテクニカル分析を実行
        
        Args:
            dataset: 履歴データセット
            
        Returns:
            TechnicalAnalysisResult: 分析結果
        """
        if dataset.is_empty or len(dataset.price_data) < 30:
            raise ValueError("テクニカル分析には最低30日分のデータが必要です")
        
        result = TechnicalAnalysisResult(
            symbol=dataset.symbol,
            analysis_date=datetime.now(),
            current_price=dataset.get_latest_price().close
        )
        
        try:
            # 基本移動平均の計算
            result.sma_5 = self.calculate_sma(dataset.price_data, 5)
            result.sma_25 = self.calculate_sma(dataset.price_data, 25)
            result.sma_75 = self.calculate_sma(dataset.price_data, 75)
            result.ema_12 = self.calculate_ema(dataset.price_data, 12)
            result.ema_26 = self.calculate_ema(dataset.price_data, 26)
            
            # テクニカル指標の計算
            result.rsi = self.calculate_rsi(dataset.price_data)
            result.macd = self.calculate_macd(dataset.price_data)
            result.bollinger_bands = self.calculate_bollinger_bands(dataset.price_data)
            
            # クロスオーバーシグナルの検出
            result.crossover_signals = self.detect_crossover_signals(
                result.sma_5, result.sma_25, dataset.price_data
            )
            
            # ブレイクアウトシグナルの検出
            result.breakout_signals = self.detect_breakout_signals(dataset.price_data, dataset.volume_data)
            
            # 新高値・新安値の検出
            result.is_new_high, result.new_high_period = self.detect_new_high(dataset.price_data)
            result.is_new_low, result.new_low_period = self.detect_new_low(dataset.price_data)
            
            # サポート・レジスタンスレベルの計算
            result.support_resistance = self.calculate_support_resistance(dataset.price_data)
            
            # 市場相関の計算（基準データがある場合）
            if self.enable_advanced_patterns:
                result.market_correlation = self.calculate_market_correlation(dataset.price_data)
            
            # トレンド分析
            result.trend_direction = self.analyze_trend(result)
            
            # 総合シグナル生成
            result.overall_signal, result.signal_strength = self.generate_overall_signal(result)
            
            # 追加指標の計算
            result.price_change_pct = self._calculate_price_change_pct(dataset.price_data)
            if self.enable_volume_analysis and dataset.volume_data:
                result.volume_change_pct = self._calculate_volume_change_pct(dataset.volume_data)
            result.volatility = self._calculate_volatility(dataset.price_data)
            
            self.logger.info(f"テクニカル分析完了: {dataset.symbol} - シグナル: {result.overall_signal.value}")
            
        except Exception as e:
            self.logger.error(f"テクニカル分析中にエラーが発生: {e}")
            raise
        
        return result
    
    def calculate_sma(self, price_data: List[PriceData], period: int) -> MovingAverage:
        """
        単純移動平均（SMA）を計算
        
        Args:
            price_data: 価格データ
            period: 期間
            
        Returns:
            MovingAverage: 移動平均データ
        """
        if len(price_data) < period:
            return MovingAverage(period=period)
        
        sma = MovingAverage(period=period)
        
        for i in range(period - 1, len(price_data)):
            # 過去period日間の終値平均を計算
            prices = [price_data[j].close for j in range(i - period + 1, i + 1)]
            sma_value = sum(prices) / period
            
            sma.values.append(sma_value)
            sma.dates.append(price_data[i].date)
        
        return sma
    
    def calculate_ema(self, price_data: List[PriceData], period: int) -> MovingAverage:
        """
        指数移動平均（EMA）を計算
        
        Args:
            price_data: 価格データ
            period: 期間
            
        Returns:
            MovingAverage: 移動平均データ
        """
        if len(price_data) < period:
            return MovingAverage(period=period)
        
        ema = MovingAverage(period=period)
        multiplier = 2 / (period + 1)
        
        # 最初のEMAはSMAで初期化
        initial_prices = [price_data[i].close for i in range(period)]
        initial_ema = sum(initial_prices) / period
        
        ema.values.append(initial_ema)
        ema.dates.append(price_data[period - 1].date)
        
        # EMAの計算
        for i in range(period, len(price_data)):
            current_price = price_data[i].close
            previous_ema = ema.values[-1]
            
            current_ema = (current_price * multiplier) + (previous_ema * (1 - multiplier))
            
            ema.values.append(current_ema)
            ema.dates.append(price_data[i].date)
        
        return ema
    
    def calculate_rsi(self, price_data: List[PriceData], period: int = 14) -> RSIData:
        """
        RSI（相対力指数）を計算
        
        Args:
            price_data: 価格データ
            period: 期間（デフォルト14）
            
        Returns:
            RSIData: RSIデータ
        """
        if len(price_data) < period + 1:
            return RSIData(period=period)
        
        rsi_data = RSIData(period=period)
        
        # 価格変化を計算
        price_changes = []
        for i in range(1, len(price_data)):
            change = price_data[i].close - price_data[i-1].close
            price_changes.append(change)
        
        # 初期の平均利得・損失を計算
        gains = [max(change, 0) for change in price_changes[:period]]
        losses = [abs(min(change, 0)) for change in price_changes[:period]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        # 最初のRSI計算
        if avg_loss == 0:
            rsi_value = 100
        else:
            rs = avg_gain / avg_loss
            rsi_value = 100 - (100 / (1 + rs))
        
        rsi_data.values.append(rsi_value)
        rsi_data.dates.append(price_data[period].date)
        rsi_data.gains.append(avg_gain)
        rsi_data.losses.append(avg_loss)
        
        # 残りのRSI計算（指数移動平均を使用）
        for i in range(period + 1, len(price_data)):
            change = price_data[i].close - price_data[i-1].close
            gain = max(change, 0)
            loss = abs(min(change, 0))
            
            # スムーズ化された平均利得・損失
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            
            if avg_loss == 0:
                rsi_value = 100
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))
            
            rsi_data.values.append(rsi_value)
            rsi_data.dates.append(price_data[i].date)
            rsi_data.gains.append(avg_gain)
            rsi_data.losses.append(avg_loss)
        
        return rsi_data
    
    def calculate_macd(self, 
                      price_data: List[PriceData], 
                      fast_period: int = 12, 
                      slow_period: int = 26, 
                      signal_period: int = 9) -> MACDData:
        """
        MACD（移動平均収束拡散法）を計算
        
        Args:
            price_data: 価格データ
            fast_period: 高速EMA期間
            slow_period: 低速EMA期間  
            signal_period: シグナルライン期間
            
        Returns:
            MACDData: MACDデータ
        """
        if len(price_data) < slow_period + signal_period:
            return MACDData(fast_period=fast_period, slow_period=slow_period, signal_period=signal_period)
        
        # 高速・低速EMAを計算
        fast_ema = self.calculate_ema(price_data, fast_period)
        slow_ema = self.calculate_ema(price_data, slow_period)
        
        macd_data = MACDData(
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period
        )
        
        # MACDライン = 高速EMA - 低速EMA
        # 低速EMAの開始インデックスに合わせる
        start_index = slow_period - fast_period
        
        for i in range(len(slow_ema.values)):
            fast_value = fast_ema.values[i + start_index]
            slow_value = slow_ema.values[i]
            macd_value = fast_value - slow_value
            
            macd_data.macd_line.append(macd_value)
            macd_data.dates.append(slow_ema.dates[i])
        
        # シグナルライン（MACDのEMA）
        if len(macd_data.macd_line) >= signal_period:
            # シグナルラインの計算
            multiplier = 2 / (signal_period + 1)
            
            # 初期シグナル値（SMA）
            initial_signal = sum(macd_data.macd_line[:signal_period]) / signal_period
            macd_data.signal_line.append(initial_signal)
            
            # EMAでシグナルライン計算
            for i in range(signal_period, len(macd_data.macd_line)):
                current_macd = macd_data.macd_line[i]
                previous_signal = macd_data.signal_line[-1]
                
                signal_value = (current_macd * multiplier) + (previous_signal * (1 - multiplier))
                macd_data.signal_line.append(signal_value)
        
        # ヒストグラム = MACDライン - シグナルライン
        signal_start_index = signal_period - 1
        for i in range(len(macd_data.signal_line)):
            macd_value = macd_data.macd_line[i + signal_start_index]
            signal_value = macd_data.signal_line[i]
            histogram_value = macd_value - signal_value
            
            macd_data.histogram.append(histogram_value)
        
        return macd_data
    
    def calculate_bollinger_bands(self, 
                                 price_data: List[PriceData], 
                                 period: int = 20, 
                                 std_dev: float = 2.0) -> BollingerBandsData:
        """
        ボリンジャーバンドを計算
        
        Args:
            price_data: 価格データ
            period: 期間
            std_dev: 標準偏差の倍数
            
        Returns:
            BollingerBandsData: ボリンジャーバンドデータ
        """
        if len(price_data) < period:
            return BollingerBandsData(period=period, std_dev=std_dev)
        
        bb_data = BollingerBandsData(period=period, std_dev=std_dev)
        
        for i in range(period - 1, len(price_data)):
            # 期間内の終値
            prices = [price_data[j].close for j in range(i - period + 1, i + 1)]
            
            # 中央線（SMA）
            middle = sum(prices) / period
            
            # 標準偏差
            variance = sum((price - middle) ** 2 for price in prices) / period
            std = math.sqrt(variance)
            
            # 上下バンド
            upper = middle + (std * std_dev)
            lower = middle - (std * std_dev)
            
            bb_data.middle_band.append(middle)
            bb_data.upper_band.append(upper)
            bb_data.lower_band.append(lower)
            bb_data.dates.append(price_data[i].date)
        
        return bb_data
    
    def detect_crossover_signals(self, 
                                short_ma: MovingAverage, 
                                long_ma: MovingAverage, 
                                price_data: List[PriceData]) -> List[CrossoverSignal]:
        """
        移動平均のクロスオーバーシグナルを検出
        
        Args:
            short_ma: 短期移動平均
            long_ma: 長期移動平均
            price_data: 価格データ
            
        Returns:
            List[CrossoverSignal]: クロスオーバーシグナルのリスト
        """
        signals = []
        
        if (len(short_ma.values) < 2 or len(long_ma.values) < 2 or 
            len(short_ma.values) != len(long_ma.values)):
            return signals
        
        # 価格データのインデックス調整
        price_start_index = len(price_data) - len(short_ma.values)
        
        for i in range(1, len(short_ma.values)):
            short_current = short_ma.values[i]
            short_previous = short_ma.values[i-1]
            long_current = long_ma.values[i]
            long_previous = long_ma.values[i-1]
            
            current_price = price_data[price_start_index + i].close
            
            # ゴールデンクロス（短期が長期を上抜け）
            if (short_previous <= long_previous and short_current > long_current):
                signal_strength = min(abs(short_current - long_current) / long_current, 1.0)
                
                signals.append(CrossoverSignal(
                    date=short_ma.dates[i],
                    crossover_type=CrossoverType.GOLDEN_CROSS,
                    price=current_price,
                    signal_strength=signal_strength,
                    description=f"短期MA({short_ma.period})が長期MA({long_ma.period})を上抜け",
                    additional_data={
                        "short_ma_value": short_current,
                        "long_ma_value": long_current,
                        "price_vs_ma": current_price / short_current
                    }
                ))
            
            # デッドクロス（短期が長期を下抜け）
            elif (short_previous >= long_previous and short_current < long_current):
                signal_strength = min(abs(long_current - short_current) / long_current, 1.0)
                
                signals.append(CrossoverSignal(
                    date=short_ma.dates[i],
                    crossover_type=CrossoverType.DEAD_CROSS,
                    price=current_price,
                    signal_strength=signal_strength,
                    description=f"短期MA({short_ma.period})が長期MA({long_ma.period})を下抜け",
                    additional_data={
                        "short_ma_value": short_current,
                        "long_ma_value": long_current,
                        "price_vs_ma": current_price / short_current
                    }
                ))
        
        return signals
    
    def calculate_support_resistance(self, price_data: List[PriceData], 
                                   lookback_period: int = 20,
                                   min_touches: int = 2) -> List[SupportResistanceLevel]:
        """
        サポート・レジスタンスレベルを計算
        
        Args:
            price_data: 価格データ
            lookback_period: 振り返り期間
            min_touches: 最小タッチ回数
            
        Returns:
            List[SupportResistanceLevel]: サポート・レジスタンスレベル
        """
        levels = []
        
        if len(price_data) < lookback_period * 2:
            return levels
        
        # 直近のデータを分析
        recent_data = price_data[-lookback_period * 3:]
        
        # 高値・安値の候補を特定
        highs = []
        lows = []
        
        for i in range(1, len(recent_data) - 1):
            # 局所的な高値
            if (recent_data[i].high > recent_data[i-1].high and 
                recent_data[i].high > recent_data[i+1].high):
                highs.append((recent_data[i].date, recent_data[i].high))
            
            # 局所的な安値
            if (recent_data[i].low < recent_data[i-1].low and 
                recent_data[i].low < recent_data[i+1].low):
                lows.append((recent_data[i].date, recent_data[i].low))
        
        # レジスタンスレベルの計算
        for date, high in highs:
            touch_count = 0
            touches = []
            tolerance = high * 0.02  # 2%の許容範囲
            
            for other_date, other_high in highs:
                if abs(other_high - high) <= tolerance:
                    touch_count += 1
                    touches.append(other_date)
            
            if touch_count >= min_touches:
                strength = min(touch_count / 5.0, 1.0)  # 最大5回で強度1.0
                confidence = min(0.5 + (touch_count - min_touches) * 0.1, 0.9)
                
                levels.append(SupportResistanceLevel(
                    level=high,
                    level_type="resistance",
                    strength=strength,
                    touch_count=touch_count,
                    last_touch_date=max(touches),
                    confidence=confidence
                ))
        
        # サポートレベルの計算
        for date, low in lows:
            touch_count = 0
            touches = []
            tolerance = low * 0.02  # 2%の許容範囲
            
            for other_date, other_low in lows:
                if abs(other_low - low) <= tolerance:
                    touch_count += 1
                    touches.append(other_date)
            
            if touch_count >= min_touches:
                strength = min(touch_count / 5.0, 1.0)
                confidence = min(0.5 + (touch_count - min_touches) * 0.1, 0.9)
                
                levels.append(SupportResistanceLevel(
                    level=low,
                    level_type="support",
                    strength=strength,
                    touch_count=touch_count,
                    last_touch_date=max(touches),
                    confidence=confidence
                ))
        
        # 強度順にソート
        levels.sort(key=lambda x: x.strength, reverse=True)
        
        return levels[:5]  # 上位5つのレベルを返す
    
    def analyze_trend(self, result: TechnicalAnalysisResult) -> TrendDirection:
        """
        トレンド分析
        
        Args:
            result: テクニカル分析結果
            
        Returns:
            TrendDirection: トレンド方向
        """
        bullish_signals = 0
        bearish_signals = 0
        
        # 移動平均の位置関係
        if (result.sma_5 and result.sma_25 and 
            result.sma_5.current_value and result.sma_25.current_value):
            if result.sma_5.current_value > result.sma_25.current_value:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # RSIの状況
        if result.rsi and result.rsi.current_value:
            if result.rsi.current_value > 50:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # MACDの状況
        if (result.macd and result.macd.current_macd and 
            result.macd.current_signal):
            if result.macd.current_macd > result.macd.current_signal:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # 価格とボリンジャーバンドの関係
        if (result.bollinger_bands and result.bollinger_bands.current_middle):
            if result.current_price > result.bollinger_bands.current_middle:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # 総合判定
        if bullish_signals > bearish_signals + 1:
            return TrendDirection.BULLISH
        elif bearish_signals > bullish_signals + 1:
            return TrendDirection.BEARISH
        else:
            return TrendDirection.NEUTRAL
    
    def generate_overall_signal(self, result: TechnicalAnalysisResult) -> Tuple[SignalType, float]:
        """
        総合シグナルを生成
        
        Args:
            result: テクニカル分析結果
            
        Returns:
            Tuple[SignalType, float]: シグナルタイプと強度
        """
        signal_score = 0.0
        max_score = 0.0
        
        # RSI判定
        if result.rsi and result.rsi.current_value:
            max_score += 1.0
            if result.rsi.is_oversold:
                signal_score += 1.0  # 買いシグナル
            elif result.rsi.is_overbought:
                signal_score -= 1.0  # 売りシグナル
            elif 40 <= result.rsi.current_value <= 60:
                signal_score += 0.0  # 中立
            elif result.rsi.current_value > 60:
                signal_score -= 0.5
            else:
                signal_score += 0.5
        
        # MACD判定
        if (result.macd and result.macd.current_macd and 
            result.macd.current_signal):
            max_score += 1.0
            if result.macd.current_macd > result.macd.current_signal:
                signal_score += 0.5
            else:
                signal_score -= 0.5
            
            # ヒストグラムの傾向
            if (result.macd.histogram and len(result.macd.histogram) >= 2):
                if result.macd.histogram[-1] > result.macd.histogram[-2]:
                    signal_score += 0.3
                else:
                    signal_score -= 0.3
        
        # 移動平均判定
        if (result.sma_5 and result.sma_25 and 
            result.sma_5.current_value and result.sma_25.current_value):
            max_score += 1.0
            if result.current_price > result.sma_5.current_value > result.sma_25.current_value:
                signal_score += 1.0
            elif result.current_price < result.sma_5.current_value < result.sma_25.current_value:
                signal_score -= 1.0
            else:
                signal_score += 0.0
        
        # 最近のクロスオーバーシグナル
        if result.crossover_signals:
            recent_signal = result.crossover_signals[-1]
            max_score += 1.0
            if recent_signal.crossover_type == CrossoverType.GOLDEN_CROSS:
                signal_score += recent_signal.signal_strength
            elif recent_signal.crossover_type == CrossoverType.DEAD_CROSS:
                signal_score -= recent_signal.signal_strength
        
        # 正規化
        if max_score > 0:
            normalized_score = signal_score / max_score
        else:
            normalized_score = 0.0
        
        # シグナル決定
        strength = abs(normalized_score)
        
        if normalized_score > 0.6:
            return SignalType.STRONG_BUY, strength
        elif normalized_score > 0.2:
            return SignalType.BUY, strength
        elif normalized_score < -0.6:
            return SignalType.STRONG_SELL, strength
        elif normalized_score < -0.2:
            return SignalType.SELL, strength
        else:
            return SignalType.HOLD, strength
    
    def _calculate_price_change_pct(self, price_data: List[PriceData]) -> float:
        """価格変化率を計算"""
        if len(price_data) < 2:
            return 0.0
        
        current = price_data[-1].close
        previous = price_data[-2].close
        
        return ((current - previous) / previous) * 100 if previous != 0 else 0.0
    
    def _calculate_volume_change_pct(self, volume_data: List[VolumeData]) -> float:
        """出来高変化率を計算"""
        if len(volume_data) < 2:
            return 0.0
        
        current = volume_data[-1].volume
        previous = volume_data[-2].volume
        
        return ((current - previous) / previous) * 100 if previous != 0 else 0.0
    
    def _calculate_volatility(self, price_data: List[PriceData], period: int = 20) -> float:
        """ボラティリティを計算"""
        if len(price_data) < period:
            return 0.0
        
        # 直近period日の日次リターンを計算
        returns = []
        for i in range(len(price_data) - period + 1, len(price_data)):
            if i > 0:
                daily_return = (price_data[i].close / price_data[i-1].close) - 1
                returns.append(daily_return)
        
        if not returns:
            return 0.0
        
        # 標準偏差を計算してボラティリティとする
        mean_return = statistics.mean(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = math.sqrt(variance) * math.sqrt(252)  # 年率化
        
        return volatility * 100  # パーセント表示
    
    def detect_breakout_signals(self, 
                               price_data: List[PriceData], 
                               volume_data: Optional[List[VolumeData]] = None) -> List[BreakoutSignal]:
        """
        ブレイクアウトシグナルを検出
        
        Args:
            price_data: 価格データ
            volume_data: 出来高データ
            
        Returns:
            List[BreakoutSignal]: ブレイクアウトシグナルのリスト
        """
        signals = []
        
        if len(price_data) < 20:
            return signals
        
        # 直近20日間のデータで分析
        recent_data = price_data[-20:]
        current_price = price_data[-1]
        
        # レジスタンスブレイク検出（過去の高値を上抜け）
        for i in range(len(recent_data) - 1):
            past_high = recent_data[i].high
            
            # 現在価格が過去の高値を上抜けしたかチェック
            if (current_price.close > past_high and 
                current_price.high > past_high):
                
                # 出来高急増をチェック
                volume_surge = False
                if volume_data and len(volume_data) >= 2:
                    current_volume = volume_data[-1].volume
                    avg_volume = sum(v.volume for v in volume_data[-5:]) / 5
                    volume_surge = current_volume > avg_volume * 1.5
                
                strength = min((current_price.close - past_high) / past_high * 10, 1.0)
                
                signals.append(BreakoutSignal(
                    date=current_price.date,
                    breakout_type="resistance_break",
                    price=current_price.close,
                    reference_level=past_high,
                    strength=strength,
                    volume_surge=volume_surge,
                    description=f"レジスタンス({past_high:.2f})を上抜け",
                    additional_data={
                        "breakout_gap": current_price.close - past_high,
                        "breakout_pct": (current_price.close - past_high) / past_high * 100,
                        "reference_date": recent_data[i].date
                    }
                ))
                break  # 最初の有効なブレイクアウトのみ
        
        # サポートブレイク検出（過去の安値を下抜け）
        for i in range(len(recent_data) - 1):
            past_low = recent_data[i].low
            
            # 現在価格が過去の安値を下抜けしたかチェック
            if (current_price.close < past_low and 
                current_price.low < past_low):
                
                # 出来高急増をチェック
                volume_surge = False
                if volume_data and len(volume_data) >= 2:
                    current_volume = volume_data[-1].volume
                    avg_volume = sum(v.volume for v in volume_data[-5:]) / 5
                    volume_surge = current_volume > avg_volume * 1.5
                
                strength = min((past_low - current_price.close) / past_low * 10, 1.0)
                
                signals.append(BreakoutSignal(
                    date=current_price.date,
                    breakout_type="support_break",
                    price=current_price.close,
                    reference_level=past_low,
                    strength=strength,
                    volume_surge=volume_surge,
                    description=f"サポート({past_low:.2f})を下抜け",
                    additional_data={
                        "breakout_gap": past_low - current_price.close,
                        "breakout_pct": (past_low - current_price.close) / past_low * 100,
                        "reference_date": recent_data[i].date
                    }
                ))
                break  # 最初の有効なブレイクアウトのみ
        
        return signals
    
    def detect_new_high(self, price_data: List[PriceData], 
                       lookback_periods: List[int] = [20, 50, 100, 200]) -> Tuple[bool, int]:
        """
        新高値を検出
        
        Args:
            price_data: 価格データ
            lookback_periods: 振り返り期間のリスト
            
        Returns:
            Tuple[bool, int]: (新高値かどうか, 何日ぶりの高値か)
        """
        if len(price_data) < 2:
            return False, 0
        
        current_high = price_data[-1].high
        
        for period in lookback_periods:
            if len(price_data) <= period:
                continue
                
            # 過去period日間の最高値
            past_data = price_data[-(period+1):-1]  # 現在日を除く
            max_high = max(data.high for data in past_data)
            
            # 新高値かチェック
            if current_high > max_high:
                return True, period
        
        return False, 0
    
    def detect_new_low(self, price_data: List[PriceData], 
                      lookback_periods: List[int] = [20, 50, 100, 200]) -> Tuple[bool, int]:
        """
        新安値を検出
        
        Args:
            price_data: 価格データ
            lookback_periods: 振り返り期間のリスト
            
        Returns:
            Tuple[bool, int]: (新安値かどうか, 何日ぶりの安値か)
        """
        if len(price_data) < 2:
            return False, 0
        
        current_low = price_data[-1].low
        
        for period in lookback_periods:
            if len(price_data) <= period:
                continue
                
            # 過去period日間の最安値
            past_data = price_data[-(period+1):-1]  # 現在日を除く
            min_low = min(data.low for data in past_data)
            
            # 新安値かチェック
            if current_low < min_low:
                return True, period
        
        return False, 0
    
    def calculate_market_correlation(self, 
                                   price_data: List[PriceData],
                                   reference_data: Optional[List[PriceData]] = None,
                                   period: int = 50) -> Optional[MarketCorrelation]:
        """
        市場相関係数を計算
        
        Args:
            price_data: 対象銘柄の価格データ
            reference_data: 基準銘柄の価格データ（Noneの場合は仮想的な市場データを使用）
            period: 計算期間
            
        Returns:
            MarketCorrelation: 相関データ（計算できない場合はNone）
        """
        if len(price_data) < period:
            return None
        
        # 日次リターンを計算
        target_returns = []
        for i in range(len(price_data) - period + 1, len(price_data)):
            if i > 0:
                daily_return = (price_data[i].close / price_data[i-1].close) - 1
                target_returns.append(daily_return)
        
        if not target_returns:
            return None
        
        # 基準データがない場合は、仮想的な市場データを生成
        # （実際の実装では、日経平均やTOPIXのデータを使用）
        if reference_data is None:
            # シンプルな市場シミュレーション（通常は外部データを使用）
            reference_returns = []
            base_trend = 0.0005  # 基本的な上昇トレンド
            
            for i, target_return in enumerate(target_returns):
                # 市場との相関を模擬（実際の銘柄の動きに基づいて調整）
                market_return = base_trend + (target_return * 0.7) + (
                    (hash(str(i)) % 1000 - 500) / 100000  # ランダム要素
                )
                reference_returns.append(market_return)
            
            reference_symbol = "MARKET_INDEX"
        else:
            # 実際の基準データから計算
            reference_returns = []
            ref_start = len(reference_data) - len(target_returns) - 1
            
            for i in range(len(target_returns)):
                ref_idx = ref_start + i + 1
                if ref_idx < len(reference_data) and ref_start + i >= 0:
                    ref_return = (reference_data[ref_idx].close / reference_data[ref_start + i].close) - 1
                    reference_returns.append(ref_return)
            
            reference_symbol = "REFERENCE_INDEX"
        
        # 相関係数を計算
        if len(target_returns) != len(reference_returns):
            return None
        
        try:
            # ピアソン相関係数の計算
            n = len(target_returns)
            if n < 10:  # 最小サンプル数
                return None
            
            mean_target = sum(target_returns) / n
            mean_reference = sum(reference_returns) / n
            
            numerator = sum((target_returns[i] - mean_target) * (reference_returns[i] - mean_reference) 
                          for i in range(n))
            
            sum_sq_target = sum((target_returns[i] - mean_target) ** 2 for i in range(n))
            sum_sq_reference = sum((reference_returns[i] - mean_reference) ** 2 for i in range(n))
            
            denominator = math.sqrt(sum_sq_target * sum_sq_reference)
            
            if denominator == 0:
                return None
            
            correlation = numerator / denominator
            
            # 信頼度の計算（サンプル数と相関の強さに基づく）
            confidence = min(0.5 + (n / 100) * 0.3 + abs(correlation) * 0.2, 0.95)
            
            # 相関の解釈
            if abs(correlation) > 0.7:
                description = f"市場と{'強い正の' if correlation > 0 else '強い負の'}相関"
            elif abs(correlation) > 0.3:
                description = f"市場と{'中程度の正の' if correlation > 0 else '中程度の負の'}相関"
            else:
                description = "市場との相関は低い"
            
            return MarketCorrelation(
                correlation_coefficient=correlation,
                period_days=len(target_returns),
                reference_symbol=reference_symbol,
                confidence_level=confidence,
                description=description
            )
            
        except (ZeroDivisionError, ValueError):
            return None