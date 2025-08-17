# -*- coding: utf-8 -*-
"""
外部API用モッククラス
"""

import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import random

from src.models.data_models import StockData
from src.models.analysis_models import AnalysisResult, Recommendation, TechnicalIndicators


class MockGoogleSheetsAPI:
    """Google Sheets API モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mock_data = config.get("mock_data", {})
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
    
    async def get_values(self, spreadsheet_id: str, range_name: str) -> List[List[str]]:
        """シートの値を取得（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.5))
        
        # 失敗をシミュレート
        if random.random() < self._failure_rate:
            raise ConnectionError("Google Sheets API connection failed")
        
        # モックデータを返す
        if "portfolio" in range_name.lower():
            return self.mock_data.get("portfolio", [])
        elif "watchlist" in range_name.lower():
            return self.mock_data.get("watchlist", [])
        else:
            return []
    
    async def batch_get(self, spreadsheet_id: str, ranges: List[str]) -> Dict[str, List[List[str]]]:
        """バッチでシートの値を取得（モック）"""
        result = {}
        for range_name in ranges:
            result[range_name] = await self.get_values(spreadsheet_id, range_name)
        return result
    
    async def append_values(self, spreadsheet_id: str, range_name: str, values: List[List[str]]) -> bool:
        """値を追加（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if random.random() < self._failure_rate:
            raise ConnectionError("Google Sheets API write failed")
        
        return True


class MockYahooFinanceAPI:
    """Yahoo Finance API モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mock_data = config.get("mock_data", {})
        self.historical_config = config.get("historical_data_mock", {})
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
    
    async def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """株式情報を取得（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.2, 0.8))
        
        if random.random() < self._failure_rate:
            raise ConnectionError(f"Yahoo Finance API failed for {symbol}")
        
        if symbol in self.mock_data:
            return self.mock_data[symbol]
        else:
            # デフォルトデータを生成
            return self._generate_default_stock_data(symbol)
    
    async def get_historical_data(self, symbol: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
        """履歴データを取得（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        if random.random() < self._failure_rate:
            raise ConnectionError(f"Yahoo Finance historical data failed for {symbol}")
        
        return self._generate_historical_data(symbol, period, interval)
    
    def _generate_default_stock_data(self, symbol: str) -> Dict[str, Any]:
        """デフォルト株式データを生成"""
        base_price = random.uniform(50, 500)
        return {
            "symbol": symbol,
            "regularMarketPrice": base_price,
            "previousClose": base_price * random.uniform(0.95, 1.05),
            "regularMarketOpen": base_price * random.uniform(0.98, 1.02),
            "regularMarketDayHigh": base_price * random.uniform(1.0, 1.05),
            "regularMarketDayLow": base_price * random.uniform(0.95, 1.0),
            "regularMarketVolume": random.randint(1000000, 100000000),
            "marketCap": int(base_price * random.randint(1000000000, 10000000000)),
            "trailingPE": random.uniform(15, 50)
        }
    
    def _generate_historical_data(self, symbol: str, period: str, interval: str) -> List[Dict[str, Any]]:
        """履歴データを生成"""
        # 期間に基づくデータポイント数
        period_days = {
            "1d": 1,
            "5d": 5,
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365
        }
        
        days = period_days.get(period, 30)
        base_price = random.uniform(50, 500)
        data = []
        
        for i in range(days):
            date = datetime.now() - timedelta(days=days-i)
            price_variation = random.uniform(-0.05, 0.05)
            price = base_price * (1 + price_variation)
            
            data.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Open": price * random.uniform(0.98, 1.02),
                "High": price * random.uniform(1.0, 1.05),
                "Low": price * random.uniform(0.95, 1.0),
                "Close": price,
                "Volume": random.randint(1000000, 50000000)
            })
        
        return data


