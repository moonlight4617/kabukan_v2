# -*- coding: utf-8 -*-
"""
ワークフローオーケストレーターの単体テスト
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.services.workflow_orchestrator import (
    WorkflowOrchestrator, WorkflowStage, WorkflowStepResult, WorkflowResult,
    RecoveryAction, WorkflowError, WorkflowMetrics, WorkflowContext
)


class TestWorkflowStage:
    """ワークフローステージのテストクラス"""
    
    def test_workflow_stage_creation(self):
        """ワークフローステージ作成のテスト"""
        async def test_step():
            return "success"
        
        stage = WorkflowStage(
            name="test_stage",
            step_function=test_step,
            retry_count=3,
            timeout_seconds=30,
            critical=True,
            recovery_action=RecoveryAction.RETRY
        )
        
        assert stage.name == "test_stage"
        assert stage.step_function == test_step
        assert stage.retry_count == 3
        assert stage.timeout_seconds == 30
        assert stage.critical is True
        assert stage.recovery_action == RecoveryAction.RETRY
    
    def test_workflow_stage_defaults(self):
        """ワークフローステージデフォルト値のテスト"""
        async def test_step():
            return "success"
        
        stage = WorkflowStage(
            name="default_stage",
            step_function=test_step
        )
        
        assert stage.retry_count == 3
        assert stage.timeout_seconds == 60
        assert stage.critical is False
        assert stage.recovery_action == RecoveryAction.CONTINUE
        assert stage.dependencies == []


class TestWorkflowStepResult:
    """ワークフローステップ結果のテストクラス"""
    
    def test_workflow_step_result_success(self):
        """成功結果のテスト"""
        result = WorkflowStepResult(
            stage_name="test_stage",
            success=True,
            result="test_result",
            duration_seconds=1.5,
            attempt_count=1
        )
        
        assert result.stage_name == "test_stage"
        assert result.success is True
        assert result.result == "test_result"
        assert result.duration_seconds == 1.5
        assert result.attempt_count == 1
        assert result.error is None
    
    def test_workflow_step_result_failure(self):
        """失敗結果のテスト"""
        error = ValueError("Test error")
        
        result = WorkflowStepResult(
            stage_name="failed_stage",
            success=False,
            error=error,
            duration_seconds=2.0,
            attempt_count=3
        )
        
        assert result.stage_name == "failed_stage"
        assert result.success is False
        assert result.result is None
        assert result.error == error
        assert result.duration_seconds == 2.0
        assert result.attempt_count == 3
    
    def test_workflow_step_result_to_dict(self):
        """ステップ結果辞書変換のテスト"""
        timestamp = datetime.now()
        
        result = WorkflowStepResult(
            stage_name="test_stage",
            success=True,
            result="success",
            duration_seconds=1.0,
            attempt_count=1,
            timestamp=timestamp
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["stage_name"] == "test_stage"
        assert result_dict["success"] is True
        assert result_dict["result"] == "success"
        assert result_dict["duration_seconds"] == 1.0
        assert result_dict["attempt_count"] == 1
        assert result_dict["timestamp"] == timestamp.isoformat()


class TestWorkflowResult:
    """ワークフロー結果のテストクラス"""
    
    def test_workflow_result_creation(self):
        """ワークフロー結果作成のテスト"""
        step_results = [
            WorkflowStepResult("stage1", True, "result1", 1.0, 1),
            WorkflowStepResult("stage2", True, "result2", 2.0, 1)
        ]
        
        result = WorkflowResult(
            workflow_id="test_workflow",
            success=True,
            step_results=step_results,
            total_duration_seconds=3.0,
            completed_stages=2,
            total_stages=2
        )
        
        assert result.workflow_id == "test_workflow"
        assert result.success is True
        assert len(result.step_results) == 2
        assert result.total_duration_seconds == 3.0
        assert result.completed_stages == 2
        assert result.total_stages == 2
        assert result.failure_stage is None
    
    def test_workflow_result_failure(self):
        """ワークフロー失敗結果のテスト"""
        step_results = [
            WorkflowStepResult("stage1", True, "result1", 1.0, 1),
            WorkflowStepResult("stage2", False, None, 2.0, 3, error=ValueError("Failed"))
        ]
        
        result = WorkflowResult(
            workflow_id="failed_workflow",
            success=False,
            step_results=step_results,
            total_duration_seconds=3.0,
            completed_stages=1,
            total_stages=2,
            failure_stage="stage2",
            error=ValueError("Failed")
        )
        
        assert result.success is False
        assert result.failure_stage == "stage2"
        assert isinstance(result.error, ValueError)
    
    def test_workflow_result_to_dict(self):
        """ワークフロー結果辞書変換のテスト"""
        start_time = datetime.now()
        end_time = datetime.now()
        
        step_results = [
            WorkflowStepResult("stage1", True, "result1", 1.0, 1)
        ]
        
        result = WorkflowResult(
            workflow_id="test_workflow",
            success=True,
            step_results=step_results,
            total_duration_seconds=1.0,
            completed_stages=1,
            total_stages=1,
            start_time=start_time,
            end_time=end_time
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["workflow_id"] == "test_workflow"
        assert result_dict["success"] is True
        assert result_dict["total_duration_seconds"] == 1.0
        assert result_dict["completed_stages"] == 1
        assert result_dict["total_stages"] == 1
        assert result_dict["start_time"] == start_time.isoformat()
        assert result_dict["end_time"] == end_time.isoformat()
        assert len(result_dict["step_results"]) == 1


class TestWorkflowError:
    """ワークフローエラーのテストクラス"""
    
    def test_workflow_error_creation(self):
        """ワークフローエラー作成のテスト"""
        original_error = ValueError("Original error")
        
        workflow_error = WorkflowError(
            stage_name="failed_stage",
            original_error=original_error,
            attempt_count=3,
            recovery_attempted=True
        )
        
        assert workflow_error.stage_name == "failed_stage"
        assert workflow_error.original_error == original_error
        assert workflow_error.attempt_count == 3
        assert workflow_error.recovery_attempted is True
        assert "failed_stage" in str(workflow_error)


class TestWorkflowMetrics:
    """ワークフローメトリクスのテストクラス"""
    
    def test_workflow_metrics_creation(self):
        """ワークフローメトリクス作成のテスト"""
        metrics = WorkflowMetrics()
        
        assert metrics.total_workflows == 0
        assert metrics.successful_workflows == 0
        assert metrics.failed_workflows == 0
        assert metrics.average_duration == 0.0
        assert len(metrics.stage_success_rates) == 0
        assert len(metrics.error_counts) == 0
    
    def test_workflow_metrics_record_success(self):
        """成功ワークフロー記録のテスト"""
        metrics = WorkflowMetrics()
        
        step_results = [
            WorkflowStepResult("stage1", True, "result1", 1.0, 1),
            WorkflowStepResult("stage2", True, "result2", 2.0, 1)
        ]
        
        workflow_result = WorkflowResult(
            workflow_id="test",
            success=True,
            step_results=step_results,
            total_duration_seconds=3.0,
            completed_stages=2,
            total_stages=2
        )
        
        metrics.record_workflow(workflow_result)
        
        assert metrics.total_workflows == 1
        assert metrics.successful_workflows == 1
        assert metrics.failed_workflows == 0
        assert metrics.success_rate == 1.0
        assert metrics.average_duration == 3.0
        
        # ステージ成功率
        assert metrics.stage_success_rates["stage1"] == 1.0
        assert metrics.stage_success_rates["stage2"] == 1.0
    
    def test_workflow_metrics_record_failure(self):
        """失敗ワークフロー記録のテスト"""
        metrics = WorkflowMetrics()
        
        step_results = [
            WorkflowStepResult("stage1", True, "result1", 1.0, 1),
            WorkflowStepResult("stage2", False, None, 2.0, 3, error=ValueError("Failed"))
        ]
        
        workflow_result = WorkflowResult(
            workflow_id="test",
            success=False,
            step_results=step_results,
            total_duration_seconds=3.0,
            completed_stages=1,
            total_stages=2,
            failure_stage="stage2",
            error=ValueError("Failed")
        )
        
        metrics.record_workflow(workflow_result)
        
        assert metrics.total_workflows == 1
        assert metrics.successful_workflows == 0
        assert metrics.failed_workflows == 1
        assert metrics.success_rate == 0.0
        
        # エラーカウント
        assert metrics.error_counts["ValueError"] == 1
        
        # ステージ成功率
        assert metrics.stage_success_rates["stage1"] == 1.0
        assert metrics.stage_success_rates["stage2"] == 0.0
    
    def test_workflow_metrics_to_dict(self):
        """メトリクス辞書変換のテスト"""
        metrics = WorkflowMetrics()
        metrics.total_workflows = 2
        metrics.successful_workflows = 1
        metrics.failed_workflows = 1
        metrics.total_duration = 5.0
        
        result = metrics.to_dict()
        
        assert result["total_workflows"] == 2
        assert result["successful_workflows"] == 1
        assert result["failed_workflows"] == 1
        assert result["success_rate"] == 0.5
        assert result["average_duration"] == 2.5


class TestWorkflowContext:
    """ワークフローコンテキストのテストクラス"""
    
    def test_workflow_context_creation(self):
        """ワークフローコンテキスト作成のテスト"""
        context = WorkflowContext(
            workflow_id="test_workflow",
            user_id="user123",
            execution_environment="test",
            parameters={"param1": "value1"}
        )
        
        assert context.workflow_id == "test_workflow"
        assert context.user_id == "user123"
        assert context.execution_environment == "test"
        assert context.parameters == {"param1": "value1"}
        assert context.start_time is not None
        assert context.metadata == {}
    
    def test_workflow_context_add_metadata(self):
        """ワークフローコンテキストメタデータ追加のテスト"""
        context = WorkflowContext("test")
        
        context.add_metadata("key1", "value1")
        context.add_metadata("key2", "value2")
        
        assert context.metadata["key1"] == "value1"
        assert context.metadata["key2"] == "value2"
    
    def test_workflow_context_to_dict(self):
        """ワークフローコンテキスト辞書変換のテスト"""
        context = WorkflowContext(
            workflow_id="test",
            user_id="user123",
            parameters={"param": "value"}
        )
        context.add_metadata("meta", "data")
        
        result = context.to_dict()
        
        assert result["workflow_id"] == "test"
        assert result["user_id"] == "user123"
        assert result["parameters"] == {"param": "value"}
        assert result["metadata"] == {"meta": "data"}
        assert "start_time" in result


class TestWorkflowOrchestrator:
    """ワークフローオーケストレーターのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.orchestrator = WorkflowOrchestrator()
    
    def test_orchestrator_initialization(self):
        """オーケストレーター初期化のテスト"""
        assert len(self.orchestrator.stages) == 0
        assert isinstance(self.orchestrator.metrics, WorkflowMetrics)
        assert len(self.orchestrator.execution_history) == 0
    
    def test_add_stage(self):
        """ステージ追加のテスト"""
        async def test_step():
            return "success"
        
        stage = WorkflowStage("test_stage", test_step)
        self.orchestrator.add_stage(stage)
        
        assert len(self.orchestrator.stages) == 1
        assert self.orchestrator.stages[0] == stage
    
    def test_add_stages_multiple(self):
        """複数ステージ追加のテスト"""
        async def step1():
            return "step1"
        
        async def step2():
            return "step2"
        
        stages = [
            WorkflowStage("stage1", step1),
            WorkflowStage("stage2", step2)
        ]
        
        self.orchestrator.add_stages(stages)
        
        assert len(self.orchestrator.stages) == 2
        assert self.orchestrator.stages[0].name == "stage1"
        assert self.orchestrator.stages[1].name == "stage2"
    
    @pytest.mark.asyncio
    async def test_execute_workflow_success(self):
        """ワークフロー実行成功のテスト"""
        async def step1():
            await asyncio.sleep(0.01)
            return "result1"
        
        async def step2():
            await asyncio.sleep(0.01)
            return "result2"
        
        stages = [
            WorkflowStage("stage1", step1),
            WorkflowStage("stage2", step2)
        ]
        self.orchestrator.add_stages(stages)
        
        context = WorkflowContext("test_workflow")
        result = await self.orchestrator.execute_workflow(context)
        
        assert result.success is True
        assert result.workflow_id == "test_workflow"
        assert len(result.step_results) == 2
        assert result.completed_stages == 2
        assert result.total_stages == 2
        assert result.total_duration_seconds > 0
        
        # 各ステージの結果確認
        assert result.step_results[0].stage_name == "stage1"
        assert result.step_results[0].success is True
        assert result.step_results[0].result == "result1"
        
        assert result.step_results[1].stage_name == "stage2"
        assert result.step_results[1].success is True
        assert result.step_results[1].result == "result2"
    
    @pytest.mark.asyncio
    async def test_execute_workflow_failure(self):
        """ワークフロー実行失敗のテスト"""
        async def step1():
            return "result1"
        
        async def step2():
            raise ValueError("Step 2 failed")
        
        stages = [
            WorkflowStage("stage1", step1),
            WorkflowStage("stage2", step2, critical=True)
        ]
        self.orchestrator.add_stages(stages)
        
        context = WorkflowContext("failed_workflow")
        result = await self.orchestrator.execute_workflow(context)
        
        assert result.success is False
        assert result.failure_stage == "stage2"
        assert isinstance(result.error, ValueError)
        assert result.completed_stages == 1
        assert result.total_stages == 2
        
        # 失敗したステージの結果確認
        failed_step = result.step_results[1]
        assert failed_step.stage_name == "stage2"
        assert failed_step.success is False
        assert isinstance(failed_step.error, ValueError)
    
    @pytest.mark.asyncio
    async def test_execute_workflow_with_retry(self):
        """リトライ付きワークフロー実行のテスト"""
        call_count = 0
        
        async def flaky_step():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"
        
        stage = WorkflowStage(
            "flaky_stage",
            flaky_step,
            retry_count=3,
            recovery_action=RecoveryAction.RETRY
        )
        self.orchestrator.add_stage(stage)
        
        context = WorkflowContext("retry_workflow")
        result = await self.orchestrator.execute_workflow(context)
        
        assert result.success is True
        assert call_count == 3
        assert result.step_results[0].attempt_count == 3
        assert result.step_results[0].result == "success"
    
    @pytest.mark.asyncio
    async def test_execute_workflow_timeout(self):
        """ワークフロータイムアウトのテスト"""
        async def slow_step():
            await asyncio.sleep(0.1)  # 100ms
            return "slow_result"
        
        stage = WorkflowStage(
            "slow_stage",
            slow_step,
            timeout_seconds=0.05  # 50ms timeout
        )
        self.orchestrator.add_stage(stage)
        
        context = WorkflowContext("timeout_workflow")
        result = await self.orchestrator.execute_workflow(context)
        
        assert result.success is False
        assert "timeout" in str(result.error).lower() or "timeout" in result.failure_stage
    
    @pytest.mark.asyncio
    async def test_execute_workflow_with_dependencies(self):
        """依存関係付きワークフロー実行のテスト"""
        execution_order = []
        
        async def step1():
            execution_order.append("step1")
            return "result1"
        
        async def step2():
            execution_order.append("step2")
            return "result2"
        
        async def step3():
            execution_order.append("step3")
            return "result3"
        
        stages = [
            WorkflowStage("stage3", step3, dependencies=["stage1", "stage2"]),
            WorkflowStage("stage1", step1),
            WorkflowStage("stage2", step2, dependencies=["stage1"])
        ]
        self.orchestrator.add_stages(stages)
        
        context = WorkflowContext("dependency_workflow")
        result = await self.orchestrator.execute_workflow(context)
        
        assert result.success is True
        
        # 実行順序が依存関係に従っている
        assert execution_order == ["step1", "step2", "step3"]
    
    @pytest.mark.asyncio
    async def test_execute_stage_with_context(self):
        """コンテキスト付きステージ実行のテスト"""
        async def context_step(context):
            return f"Hello {context.user_id}"
        
        stage = WorkflowStage("context_stage", context_step)
        context = WorkflowContext("test", user_id="user123")
        
        result = await self.orchestrator._execute_stage(stage, context)
        
        assert result.success is True
        assert result.result == "Hello user123"
    
    def test_get_execution_metrics(self):
        """実行メトリクス取得のテスト"""
        # テスト用のワークフロー結果を追加
        step_results = [WorkflowStepResult("stage1", True, "result1", 1.0, 1)]
        workflow_result = WorkflowResult(
            "test", True, step_results, 1.0, 1, 1
        )
        self.orchestrator.execution_history.append(workflow_result)
        self.orchestrator.metrics.record_workflow(workflow_result)
        
        metrics = self.orchestrator.get_execution_metrics()
        
        assert metrics["total_workflows"] == 1
        assert metrics["successful_workflows"] == 1
        assert metrics["success_rate"] == 1.0
    
    def test_clear_execution_history(self):
        """実行履歴クリアのテスト"""
        # テスト用のワークフロー結果を追加
        step_results = [WorkflowStepResult("stage1", True, "result1", 1.0, 1)]
        workflow_result = WorkflowResult(
            "test", True, step_results, 1.0, 1, 1
        )
        self.orchestrator.execution_history.append(workflow_result)
        
        assert len(self.orchestrator.execution_history) == 1
        
        # クリア実行
        self.orchestrator.clear_execution_history()
        
        assert len(self.orchestrator.execution_history) == 0
    
    def test_get_stage_by_name(self):
        """ステージ名による取得のテスト"""
        async def test_step():
            return "success"
        
        stage = WorkflowStage("target_stage", test_step)
        self.orchestrator.add_stage(stage)
        
        found_stage = self.orchestrator._get_stage_by_name("target_stage")
        assert found_stage == stage
        
        not_found = self.orchestrator._get_stage_by_name("nonexistent")
        assert not_found is None


if __name__ == "__main__":
    pytest.main([__file__])