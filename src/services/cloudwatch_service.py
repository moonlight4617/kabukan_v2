"""
CloudWatch ログとメトリクス統合サービス
構造化ログ機能とカスタムメトリクス送信機能を提供
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError, NoCredentialsError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False


class LogLevel(Enum):
    """ログレベル"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MetricUnit(Enum):
    """CloudWatchメトリクスの単位"""
    COUNT = "Count"
    PERCENT = "Percent"
    SECONDS = "Seconds"
    MILLISECONDS = "Milliseconds"
    BYTES = "Bytes"
    KILOBYTES = "Kilobytes"
    MEGABYTES = "Megabytes"
    NONE = "None"


@dataclass
class LogEvent:
    """構造化ログイベント"""
    timestamp: datetime
    level: LogLevel
    message: str
    logger_name: str
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "logger": self.logger_name,
            "context": self.context
        }


@dataclass
class MetricDatum:
    """CloudWatchメトリクスデータ"""
    name: str
    value: float
    unit: MetricUnit = MetricUnit.NONE
    dimensions: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class CloudWatchService:
    """CloudWatch ログとメトリクス統合サービス"""
    
    def __init__(self, 
                 region_name: str = "ap-northeast-1",
                 log_group_name: str = "/aws/lambda/stock-analysis",
                 log_stream_name: Optional[str] = None,
                 namespace: str = "StockAnalysis"):
        """
        Args:
            region_name: AWS リージョン名
            log_group_name: CloudWatch Logs グループ名
            log_stream_name: ログストリーム名（Noneの場合は自動生成）
            namespace: CloudWatch メトリクスの名前空間
        """
        self.region_name = region_name
        self.log_group_name = log_group_name
        self.log_stream_name = log_stream_name or self._generate_log_stream_name()
        self.namespace = namespace
        self.logger = logging.getLogger(__name__)
        
        self._logs_client = None
        self._cloudwatch_client = None
        self._sequence_token = None
        self._lock = threading.Lock()
        
        # AWS可用性チェック
        if not AWS_AVAILABLE:
            self.logger.warning("boto3がインストールされていません。CloudWatch機能は利用できません。")
            return
        
        try:
            self._initialize_clients()
        except Exception as e:
            self.logger.error(f"CloudWatch clients初期化に失敗: {e}")
    
    def _generate_log_stream_name(self) -> str:
        """ログストリーム名を生成"""
        timestamp = datetime.utcnow().strftime("%Y/%m/%d")
        instance_id = os.getenv("AWS_LAMBDA_LOG_STREAM_NAME", "local")
        return f"{timestamp}/{instance_id}"
    
    def _initialize_clients(self):
        """CloudWatch クライアントを初期化"""
        if not AWS_AVAILABLE:
            raise RuntimeError("boto3が利用できません")
        
        try:
            # 認証情報の確認
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials is None:
                raise NoCredentialsError()
            
            self._logs_client = boto3.client('logs', region_name=self.region_name)
            self._cloudwatch_client = boto3.client('cloudwatch', region_name=self.region_name)
            
            # ロググループとログストリームの作成
            self._ensure_log_group_exists()
            self._ensure_log_stream_exists()
            
            self.logger.info(f"CloudWatch clients初期化完了 (region: {self.region_name})")
            
        except NoCredentialsError:
            self.logger.error(
                "AWS認証情報が設定されていません。"
                "AWS CLI設定、環境変数、またはIAMロールを確認してください。"
            )
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'UnauthorizedOperation':
                self.logger.error("CloudWatchへのアクセス権限がありません")
            else:
                self.logger.error(f"CloudWatch接続エラー: {e}")
            raise
        except Exception as e:
            self.logger.error(f"予期しないエラー: {e}")
            raise
    
    @property
    def is_available(self) -> bool:
        """CloudWatchが利用可能かチェック"""
        return AWS_AVAILABLE and self._logs_client is not None and self._cloudwatch_client is not None
    
    def _ensure_log_group_exists(self):
        """ロググループの存在確認と作成"""
        try:
            self._logs_client.describe_log_groups(logGroupNamePrefix=self.log_group_name)
            groups = self._logs_client.describe_log_groups(
                logGroupNamePrefix=self.log_group_name
            )['logGroups']
            
            if not any(group['logGroupName'] == self.log_group_name for group in groups):
                self._logs_client.create_log_group(logGroupName=self.log_group_name)
                self.logger.info(f"ロググループを作成: {self.log_group_name}")
            
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'ResourceAlreadyExistsException':
                raise
    
    def _ensure_log_stream_exists(self):
        """ログストリームの存在確認と作成"""
        try:
            streams = self._logs_client.describe_log_streams(
                logGroupName=self.log_group_name,
                logStreamNamePrefix=self.log_stream_name
            )['logStreams']
            
            if not any(stream['logStreamName'] == self.log_stream_name for stream in streams):
                self._logs_client.create_log_stream(
                    logGroupName=self.log_group_name,
                    logStreamName=self.log_stream_name
                )
                self.logger.info(f"ログストリームを作成: {self.log_stream_name}")
            else:
                # 既存のシーケンストークンを取得
                for stream in streams:
                    if stream['logStreamName'] == self.log_stream_name:
                        self._sequence_token = stream.get('uploadSequenceToken')
                        break
            
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'ResourceAlreadyExistsException':
                raise
    
    def send_log(self, 
                 level: LogLevel,
                 message: str,
                 context: Optional[Dict[str, Any]] = None,
                 logger_name: str = "stock-analysis") -> bool:
        """
        構造化ログをCloudWatchに送信
        
        Args:
            level: ログレベル
            message: ログメッセージ
            context: 追加のコンテキスト情報
            logger_name: ロガー名
            
        Returns:
            bool: 送信成功したかどうか
        """
        if not self.is_available:
            # ローカルロガーにフォールバック
            local_logger = logging.getLogger(logger_name)
            log_level = getattr(logging, level.value)
            local_logger.log(log_level, f"{message} - context: {context or {}}")
            return False
        
        try:
            log_event = LogEvent(
                timestamp=datetime.utcnow(),
                level=level,
                message=message,
                logger_name=logger_name,
                context=context or {}
            )
            
            return self._send_log_event(log_event)
            
        except Exception as e:
            self.logger.error(f"ログ送信エラー: {e}")
            return False
    
    def _send_log_event(self, log_event: LogEvent) -> bool:
        """ログイベントをCloudWatchに送信"""
        with self._lock:
            try:
                # ログイベントを構造化JSON形式で送信
                log_data = {
                    'timestamp': int(log_event.timestamp.timestamp() * 1000),  # ミリ秒
                    'message': json.dumps(log_event.to_dict(), ensure_ascii=False)
                }
                
                kwargs = {
                    'logGroupName': self.log_group_name,
                    'logStreamName': self.log_stream_name,
                    'logEvents': [log_data]
                }
                
                if self._sequence_token:
                    kwargs['sequenceToken'] = self._sequence_token
                
                response = self._logs_client.put_log_events(**kwargs)
                self._sequence_token = response.get('nextSequenceToken')
                
                return True
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'InvalidSequenceTokenException':
                    # シーケンストークンが無効な場合、再取得して再試行
                    self._refresh_sequence_token()
                    return self._send_log_event(log_event)
                else:
                    self.logger.error(f"ログ送信失敗: {e}")
                    return False
    
    def _refresh_sequence_token(self):
        """シーケンストークンを再取得"""
        try:
            streams = self._logs_client.describe_log_streams(
                logGroupName=self.log_group_name,
                logStreamNamePrefix=self.log_stream_name
            )['logStreams']
            
            for stream in streams:
                if stream['logStreamName'] == self.log_stream_name:
                    self._sequence_token = stream.get('uploadSequenceToken')
                    break
                    
        except Exception as e:
            self.logger.error(f"シーケンストークン再取得エラー: {e}")
            self._sequence_token = None
    
    def send_metric(self, metric: MetricDatum) -> bool:
        """
        カスタムメトリクスをCloudWatchに送信
        
        Args:
            metric: メトリクスデータ
            
        Returns:
            bool: 送信成功したかどうか
        """
        if not self.is_available:
            self.logger.warning(f"CloudWatchが利用できません。メトリクス '{metric.name}' はスキップされました。")
            return False
        
        try:
            metric_data = {
                'MetricName': metric.name,
                'Value': metric.value,
                'Unit': metric.unit.value,
                'Timestamp': metric.timestamp
            }
            
            if metric.dimensions:
                metric_data['Dimensions'] = [
                    {'Name': name, 'Value': value}
                    for name, value in metric.dimensions.items()
                ]
            
            self._cloudwatch_client.put_metric_data(
                Namespace=self.namespace,
                MetricData=[metric_data]
            )
            
            self.logger.debug(f"メトリクス送信成功: {metric.name} = {metric.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"メトリクス送信エラー: {e}")
            return False
    
    def send_metrics(self, metrics: List[MetricDatum]) -> int:
        """
        複数のメトリクスをバッチで送信
        
        Args:
            metrics: メトリクスデータのリスト
            
        Returns:
            int: 送信成功したメトリクス数
        """
        if not self.is_available:
            self.logger.warning(f"CloudWatchが利用できません。{len(metrics)}個のメトリクスがスキップされました。")
            return 0
        
        success_count = 0
        
        # CloudWatchは一度に最大20個のメトリクスを受け付ける
        batch_size = 20
        for i in range(0, len(metrics), batch_size):
            batch = metrics[i:i + batch_size]
            
            try:
                metric_data = []
                for metric in batch:
                    data = {
                        'MetricName': metric.name,
                        'Value': metric.value,
                        'Unit': metric.unit.value,
                        'Timestamp': metric.timestamp
                    }
                    
                    if metric.dimensions:
                        data['Dimensions'] = [
                            {'Name': name, 'Value': value}
                            for name, value in metric.dimensions.items()
                        ]
                    
                    metric_data.append(data)
                
                self._cloudwatch_client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=metric_data
                )
                
                success_count += len(batch)
                self.logger.debug(f"メトリクスバッチ送信成功: {len(batch)}個")
                
            except Exception as e:
                self.logger.error(f"メトリクスバッチ送信エラー: {e}")
        
        return success_count
    
    def log_analysis_start(self, analysis_type: str, symbols: List[str]) -> bool:
        """分析開始ログを送信"""
        context = {
            "analysis_type": analysis_type,
            "symbol_count": len(symbols),
            "symbols": symbols[:10]  # 最初の10銘柄のみ記録
        }
        
        return self.send_log(
            LogLevel.INFO,
            f"{analysis_type}分析を開始",
            context,
            "analysis_workflow"
        )
    
    def log_analysis_completion(self, 
                              analysis_type: str,
                              duration: float,
                              recommendations_count: int,
                              success: bool) -> bool:
        """分析完了ログを送信"""
        context = {
            "analysis_type": analysis_type,
            "duration_seconds": duration,
            "recommendations_count": recommendations_count,
            "success": success
        }
        
        level = LogLevel.INFO if success else LogLevel.ERROR
        message = f"{analysis_type}分析が{'完了' if success else '失敗'}"
        
        return self.send_log(level, message, context, "analysis_workflow")
    
    def log_api_call(self, 
                     service: str,
                     method: str,
                     duration: float,
                     success: bool,
                     error_message: Optional[str] = None) -> bool:
        """API呼び出しログを送信"""
        context = {
            "service": service,
            "method": method,
            "duration_ms": duration * 1000,
            "success": success
        }
        
        if error_message:
            context["error"] = error_message
        
        level = LogLevel.INFO if success else LogLevel.WARNING
        message = f"{service}.{method} {'成功' if success else '失敗'}"
        
        return self.send_log(level, message, context, "api_calls")
    
    def send_performance_metrics(self, 
                               analysis_type: str,
                               duration: float,
                               recommendations_count: int,
                               api_calls_count: int) -> bool:
        """パフォーマンスメトリクスを送信"""
        metrics = [
            MetricDatum(
                name="AnalysisDuration",
                value=duration,
                unit=MetricUnit.SECONDS,
                dimensions={"AnalysisType": analysis_type}
            ),
            MetricDatum(
                name="RecommendationsGenerated",
                value=recommendations_count,
                unit=MetricUnit.COUNT,
                dimensions={"AnalysisType": analysis_type}
            ),
            MetricDatum(
                name="ApiCallsCount",
                value=api_calls_count,
                unit=MetricUnit.COUNT,
                dimensions={"AnalysisType": analysis_type}
            )
        ]
        
        success_count = self.send_metrics(metrics)
        return success_count == len(metrics)
    
    def send_error_metric(self, 
                         error_type: str,
                         component: str) -> bool:
        """エラーメトリクスを送信"""
        metric = MetricDatum(
            name="Errors",
            value=1,
            unit=MetricUnit.COUNT,
            dimensions={
                "ErrorType": error_type,
                "Component": component
            }
        )
        
        return self.send_metric(metric)
    
    def validate_connection(self) -> bool:
        """CloudWatchへの接続を検証"""
        if not self.is_available:
            return False
        
        try:
            # CloudWatch Logsへの接続テスト
            self._logs_client.describe_log_groups(limit=1)
            
            # CloudWatch Metricsへの接続テスト
            self._cloudwatch_client.list_metrics(MaxRecords=1)
            
            return True
            
        except Exception as e:
            self.logger.error(f"CloudWatch接続検証に失敗: {e}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状況を取得"""
        return {
            "available": self.is_available,
            "log_group_name": self.log_group_name,
            "log_stream_name": self.log_stream_name,
            "namespace": self.namespace,
            "region": self.region_name,
            "connection_valid": self.validate_connection() if self.is_available else False
        }


class StructuredLogger:
    """構造化ログを簡単に使用するためのヘルパークラス"""
    
    def __init__(self, cloudwatch_service: CloudWatchService, logger_name: str = "stock-analysis"):
        self.cloudwatch_service = cloudwatch_service
        self.logger_name = logger_name
        self.local_logger = logging.getLogger(logger_name)
    
    def debug(self, message: str, **context):
        """デバッグログ"""
        self.cloudwatch_service.send_log(LogLevel.DEBUG, message, context, self.logger_name)
        self.local_logger.debug(f"{message} - {context}")
    
    def info(self, message: str, **context):
        """情報ログ"""
        self.cloudwatch_service.send_log(LogLevel.INFO, message, context, self.logger_name)
        self.local_logger.info(f"{message} - {context}")
    
    def warning(self, message: str, **context):
        """警告ログ"""
        self.cloudwatch_service.send_log(LogLevel.WARNING, message, context, self.logger_name)
        self.local_logger.warning(f"{message} - {context}")
    
    def error(self, message: str, **context):
        """エラーログ"""
        self.cloudwatch_service.send_log(LogLevel.ERROR, message, context, self.logger_name)
        self.local_logger.error(f"{message} - {context}")
    
    def critical(self, message: str, **context):
        """クリティカルログ"""
        self.cloudwatch_service.send_log(LogLevel.CRITICAL, message, context, self.logger_name)
        self.local_logger.critical(f"{message} - {context}")