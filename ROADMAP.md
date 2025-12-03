# Bloom Framework Roadmap

## Phase 1: Core DI System ✅

### 1.1 기본 DI 컨테이너 ✅

- [x] `@Component`, `@Service`, `@Repository` 데코레이터
- [x] `Container`, `ContainerManager` 구현
- [x] 의존성 분석 및 주입 (`DependencyInfo`, `DependencyResolver`)
- [x] `LazyProxy`를 통한 순환 참조 해결
- [x] `@Factory` 메서드 지원

### 1.2 스코프 관리 ✅

- [x] `Scope.SINGLETON` - 앱 전체 단일 인스턴스
- [x] `Scope.REQUEST` - 요청 단위 인스턴스 (구조만)
- [x] `Scope.CALL` - @Handler 메서드 단위 인스턴스
- [x] `ScopeManager` - 스코프별 인스턴스 저장/조회/정리
- [x] `asynccontextmanager` 지원 (`call_scope()`, `request_scope()`)

### 1.3 라이프사이클 관리 ✅

- [x] `@PostConstruct` - 초기화 콜백
- [x] `@PreDestroy` - 정리 콜백
- [x] `AutoClosable` 인터페이스
- [x] CALL 스코프 중첩 지원 (frame_id 스택)
- [x] `inherit_parent` 옵션

### 1.4 AOP 모듈 ✅

- [x] `Interceptor` 인터페이스
- [x] `InterceptorChain` - 체인 패턴
- [x] `DecoratorFactory` - 데코레이터 기반 AOP
- [x] `InjectableDecoratorFactory` - DI 통합 AOP
- [x] `FlatDecorator` - 단순 데코레이터
- [x] Sync/Async 메서드 지원

---

## Phase 2: Web Layer 🚧 (현재 진행 중)

### 2.1 ASGI 기반 HTTP 처리 ✅

- [x] `ASGIApplication` - ASGI 앱 구현
- [x] `Request`, `Response` 객체
- [x] 미들웨어 체인 구조 (`Middleware`, `MiddlewareStack`)
- [x] `RequestScopeMiddleware` - REQUEST 스코프 통합
- [x] DB 모듈 연동 (`Session`, `AsyncSession` → `AutoClosable`)

### 2.2 라우팅 ✅

- [x] `Router` - URL 패턴 매칭 (path parameter: `{id}`, `{id:int}`, `{path:path}`)
- [x] `@Controller` - 라우트 그룹 + DI 자동 등록
- [x] `@RequestMapping` - 클래스 레벨 prefix
- [x] `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`
- [x] Path 파라미터, Query 파라미터

### 2.3 요청/응답 처리 ✅

- [x] `PathVariable[T]`, `Query[T]` 파라미터 바인딩
- [x] `RequestBody[T]`, `RequestField[T]` - JSON 바디 처리
- [x] `Header[T]`, `Cookie[T]` 헤더/쿠키 추출
- [x] `ParameterResolver` - 확장 가능한 파라미터 리졸버
- [ ] 파일 업로드 (`UploadedFile`)
- [ ] 스트리밍 응답 (`StreamingResponse`, `SSEResponse`)

```python
@Controller
@RequestMapping("/api/v1/")
class UserController:
     service:UserService # Field 주입
     @PostMapping("/{path}")
     async def post_request[T](self,
          body:RequestBody[BodySchema], # 전체 바디 데이터, 바디나, 쿼리, 필드는 RequestBody[list[BodySchema]]등의 리스트들도 기본 지원하도록
          username: str, # 바디의 필드 데이터
          address:RequestField[AddressSchema]# 혹은 :AddressSchema,  바디의 필드 데이터
          path:str:PathVariable[str], # 패스데이터
          subpath:str:Query[str], # 혹은 :str록록
          file:UploadedFile # IO rw 가능한 파일객체,
          authentication:Authentication[int] # 스프링의 Principal비슷한 객체, 기본으로 Authentication[T] = id:T지원
     )->T|HttpResponse[T]|StreamingResponse[UploadedFile|File]|SSEResponse:...

```

ParameterResolver는 상속이 가능한 구조로, WebSocket세션과 같은 추상 구현체를 가져서 호환이 되도록 만들어줘

### 2.4 에러 처리

- [ ] `@ExceptionHandler` - 예외 핸들러
- [ ] 전역 에러 핸들링
- [ ] HTTP 상태 코드 매핑

---

## Phase 3: Database & ORM ✅ (이미 구현됨)

### 3.1 데이터베이스 연결 ✅

- [x] `SessionFactory` - 세션 팩토리
- [x] `Session` / `AsyncSession` - Unit of Work 패턴
- [x] 연결 풀링 (`ConnectionPool`)
- [x] `AutoClosable` 인터페이스로 DI 통합

### 3.2 ORM ✅

- [x] `Entity` 정의 (`@Entity`, `Column`, `PrimaryKey`, `ForeignKey`)
- [x] `CrudRepository` 패턴
- [x] QueryDSL 스타일 쿼리 빌더
- [x] Django 스타일 마이그레이션
- [x] Dirty Tracking

---

## Phase 4: Advanced Features

### 4.1 설정 관리

- [ ] `@Value` - 설정값 주입
- [ ] `@ConfigurationProperties` - 설정 클래스
- [ ] 환경별 설정 (dev, prod)

### 4.2 보안

- [ ] 인증 미들웨어
- [ ] `@Authenticated` 데코레이터
- [ ] JWT 지원

### 4.3 테스팅

- [ ] `TestClient` - HTTP 테스트
- [ ] `@MockBean` - 모킹 지원
- [ ] 픽스처 통합

---

## 현재 작업: Phase 2.4 - 에러 처리 & 고급 기능 (다음 작업)

### 목표

`@ExceptionHandler`, 전역 에러 핸들링, 파일 업로드 등

### 작업 항목

1. [ ] `@ExceptionHandler` - 예외 핸들러
2. [ ] 전역 에러 핸들링 미들웨어
3. [ ] HTTP 상태 코드 매핑
4. [ ] `UploadedFile` - 파일 업로드
5. [ ] `StreamingResponse`, `SSEResponse`

### 구현 완료 (Phase 2.1 ~ 2.3)

```
bloom/web/
├── __init__.py          # exports
├── types.py             # ASGI 타입 정의
├── request.py           # Request 객체 (cookie 지원)
├── response.py          # Response, JSONResponse 등
├── asgi.py              # ASGIApplication
├── middleware/
│   ├── __init__.py
│   ├── base.py          # Middleware, MiddlewareStack
│   └── request_scope.py # RequestScopeMiddleware
├── routing/
│   ├── __init__.py
│   ├── router.py        # Router, Route, RouteMatch
│   ├── decorators.py    # @Controller, @GetMapping 등
│   ├── params.py        # PathVariable, Query, RequestBody 등
│   └── resolver.py      # ParameterResolver 시스템
tests/web/
├── __init__.py
├── test_request_scope.py  # 12개 테스트 통과
└── test_routing.py        # 20개 테스트 통과
```
