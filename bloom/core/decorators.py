from .manager import get_container_registry
from .container import Container


def Component[T: type](kls: T) -> T:
    """컴포넌트 데코레이터: 클래스를 특정 컨테이너 타입에 등록합니다."""
    registry = get_container_registry()
    if kls not in registry:
        registry[kls] = []
    registry[kls].append(Container(kls))
    return kls
