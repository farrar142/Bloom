from typing import Callable, Concatenate
from .container import Container, HandlerContainer, FactoryContainer


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
    handler = HandlerContainer.register(func)
    return func


def Factory[T: type](kls: T) -> T:
    """Factory 데코레이터: 클래스를 FactoryContainer에 등록합니다.

    Factory는 Container에 등록된 다른 서비스들을 의존성으로 주입받아서
    인스턴스를 생성(Creator)하거나 수정(Modifier)하는 역할을 합니다.

    - Modifier 메서드: 단일 파라미터를 받아서 같은 타입을 반환 (T) -> T
    - Creator 메서드: 그 외 모든 메서드 (새 인스턴스 생성)

    사용법:
        @Factory
        class UserFactory:
            user_repository: UserRepository  # 의존성 주입
            email_service: EmailService

            def create(self, name: str, email: str) -> User:
                '''Creator: 새 User 인스턴스 생성'''
                user = User(name=name, email=email)
                self.user_repository.save(user)
                return user

            async def create_with_notification(self, name: str) -> User:
                '''Async Creator'''
                user = User(name=name)
                await self.email_service.send_welcome(user)
                return user

            def enhance(self, user: User) -> User:
                '''Modifier: 기존 User 수정'''
                user.enhanced = True
                return user

            async def process(self, user: User) -> User:
                '''Async Modifier'''
                await self.email_service.notify(user)
                user.notified = True
                return user
    """
    container = FactoryContainer.register(kls)
    return kls
