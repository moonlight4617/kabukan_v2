#!/usr/bin/env python3
"""
運用監視スクリプト

株式分析システムの包括的な監視を実行し、
レポートを生成するスクリプト
"""

import json
import sys
import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from monitoring import (
    operational_monitor,
    performance_monitor,
    alert_manager,
    metrics_publisher
)


def setup_logging():
    """ログ設定を初期化"""
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'monitoring-{datetime.now().strftime("%Y%m%d")}.log')
        ]
    )
    
    return logging.getLogger(__name__)


async def run_health_check(environment: str, verbose: bool = False):
    """ヘルスチェックを実行"""
    logger = setup_logging()
    logger.info(f"Starting health check for environment: {environment}")
    
    try:
        # 運用監視インスタンスを環境に合わせて設定
        monitor = operational_monitor
        if monitor.environment != environment:
            from monitoring.operational_monitor import OperationalMonitor
            monitor = OperationalMonitor(environment=environment)
        
        # 包括的ヘルスチェック実行
        system_status = await monitor.perform_comprehensive_health_check()
        
        # 結果を表示
        print(f"\n=== Health Check Report - {environment.upper()} ===")
        print(f"Timestamp: {system_status.timestamp}")
        print(f"Overall Status: {system_status.overall_status.upper()}")
        print(f"Active Alerts: {system_status.active_alerts}")
        
        # コンポーネント別状態
        print(f"\n--- Component Health ---")
        for component in system_status.components:
            status_icon = {
                'healthy': '✅',
                'warning': '⚠️',
                'critical': '❌',
                'unknown': '❓'
            }.get(component.status, '❓')
            
            print(f"{status_icon} {component.component}: {component.status} ({component.response_time:.2f}s)")
            if verbose and component.message:
                print(f"   Message: {component.message}")
        
        # パフォーマンス概要
        if system_status.performance_summary:
            print(f"\n--- Performance Summary ---")
            perf = system_status.performance_summary
            print(f"Average Duration: {perf.get('avg_duration', 0):.1f}ms")
            print(f"P95 Duration: {perf.get('p95_duration', 0):.1f}ms")
            print(f"Error Rate: {perf.get('error_rate', 0):.2f}%")
            print(f"Memory Utilization: {perf.get('avg_memory_utilization', 0):.1f}%")
        
        # 推奨事項
        if system_status.recommendations:
            print(f"\n--- Recommendations ---")
            for i, rec in enumerate(system_status.recommendations, 1):
                print(f"{i}. {rec}")
        
        # 運用レポート生成
        report = monitor.generate_operational_report(system_status)
        
        # レポートをファイルに保存
        report_file = f"health-check-{environment}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\nDetailed report saved to: {report_file}")
        
        # 終了コードを設定
        if system_status.overall_status == 'critical':
            return 2
        elif system_status.overall_status == 'warning':
            return 1
        else:
            return 0
            
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        print(f"❌ Health check failed: {str(e)}")
        return 3


def run_performance_analysis(environment: str, hours: int = 24):
    """パフォーマンス分析を実行"""
    logger = setup_logging()
    logger.info(f"Starting performance analysis for environment: {environment}")
    
    try:
        # パフォーマンス監視インスタンスを設定
        from monitoring.performance_monitor import PerformanceMonitor
        monitor = PerformanceMonitor(environment=environment)
        
        # パフォーマンスメトリクス収集
        print(f"Collecting performance metrics for last {hours} hours...")
        metrics = monitor.collect_performance_metrics(hours_back=hours)
        
        if not metrics:
            print("❌ No performance metrics found")
            return 1
        
        # パフォーマンス分析
        analysis = monitor.analyze_performance(metrics)
        
        # 結果表示
        print(f"\n=== Performance Analysis Report - {environment.upper()} ===")
        print(f"Analysis Period: Last {hours} hours")
        print(f"Metrics Count: {len(metrics)}")
        
        summary = analysis.get("performance_summary", {})
        if summary:
            print(f"\n--- Performance Metrics ---")
            print(f"Average Duration: {summary.get('avg_duration', 0):.1f}ms")
            print(f"P95 Duration: {summary.get('p95_duration', 0):.1f}ms")
            print(f"P99 Duration: {summary.get('p99_duration', 0):.1f}ms")
            print(f"Max Duration: {summary.get('max_duration', 0):.1f}ms")
            print(f"Average Memory Utilization: {summary.get('avg_memory_utilization', 0):.1f}%")
            print(f"Max Memory Utilization: {summary.get('max_memory_utilization', 0):.1f}%")
            print(f"Error Rate: {summary.get('error_rate', 0):.2f}%")
            print(f"Cold Start Rate: {summary.get('cold_start_rate', 0):.2f}%")
        
        # アラート
        alerts = analysis.get("alerts", [])
        if alerts:
            print(f"\n--- Generated Alerts ---")
            for alert in alerts:
                print(f"⚠️ {alert['title']}: {alert['description']}")
        
        # 推奨事項
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            print(f"\n--- Optimization Recommendations ---")
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        
        # レポート保存
        report_file = f"performance-analysis-{environment}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\nDetailed analysis saved to: {report_file}")
        return 0
        
    except Exception as e:
        logger.error(f"Performance analysis failed: {str(e)}")
        print(f"❌ Performance analysis failed: {str(e)}")
        return 1


