"""
CloudWatch カスタムメトリクス送信機能

株式分析システムの運用監視用のカスタムメトリクスを
CloudWatchに送信するためのクラス
"""

import boto3
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """メトリクスデータクラス"""
    name: str
    value: float
    unit: str = 'Count'
    dimensions: Optional[Dict[str, str]] = None
    timestamp: Optional[datetime] = None


class MetricsPublisher:
    """CloudWatch カスタムメトリクス送信クラス"""
    
    def __init__(self, namespace: str = "Custom/StockAnalysis", environment: str = "dev"):
        """
        初期化
        
        Args:
            namespace: CloudWatchの名前空間
            environment: 環境名（dev/staging/prod）
        """
        self.namespace = namespace
        self.environment = environment
        self.cloudwatch = boto3.client('cloudwatch')
        self.batch_metrics: List[Metric] = []
        
    def put_metric(self, 
                   metric_name: str, 
                   value: float, 
                   unit: str = 'Count',
                   dimensions: Optional[Dict[str, str]] = None) -> None:
        """
        メトリクスを送信
        
        Args:
            metric_name: メトリクス名
            value: 値
            unit: 単位
            dimensions: ディメンション
        """
        try:
            # デフォルトディメンションを追加
            default_dimensions = {'Environment': self.environment}
            if dimensions:
                default_dimensions.update(dimensions)
            
            # CloudWatchディメンション形式に変換
            cloudwatch_dimensions = [
                {'Name': key, 'Value': value} 
                for key, value in default_dimensions.items()
            ]
            
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': unit,
                        'Dimensions': cloudwatch_dimensions,
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
            
            logger.info(f"Metric sent: {metric_name}={value} {unit} {default_dimensions}")
            
        except Exception as e:
            logger.error(f"Failed to send metric {metric_name}: {str(e)}")
    
    def add_to_batch(self, 
                     metric_name: str, 
                     value: float, 
                     unit: str = 'Count',
                     dimensions: Optional[Dict[str, str]] = None) -> None:
        """
        バッチ送信用にメトリクスを追加
        
        Args:
            metric_name: メトリクス名
            value: 値
            unit: 単位
            dimensions: ディメンション
        """
        # デフォルトディメンションを追加
        default_dimensions = {'Environment': self.environment}
        if dimensions:
            default_dimensions.update(dimensions)
            
        metric = Metric(
            name=metric_name,
            value=value,
            unit=unit,
            dimensions=default_dimensions,
            timestamp=datetime.utcnow()
        )
        
        self.batch_metrics.append(metric)
        
        # バッチサイズ制限（CloudWatchは最大20メトリクス）
        if len(self.batch_metrics) >= 20:
            self.flush_batch()
    
    def flush_batch(self) -> None:
        """バッチ送信されたメトリクスを送信"""
        if not self.batch_metrics:
            return
        
        try:
            metric_data = []
            for metric in self.batch_metrics:
                cloudwatch_dimensions = [
                    {'Name': key, 'Value': value} 
                    for key, value in metric.dimensions.items()
                ]
                
                metric_data.append({
                    'MetricName': metric.name,
                    'Value': metric.value,
                    'Unit': metric.unit,
                    'Dimensions': cloudwatch_dimensions,
                    'Timestamp': metric.timestamp
                })
            
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            logger.info(f"Batch metrics sent: {len(self.batch_metrics)} metrics")
            self.batch_metrics.clear()
            
        except Exception as e:
            logger.error(f"Failed to send batch metrics: {str(e)}")
            # 失敗したメトリクスはクリアして再送を防ぐ
            self.batch_metrics.clear()
    
    def record_analysis_success(self, analysis_type: str, duration: float = None) -> None:
        """分析成功メトリクスを記録"""
        self.add_to_batch(
            'AnalysisSuccess',
            1,
            'Count',
            {'AnalysisType': analysis_type}
        )
        
        if duration is not None:
            self.add_to_batch(
                'AnalysisDuration',
                duration,
                'Seconds',
                {'AnalysisType': analysis_type}
            )
    
    def record_analysis_failure(self, analysis_type: str, error_type: str = None) -> None:
        """分析失敗メトリクスを記録"""
        dimensions = {'AnalysisType': analysis_type}
        if error_type:
            dimensions['ErrorType'] = error_type
            
        self.add_to_batch(
            'AnalysisFailure',
            1,
            'Count',
            dimensions
        )
    
    def record_api_call(self, api_name: str, status: str, duration: float = None) -> None:
        """API呼び出しメトリクスを記録"""
        self.add_to_batch(
            f'{api_name}APICall',
            1,
            'Count',
            {'Status': status}
        )
        
        if status == 'error':
            self.add_to_batch(
                f'{api_name}APIError',
                1,
                'Count'
            )
        
        if duration is not None:
            self.add_to_batch(
                f'{api_name}APIDuration',
                duration,
                'Seconds',
                {'Status': status}
            )
    
    def record_notification_sent(self, notification_type: str = 'slack') -> None:
        """通知送信成功メトリクスを記録"""
        self.add_to_batch(
            f'{notification_type.title()}NotificationSent',
            1,
            'Count'
        )
    
    def record_notification_failed(self, notification_type: str = 'slack', error_type: str = None) -> None:
        """通知送信失敗メトリクスを記録"""
        dimensions = {}
        if error_type:
            dimensions['ErrorType'] = error_type
            
        self.add_to_batch(
            f'{notification_type.title()}NotificationFailed',
            1,
            'Count',
            dimensions
        )
    
    def record_portfolio_metrics(self, 
                                portfolio_value: float,
                                analyzed_stocks: int,
                                watchlist_stocks: int) -> None:
        """ポートフォリオメトリクスを記録"""
        self.add_to_batch('PortfolioValue', portfolio_value, 'None')
        self.add_to_batch('AnalyzedStocks', analyzed_stocks, 'Count')
        self.add_to_batch('WatchlistStocks', watchlist_stocks, 'Count')
    
    def record_business_metrics(self, 
                               total_trades_suggested: int,
                               profitable_trades: int,
                               accuracy_rate: float) -> None:
        """ビジネスメトリクスを記録"""
        self.add_to_batch('TotalTradesSuggested', total_trades_suggested, 'Count')
        self.add_to_batch('ProfitableTrades', profitable_trades, 'Count')
        self.add_to_batch('AccuracyRate', accuracy_rate, 'Percent')


