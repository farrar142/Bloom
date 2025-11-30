"""콜스택 추적 예제

이 예제는 모든 메서드 호출을 자동으로 추적하여 콜스택을 출력합니다.
"""

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.core.advice import (
    MethodAdvice,
    MethodAdviceRegistry,
    CallStackTraceAdvice,
    CallFrame,
    get_call_stack,
)


# =============================================================================
# 커스텀 트레이싱 Advice - 모든 메서드 호출을 로깅
# =============================================================================


@Component
class LoggingTraceAdvice(CallStackTraceAdvice):
    """모든 메서드 호출을 로깅하는 Advice"""

    include_args = True  # 인자 요약 포함

    def on_enter(self, frame: CallFrame) -> None:
        indent = "  " * frame.depth
        print(f"{indent}→ {frame.full_name}({frame.args_summary})")

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        indent = "  " * frame.depth
        print(f"{indent}← {frame.full_name} [{duration_ms:.2f}ms]")

    def on_error(self, frame: CallFrame, error: Exception) -> None:
        indent = "  " * frame.depth
        print(f"{indent}✗ {frame.full_name} ERROR: {error}")


# =============================================================================
# 비즈니스 로직 컴포넌트들
# =============================================================================


@Component
class UserRepository:
    """사용자 저장소"""

    def find_by_id(self, user_id: int) -> dict:
        # 여기서 현재 콜스택을 확인할 수 있음
        stack = get_call_stack()
        print(f"      [DEBUG] 현재 콜스택 깊이: {len(stack)}")
        return {"id": user_id, "name": f"User{user_id}", "email": f"user{user_id}@example.com"}

    def save(self, user: dict) -> dict:
        user["saved"] = True
        return user


@Component
class EmailService:
    """이메일 서비스"""

    def send_welcome_email(self, email: str) -> bool:
        print(f"      📧 Sending welcome email to {email}")
        return True


@Component
class UserService:
    """사용자 서비스 - Repository와 EmailService를 사용"""

    user_repo: UserRepository
    email_service: EmailService

    def get_user(self, user_id: int) -> dict:
        return self.user_repo.find_by_id(user_id)

    def create_user(self, name: str, email: str) -> dict:
        user = {"name": name, "email": email}
        saved_user = self.user_repo.save(user)
        self.email_service.send_welcome_email(email)
        return saved_user


@Component
class UserController:
    """사용자 컨트롤러 - 최상위 진입점"""

    user_service: UserService

    def get_user_detail(self, user_id: int) -> dict:
        print(f"\n{'='*60}")
        print(f"[Request] GET /users/{user_id}")
        print(f"{'='*60}")
        return self.user_service.get_user(user_id)

    def register_user(self, name: str, email: str) -> dict:
        print(f"\n{'='*60}")
        print(f"[Request] POST /users - name={name}, email={email}")
        print(f"{'='*60}")
        return self.user_service.create_user(name, email)


# =============================================================================
# Advice Registry 설정 (필수!)
# =============================================================================


@Component
class AdviceConfig:
    @Factory
    def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        """모든 MethodAdvice를 자동 수집하여 Registry에 등록"""
        registry = MethodAdviceRegistry()
        for advice in advices:
            registry.register(advice)
            print(f"[Config] Registered advice: {type(advice).__name__}")
        return registry


# =============================================================================
# 앱 실행
# =============================================================================


def main():
    print("=" * 60)
    print("콜스택 추적 예제")
    print("=" * 60)
    print()

    # 앱 초기화
    app = Application("tracing_example")
    app.scan(LoggingTraceAdvice)
    app.scan(UserRepository)
    app.scan(EmailService)
    app.scan(UserService)
    app.scan(UserController)
    app.scan(AdviceConfig)
    app.ready()

    print("\n[App] Application initialized successfully!")
    print()

    # 컨트롤러 가져오기
    controller = app.manager.get_instance(UserController)

    # 1. 사용자 조회 - 콜스택: Controller → Service → Repository
    result = controller.get_user_detail(42)
    print(f"\n[Response] {result}")

    # 2. 사용자 등록 - 콜스택: Controller → Service → Repository + EmailService
    result = controller.register_user("Alice", "alice@example.com")
    print(f"\n[Response] {result}")

    print("\n" + "=" * 60)
    print("예제 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