def run_cost_analysis(environment: str, days: int = 7):
    """コスト分析を実行"""
    logger = setup_logging()
    logger.info(f"Starting cost analysis for environment: {environment}")
    
    try:
        from monitoring.performance_monitor import PerformanceMonitor
        monitor = PerformanceMonitor(environment=environment)
        
        # コストメトリクス収集
        print(f"Collecting cost metrics for last {days} days...")
        current_metrics = monitor.collect_cost_metrics(days_back=days)
        
        # 前回期間のメトリクス取得（比較用）
        previous_metrics = monitor.collect_cost_metrics(days_back=days*2)
        
        # コスト分析
        analysis = monitor.analyze_cost_optimization(current_metrics, previous_metrics)
        
        # 結果表示
        print(f"\n=== Cost Analysis Report - {environment.upper()} ===")
        print(f"Analysis Period: Last {days} days")
        
        print(f"\n--- Cost Metrics ---")
        print(f"Estimated Cost: ${current_metrics.estimated_cost:.4f}")
        print(f"Cost per Request: ${current_metrics.cost_per_request:.6f}")
        print(f"Total Requests: {current_metrics.total_requests:,}")
        print(f"Total Duration: {current_metrics.total_duration_ms:,}ms")
        print(f"Memory GB-Seconds: {current_metrics.total_memory_gb_seconds:.2f}")
        
        # コスト変化
        cost_change = analysis.get("cost_change_percent")
        if cost_change is not None:
            change_icon = "📈" if cost_change > 0 else "📉"
            print(f"Cost Change: {change_icon} {cost_change:+.1f}%")
        
        # 最適化機会
        opportunities = analysis.get("optimization_opportunities", [])
        if opportunities:
            print(f"\n--- Cost Optimization Opportunities ---")
            for i, opp in enumerate(opportunities, 1):
                print(f"{i}. {opp['description']}")
                print(f"   Recommendation: {opp['recommendation']}")
                print(f"   Potential Savings: {opp['potential_savings']}")
        
        # アラート
        alerts = analysis.get("alerts", [])
        if alerts:
            print(f"\n--- Cost Alerts ---")
            for alert in alerts:
                print(f"⚠️ {alert['title']}: {alert['description']}")
        
        # レポート保存
        report_file = f"cost-analysis-{environment}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "current_metrics": current_metrics.__dict__,
                "analysis": analysis
            }, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\nDetailed analysis saved to: {report_file}")
        return 0
        
    except Exception as e:
        logger.error(f"Cost analysis failed: {str(e)}")
        print(f"❌ Cost analysis failed: {str(e)}")
        return 1


def send_test_alert(environment: str, severity: str = "medium"):
    """テストアラートを送信"""
    logger = setup_logging()
    logger.info(f"Sending test alert for environment: {environment}")
    
    try:
        from monitoring.alert_manager import AlertManager, AlertSeverity
        manager = AlertManager(environment=environment)
        
        severity_map = {
            'low': AlertSeverity.LOW,
            'medium': AlertSeverity.MEDIUM,
            'high': AlertSeverity.HIGH,
            'critical': AlertSeverity.CRITICAL
        }
        
        alert_severity = severity_map.get(severity.lower(), AlertSeverity.MEDIUM)
        
        alert = manager.create_alert(
            title="Test Alert",
            description=f"This is a test alert for {environment} environment",
            severity=alert_severity,
            source="MonitoringScript",
            metadata={
                "test": True,
                "script_execution": datetime.now().isoformat(),
                "severity_requested": severity
            }
        )
        
        print(f"✅ Test alert created: {alert.id}")
        print(f"   Severity: {alert.severity.value}")
        print(f"   Status: {alert.status.value}")
        print(f"   Timestamp: {alert.timestamp}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to send test alert: {str(e)}")
        print(f"❌ Failed to send test alert: {str(e)}")
        return 1


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Stock Analysis System Monitoring")
    parser.add_argument("command", choices=[
        "health-check", "performance", "cost", "test-alert"
    ], help="Monitoring command to execute")
    
    parser.add_argument("--environment", "-e", default="dev",
                       choices=["dev", "staging", "prod"],
                       help="Environment to monitor")
    
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")
    
    parser.add_argument("--hours", type=int, default=24,
                       help="Hours of data to analyze (for performance command)")
    
    parser.add_argument("--days", type=int, default=7,
                       help="Days of data to analyze (for cost command)")
    
    parser.add_argument("--severity", choices=["low", "medium", "high", "critical"],
                       default="medium", help="Alert severity (for test-alert command)")
    
    args = parser.parse_args()
    
    try:
        if args.command == "health-check":
            return asyncio.run(run_health_check(args.environment, args.verbose))
        elif args.command == "performance":
            return run_performance_analysis(args.environment, args.hours)
        elif args.command == "cost":
            return run_cost_analysis(args.environment, args.days)
        elif args.command == "test-alert":
            return send_test_alert(args.environment, args.severity)
        
    except KeyboardInterrupt:
        print("\n⚠️ Monitoring interrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Monitoring failed: {str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)