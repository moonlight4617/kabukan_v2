"""
監視システム統合モジュール

株式分析システムの包括的な監視機能を提供する
"""

from .metrics_publisher import MetricsPublisher, MetricsDecorator, metrics_publisher, metrics_decorator
from .alert_manager import AlertManager, AlertSeverity, AlertStatus, Alert, alert_manager
from .performance_monitor import PerformanceMonitor, PerformanceMetrics, CostMetrics, performance_monitor
from .operational_monitor import OperationalMonitor, HealthCheckResult, SystemStatus, operational_monitor

__all__ = [
    # メトリクス関連
    'MetricsPublisher',
    'MetricsDecorator', 
    'metrics_publisher',
    'metrics_decorator',
    
    # アラート関連
    'AlertManager',
    'AlertSeverity',
    'AlertStatus',
    'Alert',
    'alert_manager',
    
    # パフォーマンス監視関連
    'PerformanceMonitor',
    'PerformanceMetrics',
    'CostMetrics',
    'performance_monitor',
    
    # 運用監視関連
    'OperationalMonitor',
    'HealthCheckResult',
    'SystemStatus',
    'operational_monitor'
]

# バージョン情報
__version__ = "1.0.0"

# 設定
MONITORING_CONFIG = {
    'default_namespace': 'Custom/StockAnalysis',
    'batch_size': 20,
    'cache_duration_minutes': 5,
    'health_check_timeout_seconds': 30,
    'alert_suppression_window_minutes': 30
}