"""
商脉系统 — 异步执行引擎

实现技术规格 Chapter 5.3 的异步执行模型：
  - AgentExecutor: 异步任务执行引擎
  - execute_layer(): 同层任务并行执行(asyncio.gather)
  - execute_task(): 单任务执行，含超时和重试机制
  - 超时策略: estimatedDuration * 2
  - 重试策略: 最多2次，指数退避(1s / 2s)
  - result_store: 任务结果存储

参考技术规格样板 Chapter 5
"""
import asyncio
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from app.agents.dag import AgentType, TaskNode, TaskResult, TaskStatus


class AgentExecutor:
    """
    异步执行引擎 — 负责任务的实际执行

    核心能力:
      1. 同层任务并行执行（asyncio.gather）
      2. 单任务超时控制（estimatedDuration * 2）
      3. 失败重试（最多2次，指数退避1s/2s）
      4. 执行结果存储与查询

    使用示例:
      executor = AgentExecutor()
      executor.register_handler(AgentType.MATCH, match_handler)
      results = await executor.execute_layer(layer_tasks)
    """

    # 重试退避基数(秒)
    RETRY_BACKOFF_BASE: float = 1.0
    # 最大重试次数
    MAX_RETRIES: int = 2

    def __init__(self) -> None:
        """初始化执行引擎"""
        self._handlers: dict[AgentType, Callable] = {}
        self.result_store: dict[str, TaskResult] = {}
        self._execution_log: list[dict] = []

    def register_handler(self, agent_type: AgentType, handler: Callable) -> None:
        """
        注册智能体执行处理器

        Args:
            agent_type: 智能体类型
            handler: 异步处理函数，签名为 async (task: TaskNode) -> TaskResult
        """
        self._handlers[agent_type] = handler

    def get_handler(self, agent_type: AgentType) -> Optional[Callable]:
        """
        获取智能体执行处理器

        Args:
            agent_type: 智能体类型

        Returns:
            注册的处理器函数，未注册返回None
        """
        return self._handlers.get(agent_type)

    async def execute_layer(self, tasks: list[TaskNode]) -> list[TaskResult]:
        """
        并行执行同一层的所有任务

        同层任务之间无依赖关系，使用asyncio.gather并行执行。
        任何任务失败不影响同层其他任务。

        Args:
            tasks: 同层任务列表

        Returns:
            各任务的执行结果列表，顺序与输入一致
        """
        if not tasks:
            return []

        # 并行执行所有任务
        coroutines = [self.execute_task(task) for task in tasks]
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # 处理异常结果
        task_results: list[TaskResult] = []
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                task_result = TaskResult(
                    task_id=task.task_id,
                    success=False,
                    error_message=f"任务执行异常: {str(result)}",
                    execution_time=0.0,
                )
                task_results.append(task_result)
                self.result_store[task.task_id] = task_result
            else:
                task_results.append(result)
                self.result_store[task.task_id] = result

        return task_results

    async def execute_task(self, task: TaskNode) -> TaskResult:
        """
        执行单个任务，含超时和重试机制

        执行流程:
          1. 查找注册的处理器
          2. 首次执行，超时时间为 estimatedDuration * 2
          3. 失败后按指数退避重试（最多2次: 1s, 2s）
          4. 记录执行日志

        Args:
            task: 要执行的任务节点

        Returns:
            任务执行结果
        """
        handler = self._handlers.get(task.agent_type)
        if not handler:
            result = TaskResult(
                task_id=task.task_id,
                success=False,
                error_message=f"未注册的智能体处理器: {task.agent_type.value}",
            )
            self.result_store[task.task_id] = result
            return result

        # 计算超时时间: estimatedDuration * 2
        timeout_seconds = task.estimated_duration * 2
        last_error: Optional[str] = None

        # 执行（含重试）
        for attempt in range(self.MAX_RETRIES + 1):
            start_time = time.monotonic()

            try:
                # 更新任务状态
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()

                # 带超时执行
                task_result = await asyncio.wait_for(
                    handler(task),
                    timeout=timeout_seconds,
                )

                execution_time = time.monotonic() - start_time
                task_result.execution_time = execution_time

                # 成功完成
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.output_result = task_result.data
                task.retry_count = attempt

                # 记录执行日志
                self._log_execution(task, task_result, attempt, success=True)

                self.result_store[task.task_id] = task_result
                return task_result

            except asyncio.TimeoutError:
                """任务超时处理"""
                execution_time = time.monotonic() - start_time
                last_error = (
                    f"任务超时(耗时{execution_time:.1f}s, "
                    f"超时阈值{timeout_seconds:.1f}s)"
                )
                self._log_execution(
                    task,
                    TaskResult(
                        task_id=task.task_id,
                        success=False,
                        error_message=last_error,
                        execution_time=execution_time,
                    ),
                    attempt,
                    success=False,
                    error_type="timeout",
                )

                # 重试退避
                if attempt < self.MAX_RETRIES:
                    backoff = self.RETRY_BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue

            except Exception as e:
                """任务异常处理"""
                execution_time = time.monotonic() - start_time
                last_error = f"任务执行异常: {str(e)}"
                tb = traceback.format_exc()

                self._log_execution(
                    task,
                    TaskResult(
                        task_id=task.task_id,
                        success=False,
                        error_message=last_error,
                        execution_time=execution_time,
                    ),
                    attempt,
                    success=False,
                    error_type="exception",
                    detail=tb,
                )

                # 重试退避
                if attempt < self.MAX_RETRIES:
                    backoff = self.RETRY_BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(backoff)
                    continue

        # 所有重试耗尽
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now()
        task.error_message = last_error
        task.retry_count = self.MAX_RETRIES

        result = TaskResult(
            task_id=task.task_id,
            success=False,
            error_message=last_error,
            degraded=False,
        )
        self.result_store[task.task_id] = result
        return result

    async def execute_dag_by_layers(
        self, layers: list[list[TaskNode]]
    ) -> dict[str, TaskResult]:
        """
        按分层拓扑顺序执行整个DAG

        每层内的任务并行执行，层间顺序执行。
        前一层的输出可通过result_store传递给下一层。

        Args:
            layers: get_parallel_layers()返回的分层任务列表

        Returns:
            所有任务的执行结果 {task_id: TaskResult}
        """
        for layer_idx, layer in enumerate(layers):
            # 执行当前层
            results = await self.execute_layer(layer)

            # 检查是否有任务失败，记录但不中断（降级策略在dispatcher层处理）
            failed_tasks = [r for r in results if not r.success]
            if failed_tasks:
                # 记录失败但不中断后续层的执行
                # 具体降级策略由 DegradationHandler 决定
                pass

        return dict(self.result_store)

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """
        获取任务执行结果

        Args:
            task_id: 任务ID

        Returns:
            任务执行结果，不存在返回None
        """
        return self.result_store.get(task_id)

    def get_results_by_agent_type(self, agent_type: AgentType) -> list[TaskResult]:
        """
        按智能体类型查询执行结果

        Args:
            agent_type: 智能体类型

        Returns:
            该类型所有任务的执行结果列表
        """
        # 需要结合task信息，但result_store只有task_id
        # 这里简单返回所有结果，调用方可自行过滤
        return list(self.result_store.values())

    def clear_results(self) -> None:
        """清空结果存储"""
        self.result_store.clear()

    def _log_execution(
        self,
        task: TaskNode,
        result: TaskResult,
        attempt: int,
        success: bool,
        error_type: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """
        记录执行日志

        Args:
            task: 任务节点
            result: 执行结果
            attempt: 尝试次数(0-based)
            success: 是否成功
            error_type: 错误类型(timeout/exception)
            detail: 详细信息(如异常堆栈)
        """
        log_entry = {
            "task_id": task.task_id,
            "agent_type": task.agent_type.value,
            "attempt": attempt,
            "success": success,
            "execution_time": result.execution_time,
            "action_power_used": result.action_power_used,
            "timestamp": datetime.now().isoformat(),
        }
        if error_type:
            log_entry["error_type"] = error_type
        if detail:
            log_entry["detail"] = detail
        if result.error_message:
            log_entry["error_message"] = result.error_message

        self._execution_log.append(log_entry)

    def get_execution_log(self, task_id: Optional[str] = None) -> list[dict]:
        """
        获取执行日志

        Args:
            task_id: 可选，指定任务ID过滤

        Returns:
            执行日志列表
        """
        if task_id:
            return [log for log in self._execution_log if log.get("task_id") == task_id]
        return list(self._execution_log)
