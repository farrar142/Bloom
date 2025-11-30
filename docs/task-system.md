# Bloom Task System

Bloom Task System은 Celery와 유사한 비동기 태스크 처리 시스템입니다.
단일 프로세스 내 비동기 실행부터 Redis를 통한 분산 처리까지 지원합니다.

## 개요

### 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application                               │
│  ┌──────────────────────┐    ┌──────────────────────┐           │
│  │     app.asgi         │    │     app.queue        │           │
│  │   (웹 서버용)        │    │   (워커용)           │           │
│  └──────────────────────┘    └──────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         │ delay() 호출                 │ 태스크 실행
         ▼                              ▼
    ┌────────────────────────────────────────┐
    │              Broker                     │
    │   ┌─────────────────────────────────┐  │
    │   │   InMemoryBroker (개발)         │  │
    │   │   RedisBroker (프로덕션)        │  │
    │   └─────────────────────────────────┘  │
    └────────────────────────────────────────┘
```

### 주요 컴포넌트

| 컴포넌트                 | 역할                                                     |
| ------------------------ | -------------------------------------------------------- |
| `@Task`                  | 메서드를 태스크로 데코레이트                             |
| `BoundTask`              | 인스턴스에 바인딩된 태스크 (delay, schedule 메서드 제공) |
| `TaskBackend`            | 태스크 실행 추상 인터페이스                              |
| `AsyncioTaskBackend`     | 단일 프로세스 asyncio 기반 백엔드                        |
| `DistributedTaskBackend` | 분산 처리 백엔드 (브로커 사용)                           |
| `Broker`                 | 메시지 큐 추상 인터페이스                                |
| `InMemoryBroker`         | 개발용 인메모리 브로커                                   |
| `RedisBroker`            | 프로덕션용 Redis 브로커                                  |
| `QueueApplication`       | 워커 애플리케이션 (`app.queue`)                          |
| `TaskRegistry`           | 태스크 이름 → 핸들러 매핑                                |

## 로컬 태스크 (AsyncioTaskBackend)

단일 프로세스 내에서 asyncio를 사용하여 백그라운드 태스크를 실행합니다.

### 기본 사용법

```python
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import Task, AsyncioTaskBackend, TaskResult

@Component
class EmailService:
    @Task
    def send_email(self, to: str, subject: str) -> str:
        # 이메일 전송 로직
        return f"Sent to {to}: {subject}"

    @Task(name="important-email", max_retries=3)
    async def send_important_email(self, to: str) -> str:
        await self.send_with_retry(to)
        return f"Important sent to {to}"

@Component
class TaskConfig:
    @Factory
    def task_backend(self) -> AsyncioTaskBackend:
        return AsyncioTaskBackend(max_workers=4)

app = Application("myapp").scan(__name__).ready()
```

### 태스크 실행 방법

```python
service = app.manager.get_instance(EmailService)

# 1. 직접 호출 (동기)
result = service.send_email("user@example.com", "Hello")
print(result)  # "Sent to user@example.com: Hello"

# 2. 백그라운드 실행
task_result: TaskResult = service.send_email.delay(
    "user@example.com",
    "Hello"
)

# 결과 대기
value = task_result.get()  # 블로킹
value = task_result.get(timeout=10)  # 타임아웃

# 상태 확인
task_result.ready()      # 완료 여부
task_result.successful() # 성공 여부
task_result.failed()     # 실패 여부

# 결과/에러 접근
task_result.result  # 결과값
task_result.error   # 예외 객체 (실패 시)

# 취소
task_result.revoke()
```

### 스케줄 태스크

정기적으로 태스크를 실행할 수 있습니다:

```python
from bloom.task import ScheduledTask

# fixed_rate: 시작 시점 기준 고정 간격 (초)
scheduled = service.send_email.schedule(
    fixed_rate=60,  # 60초마다
    args=("admin@example.com", "Report"),
    kwargs={"priority": "low"},
)

# fixed_delay: 완료 시점 기준 고정 지연 (초)
scheduled = service.send_email.schedule(
    fixed_delay=30,  # 완료 후 30초 대기
    args=("admin@example.com", "Report"),
)

# cron: cron 표현식
scheduled = service.send_email.schedule(
    cron="0 9 * * 1-5",  # 평일 오전 9시
    args=("admin@example.com", "Daily Report"),
)

# 제어
scheduled.pause()   # 일시정지
scheduled.resume()  # 재개
scheduled.cancel()  # 취소 (복구 불가)

# 정보 조회
info = scheduled.info()
print(info)  # {'status': 'active', 'next_run': ..., 'run_count': 5}
```

### 트리거 종류

```python
from bloom.task import FixedRateTrigger, FixedDelayTrigger, CronTrigger

