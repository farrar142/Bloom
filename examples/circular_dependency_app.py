"""
Bloom 순환 의존성 예제 앱

이 예제는 의도적으로 순환 의존성을 생성하여
Bloom 프레임워크가 어떻게 감지하고 보고하는지 보여줍니다.

실행하면:
1. 순환 의존성이 감지됩니다
2. 의존성 그래프가 circular-dependency-{timestamp}.txt 파일로 저장됩니다
3. CircularDependencyError 예외가 발생합니다

순환 의존성 구조:
    ServiceA → ServiceB → ServiceC → ServiceA (순환!)

해결 방법:
1. Lazy 사용: ServiceA가 ServiceC를 Lazy[ServiceC]로 주입받음
2. 설계 변경: 공통 인터페이스나 이벤트 기반 통신 사용
"""

from __future__ import annotations

from bloom import Application, Component

# =============================================================================
# 순환 의존성 예제: A → B → C → A
# =============================================================================


@Component
class ServiceA:
    """ServiceA - ServiceB에 의존"""

    service_b: ServiceB

    def execute(self) -> str:
        return f"ServiceA: {self.service_b.process()}"


@Component
class ServiceB:
    """ServiceB - ServiceC에 의존"""

    service_c: ServiceC

    def process(self) -> str:
        return f"ServiceB: {self.service_c.do_something()}"


@Component
class ServiceC:
    """ServiceC - ServiceA에 의존 (순환 완성)"""

    service_a: ServiceA

    def do_something(self) -> str:
        return f"ServiceC: calling {self.service_a}"


# =============================================================================
# 추가 순환 예제: 직접 순환 (X ↔ Y)
# =============================================================================


@Component
class ServiceX:
    """ServiceX - ServiceY에 의존"""

    service_y: ServiceY

    def call_y(self) -> str:
        return f"X calling Y"


@Component
class ServiceY:
    """ServiceY - ServiceX에 의존 (직접 순환)"""

    service_x: ServiceX

    def call_x(self) -> str:
        return f"Y calling X"


# =============================================================================
# 메인 실행
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Bloom Circular Dependency Detection Demo")
    print("=" * 60)
    print()
    print("This example intentionally creates circular dependencies:")
    print("  - ServiceA → ServiceB → ServiceC → ServiceA")
    print("  - ServiceX ↔ ServiceY")
    print()
    print("Starting application initialization...")
    print()

    try:
        # 현재 모듈을 등록
        sys.modules["circular_dependency_app"] = sys.modules["__main__"]

        app = Application("circular-demo").scan(sys.modules["__main__"]).ready()

        # 이 코드는 실행되지 않음 (예외 발생)
        print("Application started successfully!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print()

        # CircularDependencyError인 경우 추가 정보 출력
        from bloom.core.exceptions import CircularDependencyError

        if isinstance(e, CircularDependencyError):
            if e.graph_saved_path:
                print(f"📄 Dependency graph saved to: {e.graph_saved_path}")
                print()
                print("You can open this file to see the full dependency graph")
                print("and understand which components form the cycle.")

        sys.exit(1)
