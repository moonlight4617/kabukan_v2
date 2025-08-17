# -*- coding: utf-8 -*-
"""
Slack通知メッセージフォーマットサービス
分析結果をSlackメッセージ形式に変換、リッチフォーマット（ブロック、添付ファイル）のサポート機能を提供
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.models.analysis_models import (
    AnalysisResult, AnalysisType, Recommendation, RiskAssessment, RiskLevel
)
from src.services.daily_analysis_service import (
    DailyAnalysisResult, HoldingRecommendation, WatchlistRecommendation, HoldingAction, WatchlistAction
)
from src.services.weekly_analysis_service import (
    WeeklyAnalysisResult, StockPerformance, PortfolioPerformance, BenchmarkComparison, PerformanceCategory
)
from src.services.monthly_analysis_service import (
    MonthlyAnalysisResult, RegionalPerformance, SectorPerformance, DiversificationMetrics, RebalanceRecommendation
)
from src.services.slack_service import (
    SlackMessage, SlackAttachment, SlackField, SlackBlock, MessageType, Priority
)


logger = logging.getLogger(__name__)


class NotificationTemplate(Enum):
    """通知テンプレート"""
    DAILY_ANALYSIS = "daily_analysis"
    WEEKLY_ANALYSIS = "weekly_analysis"
    MONTHLY_ANALYSIS = "monthly_analysis"
    ERROR_NOTIFICATION = "error_notification"
    SYSTEM_STATUS = "system_status"
    PORTFOLIO_ALERT = "portfolio_alert"
    RISK_WARNING = "risk_warning"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            NotificationTemplate.DAILY_ANALYSIS: "日次分析結果",
            NotificationTemplate.WEEKLY_ANALYSIS: "週次分析結果",
            NotificationTemplate.MONTHLY_ANALYSIS: "月次分析結果",
            NotificationTemplate.ERROR_NOTIFICATION: "エラー通知",
            NotificationTemplate.SYSTEM_STATUS: "システム状態",
            NotificationTemplate.PORTFOLIO_ALERT: "ポートフォリオアラート",
            NotificationTemplate.RISK_WARNING: "リスク警告"
        }[self]


@dataclass
class NotificationContext:
    """通知コンテキスト"""
    template: NotificationTemplate
    priority: Priority
    include_details: bool = True
    include_charts: bool = False
    mention_users: List[str] = None
    custom_footer: Optional[str] = None
    
    def __post_init__(self):
        if self.mention_users is None:
            self.mention_users = []


class SlackNotificationFormatter:
    """Slack通知メッセージフォーマットサービス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialize_formatters()
    
    def _initialize_formatters(self):
        """フォーマッター初期化"""
        self.action_emoji = {
            HoldingAction.BUY_MORE: ":arrow_up:",
            HoldingAction.SELL_PARTIAL: ":arrow_down:",
            HoldingAction.SELL_ALL: ":arrow_double_down:",
            HoldingAction.HOLD: ":pause_button:",
            WatchlistAction.BUY: ":green_circle:",
            WatchlistAction.WAIT: ":yellow_circle:",
            WatchlistAction.REMOVE: ":red_circle:"
        }
        
        self.risk_emoji = {
            RiskLevel.LOW: ":green_heart:",
            RiskLevel.MEDIUM: ":yellow_heart:",
            RiskLevel.HIGH: ":orange_heart:",
            RiskLevel.CRITICAL: ":red_circle:"
        }
        
        self.performance_emoji = {
            PerformanceCategory.EXCELLENT: ":star:",
            PerformanceCategory.GOOD: ":white_check_mark:",
            PerformanceCategory.AVERAGE: ":heavy_minus_sign:",
            PerformanceCategory.POOR: ":warning:",
            PerformanceCategory.VERY_POOR: ":x:"
        }
    
    def format_daily_analysis_notification(self,
                                         analysis_result: DailyAnalysisResult,
                                         context: NotificationContext) -> SlackMessage:
        """
        日次分析結果通知をフォーマット
        
        Args:
            analysis_result: 日次分析結果
            context: 通知コンテキスト
            
        Returns:
            SlackMessage: フォーマット済みSlackメッセージ
        """
        # メインタイトル
        title = f":chart_with_upwards_trend: 日次株価分析結果 - {analysis_result.analysis_date.strftime('%Y/%m/%d')}"
        
        # サマリーテキスト
        summary_parts = []
        if analysis_result.holding_recommendations:
            holding_count = len(analysis_result.holding_recommendations)
            summary_parts.append(f"保有銘柄 {holding_count}件の分析")
        
        if analysis_result.watchlist_recommendations:
            watchlist_count = len(analysis_result.watchlist_recommendations)
            summary_parts.append(f"ウォッチリスト {watchlist_count}件の分析")
        
        summary_text = "、".join(summary_parts) if summary_parts else "日次分析を実行しました"
        
        # 添付ファイルの作成
        attachments = []
        
        # 保有銘柄の推奨事項
        if analysis_result.holding_recommendations and context.include_details:
            holding_attachment = self._create_holding_recommendations_attachment(
                analysis_result.holding_recommendations
            )
            attachments.append(holding_attachment)
        
        # ウォッチリストの推奨事項
        if analysis_result.watchlist_recommendations and context.include_details:
            watchlist_attachment = self._create_watchlist_recommendations_attachment(
                analysis_result.watchlist_recommendations
            )
            attachments.append(watchlist_attachment)
        
        # 市場サマリー
        if analysis_result.market_summary:
            market_attachment = SlackAttachment(
                color="#0099cc",
                title="市場概況",
                text=analysis_result.market_summary,
                footer=context.custom_footer or "株価分析システム",
                timestamp=analysis_result.analysis_date.timestamp()
            )
            attachments.append(market_attachment)
        
        # メンション追加
        mention_text = ""
        if context.mention_users:
            mentions = " ".join([f"<@{user}>" for user in context.mention_users])
            mention_text = f"{mentions} "
        
        final_text = f"{mention_text}{title}\n{summary_text}"
        
        return SlackMessage(
            text=final_text,
            attachments=attachments,
            message_type=MessageType.ANALYSIS_RESULT,
            priority=context.priority
        )
    
    def format_weekly_analysis_notification(self,
                                          analysis_result: WeeklyAnalysisResult,
                                          context: NotificationContext) -> SlackMessage:
        """
        週次分析結果通知をフォーマット
        
        Args:
            analysis_result: 週次分析結果
            context: 通知コンテキスト
            
        Returns:
            SlackMessage: フォーマット済みSlackメッセージ
        """
        # メインタイトル
        period_start = analysis_result.analysis_period_start.strftime('%m/%d')
        period_end = analysis_result.analysis_period_end.strftime('%m/%d')
        title = f":bar_chart: 週次ポートフォリオ分析結果 ({period_start} - {period_end})"
        
        # パフォーマンスサマリー
        portfolio = analysis_result.portfolio_performance
        return_direction = "利益" if portfolio.weekly_return > 0 else "損失"
        performance_emoji = ":green_circle:" if portfolio.weekly_return > 0 else ":red_circle:"
        
        summary_text = f"{performance_emoji} 週間リターン: {portfolio.weekly_return_pct:.2f}% ({return_direction}: ¥{abs(portfolio.weekly_return):,.0f})"
        
        # 添付ファイルの作成
        attachments = []
        
        # ポートフォリオパフォーマンス
        if context.include_details:
            portfolio_fields = [
                SlackField("ポートフォリオ価値", f"¥{portfolio.total_value:,.0f}", True),
                SlackField("週間リターン", f"{portfolio.weekly_return_pct:.2f}%", True),
                SlackField("ボラティリティ", f"{portfolio.weekly_volatility:.2f}%", True),
                SlackField("シャープレシオ", f"{portfolio.sharpe_ratio:.2f}", True),
                SlackField("最大ドローダウン", f"{portfolio.max_drawdown:.2f}%", True),
                SlackField("リスク調整後リターン", f"{portfolio.risk_adjusted_return:.2f}", True)
            ]
            
            portfolio_attachment = SlackAttachment(
                color="#36a64f" if portfolio.weekly_return > 0 else "#ff0000",
                title="ポートフォリオパフォーマンス",
                fields=portfolio_fields,
                footer="週次分析",
                timestamp=analysis_result.analysis_date.timestamp()
            )
            attachments.append(portfolio_attachment)
        
        # ベンチマーク比較
        if context.include_details:
            benchmark = analysis_result.benchmark_comparison
            benchmark_fields = [
                SlackField("ベンチマーク", benchmark.benchmark_name, True),
                SlackField("ベンチマークリターン", f"{benchmark.benchmark_return:.2f}%", True),
                SlackField("アルファ", f"{benchmark.alpha:.2f}%", True),
                SlackField("ベータ", f"{benchmark.beta:.2f}", True),
                SlackField("相関係数", f"{benchmark.correlation:.2f}", True),
                SlackField("情報比率", f"{benchmark.information_ratio:.2f}", True)
            ]
            
            benchmark_color = "#36a64f" if benchmark.alpha > 0 else "#ff9500"
            benchmark_attachment = SlackAttachment(
                color=benchmark_color,
                title="ベンチマーク比較",
                fields=benchmark_fields,
                footer="ベンチマーク分析",
                timestamp=analysis_result.analysis_date.timestamp()
            )
            attachments.append(benchmark_attachment)
        
        # トップパフォーマー
        if analysis_result.top_performers and context.include_details:
            top_performers_text = self._format_stock_performances(analysis_result.top_performers, "上位")
            top_attachment = SlackAttachment(
                color="#00ff00",
                title="トップパフォーマー",
                text=top_performers_text,
                footer="個別銘柄分析"
            )
            attachments.append(top_attachment)
        
        # ボトムパフォーマー
        if analysis_result.bottom_performers and context.include_details:
            bottom_performers_text = self._format_stock_performances(analysis_result.bottom_performers, "下位")
            bottom_attachment = SlackAttachment(
                color="#ff9500",
                title="ボトムパフォーマー",
                text=bottom_performers_text,
                footer="個別銘柄分析"
            )
            attachments.append(bottom_attachment)
        
        # 推奨事項
        if analysis_result.recommendations:
            recommendations_text = "\n".join([f"• {rec}" for rec in analysis_result.recommendations])
            rec_attachment = SlackAttachment(
                color="#0099cc",
                title="推奨事項",
                text=recommendations_text,
                footer="投資推奨"
            )
            attachments.append(rec_attachment)
        
        return SlackMessage(
            text=f"{title}\n{summary_text}",
            attachments=attachments,
            message_type=MessageType.ANALYSIS_RESULT,
            priority=context.priority
        )
    
    def format_monthly_analysis_notification(self,
                                           analysis_result: MonthlyAnalysisResult,
                                           context: NotificationContext) -> SlackMessage:
        """
        月次分析結果通知をフォーマット
        
        Args:
            analysis_result: 月次分析結果
            context: 通知コンテキスト
            
        Returns:
            SlackMessage: フォーマット済みSlackメッセージ
        """
        # メインタイトル
        month_str = analysis_result.analysis_date.strftime('%Y年%m月')
        title = f":calendar: 月次ポートフォリオ分析結果 - {month_str}"
        
        # サマリーテキスト
        diversification = analysis_result.diversification_metrics
        summary_text = f":chart_with_upwards_trend: 分散投資スコア: {diversification.overall_score}/100"
        
        # 添付ファイルの作成
        attachments = []
        
        # 地域別パフォーマンス
        if analysis_result.regional_performances and context.include_details:
            regional_attachment = self._create_regional_performance_attachment(
                analysis_result.regional_performances
            )
            attachments.append(regional_attachment)
        
        # セクター別パフォーマンス
        if analysis_result.sector_performances and context.include_details:
            sector_attachment = self._create_sector_performance_attachment(
                analysis_result.sector_performances
            )
            attachments.append(sector_attachment)
        
        # 分散投資メトリクス
        if context.include_details:
            diversification_fields = [
                SlackField("総合スコア", f"{diversification.overall_score}/100", True),
                SlackField("地域分散度", diversification.regional_diversification.display_name, True),
                SlackField("セクター分散度", diversification.sector_diversification.display_name, True),
                SlackField("集中リスクスコア", f"{diversification.concentration_risk_score}/100", True),
                SlackField("相関リスクスコア", f"{diversification.correlation_risk_score}/100", True)
            ]
            
            diversification_color = self._get_diversification_color(diversification.overall_score)
            diversification_attachment = SlackAttachment(
                color=diversification_color,
                title="分散投資メトリクス",
                fields=diversification_fields,
                footer="リスク分析",
                timestamp=analysis_result.analysis_date.timestamp()
            )
            attachments.append(diversification_attachment)
        
        # リバランス推奨
        if analysis_result.rebalance_recommendations and context.include_details:
            rebalance_attachment = self._create_rebalance_recommendations_attachment(
                analysis_result.rebalance_recommendations
            )
            attachments.append(rebalance_attachment)
        
        return SlackMessage(
            text=f"{title}\n{summary_text}",
            attachments=attachments,
            message_type=MessageType.ANALYSIS_RESULT,
            priority=context.priority
        )
    
    def format_error_notification(self,
                                error_message: str,
                                error_context: Optional[Dict[str, Any]] = None,
                                context: NotificationContext = None) -> SlackMessage:
        """
        エラー通知をフォーマット
        
        Args:
            error_message: エラーメッセージ
            error_context: エラーコンテキスト
            context: 通知コンテキスト
            
        Returns:
            SlackMessage: フォーマット済みSlackメッセージ
        """
        if context is None:
            context = NotificationContext(
                template=NotificationTemplate.ERROR_NOTIFICATION,
                priority=Priority.HIGH
            )
        
        title = ":rotating_light: システムエラーが発生しました"
        
        fields = []
        if error_context:
            for key, value in error_context.items():
                fields.append(SlackField(
                    title=key.replace('_', ' ').title(),
                    value=str(value),
                    short=True
                ))
        
        attachment = SlackAttachment(
            color="#ff0000",
            title="エラー詳細",
            text=error_message,
            fields=fields,
            footer="システム監視",
            timestamp=datetime.now().timestamp()
        )
        
        mention_text = ""
        if context.mention_users:
            mentions = " ".join([f"<@{user}>" for user in context.mention_users])
            mention_text = f"{mentions} "
        
        return SlackMessage(
            text=f"{mention_text}{title}",
            attachments=[attachment],
            message_type=MessageType.ERROR,
            priority=context.priority
        )
    
    def format_risk_warning_notification(self,
                                       risk_assessment: RiskAssessment,
                                       context: NotificationContext) -> SlackMessage:
        """
        リスク警告通知をフォーマット
        
        Args:
            risk_assessment: リスク評価
            context: 通知コンテキスト
            
        Returns:
            SlackMessage: フォーマット済みSlackメッセージ
        """
        risk_emoji = self.risk_emoji.get(risk_assessment.level, ":warning:")
        title = f"{risk_emoji} リスク警告 - {risk_assessment.level.display_name}レベル"
        
        fields = [
            SlackField("リスクレベル", risk_assessment.level.display_name, True),
            SlackField("リスクスコア", f"{risk_assessment.score}/100", True)
        ]
        
        if risk_assessment.factors:
            factors_text = "\n".join([f"• {factor}" for factor in risk_assessment.factors])
            fields.append(SlackField("リスク要因", factors_text, False))
        
        if risk_assessment.mitigation_strategies:
            strategies_text = "\n".join([f"• {strategy}" for strategy in risk_assessment.mitigation_strategies])
            fields.append(SlackField("対策", strategies_text, False))
        
        risk_color = {
            RiskLevel.LOW: "#36a64f",
            RiskLevel.MEDIUM: "#ff9500",
            RiskLevel.HIGH: "#ff6600",
            RiskLevel.CRITICAL: "#ff0000"
        }.get(risk_assessment.level, "#ff9500")
        
        attachment = SlackAttachment(
            color=risk_color,
            title="リスク評価詳細",
            text=risk_assessment.description,
            fields=fields,
            footer="リスク管理システム",
            timestamp=datetime.now().timestamp()
        )
        
        return SlackMessage(
            text=title,
            attachments=[attachment],
            message_type=MessageType.ALERT,
            priority=context.priority
        )
    
    def _create_holding_recommendations_attachment(self,
                                                 recommendations: List[HoldingRecommendation]) -> SlackAttachment:
        """保有銘柄推奨事項の添付ファイルを作成"""
        fields = []
        
        for rec in recommendations[:5]:  # 上位5件
            action_emoji = self.action_emoji.get(rec.action, ":question:")
            confidence_bar = self._create_confidence_bar(rec.confidence)
            
            field_value = f"{action_emoji} {rec.action.display_name}\n"
            field_value += f"信頼度: {confidence_bar} {rec.confidence:.1%}\n"
            if rec.reasoning:
                field_value += f"理由: {rec.reasoning[:50]}..."
            
            fields.append(SlackField(
                title=f"{rec.symbol}",
                value=field_value,
                short=True
            ))
        
        return SlackAttachment(
            color="#36a64f",
            title="保有銘柄推奨事項",
            fields=fields,
            footer=f"分析対象: {len(recommendations)}銘柄"
        )
    
    def _create_watchlist_recommendations_attachment(self,
                                                   recommendations: List[WatchlistRecommendation]) -> SlackAttachment:
        """ウォッチリスト推奨事項の添付ファイルを作成"""
        fields = []
        
        for rec in recommendations[:5]:  # 上位5件
            action_emoji = self.action_emoji.get(rec.action, ":question:")
            priority_stars = "⭐" * min(rec.priority, 5)
            
            field_value = f"{action_emoji} {rec.action.display_name}\n"
            field_value += f"優先度: {priority_stars} ({rec.priority})\n"
            if rec.reasoning:
                field_value += f"理由: {rec.reasoning[:50]}..."
            
            fields.append(SlackField(
                title=f"{rec.symbol}",
                value=field_value,
                short=True
            ))
        
        return SlackAttachment(
            color="#0099cc",
            title="ウォッチリスト推奨事項",
            fields=fields,
            footer=f"分析対象: {len(recommendations)}銘柄"
        )
    
    def _create_regional_performance_attachment(self,
                                              performances: List[RegionalPerformance]) -> SlackAttachment:
        """地域別パフォーマンスの添付ファイルを作成"""
        fields = []
        
        for perf in performances:
            return_emoji = ":chart_with_upwards_trend:" if perf.return_percentage > 0 else ":chart_with_downwards_trend:"
            
            field_value = f"{return_emoji} {perf.return_percentage:.2f}%\n"
            field_value += f"配分: {perf.allocation_percentage:.1f}%"
            
            fields.append(SlackField(
                title=perf.region.display_name,
                value=field_value,
                short=True
            ))
        
        return SlackAttachment(
            color="#9966cc",
            title="地域別パフォーマンス",
            fields=fields,
            footer="地域分析"
        )
    
    def _create_sector_performance_attachment(self,
                                            performances: List[SectorPerformance]) -> SlackAttachment:
        """セクター別パフォーマンスの添付ファイルを作成"""
        fields = []
        
        for perf in performances:
            return_emoji = ":chart_with_upwards_trend:" if perf.return_percentage > 0 else ":chart_with_downwards_trend:"
            
            field_value = f"{return_emoji} {perf.return_percentage:.2f}%\n"
            field_value += f"配分: {perf.allocation_percentage:.1f}%"
            
            fields.append(SlackField(
                title=perf.sector.display_name,
                value=field_value,
                short=True
            ))
        
        return SlackAttachment(
            color="#ff6600",
            title="セクター別パフォーマンス",
            fields=fields,
            footer="セクター分析"
        )
    
    def _create_rebalance_recommendations_attachment(self,
                                                   recommendations: List[RebalanceRecommendation]) -> SlackAttachment:
        """リバランス推奨事項の添付ファイルを作成"""
        fields = []
        
        for rec in recommendations:
            urgency_emoji = ":exclamation:" if rec.urgency_level.value == "high" else ":information_source:"
            
            field_value = f"{urgency_emoji} 緊急度: {rec.urgency_level.display_name}\n"
            field_value += f"理由: {rec.reasoning[:50]}..."
            
            fields.append(SlackField(
                title=rec.recommendation_type.display_name,
                value=field_value,
                short=False
            ))
        
        return SlackAttachment(
            color="#ff9500",
            title="リバランス推奨事項",
            fields=fields,
            footer="ポートフォリオ最適化"
        )
    
    def _format_stock_performances(self, performances: List[StockPerformance], category: str) -> str:
        """株式パフォーマンスをフォーマット"""
        lines = []
        for i, perf in enumerate(performances, 1):
            perf_emoji = self.performance_emoji.get(perf.performance_category, ":heavy_minus_sign:")
            lines.append(f"{i}. {perf.symbol} {perf_emoji} {perf.weekly_return_pct:.2f}%")
        
        return "\n".join(lines)
    
    def _create_confidence_bar(self, confidence: float) -> str:
        """信頼度バーを作成"""
        bar_length = 5
        filled_length = int(confidence * bar_length)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return f"[{bar}]"
    
    def _get_diversification_color(self, score: int) -> str:
        """分散投資スコアに基づく色を取得"""
        if score >= 80:
            return "#36a64f"  # 緑
        elif score >= 60:
            return "#ff9500"  # オレンジ
        else:
            return "#ff0000"  # 赤