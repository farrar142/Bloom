"""ProxyableDescriptor 추상 클래스

디스크립터가 프록시 적용을 지원하기 위한 인터페이스입니다.
Application은 이 추상 클래스만 알면 되고, 구체적인 디스크립터 타입을 몰라도 됩니다.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class ProxyableDescriptor(ABC):
    """
    프록시 적용이 가능한 디스크립터 추상 클래스

    @Task 등의 디스크립터가 이 클래스를 상속하면,
    Application에서 자동으로 프록시를 적용할 수 있습니다.

    Example:
        class TaskDescriptor(ProxyableDescriptor):
            def get_original_handler(self) -> Callable | None:
                return self._handler

            def apply_proxy(self, instance: Any, proxy: Any) -> Any:
                bound_task = self.__get__(instance, type(instance))
                bound_task._proxy = proxy
                bound_task._use_proxy = True
                return bound_task
    """

    @abstractmethod
    def get_original_handler(self) -> Callable | None:
        """
        원본 핸들러를 반환합니다.

        HandlerContainer를 조회하기 위해 사용됩니다.

        Returns:
            원본 핸들러 함수, 없으면 None
        """
        ...

    @abstractmethod
    def apply_proxy(self, instance: Any, proxy: Any) -> Any:
        """
        프록시를 적용하고 바인딩된 객체를 반환합니다.

        Args:
            instance: 디스크립터가 속한 인스턴스
            proxy: 적용할 MethodProxy

        Returns:
            프록시가 적용된 바인딩된 객체 (예: BoundTask)
        """
        ...
