"""TaskRegistry - 태스크 이름과 핸들러 매핑

@Task로 등록된 메서드들을 이름으로 조회할 수 있게 합니다.
분산 환경에서 태스크 이름만으로 실제 핸들러를 찾을 수 있습니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager

logger = logging.getLogger(__name__)


class TaskRegistry:
    """
    태스크 레지스트리

    @Task로 데코레이트된 모든 메서드를 이름으로 조회할 수 있게 합니다.
    분산 워커가 태스크 이름만으로 실제 핸들러를 찾을 수 있습니다.

    Example:
        registry = TaskRegistry()
        registry.scan(container_manager)

        # 태스크 이름으로 핸들러 조회
        handler_info = registry.get("EmailService.send_email")
        instance = container_manager.get_instance(handler_info.component_type)
        result = handler_info.handler(instance, *args, **kwargs)
    """

    def __init__(self):
        self._tasks: dict[str, TaskInfo] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        component_type: type,
        instance: Any = None,
    ) -> None:
        """
        태스크 등록

        Args:
            name: 태스크 이름
            handler: 핸들러 함수 (언바운드 메서드)
            component_type: 컴포넌트 클래스
            instance: 인스턴스 (있으면 바운드 메서드로 호출)
        """
        self._tasks[name] = TaskInfo(
            name=name,
            handler=handler,
            component_type=component_type,
            instance=instance,
        )
        logger.debug(f"Task registered: {name}")

    def get(self, name: str) -> TaskInfo | None:
        """태스크 정보 조회"""
        return self._tasks.get(name)

    def has(self, name: str) -> bool:
        """태스크 존재 여부"""
        return name in self._tasks

    def names(self) -> list[str]:
        """등록된 모든 태스크 이름"""
        return list(self._tasks.keys())

    def scan(self, manager: ContainerManager) -> None:
        """
        ContainerManager에서 모든 @Task 메서드를 스캔하여 등록

        Args:
            manager: ContainerManager 인스턴스
        """
        from bloom.task.decorator import TaskDescriptor

        # instance_registry를 순회
        for component_type, instances in manager.instance_registry.items():
            if not instances:
                continue
            instance = instances[0]  # 첫 번째 인스턴스 사용

            # 클래스의 모든 속성 검사
            for attr_name in dir(component_type):
                if attr_name.startswith("_"):
                    continue

                try:
                    attr = getattr(component_type, attr_name, None)
                except Exception:
                    continue

                # TaskDescriptor인지 확인
                if isinstance(attr, TaskDescriptor):
                    # 태스크 이름: @Task(name=...)으로 지정한 이름 또는 ClassName.method_name
                    element = attr._element
                    if element and element.name:
                        task_name = element.name
                    else:
                        task_name = f"{component_type.__name__}.{attr_name}"

                    # 원본 핸들러 가져오기
                    handler = attr.get_original_handler()

                    self.register(
                        name=task_name,
                        handler=handler,
                        component_type=component_type,
                        instance=instance,
                    )

        logger.info(f"TaskRegistry scanned: {len(self._tasks)} tasks found")

    def clear(self) -> None:
        """모든 태스크 제거"""
        self._tasks.clear()

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, name: str) -> bool:
        return name in self._tasks

    def __repr__(self) -> str:
        return f"<TaskRegistry tasks={len(self._tasks)}>"


class TaskInfo:
    """
    태스크 정보

    Attributes:
        name: 태스크 이름
        handler: 핸들러 함수 (언바운드)
        component_type: 컴포넌트 클래스
        instance: 인스턴스 (캐시됨)
    """

    def __init__(
        self,
        name: str,
        handler: Callable,
        component_type: type,
        instance: Any = None,
    ):
        self.name = name
        self.handler = handler
        self.component_type = component_type
        self.instance = instance

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """
        태스크 실행

        인스턴스가 있으면 바운드 메서드로, 없으면 에러
        """
        if self.instance is None:
            raise RuntimeError(
                f"Task {self.name} has no instance. "
                "Use TaskRegistry.scan() with ContainerManager."
            )
        return self.handler(self.instance, *args, **kwargs)

    async def execute_async(self, *args: Any, **kwargs: Any) -> Any:
        """
        비동기 태스크 실행
        """
        import asyncio

        result = self.execute(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def __repr__(self) -> str:
        return f"<TaskInfo {self.name} -> {self.component_type.__name__}>"
