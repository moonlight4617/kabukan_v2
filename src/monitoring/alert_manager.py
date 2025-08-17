"""
アラートマネージャー

システムの異常検知、通知管理、エスカレーション処理を行う
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, asdict
import boto3
import requests
import logging

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """アラート重要度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """アラート状態"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """アラートデータクラス"""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    status: AlertStatus
    source: str
    timestamp: datetime
    environment: str
    metadata: Dict[str, Any] = None
    resolved_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['severity'] = self.severity.value
        data['status'] = self.status.value
        if self.resolved_at:
            data['resolved_at'] = self.resolved_at.isoformat()
        if self.acknowledged_at:
            data['acknowledged_at'] = self.acknowledged_at.isoformat()
        return data


class AlertManager:
    """アラート管理クラス"""
    
    def __init__(self, environment: str = "dev"):
        """
        初期化
        
        Args:
            environment: 環境名
        """
        self.environment = environment
        self.dynamodb = boto3.resource('dynamodb')
        self.ssm = boto3.client('ssm')
        
        # アラート状態を保存するDynamoDBテーブル
        self.alerts_table_name = f"stock-analysis-alerts-{environment}"
        
        # 通知設定をキャッシュ
        self._notification_cache = {}
        self._cache_expiry = {}
        
        # アラート抑制ルール
        self.suppression_rules = {
            # 同じアラートを30分以内に再送しない
            'duplicate_window': timedelta(minutes=30),
            # 同じソースからの類似アラートを5分以内に抑制
            'similar_alert_window': timedelta(minutes=5),
        }
    
    def _get_alert_id(self, title: str, source: str, severity: AlertSeverity) -> str:
        """アラートIDを生成"""
        content = f"{title}-{source}-{severity.value}-{self.environment}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _get_notification_config(self, key: str) -> Optional[str]:
        """通知設定を取得（キャッシュ付き）"""
        cache_key = f"/stock-analysis-{self.environment}/{key}"
        
        # キャッシュチェック
        if cache_key in self._notification_cache:
            if datetime.now() < self._cache_expiry.get(cache_key, datetime.now()):
                return self._notification_cache[cache_key]
        
        try:
            response = self.ssm.get_parameter(
                Name=cache_key,
                WithDecryption=True
            )
            value = response['Parameter']['Value']
            
            # 5分間キャッシュ
            self._notification_cache[cache_key] = value
            self._cache_expiry[cache_key] = datetime.now() + timedelta(minutes=5)
            
            return value
        except Exception as e:
            logger.warning(f"Failed to get notification config for {key}: {str(e)}")
            return None
    
    def create_alert(self, 
                    title: str,
                    description: str,
                    severity: AlertSeverity,
                    source: str,
                    metadata: Optional[Dict[str, Any]] = None) -> Alert:
        """
        新しいアラートを作成
        
        Args:
            title: アラートタイトル
            description: アラート詳細
            severity: 重要度
            source: 発生源
            metadata: 追加メタデータ
            
        Returns:
            作成されたアラート
        """
        alert_id = self._get_alert_id(title, source, severity)
        
        alert = Alert(
            id=alert_id,
            title=title,
            description=description,
            severity=severity,
            status=AlertStatus.ACTIVE,
            source=source,
            timestamp=datetime.utcnow(),
            environment=self.environment,
            metadata=metadata or {}
        )
        
        # 抑制ルールをチェック
        if self._should_suppress_alert(alert):
            alert.status = AlertStatus.SUPPRESSED
            logger.info(f"Alert suppressed: {alert_id}")
            return alert
        
        # アラートを保存
        self._save_alert(alert)
        
        # 通知送信
        self._send_notifications(alert)
        
        logger.info(f"Alert created: {alert_id} - {title}")
        return alert
    
    def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """
        アラートを解決済みにマーク
        
        Args:
            alert_id: アラートID
            resolved_by: 解決者
            
        Returns:
            成功フラグ
        """
        try:
            alert = self._get_alert(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.utcnow()
            
            self._save_alert(alert)
            
            # 解決通知を送信
            self._send_resolution_notification(alert, resolved_by)
            
            logger.info(f"Alert resolved: {alert_id} by {resolved_by}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resolve alert {alert_id}: {str(e)}")
            return False
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """
        アラートを確認済みにマーク
        
        Args:
            alert_id: アラートID
            acknowledged_by: 確認者
            
        Returns:
            成功フラグ
        """
        try:
            alert = self._get_alert(alert_id)
            if not alert:
                return False
            
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = acknowledged_by
            
            self._save_alert(alert)
            
            logger.info(f"Alert acknowledged: {alert_id} by {acknowledged_by}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to acknowledge alert {alert_id}: {str(e)}")
            return False
    
    def _should_suppress_alert(self, alert: Alert) -> bool:
        """アラート抑制ルールをチェック"""
        try:
            # 同じアラートIDの最近のアラートをチェック
            recent_alerts = self._get_recent_alerts(
                alert.id,
                self.suppression_rules['duplicate_window']
            )
            
            if recent_alerts:
                return True
            
            # 同じソースからの類似アラートをチェック
            similar_alerts = self._get_similar_alerts(
                alert.source,
                alert.severity,
                self.suppression_rules['similar_alert_window']
            )
            
            if len(similar_alerts) > 3:  # 5分間に3回以上同じレベルのアラート
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking suppression rules: {str(e)}")
            return False
    
    def _save_alert(self, alert: Alert) -> None:
        """アラートをDynamoDBに保存"""
        try:
            table = self.dynamodb.Table(self.alerts_table_name)
            
            table.put_item(
                Item={
                    'alert_id': alert.id,
                    'timestamp': int(alert.timestamp.timestamp()),
                    'title': alert.title,
                    'description': alert.description,
                    'severity': alert.severity.value,
                    'status': alert.status.value,
                    'source': alert.source,
                    'environment': alert.environment,
                    'metadata': json.dumps(alert.metadata) if alert.metadata else '',
                    'resolved_at': int(alert.resolved_at.timestamp()) if alert.resolved_at else None,
                    'acknowledged_at': int(alert.acknowledged_at.timestamp()) if alert.acknowledged_at else None,
                    'acknowledged_by': alert.acknowledged_by,
                    'ttl': int((alert.timestamp + timedelta(days=30)).timestamp())  # 30日後に自動削除
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to save alert to DynamoDB: {str(e)}")
            # DynamoDB保存失敗でも通知は継続
    
    def _get_alert(self, alert_id: str) -> Optional[Alert]:
        """アラートを取得"""
        try:
            table = self.dynamodb.Table(self.alerts_table_name)
            response = table.get_item(Key={'alert_id': alert_id})
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            return Alert(
                id=item['alert_id'],
                title=item['title'],
                description=item['description'],
                severity=AlertSeverity(item['severity']),
                status=AlertStatus(item['status']),
                source=item['source'],
                timestamp=datetime.fromtimestamp(item['timestamp']),
                environment=item['environment'],
                metadata=json.loads(item['metadata']) if item['metadata'] else {},
                resolved_at=datetime.fromtimestamp(item['resolved_at']) if item.get('resolved_at') else None,
                acknowledged_at=datetime.fromtimestamp(item['acknowledged_at']) if item.get('acknowledged_at') else None,
                acknowledged_by=item.get('acknowledged_by')
            )
            
        except Exception as e:
            logger.error(f"Failed to get alert {alert_id}: {str(e)}")
            return None
    
    def _get_recent_alerts(self, alert_id: str, time_window: timedelta) -> List[Alert]:
        """指定時間内の同じアラートIDのアラートを取得"""
        # 実装簡素化のため、ここでは空リストを返す
        # 実際の実装ではDynamoDBクエリを使用
        return []
    
    def _get_similar_alerts(self, source: str, severity: AlertSeverity, time_window: timedelta) -> List[Alert]:
        """指定時間内の同じソース・重要度のアラートを取得"""
        # 実装簡素化のため、ここでは空リストを返す
        # 実際の実装ではDynamoDBクエリを使用
        return []
    
    def _send_notifications(self, alert: Alert) -> None:
        """通知を送信"""
        # Slack通知
        slack_webhook = self._get_notification_config('slack-webhook-url')
        if slack_webhook:
            self._send_slack_notification(alert, slack_webhook)
        
        # 重要度に応じてエスカレーション
        if alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
            self._send_escalation_notifications(alert)
    
    def _send_slack_notification(self, alert: Alert, webhook_url: str) -> None:
        """Slack通知を送信"""
        try:
            # 重要度に応じて色とアイコンを変更
            color_map = {
                AlertSeverity.LOW: "good",
                AlertSeverity.MEDIUM: "warning", 
                AlertSeverity.HIGH: "danger",
                AlertSeverity.CRITICAL: "#8B0000"  # dark red
            }
            
            emoji_map = {
                AlertSeverity.LOW: "ℹ️",
                AlertSeverity.MEDIUM: "⚠️",
                AlertSeverity.HIGH: "🚨",
                AlertSeverity.CRITICAL: "🔥"
            }
            
            color = color_map.get(alert.severity, "warning")
            emoji = emoji_map.get(alert.severity, "⚠️")
            
            # メタデータ情報を整形
            metadata_text = ""
            if alert.metadata:
                metadata_items = [f"*{k}:* {v}" for k, v in alert.metadata.items()]
                metadata_text = f"\n\n*Additional Info:*\n{chr(10).join(metadata_items)}"
            
            slack_message = {
                "text": f"{emoji} {alert.severity.value.upper()} Alert: {alert.title}",
                "attachments": [
                    {
                        "color": color,
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"*{alert.severity.value.upper()} Alert* {emoji}\n\n*Title:* {alert.title}\n*Environment:* {alert.environment}\n*Source:* {alert.source}\n*Time:* {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n*Description:*\n{alert.description}{metadata_text}"
                                }
                            },
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {
                                            "type": "plain_text",
                                            "text": "Acknowledge"
                                        },
                                        "action_id": f"ack_{alert.id}",
                                        "style": "primary"
                                    },
                                    {
                                        "type": "button",
                                        "text": {
                                            "type": "plain_text",
                                            "text": "View Logs"
                                        },
                                        "url": f"https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group//aws/lambda/stock-analysis-{self.environment}"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(
                webhook_url,
                json=slack_message,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Slack notification sent for alert {alert.id}")
            else:
                logger.error(f"Failed to send Slack notification: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to send Slack notification for alert {alert.id}: {str(e)}")
    
    def _send_resolution_notification(self, alert: Alert, resolved_by: str) -> None:
        """解決通知を送信"""
        slack_webhook = self._get_notification_config('slack-webhook-url')
        if not slack_webhook:
            return
        
        try:
            slack_message = {
                "text": f"✅ Alert Resolved: {alert.title}",
                "attachments": [
                    {
                        "color": "good",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"*Alert Resolved* ✅\n\n*Title:* {alert.title}\n*Environment:* {alert.environment}\n*Resolved by:* {resolved_by}\n*Duration:* {(alert.resolved_at - alert.timestamp).total_seconds() / 60:.1f} minutes"
                                }
                            }
                        ]
                    }
                ]
            }
            
            requests.post(slack_webhook, json=slack_message, timeout=10)
            
        except Exception as e:
            logger.error(f"Failed to send resolution notification: {str(e)}")
    
    def _send_escalation_notifications(self, alert: Alert) -> None:
        """エスカレーション通知を送信"""
        # 高重要度・クリティカルアラートの場合、追加の通知チャネルを使用
        # 例：PagerDuty、電話、SMS等
        logger.info(f"Escalation required for alert {alert.id} with severity {alert.severity.value}")
        
        # メール通知の設定例
        email_recipients = self._get_notification_config('escalation-email-list')
        if email_recipients and alert.severity == AlertSeverity.CRITICAL:
            self._send_email_notification(alert, email_recipients.split(','))
    
    def _send_email_notification(self, alert: Alert, recipients: List[str]) -> None:
        """メール通知を送信（SNS経由）"""
        try:
            sns = boto3.client('sns')
            
            subject = f"CRITICAL Alert: {alert.title} - {self.environment}"
            message = f"""
Critical Alert in Stock Analysis System

Title: {alert.title}
Environment: {alert.environment}
Source: {alert.source}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
Severity: {alert.severity.value.upper()}

Description:
{alert.description}

Additional Information:
{json.dumps(alert.metadata, indent=2) if alert.metadata else 'None'}

Please investigate immediately.
            """
            
            # SNSトピックに送信（事前に作成が必要）
            topic_arn = f"arn:aws:sns:us-east-1:123456789012:stock-analysis-critical-alerts-{self.environment}"
            
            sns.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=message
            )
            
            logger.info(f"Email notification sent for critical alert {alert.id}")
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")


# グローバルインスタンス
import os
_environment = os.environ.get('ENVIRONMENT', 'dev')
alert_manager = AlertManager(environment=_environment)