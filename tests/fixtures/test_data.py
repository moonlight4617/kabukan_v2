# -*- coding: utf-8 -*-
"""
テスト用データフィクスチャ
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
import json
import random

from src.models.data_models import StockData, StockConfig, WatchlistStock, Portfolio, StockHolding
from src.models.analysis_models import AnalysisResult, Recommendation, TechnicalIndicators


@dataclass
class TestDataSet:
    """テストデータセット"""
    name: str
    description: str
    portfolio_data: List[Dict[str, Any]]
    watchlist_data: List[Dict[str, Any]]
    stock_data: Dict[str, StockData]
    expected_analysis: AnalysisResult


class TestDataGenerator:
    """テストデータ生成クラス"""
    
    # 実際の株式銘柄のリスト
    REAL_STOCKS = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology", "region": "US"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology", "region": "US"},
        "MSFT": {"name": "Microsoft Corp.", "sector": "Technology", "region": "US"},
        "TSLA": {"name": "Tesla Inc.", "sector": "Automotive", "region": "US"},
        "AMZN": {"name": "Amazon.com Inc.", "sector": "E-commerce", "region": "US"},
        "NVDA": {"name": "NVIDIA Corp.", "sector": "Technology", "region": "US"},
        "META": {"name": "Meta Platforms Inc.", "sector": "Technology", "region": "US"},
        "NFLX": {"name": "Netflix Inc.", "sector": "Entertainment", "region": "US"},
        "AMD": {"name": "Advanced Micro Devices", "sector": "Technology", "region": "US"},
        "CRM": {"name": "Salesforce Inc.", "sector": "Technology", "region": "US"}
    }
    
    @classmethod
    def generate_stock_data(cls, symbol: str, base_price: float = None) -> StockData:
        """株式データを生成"""
        if base_price is None:
            base_price = random.uniform(50, 500)
        
        previous_close = base_price * random.uniform(0.95, 1.05)
        current_price = base_price
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100 if previous_close > 0 else 0
        
        return StockData(
            symbol=symbol,
            current_price=current_price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            volume=random.randint(1000000, 100000000),
            timestamp=datetime.now(),
            market_cap=int(current_price * random.randint(1000000000, 10000000000)),
            pe_ratio=random.uniform(15, 50),
            dividend_yield=random.uniform(0, 5)
        )
    
    @classmethod
    def generate_portfolio_entry(cls, symbol: str, shares: int = None, purchase_price: float = None) -> Dict[str, Any]:
        """ポートフォリオエントリを生成"""
        stock_info = cls.REAL_STOCKS.get(symbol, {"name": f"{symbol} Corp.", "sector": "Unknown", "region": "US"})
        
        return {
            "symbol": symbol,
            "name": stock_info["name"],
            "shares": shares or random.randint(10, 500),
            "purchase_price": purchase_price or random.uniform(50, 500),
            "purchase_date": (datetime.now() - timedelta(days=random.randint(30, 365))).strftime("%Y-%m-%d"),
            "region": stock_info["region"],
            "sector": stock_info["sector"]
        }
    
    @classmethod
    def generate_watchlist_entry(cls, symbol: str, target_price: float = None) -> Dict[str, Any]:
        """ウォッチリストエントリを生成"""
        stock_info = cls.REAL_STOCKS.get(symbol, {"name": f"{symbol} Corp.", "sector": "Unknown", "region": "US"})
        
        return {
            "symbol": symbol,
            "name": stock_info["name"],
            "target_price": target_price or random.uniform(100, 600),
            "region": stock_info["region"],
            "sector": stock_info["sector"],
            "priority": random.choice(["high", "medium", "low"])
        }
    
    @classmethod
    def generate_technical_indicators(cls, symbol: str = "MOCK") -> TechnicalIndicators:
        """テクニカル指標を生成"""
        base_price = random.uniform(50, 500)
        return TechnicalIndicators(
            rsi=random.uniform(30, 70),
            macd_signal=random.choice(["BULLISH", "BEARISH", "NEUTRAL"]),
            moving_average_20=base_price * random.uniform(0.95, 1.05),
            moving_average_50=base_price * random.uniform(0.90, 1.10),
            support_level=base_price * random.uniform(0.85, 0.95),
            resistance_level=base_price * random.uniform(1.05, 1.15)
        )
    
    @classmethod
    def generate_recommendation(cls, symbol: str, action: str = None) -> Recommendation:
        """推奨を生成"""
        actions = ["BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"]
        selected_action = action or random.choice(actions)
        
        reasoning_map = {
            "BUY": f"{symbol}の技術的指標とファンダメンタルズが良好で、購入を推奨します。",
            "SELL": f"{symbol}の短期的な調整が予想され、売却を推奨します。",
            "HOLD": f"{symbol}は現在の価格で安定しており、継続保有を推奨します。",
            "STRONG_BUY": f"{symbol}は強い上昇トレンドにあり、積極的な購入を推奨します。",
            "STRONG_SELL": f"{symbol}は大幅な下落リスクがあり、即座の売却を推奨します。"
        }
        
        return Recommendation(
            symbol=symbol,
            action=selected_action,
            confidence=random.uniform(0.6, 0.95),
            reasoning=reasoning_map.get(selected_action, f"{selected_action} recommendation for {symbol}"),
            target_price=random.uniform(100, 600)
        )
    
    @classmethod
    def generate_analysis_result(cls, analysis_type: str = "daily", symbols: List[str] = None) -> AnalysisResult:
        """分析結果を生成"""
        if symbols is None:
            symbols = random.sample(list(cls.REAL_STOCKS.keys()), random.randint(2, 5))
        
        recommendations = [cls.generate_recommendation(symbol) for symbol in symbols]
        
        summaries = {
            "daily": "本日の市場は全体的に良好なパフォーマンスを示しており、技術株が特に堅調です。",
            "weekly": "今週のポートフォリオは安定した成長を維持しており、長期投資戦略が効果的です。",
            "monthly": "月次分析では、分散投資効果により安定したリターンを実現しています。"
        }
        
        return AnalysisResult(
            analysis_id=f"test-{analysis_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(),
            analysis_type=analysis_type,
            portfolio_summary=summaries.get(analysis_type, "テスト用の分析結果です。"),
            recommendations=recommendations,
            technical_analysis=cls.generate_technical_indicators(),
            market_sentiment=random.choice(["POSITIVE", "NEGATIVE", "NEUTRAL"]),
            risk_assessment=random.choice(["LOW", "MEDIUM", "HIGH"])
        )


# 事前定義されたテストデータセット
class PreDefinedTestData:
    """事前定義されたテストデータ"""
    
    @classmethod
    def get_standard_dataset(cls) -> TestDataSet:
        """標準的なテストデータセット"""
        portfolio_symbols = ["AAPL", "GOOGL", "MSFT"]
        watchlist_symbols = ["TSLA", "NVDA", "AMD"]
        
        portfolio_data = [
            TestDataGenerator.generate_portfolio_entry("AAPL", 100, 150.0),
            TestDataGenerator.generate_portfolio_entry("GOOGL", 50, 2800.0),
            TestDataGenerator.generate_portfolio_entry("MSFT", 75, 300.0)
        ]
        
        watchlist_data = [
            TestDataGenerator.generate_watchlist_entry("TSLA", 220.0),
            TestDataGenerator.generate_watchlist_entry("NVDA", 800.0),
            TestDataGenerator.generate_watchlist_entry("AMD", 120.0)
        ]
        
        stock_data = {}
        for symbol in portfolio_symbols + watchlist_symbols:
            stock_data[symbol] = TestDataGenerator.generate_stock_data(symbol)
        
        expected_analysis = TestDataGenerator.generate_analysis_result(
            "daily", portfolio_symbols + watchlist_symbols
        )
        
        return TestDataSet(
            name="standard",
            description="標準的なテストシナリオ用データセット",
            portfolio_data=portfolio_data,
            watchlist_data=watchlist_data,
            stock_data=stock_data,
            expected_analysis=expected_analysis
        )
    
    @classmethod
    def get_large_portfolio_dataset(cls) -> TestDataSet:
        """大規模ポートフォリオテストデータセット"""
        all_symbols = list(TestDataGenerator.REAL_STOCKS.keys())
        portfolio_symbols = all_symbols[:7]
        watchlist_symbols = all_symbols[7:]
        
        portfolio_data = [
            TestDataGenerator.generate_portfolio_entry(symbol) 
            for symbol in portfolio_symbols
        ]
        
        watchlist_data = [
            TestDataGenerator.generate_watchlist_entry(symbol) 
            for symbol in watchlist_symbols
        ]
        
        stock_data = {}
        for symbol in all_symbols:
            stock_data[symbol] = TestDataGenerator.generate_stock_data(symbol)
        
        expected_analysis = TestDataGenerator.generate_analysis_result(
            "monthly", all_symbols
        )
        
        return TestDataSet(
            name="large_portfolio",
            description="大規模ポートフォリオ用テストデータセット",
            portfolio_data=portfolio_data,
            watchlist_data=watchlist_data,
            stock_data=stock_data,
            expected_analysis=expected_analysis
        )
    
    @classmethod
    def get_volatile_market_dataset(cls) -> TestDataSet:
        """ボラティルな市場状況テストデータセット"""
        symbols = ["AAPL", "TSLA", "NVDA", "AMD"]
        
        portfolio_data = [
            TestDataGenerator.generate_portfolio_entry("AAPL", 100, 150.0),
            TestDataGenerator.generate_portfolio_entry("TSLA", 50, 200.0)
        ]
        
        watchlist_data = [
            TestDataGenerator.generate_watchlist_entry("NVDA", 800.0),
            TestDataGenerator.generate_watchlist_entry("AMD", 120.0)
        ]
        
        # ボラティルな株価データを生成
        stock_data = {}
        for symbol in symbols:
            base_price = random.uniform(100, 400)
            stock_data[symbol] = StockData(
                symbol=symbol,
                current_price=base_price,
                previous_close=base_price * random.uniform(0.85, 1.15),  # 大きな変動
                change=base_price * random.uniform(-0.15, 0.15),
                change_percent=random.uniform(-15, 15),
                volume=random.randint(50000000, 200000000),  # 高い出来高
                timestamp=datetime.now(),
                market_cap=int(base_price * random.randint(500000000, 5000000000)),
                pe_ratio=random.uniform(50, 150),  # 高いPE比
                dividend_yield=random.uniform(0, 2)
            )
        
        # ボラティルな市場用の分析結果
        volatile_analysis = AnalysisResult(
            analysis_id=f"test-volatile-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp=datetime.now(),
            analysis_type="daily",
            portfolio_summary="市場の高いボラティリティにより、慎重な投資判断が必要です。",
            recommendations=[
                Recommendation(
                    symbol="AAPL",
                    action="HOLD",
                    confidence=0.6,
                    reasoning="市場の不安定性により、現状維持を推奨します。",
                    target_price=160.0
                ),
                Recommendation(
                    symbol="TSLA",
                    action="SELL",
                    confidence=0.8,
                    reasoning="高いボラティリティとバリュエーション懸念により売却を推奨します。",
                    target_price=180.0
                )
            ],
            technical_analysis=TechnicalIndicators(
                rsi=75.0,  # 過買い状態
                macd_signal="BEARISH",
                moving_average_20=200.0,
                moving_average_50=190.0,
                support_level=180.0,
                resistance_level=220.0
            ),
            market_sentiment="NEGATIVE",
            risk_assessment="HIGH"
        )
        
        return TestDataSet(
            name="volatile_market",
            description="ボラティルな市場状況用テストデータセット",
            portfolio_data=portfolio_data,
            watchlist_data=watchlist_data,
            stock_data=stock_data,
            expected_analysis=volatile_analysis
        )
    
    @classmethod
    def get_error_scenario_dataset(cls) -> TestDataSet:
        """エラーシナリオテストデータセット"""
        # 不正なデータを含むテストセット
        portfolio_data = [
            {
                "symbol": "",  # 空の銘柄コード
                "name": "Invalid Stock",
                "shares": 100,
                "purchase_price": 150.0,
                "purchase_date": "2024-01-01",
                "region": "US",
                "sector": "Technology"
            },
            {
                "symbol": "VALID",
                "name": "Valid Stock",
                "shares": -50,  # 負の株数
                "purchase_price": 100.0,
                "purchase_date": "invalid-date",  # 不正な日付
                "region": "US",
                "sector": "Technology"
            }
        ]
        
        watchlist_data = [
            {
                "symbol": "INVALID",
                "name": "",  # 空の名前
                "target_price": -100.0,  # 負の目標価格
                "region": "US",
                "sector": "Technology",
                "priority": "invalid_priority"  # 不正な優先度
            }
        ]
        
        stock_data = {
            "INVALID": StockData(
                symbol="INVALID",
                current_price=-100.0,  # 負の価格
                previous_close=100.0,
                change=-200.0,
                change_percent=-200.0,
                volume=-1000000,  # 負の出来高
                timestamp=datetime.now(),
                market_cap=1000000000,
                pe_ratio=25.0
            )
        }
        
        # エラー用の分析結果
        error_analysis = AnalysisResult(
            analysis_id="test-error-001",
            timestamp=datetime.now(),
            analysis_type="daily",
            portfolio_summary="データエラーが発生しました。",
            recommendations=[],
            technical_analysis=None,
            market_sentiment="UNKNOWN",
            risk_assessment="UNKNOWN"
        )
        
        return TestDataSet(
            name="error_scenario",
            description="エラーシナリオ用テストデータセット",
            portfolio_data=portfolio_data,
            watchlist_data=watchlist_data,
            stock_data=stock_data,
            expected_analysis=error_analysis
        )


# テストデータファクトリー
class TestDataFactory:
    """テストデータファクトリー"""
    
    _datasets = {
        "standard": PreDefinedTestData.get_standard_dataset,
        "large_portfolio": PreDefinedTestData.get_large_portfolio_dataset,
        "volatile_market": PreDefinedTestData.get_volatile_market_dataset,
        "error_scenario": PreDefinedTestData.get_error_scenario_dataset
    }
    
    @classmethod
    def get_dataset(cls, name: str) -> TestDataSet:
        """指定されたテストデータセットを取得"""
        if name not in cls._datasets:
            raise ValueError(f"Unknown dataset: {name}. Available: {list(cls._datasets.keys())}")
        
        return cls._datasets[name]()
    
    @classmethod
    def get_all_datasets(cls) -> Dict[str, TestDataSet]:
        """全てのテストデータセットを取得"""
        return {name: factory() for name, factory in cls._datasets.items()}
    
    @classmethod
    def create_custom_dataset(cls, portfolio_symbols: List[str], watchlist_symbols: List[str], 
                              analysis_type: str = "daily") -> TestDataSet:
        """カスタムテストデータセットを作成"""
        portfolio_data = [
            TestDataGenerator.generate_portfolio_entry(symbol) 
            for symbol in portfolio_symbols
        ]
        
        watchlist_data = [
            TestDataGenerator.generate_watchlist_entry(symbol) 
            for symbol in watchlist_symbols
        ]
        
        stock_data = {}
        all_symbols = portfolio_symbols + watchlist_symbols
        for symbol in all_symbols:
            stock_data[symbol] = TestDataGenerator.generate_stock_data(symbol)
        
        expected_analysis = TestDataGenerator.generate_analysis_result(analysis_type, all_symbols)
        
        return TestDataSet(
            name="custom",
            description="カスタムテストデータセット",
            portfolio_data=portfolio_data,
            watchlist_data=watchlist_data,
            stock_data=stock_data,
            expected_analysis=expected_analysis
        )


# JSON形式でのテストデータエクスポート/インポート
class TestDataIO:
    """テストデータの入出力"""
    
    @staticmethod
    def export_dataset_to_json(dataset: TestDataSet, file_path: str):
        """テストデータセットをJSONファイルにエクスポート"""
        data = {
            "name": dataset.name,
            "description": dataset.description,
            "portfolio_data": dataset.portfolio_data,
            "watchlist_data": dataset.watchlist_data,
            "stock_data": {
                symbol: {
                    "symbol": stock.symbol,
                    "current_price": stock.current_price,
                    "previous_close": stock.previous_close,
                    "change": stock.change,
                    "change_percent": stock.change_percent,
                    "volume": stock.volume,
                    "timestamp": stock.timestamp.isoformat(),
                    "market_cap": stock.market_cap,
                    "pe_ratio": stock.pe_ratio,
                    "dividend_yield": stock.dividend_yield
                }
                for symbol, stock in dataset.stock_data.items()
            },
            "expected_analysis": {
                "analysis_id": dataset.expected_analysis.analysis_id,
                "timestamp": dataset.expected_analysis.timestamp.isoformat(),
                "analysis_type": dataset.expected_analysis.analysis_type,
                "portfolio_summary": dataset.expected_analysis.portfolio_summary,
                "market_sentiment": dataset.expected_analysis.market_sentiment,
                "risk_assessment": dataset.expected_analysis.risk_assessment
            }
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def import_dataset_from_json(file_path: str) -> TestDataSet:
        """JSONファイルからテストデータセットをインポート"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # StockDataオブジェクトを復元
        stock_data = {}
        for symbol, stock_dict in data["stock_data"].items():
            stock_data[symbol] = StockData(
                symbol=stock_dict["symbol"],
                current_price=stock_dict["current_price"],
                previous_close=stock_dict["previous_close"],
                change=stock_dict["change"],
                change_percent=stock_dict["change_percent"],
                volume=stock_dict["volume"],
                timestamp=datetime.fromisoformat(stock_dict["timestamp"]),
                market_cap=stock_dict.get("market_cap"),
                pe_ratio=stock_dict.get("pe_ratio"),
                dividend_yield=stock_dict.get("dividend_yield")
            )
        
        # AnalysisResultオブジェクトを復元（簡略版）
        analysis_dict = data["expected_analysis"]
        expected_analysis = AnalysisResult(
            analysis_id=analysis_dict["analysis_id"],
            timestamp=datetime.fromisoformat(analysis_dict["timestamp"]),
            analysis_type=analysis_dict["analysis_type"],
            portfolio_summary=analysis_dict["portfolio_summary"],
            recommendations=[],  # 簡略化
            market_sentiment=analysis_dict["market_sentiment"],
            risk_assessment=analysis_dict["risk_assessment"]
        )
        
        return TestDataSet(
            name=data["name"],
            description=data["description"],
            portfolio_data=data["portfolio_data"],
            watchlist_data=data["watchlist_data"],
            stock_data=stock_data,
            expected_analysis=expected_analysis
        )