class MetricsDecorator:
    """メトリクス送信用デコレータ"""
    
    def __init__(self, metrics_publisher: MetricsPublisher):
        self.metrics = metrics_publisher
    
    def track_execution(self, metric_prefix: str, analysis_type: str = None):
        """関数実行を追跡するデコレータ"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    
                    # 成功メトリクス
                    duration = time.time() - start_time
                    if analysis_type:
                        self.metrics.record_analysis_success(analysis_type, duration)
                    else:
                        self.metrics.add_to_batch(
                            f'{metric_prefix}Success',
                            1,
                            'Count'
                        )
                        self.metrics.add_to_batch(
                            f'{metric_prefix}Duration',
                            duration,
                            'Seconds'
                        )
                    
                    return result
                    
                except Exception as e:
                    # 失敗メトリクス
                    error_type = type(e).__name__
                    if analysis_type:
                        self.metrics.record_analysis_failure(analysis_type, error_type)
                    else:
                        self.metrics.add_to_batch(
                            f'{metric_prefix}Failure',
                            1,
                            'Count',
                            {'ErrorType': error_type}
                        )
                    
                    raise
                finally:
                    # バッチメトリクスをフラッシュ
                    self.metrics.flush_batch()
            
            return wrapper
        return decorator
    
    def track_api_call(self, api_name: str):
        """API呼び出しを追跡するデコレータ"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    self.metrics.record_api_call(api_name, 'success', duration)
                    return result
                    
                except Exception as e:
                    duration = time.time() - start_time
                    self.metrics.record_api_call(api_name, 'error', duration)
                    raise
                finally:
                    self.metrics.flush_batch()
            
            return wrapper
        return decorator


# シングルトンインスタンス（環境変数から環境名を取得）
import os
_environment = os.environ.get('ENVIRONMENT', 'dev')
metrics_publisher = MetricsPublisher(environment=_environment)
metrics_decorator = MetricsDecorator(metrics_publisher)