"""MethodAdvice - 메서드 어드바이스 인터페이스"""

from abc import ABC, abstractmethod
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..container import HandlerContainer
    from .context import InvocationContext


class MethodAdvice(ABC):
    """
    메서드 호출 전후에 실행되는 어드바이스 인터페이스

    Container의 Element를 기반으로 적용 여부를 결정하고,
    before/after/on_error 훅으로 로직을 실행합니다.

    동기/비동기 모두 지원:
    - 비동기 메서드: before(), after(), on_error() 호출
    - 동기 메서드: before_sync(), after_sync(), on_error_sync() 호출

    Example:
        @Component
        class TransactionAdvice(MethodAdvice):
            db: Database

            def supports(self, container: HandlerContainer) -> bool:
                return container.has_element(TransactionalElement)

            # 비동기 버전
            async def before(self, context: InvocationContext) -> None:
                tx = await self.db.begin()
                context.set_attribute("tx", tx)

            async def after(self, context: InvocationContext, result: Any) -> Any:
                tx = context.get_attribute("tx")
                await tx.commit()
                return result

            async def on_error(self, context: InvocationContext, error: Exception) -> Any:
                tx = context.get_attribute("tx")
                await tx.rollback()
                raise error

            # 동기 버전 (동기 메서드에서 호출됨)
            def before_sync(self, context: InvocationContext) -> None:
                tx = self.db.begin_sync()
                context.set_attribute("tx", tx)

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                context.get_attribute("tx").commit_sync()
                return result

            def on_error_sync(self, context: InvocationContext, error: Exception) -> Any:
                context.get_attribute("tx").rollback_sync()
                raise error
    """

    @abstractmethod
    def supports(self, container: "HandlerContainer") -> bool:
        """
        이 컨테이너에 어드바이스를 적용할지 결정합니다.

        일반적으로 container.has_element()로 특정 Element 존재 여부를 확인합니다.

        Args:
            container: 핸들러 컨테이너

        Returns:
            True면 이 어드바이스 적용, False면 스킵
        """
        ...

    def invoke_sync(
        self,
        context: "InvocationContext",
        proceed: Callable[[], Any],
    ) -> Any | None:
        """
        동기 호출을 가로챕니다.

        이 메서드가 None이 아닌 값을 반환하면 그 값이 최종 결과가 됩니다.
        None을 반환하면 다음 Advice로 진행하거나 기본 실행을 수행합니다.

        Args:
            context: 호출 컨텍스트
            proceed: 나머지 Advice 체인 + 핸들러를 실행하는 함수

        Returns:
            None: 가로채지 않음 (다음으로 진행)
            Any: 가로챔 (이 값이 최종 결과)
        """
        return None

    async def invoke_async(
        self,
        context: "InvocationContext",
        proceed: Callable[[], Any],
    ) -> Any | None:
        """
        비동기 호출을 가로챕니다.

        이 메서드가 None이 아닌 값을 반환하면 그 값이 최종 결과가 됩니다.
        None을 반환하면 다음 Advice로 진행하거나 기본 실행을 수행합니다.

        Args:
            context: 호출 컨텍스트
            proceed: 나머지 Advice 체인 + 핸들러를 실행하는 함수

        Returns:
            None: 가로채지 않음 (다음으로 진행)
            Any: 가로챔 (이 값이 최종 결과)
        """
        return None

    # === 비동기 버전 ===

    async def before(self, context: "InvocationContext") -> None:
        """
        메서드 실행 전에 호출됩니다 (비동기).

        context.set_attribute()로 데이터를 저장하면
        after/on_error에서 get_attribute()로 접근할 수 있습니다.

        Args:
            context: 호출 컨텍스트 (container, instance, args, kwargs)
        """
        pass

    async def after(self, context: "InvocationContext", result: Any) -> Any:
        """
        메서드 실행 후에 호출됩니다 (비동기).

        result를 수정하여 반환하면 최종 결과가 변경됩니다.

        Args:
            context: 호출 컨텍스트
            result: 메서드 실행 결과

        Returns:
            수정된 결과 (또는 원본 result 그대로)
        """
        return result

    async def on_error(self, context: "InvocationContext", error: Exception) -> Any:
        """
        메서드 실행 중 예외 발생 시 호출됩니다 (비동기).

        예외를 복구하려면 값을 반환하고,
        예외를 전파하려면 raise error 합니다.

        Args:
            context: 호출 컨텍스트
            error: 발생한 예외

        Returns:
            복구 시 반환할 값

        Raises:
            Exception: 예외를 전파할 때
        """
        raise error

    # === 동기 버전 ===

    def before_sync(self, context: "InvocationContext") -> None:
        """
        메서드 실행 전에 호출됩니다 (동기).

        기본 구현은 아무것도 하지 않습니다.
        동기 메서드에서 Advice를 사용하려면 이 메서드를 오버라이드하세요.

        Args:
            context: 호출 컨텍스트
        """
        pass

    def after_sync(self, context: "InvocationContext", result: Any) -> Any:
        """
        메서드 실행 후에 호출됩니다 (동기).

        Args:
            context: 호출 컨텍스트
            result: 메서드 실행 결과

        Returns:
            수정된 결과 (또는 원본 result 그대로)
        """
        return result

    def on_error_sync(self, context: "InvocationContext", error: Exception) -> Any:
        """
        메서드 실행 중 예외 발생 시 호출됩니다 (동기).

        Args:
            context: 호출 컨텍스트
            error: 발생한 예외

        Returns:
            복구 시 반환할 값

        Raises:
            Exception: 예외를 전파할 때
        """
        raise error