# FixedRateTrigger: 시작 시점 기준
trigger = FixedRateTrigger(seconds=60)
trigger = FixedRateTrigger(minutes=5)
trigger = FixedRateTrigger(hours=1)
trigger = FixedRateTrigger(minutes=30, initial_delay=10)

# FixedDelayTrigger: 완료 시점 기준
trigger = FixedDelayTrigger(seconds=30)

# CronTrigger: cron 표현식
trigger = CronTrigger("*/5 * * * *")   # 5분마다
trigger = CronTrigger("0 0 * * *")     # 매일 자정
trigger = CronTrigger("0 9 * * 1-5")   # 평일 오전 9시
```

## 분산 태스크 (DistributedTaskBackend)

여러 프로세스 또는 서버에서 태스크를 분산 처리합니다.

### 설정

```python
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import (
    Task,
    DistributedTaskBackend,
    RedisBroker,
    InMemoryBroker,
)

@Component
class EmailService:
    @Task(name="send_email")  # 분산 환경에서는 name 권장
    def send_email(self, to: str, subject: str) -> str:
        return f"Sent to {to}: {subject}"

@Component
class TaskConfig:
    @Factory
    def task_backend(self) -> DistributedTaskBackend:
        # 프로덕션: Redis 브로커
        broker = RedisBroker("redis://localhost:6379/0")

        # 개발: 인메모리 브로커
        # broker = InMemoryBroker()

        return DistributedTaskBackend(
            broker=broker,
            queue="default",      # 기본 큐 이름
            worker_count=4,       # 워커 수
            poll_interval=1.0,    # 결과 폴링 간격 (초)
        )

app = Application("myapp").scan(__name__).ready()
```

### 웹 서버 실행

```bash
# uvicorn으로 ASGI 앱 실행
uvicorn main:app.asgi --reload
uvicorn main:app.asgi --workers 4
```

### 워커 실행

```bash
# bloom CLI로 워커 실행
bloom task --worker
bloom task -w --concurrency 4
bloom task -w -c 8

# 특정 애플리케이션 지정
bloom task -w -a main:app
bloom task -w -a main:app.queue

# 직접 코드로 실행
import asyncio
asyncio.run(app.queue.run())
```

### 브로커

#### InMemoryBroker (개발용)

```python
from bloom.task import InMemoryBroker

broker = InMemoryBroker()
backend = DistributedTaskBackend(broker)
```

- 단일 프로세스 내에서만 동작
- 재시작 시 모든 태스크 소실
- 테스트 및 개발 환경에 적합

#### RedisBroker (프로덕션용)

```python
from bloom.task import RedisBroker

# 기본 연결
broker = RedisBroker("redis://localhost:6379/0")

# 인증 포함
broker = RedisBroker("redis://:password@localhost:6379/0")

# 옵션
backend = DistributedTaskBackend(
    broker=broker,
    queue="high-priority",  # 큐 이름
)
```

- 멀티 프로세스, 멀티 서버 지원
- 태스크 영속성 보장
- 프로덕션 환경에 권장

### 태스크 이름 규칙

분산 환경에서는 태스크 이름으로 핸들러를 찾습니다:

```python
# 명시적 이름 (권장)
@Task(name="send_email")
def send_email(self, to: str) -> str: ...

# 자동 이름: "ClassName.method_name"
@Task
def send_email(self, to: str) -> str: ...
# → "EmailService.send_email"
```

### 재시도 설정

```python
@Task(
    name="send_email",
    max_retries=3,      # 최대 재시도 횟수
    retry_delay=5.0,    # 재시도 간격 (초)
)
def send_email(self, to: str) -> str:
    if random.random() < 0.3:
        raise TemporaryError("Network error")
    return f"Sent to {to}"
```

## QueueApplication (app.queue)

`app.queue`는 워커 프로세스를 위한 애플리케이션입니다.
`uvicorn main:app.asgi`처럼 `bloom task -w -a main:app`로 실행합니다.

### 프로퍼티

```python
app = Application("myapp").scan(__name__).ready()

# ASGI 앱 (웹 서버용)
app.asgi  # ASGIApplication

# Queue 앱 (워커용)
app.queue  # QueueApplication
```

### QueueApplication API

```python
queue = app.queue

# 백엔드 접근
queue.backend  # DistributedTaskBackend

# 레지스트리 접근 (startup 후)
queue.registry  # TaskRegistry
queue.registry.names()  # 등록된 태스크 이름 목록

# 라이프사이클 콜백
queue.on_startup(callback)
queue.on_shutdown(callback)

