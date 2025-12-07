from typing import Callable, Concatenate
from uuid import uuid4
from .container import Container, HandlerContainer, Method


def Component[T: type](kls: T) -> T:
    """컴포넌트 데코레이터: 클래스를 특정 컨테이너 타입에 등록합니다."""
    container = Container.register(kls)
    return kls


def Service[T: type](kls: T) -> T:
    """서비스 데코레이터: 클래스를 싱글톤 컨테이너에 등록합니다."""
    container = Container.register(kls)
    return kls


def Handler[**P, T, R](
    func: Callable[Concatenate[T, P], R],
) -> Callable[Concatenate[T, P], R]:
    """핸들러 데코레이터: 함수를 특정 핸들러 컨테이너에 등록합니다."""

    # 핸들러임을 표시하는 마커 추가
    handler = HandlerContainer.register(func)

    def decorator(func: Method[P, T, R]) -> Method[P, T, R]:
        def wrapper(instance: T, *args: P.args, **kwargs: P.kwargs) -> R:
            result = func(instance, *args, **kwargs)
            return result

        return wrapper

    handler.wrappers.append(decorator)
    return func