class MockGeminiAPI:
    """Gemini AI API モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mock_responses = config.get("mock_responses", {})
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
    
    async def generate_content(self, prompt: str, analysis_type: str = "daily") -> Dict[str, Any]:
        """コンテンツ生成（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(1.0, 3.0))
        
        if random.random() < self._failure_rate:
            raise ConnectionError("Gemini API failed")
        
        # 分析タイプに基づくレスポンス
        response_key = f"{analysis_type}_analysis"
        if response_key in self.mock_responses:
            return self.mock_responses[response_key]
        
        # デフォルトレスポンス
        return self._generate_default_analysis(analysis_type)
    
    def _generate_default_analysis(self, analysis_type: str) -> Dict[str, Any]:
        """デフォルト分析結果を生成"""
        return {
            "analysis_id": f"mock-{analysis_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "portfolio_summary": f"{analysis_type}分析のモック結果です。",
            "recommendations": [
                {
                    "symbol": "MOCK",
                    "action": "HOLD",
                    "confidence": 0.8,
                    "reasoning": "モック分析による推奨です。",
                    "target_price": 100.0
                }
            ],
            "market_sentiment": "NEUTRAL",
            "risk_assessment": "MEDIUM"
        }


class MockSlackAPI:
    """Slack API モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mock_responses = config.get("mock_responses", {})
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
        self.sent_messages = []  # テスト用のメッセージ履歴
    
    async def send_message(self, webhook_url: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """メッセージ送信（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.5))
        
        if random.random() < self._failure_rate:
            return self.mock_responses.get("failure", {
                "status_code": 400,
                "response": {"error": "mock_failure"}
            })
        
        # メッセージを履歴に保存
        message_record = {
            "webhook_url": webhook_url,
            "message": message,
            "timestamp": datetime.now(),
            "message_id": f"mock-msg-{len(self.sent_messages) + 1}"
        }
        self.sent_messages.append(message_record)
        
        return self.mock_responses.get("success", {
            "status_code": 200,
            "response": {"ok": True}
        })
    
    def get_sent_messages(self) -> List[Dict[str, Any]]:
        """送信されたメッセージ履歴を取得"""
        return self.sent_messages
    
    def clear_message_history(self):
        """メッセージ履歴をクリア"""
        self.sent_messages.clear()


