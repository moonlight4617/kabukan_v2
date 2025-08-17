"""
パフォーマンス監視とコスト最適化

システムのパフォーマンス指標を監視し、
コスト最適化のための提案を行う
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import boto3
import logging
from .metrics_publisher import MetricsPublisher
from .alert_manager import AlertManager, AlertSeverity

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """パフォーマンスメトリクスデータクラス"""
    timestamp: datetime
    function_name: str
    duration: float
    memory_used: float
    memory_allocated: float
    billed_duration: float
    cold_start: bool
    error_count: int
    invocation_count: int


@dataclass
class CostMetrics:
    """コストメトリクスデータクラス"""
    timestamp: datetime
    function_name: str
    total_requests: int
    total_duration_ms: int
    total_memory_gb_seconds: float
    estimated_cost: float
    cost_per_request: float


class PerformanceMonitor:
    """パフォーマンス監視クラス"""
    
    def __init__(self, environment: str = "dev"):
        """
        初期化
        
        Args:
            environment: 環境名
        """
        self.environment = environment
        self.function_name = f"stock-analysis-{environment}"
        
        # AWS クライアント
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs = boto3.client('logs')
        self.lambda_client = boto3.client('lambda')
        self.ce = boto3.client('ce')  # Cost Explorer
        
        # 監視設定
        self.metrics = MetricsPublisher(environment=environment)
        self.alert_manager = AlertManager(environment=environment)
        
        # パフォーマンス閾値
        self.thresholds = {
            'duration_warning': 60,     # 60秒で警告
            'duration_critical': 120,   # 120秒でクリティカル
            'memory_usage_warning': 80, # 80%でメモリ使用率警告
            'memory_usage_critical': 95, # 95%でメモリ使用率クリティカル
            'error_rate_warning': 5,    # 5%でエラー率警告
            'error_rate_critical': 10,  # 10%でエラー率クリティカル
            'cold_start_rate_warning': 20, # 20%でコールドスタート率警告
            'cost_increase_warning': 20,    # 20%でコスト増加警告
            'cost_increase_critical': 50,   # 50%でコスト増加クリティカル
        }
    
    def collect_performance_metrics(self, hours_back: int = 1) -> List[PerformanceMetrics]:
        """
        パフォーマンスメトリクスを収集
        
        Args:
            hours_back: 過去何時間分のデータを取得するか
            
        Returns:
            パフォーマンスメトリクスのリスト
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        
        metrics = []
        
        try:
            # CloudWatchからメトリクスを取得
            duration_data = self._get_cloudwatch_metric(
                'AWS/Lambda', 'Duration', start_time, end_time
            )
            
            memory_data = self._get_cloudwatch_metric(
                'AWS/Lambda', 'MemoryUtilization', start_time, end_time
            )
            
            error_data = self._get_cloudwatch_metric(
                'AWS/Lambda', 'Errors', start_time, end_time
            )
            
            invocation_data = self._get_cloudwatch_metric(
                'AWS/Lambda', 'Invocations', start_time, end_time
            )
            
            # Lambda設定情報を取得
            function_config = self.lambda_client.get_function(
                FunctionName=self.function_name
            )
            memory_allocated = function_config['Configuration']['MemorySize']
            
            # データを統合
            for i, timestamp in enumerate([dp['Timestamp'] for dp in duration_data]):
                try:
                    duration = duration_data[i]['Average'] if i < len(duration_data) else 0
                    memory_util = memory_data[i]['Average'] if i < len(memory_data) else 0
                    errors = error_data[i]['Sum'] if i < len(error_data) else 0
                    invocations = invocation_data[i]['Sum'] if i < len(invocation_data) else 0
                    
                    # メモリ使用量を計算
                    memory_used = (memory_util / 100) * memory_allocated
                    
                    # コールドスタート検出（簡略化）
                    cold_start = duration > 5000  # 5秒以上は潜在的なコールドスタート
                    
                    metrics.append(PerformanceMetrics(
                        timestamp=timestamp,
                        function_name=self.function_name,
                        duration=duration,
                        memory_used=memory_used,
                        memory_allocated=memory_allocated,
                        billed_duration=max(100, duration),  # 最小100ms
                        cold_start=cold_start,
                        error_count=int(errors),
                        invocation_count=int(invocations)
                    ))
                    
                except (IndexError, KeyError) as e:
                    logger.warning(f"Error processing metrics at index {i}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {str(e)}")
            # アラートを作成
            self.alert_manager.create_alert(
                title="Performance Metrics Collection Failed",
                description=f"Failed to collect performance metrics: {str(e)}",
                severity=AlertSeverity.MEDIUM,
                source="PerformanceMonitor",
                metadata={"error": str(e), "function": self.function_name}
            )
        
        return metrics
    
    def analyze_performance(self, metrics: List[PerformanceMetrics]) -> Dict[str, Any]:
        """
        パフォーマンス分析を実行
        
        Args:
            metrics: パフォーマンスメトリクスのリスト
            
        Returns:
            分析結果
        """
        if not metrics:
            return {"status": "no_data", "recommendations": []}
        
        analysis = {
            "timestamp": datetime.utcnow().isoformat(),
            "function_name": self.function_name,
            "metrics_count": len(metrics),
            "performance_summary": {},
            "alerts": [],
            "recommendations": []
        }
        
        # 基本統計を計算
        durations = [m.duration for m in metrics]
        memory_utilizations = [(m.memory_used / m.memory_allocated * 100) for m in metrics]
        error_counts = [m.error_count for m in metrics]
        invocation_counts = [m.invocation_count for m in metrics]
        cold_starts = [m.cold_start for m in metrics]
        
        # サマリー統計
        analysis["performance_summary"] = {
            "avg_duration": sum(durations) / len(durations),
            "max_duration": max(durations),
            "min_duration": min(durations),
            "p95_duration": self._percentile(durations, 95),
            "p99_duration": self._percentile(durations, 99),
            "avg_memory_utilization": sum(memory_utilizations) / len(memory_utilizations),
            "max_memory_utilization": max(memory_utilizations),
            "total_errors": sum(error_counts),
            "total_invocations": sum(invocation_counts),
            "error_rate": (sum(error_counts) / max(sum(invocation_counts), 1)) * 100,
            "cold_start_rate": (sum(cold_starts) / len(cold_starts)) * 100
        }
        
        # 閾値チェックとアラート生成
        summary = analysis["performance_summary"]
        
        # 実行時間チェック
        if summary["p95_duration"] > self.thresholds["duration_critical"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Duration Critical",
                description=f"P95 duration ({summary['p95_duration']:.1f}ms) exceeds critical threshold",
                severity=AlertSeverity.CRITICAL,
                source="PerformanceMonitor",
                metadata={"p95_duration": summary["p95_duration"], "threshold": self.thresholds["duration_critical"]}
            )
            analysis["alerts"].append(alert.to_dict())
        elif summary["p95_duration"] > self.thresholds["duration_warning"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Duration Warning",
                description=f"P95 duration ({summary['p95_duration']:.1f}ms) exceeds warning threshold",
                severity=AlertSeverity.MEDIUM,
                source="PerformanceMonitor",
                metadata={"p95_duration": summary["p95_duration"], "threshold": self.thresholds["duration_warning"]}
            )
            analysis["alerts"].append(alert.to_dict())
        
        # メモリ使用率チェック
        if summary["max_memory_utilization"] > self.thresholds["memory_usage_critical"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Memory Usage Critical",
                description=f"Memory usage ({summary['max_memory_utilization']:.1f}%) exceeds critical threshold",
                severity=AlertSeverity.CRITICAL,
                source="PerformanceMonitor",
                metadata={"memory_usage": summary["max_memory_utilization"], "threshold": self.thresholds["memory_usage_critical"]}
            )
            analysis["alerts"].append(alert.to_dict())
        elif summary["max_memory_utilization"] > self.thresholds["memory_usage_warning"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Memory Usage Warning",
                description=f"Memory usage ({summary['max_memory_utilization']:.1f}%) exceeds warning threshold",
                severity=AlertSeverity.MEDIUM,
                source="PerformanceMonitor",
                metadata={"memory_usage": summary["max_memory_utilization"], "threshold": self.thresholds["memory_usage_warning"]}
            )
            analysis["alerts"].append(alert.to_dict())
        
        # エラー率チェック
        if summary["error_rate"] > self.thresholds["error_rate_critical"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Error Rate Critical",
                description=f"Error rate ({summary['error_rate']:.1f}%) exceeds critical threshold",
                severity=AlertSeverity.CRITICAL,
                source="PerformanceMonitor",
                metadata={"error_rate": summary["error_rate"], "threshold": self.thresholds["error_rate_critical"]}
            )
            analysis["alerts"].append(alert.to_dict())
        elif summary["error_rate"] > self.thresholds["error_rate_warning"]:
            alert = self.alert_manager.create_alert(
                title="Lambda Error Rate Warning",
                description=f"Error rate ({summary['error_rate']:.1f}%) exceeds warning threshold",
                severity=AlertSeverity.MEDIUM,
                source="PerformanceMonitor",
                metadata={"error_rate": summary["error_rate"], "threshold": self.thresholds["error_rate_warning"]}
            )
            analysis["alerts"].append(alert.to_dict())
        
        # 最適化推奨事項を生成
        analysis["recommendations"] = self._generate_recommendations(summary, metrics[0] if metrics else None)
        
        # カスタムメトリクスを送信
        self._publish_performance_metrics(summary)
        
        return analysis
    
    def collect_cost_metrics(self, days_back: int = 7) -> CostMetrics:
        """
        コストメトリクスを収集
        
        Args:
            days_back: 過去何日分のデータを取得するか
            
        Returns:
            コストメトリクス
        """
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days_back)
        
        try:
            # Cost Explorerから Lambda のコストを取得
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ],
                Filter={
                    'Dimensions': {
                        'Key': 'SERVICE',
                        'Values': ['AWS Lambda']
                    }
                }
            )
            
            # CloudWatchから使用量メトリクスを取得
            invocations = self._get_cloudwatch_metric(
                'AWS/Lambda', 'Invocations', 
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.min.time())
            )
            
            durations = self._get_cloudwatch_metric(
                'AWS/Lambda', 'Duration',
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.min.time())
            )
            
            # Lambda設定を取得
            function_config = self.lambda_client.get_function(
                FunctionName=self.function_name
            )
            memory_mb = function_config['Configuration']['MemorySize']
            
            # コスト計算
            total_requests = sum([dp['Sum'] for dp in invocations])
            total_duration_ms = sum([dp['Sum'] for dp in durations])
            
            # GB-seconds計算
            total_memory_gb_seconds = (memory_mb / 1024) * (total_duration_ms / 1000)
            
            # 推定コスト計算（2024年の料金で概算）
            # リクエスト料金: $0.0000002 per request (first 1M requests are free)
            # 実行時間料金: $0.0000166667 per GB-second
            request_cost = max(0, total_requests - 1000000) * 0.0000002
            duration_cost = total_memory_gb_seconds * 0.0000166667
            estimated_cost = request_cost + duration_cost
            
            cost_per_request = estimated_cost / max(total_requests, 1)
            
            return CostMetrics(
                timestamp=datetime.utcnow(),
                function_name=self.function_name,
                total_requests=int(total_requests),
                total_duration_ms=int(total_duration_ms),
                total_memory_gb_seconds=total_memory_gb_seconds,
                estimated_cost=estimated_cost,
                cost_per_request=cost_per_request
            )
            
        except Exception as e:
            logger.error(f"Failed to collect cost metrics: {str(e)}")
            # デフォルト値を返す
            return CostMetrics(
                timestamp=datetime.utcnow(),
                function_name=self.function_name,
                total_requests=0,
                total_duration_ms=0,
                total_memory_gb_seconds=0.0,
                estimated_cost=0.0,
                cost_per_request=0.0
            )
    
    def analyze_cost_optimization(self, current_metrics: CostMetrics, 
                                 previous_metrics: Optional[CostMetrics] = None) -> Dict[str, Any]:
        """
        コスト最適化分析を実行
        
        Args:
            current_metrics: 現在のコストメトリクス
            previous_metrics: 前回のコストメトリクス
            
        Returns:
            コスト分析結果
        """
        analysis = {
            "timestamp": datetime.utcnow().isoformat(),
            "current_cost": current_metrics.estimated_cost,
            "cost_per_request": current_metrics.cost_per_request,
            "optimization_opportunities": [],
            "alerts": [],
            "recommendations": []
        }
        
        # 前回との比較
        if previous_metrics:
            cost_change = ((current_metrics.estimated_cost - previous_metrics.estimated_cost) / 
                          max(previous_metrics.estimated_cost, 0.01)) * 100
            
            analysis["cost_change_percent"] = cost_change
            
            # コスト増加アラート
            if cost_change > self.thresholds["cost_increase_critical"]:
                alert = self.alert_manager.create_alert(
                    title="Lambda Cost Increase Critical",
                    description=f"Cost increased by {cost_change:.1f}% compared to previous period",
                    severity=AlertSeverity.CRITICAL,
                    source="CostMonitor",
                    metadata={
                        "cost_change": cost_change,
                        "current_cost": current_metrics.estimated_cost,
                        "previous_cost": previous_metrics.estimated_cost
                    }
                )
                analysis["alerts"].append(alert.to_dict())
            elif cost_change > self.thresholds["cost_increase_warning"]:
                alert = self.alert_manager.create_alert(
                    title="Lambda Cost Increase Warning",
                    description=f"Cost increased by {cost_change:.1f}% compared to previous period",
                    severity=AlertSeverity.MEDIUM,
                    source="CostMonitor",
                    metadata={
                        "cost_change": cost_change,
                        "current_cost": current_metrics.estimated_cost,
                        "previous_cost": previous_metrics.estimated_cost
                    }
                )
                analysis["alerts"].append(alert.to_dict())
        
        # 最適化機会の分析
        analysis["optimization_opportunities"] = self._analyze_cost_optimization_opportunities(current_metrics)
        
        # コストメトリクスを送信
        self._publish_cost_metrics(current_metrics)
        
        return analysis
    
    def _get_cloudwatch_metric(self, namespace: str, metric_name: str, 
                              start_time: datetime, end_time: datetime) -> List[Dict]:
        """CloudWatchメトリクスを取得"""
        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[
                    {
                        'Name': 'FunctionName',
                        'Value': self.function_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5分間隔
                Statistics=['Average', 'Sum', 'Maximum']
            )
            
            return sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            
        except Exception as e:
            logger.error(f"Failed to get CloudWatch metric {metric_name}: {str(e)}")
            return []
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """パーセンタイル値を計算"""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def _generate_recommendations(self, summary: Dict[str, Any], 
                                 sample_metric: Optional[PerformanceMetrics]) -> List[str]:
        """パフォーマンス最適化推奨事項を生成"""
        recommendations = []
        
        # メモリ最適化
        if summary["avg_memory_utilization"] < 50:
            recommendations.append(
                f"Memory utilization is low ({summary['avg_memory_utilization']:.1f}%). "
                "Consider reducing allocated memory to save costs."
            )
        elif summary["max_memory_utilization"] > 90:
            recommendations.append(
                f"Memory utilization is high ({summary['max_memory_utilization']:.1f}%). "
                "Consider increasing allocated memory to improve performance."
            )
        
        # 実行時間最適化
        if summary["p95_duration"] > 30000:  # 30秒
            recommendations.append(
                "Function duration is high. Consider optimizing code, using connection pooling, "
                "or implementing caching to reduce execution time."
            )
        
        # エラー率改善
        if summary["error_rate"] > 1:
            recommendations.append(
                f"Error rate is {summary['error_rate']:.1f}%. "
                "Review error logs and implement better error handling."
            )
        
        # コールドスタート最適化
        if summary["cold_start_rate"] > 10:
            recommendations.append(
                f"Cold start rate is {summary['cold_start_rate']:.1f}%. "
                "Consider using provisioned concurrency or optimizing package size."
            )
        
        return recommendations
    
    def _analyze_cost_optimization_opportunities(self, metrics: CostMetrics) -> List[Dict[str, Any]]:
        """コスト最適化機会を分析"""
        opportunities = []
        
        # 高い1リクエストあたりコスト
        if metrics.cost_per_request > 0.001:  # $0.001 per request
            opportunities.append({
                "type": "high_cost_per_request",
                "description": f"Cost per request (${metrics.cost_per_request:.6f}) is high",
                "recommendation": "Optimize function performance to reduce execution time",
                "potential_savings": "20-50%"
            })
        
        # 低い実行頻度
        daily_requests = metrics.total_requests / 7  # 7日間の平均
        if daily_requests < 100:
            opportunities.append({
                "type": "low_frequency",
                "description": f"Low execution frequency ({daily_requests:.1f} requests/day)",
                "recommendation": "Consider using smaller memory allocation or on-demand pricing",
                "potential_savings": "10-30%"
            })
        
        return opportunities
    
    def _publish_performance_metrics(self, summary: Dict[str, Any]) -> None:
        """パフォーマンスメトリクスをCloudWatchに送信"""
        try:
            self.metrics.add_to_batch('PerformanceP95Duration', summary['p95_duration'], 'Milliseconds')
            self.metrics.add_to_batch('PerformanceP99Duration', summary['p99_duration'], 'Milliseconds')
            self.metrics.add_to_batch('PerformanceAvgMemoryUtilization', summary['avg_memory_utilization'], 'Percent')
            self.metrics.add_to_batch('PerformanceErrorRate', summary['error_rate'], 'Percent')
            self.metrics.add_to_batch('PerformanceColdStartRate', summary['cold_start_rate'], 'Percent')
            self.metrics.flush_batch()
            
        except Exception as e:
            logger.error(f"Failed to publish performance metrics: {str(e)}")
    
    def _publish_cost_metrics(self, metrics: CostMetrics) -> None:
        """コストメトリクスをCloudWatchに送信"""
        try:
            self.metrics.add_to_batch('CostEstimated', metrics.estimated_cost, 'None')
            self.metrics.add_to_batch('CostPerRequest', metrics.cost_per_request, 'None')
            self.metrics.add_to_batch('CostTotalRequests', metrics.total_requests, 'Count')
            self.metrics.add_to_batch('CostMemoryGBSeconds', metrics.total_memory_gb_seconds, 'None')
            self.metrics.flush_batch()
            
        except Exception as e:
            logger.error(f"Failed to publish cost metrics: {str(e)}")


# グローバルインスタンス
import os
_environment = os.environ.get('ENVIRONMENT', 'dev')
performance_monitor = PerformanceMonitor(environment=_environment)