# 실행
await queue.startup()   # 시작
await queue.shutdown()  # 종료
await queue.run()       # 메인 루프 (시그널 대기)
queue.run_sync()        # 동기 실행 (asyncio.run 래퍼)
```

### 라이프사이클 콜백

```python
async def on_startup():
    print("Worker starting...")

async def on_shutdown():
    print("Worker shutting down...")

app.queue.on_startup(on_startup)
app.queue.on_shutdown(on_shutdown)
```

## CLI

### bloom task

```bash
# 워커 시작
bloom task --worker
bloom task -w

# 동시성 설정
bloom task -w --concurrency 4
bloom task -w -c 8

# 특정 애플리케이션 지정
bloom task -w -a main:app
bloom task -w -a main:app.queue
```

### 옵션

| 옵션            | 단축 | 기본값                    | 설명             |
| --------------- | ---- | ------------------------- | ---------------- |
| `--worker`      | `-w` | -                         | 워커 시작        |
| `--application` | `-a` | `application:application` | Application 경로 |
| `--concurrency` | `-c` | 4                         | 동시 워커 수     |

## 내부 구조

### TaskMessage

태스크 메시지는 JSON으로 직렬화됩니다:

```python
@dataclass
class TaskMessage:
    task_id: str           # 고유 ID (UUID)
    task_name: str         # 태스크 이름
    args: tuple = ()       # 위치 인자
    kwargs: dict = {}      # 키워드 인자
    eta: datetime | None   # 예약 실행 시간
    retries: int = 0       # 현재 재시도 횟수
    max_retries: int = 0   # 최대 재시도 횟수
    retry_delay: float = 1.0  # 재시도 간격
```

### TaskRegistry

태스크 이름과 핸들러를 매핑합니다:

```python
registry = TaskRegistry()

# ContainerManager에서 @Task 메서드 스캔
registry.scan(container_manager)

# 태스크 조회
info = registry.get("send_email")
info.handler      # 핸들러 함수
info.instance     # 컴포넌트 인스턴스
info.component_type  # 컴포넌트 클래스

# 태스크 실행
result = registry.execute("send_email", "user@example.com", "Hello")
```

### Broker 인터페이스

커스텀 브로커 구현 시 참고:

```python
from abc import ABC, abstractmethod
from bloom.task import TaskMessage

class Broker(ABC):
    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def enqueue(
        self,
        queue: str,
        message: TaskMessage,
    ) -> None: ...

    @abstractmethod
    async def dequeue(
        self,
        queue: str,
        timeout: float | None = None,
    ) -> TaskMessage | None: ...

    @abstractmethod
    async def store_result(
        self,
        task_id: str,
        result: TaskResultMessage,
    ) -> None: ...

    @abstractmethod
    async def get_result(
        self,
        task_id: str,
    ) -> TaskResultMessage | None: ...
```

## 예제: 완전한 분산 태스크 시스템

### main.py

```python
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import (
    Task,
    DistributedTaskBackend,
    RedisBroker,
)

@Component
class NotificationService:
    @Task(name="send_push", max_retries=3)
    async def send_push(self, user_id: int, message: str) -> dict:
        # 푸시 알림 전송 로직
        return {"user_id": user_id, "status": "sent"}

    @Task(name="send_email")
    def send_email(self, to: str, subject: str, body: str) -> str:
        # 이메일 전송 로직
        return f"Email sent to {to}"

@Component
class TaskConfig:
    @Factory
    def task_backend(self) -> DistributedTaskBackend:
        broker = RedisBroker("redis://localhost:6379/0")
        return DistributedTaskBackend(broker)

app = Application("notification_app").scan(__name__).ready()
```

### 웹 서버에서 태스크 호출

```python
from fastapi import FastAPI
from main import app as bloom_app

fastapi = FastAPI()

@fastapi.post("/notify/{user_id}")
async def notify_user(user_id: int, message: str):
    service = bloom_app.manager.get_instance(NotificationService)

    # 백그라운드로 푸시 전송
    task = service.send_push.delay(user_id, message)

    return {"task_id": task.id, "status": "queued"}

@fastapi.get("/task/{task_id}")
async def get_task_status(task_id: str):
    service = bloom_app.manager.get_instance(NotificationService)
    # DistributedTaskBackend에서 결과 조회
    backend = bloom_app.manager.get_instance(DistributedTaskBackend)
    result = await backend.get_result(task_id)

    return {"task_id": task_id, "result": result}
```

### 실행

```bash
# 터미널 1: Redis
docker run -p 6379:6379 redis

# 터미널 2: 웹 서버
uvicorn main:app.asgi --reload

# 터미널 3: 워커
bloom task -w -a main:app -c 4
```