class MockAWSParameterStore:
    """AWS Parameter Store モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mock_parameters = config.get("mock_parameters", {})
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
    
    async def get_parameter(self, name: str, with_decryption: bool = True) -> str:
        """パラメータ取得（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if random.random() < self._failure_rate:
            raise ConnectionError(f"Parameter Store failed for {name}")
        
        if name in self.mock_parameters:
            return self.mock_parameters[name]
        else:
            raise KeyError(f"Parameter {name} not found")
    
    async def get_parameters_by_path(self, path: str, recursive: bool = True, with_decryption: bool = True) -> Dict[str, str]:
        """パス配下のパラメータを取得（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.2, 0.5))
        
        if random.random() < self._failure_rate:
            raise ConnectionError(f"Parameter Store failed for path {path}")
        
        result = {}
        for param_name, param_value in self.mock_parameters.items():
            if param_name.startswith(path):
                result[param_name] = param_value
        
        return result


class MockCloudWatch:
    """CloudWatch モック"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._simulate_delays = config.get("simulate_delays", False)
        self._failure_rate = config.get("failure_rate", 0.0)
        self.logged_metrics = []
        self.logged_events = []
    
    async def put_metric_data(self, namespace: str, metric_data: List[Dict[str, Any]]) -> bool:
        """メトリクス送信（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if random.random() < self._failure_rate:
            raise ConnectionError("CloudWatch put_metric_data failed")
        
        # メトリクスを履歴に保存
        for metric in metric_data:
            self.logged_metrics.append({
                "namespace": namespace,
                "metric": metric,
                "timestamp": datetime.now()
            })
        
        return True
    
    async def put_log_events(self, log_group: str, log_stream: str, events: List[Dict[str, Any]]) -> bool:
        """ログイベント送信（モック）"""
        if self._simulate_delays:
            await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if random.random() < self._failure_rate:
            raise ConnectionError("CloudWatch put_log_events failed")
        
        # ログイベントを履歴に保存
        for event in events:
            self.logged_events.append({
                "log_group": log_group,
                "log_stream": log_stream,
                "event": event,
                "timestamp": datetime.now()
            })
        
        return True
    
    def get_logged_metrics(self) -> List[Dict[str, Any]]:
        """記録されたメトリクスを取得"""
        return self.logged_metrics
    
    def get_logged_events(self) -> List[Dict[str, Any]]:
        """記録されたログイベントを取得"""
        return self.logged_events
    
    def clear_logs(self):
        """ログ履歴をクリア"""
        self.logged_metrics.clear()
        self.logged_events.clear()


# モックファクトリークラス
class MockAPIFactory:
    """モックAPI生成ファクトリー"""
    
    @staticmethod
    def create_google_sheets_mock(config: Dict[str, Any]) -> MockGoogleSheetsAPI:
        """Google Sheets モックを作成"""
        return MockGoogleSheetsAPI(config)
    
    @staticmethod
    def create_yahoo_finance_mock(config: Dict[str, Any]) -> MockYahooFinanceAPI:
        """Yahoo Finance モックを作成"""
        return MockYahooFinanceAPI(config)
    
    @staticmethod
    def create_gemini_mock(config: Dict[str, Any]) -> MockGeminiAPI:
        """Gemini AI モックを作成"""
        return MockGeminiAPI(config)
    
    @staticmethod
    def create_slack_mock(config: Dict[str, Any]) -> MockSlackAPI:
        """Slack モックを作成"""
        return MockSlackAPI(config)
    
    @staticmethod
    def create_parameter_store_mock(config: Dict[str, Any]) -> MockAWSParameterStore:
        """Parameter Store モックを作成"""
        return MockAWSParameterStore(config)
    
    @staticmethod
    def create_cloudwatch_mock(config: Dict[str, Any]) -> MockCloudWatch:
        """CloudWatch モックを作成"""
        return MockCloudWatch(config)
    
    @staticmethod
    def create_all_mocks(test_config: Dict[str, Any]) -> Dict[str, Any]:
        """全てのモックを作成"""
        return {
            "google_sheets": MockAPIFactory.create_google_sheets_mock(
                test_config.get("google_sheets", {})
            ),
            "yahoo_finance": MockAPIFactory.create_yahoo_finance_mock(
                test_config.get("yahoo_finance", {})
            ),
            "gemini": MockAPIFactory.create_gemini_mock(
                test_config.get("gemini", {})
            ),
            "slack": MockAPIFactory.create_slack_mock(
                test_config.get("slack", {})
            ),
            "parameter_store": MockAPIFactory.create_parameter_store_mock(
                test_config.get("aws", {}).get("parameter_store", {})
            ),
            "cloudwatch": MockAPIFactory.create_cloudwatch_mock(
                test_config.get("aws", {}).get("cloudwatch", {})
            )
        }


# テスト用のユーティリティ関数
def create_mock_stock_data_list(symbols: List[str]) -> List[StockData]:
    """テスト用の株式データリストを作成"""
    stock_data_list = []
    for symbol in symbols:
        base_price = random.uniform(50, 500)
        stock_data = StockData(
            symbol=symbol,
            current_price=base_price,
            previous_close=base_price * random.uniform(0.95, 1.05),
            open_price=base_price * random.uniform(0.98, 1.02),
            high_price=base_price * random.uniform(1.0, 1.05),
            low_price=base_price * random.uniform(0.95, 1.0),
            volume=random.randint(1000000, 100000000),
            market_cap=int(base_price * random.randint(1000000000, 10000000000)),
            pe_ratio=random.uniform(15, 50),
            timestamp=datetime.now()
        )
        stock_data_list.append(stock_data)
    
    return stock_data_list


def create_mock_analysis_result(analysis_type: str = "daily") -> AnalysisResult:
    """テスト用の分析結果を作成"""
    return AnalysisResult(
        analysis_id=f"mock-{analysis_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        timestamp=datetime.now(),
        analysis_type=analysis_type,
        portfolio_summary=f"{analysis_type}分析のモック結果です。",
        recommendations=[
            Recommendation(
                symbol="MOCK",
                action="HOLD",
                confidence=0.8,
                reasoning="モック分析による推奨です。",
                target_price=100.0
            )
        ],
        technical_analysis=TechnicalIndicators(
            rsi=65.5,
            macd_signal="BULLISH",
            moving_average_20=95.0,
            moving_average_50=90.0,
            support_level=85.0,
            resistance_level=105.0
        ),
        market_sentiment="NEUTRAL",
        risk_assessment="MEDIUM"
    )