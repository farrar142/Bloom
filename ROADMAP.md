# Bloom Framework Roadmap

> Spring-inspired Python Web Framework with Dependency Injection

## 📋 현재 상태 (v0.1.0)

**266개 테스트 통과** ✅

### 완료된 기능

#### 🏗️ Core - 의존성 주입 컨테이너
- [x] **Container 시스템**
  - `Container` - 기본 컴포넌트 컨테이너
  - `HandlerContainer` - 핸들러 메서드 컨테이너
  - `FactoryContainer` - @Factory 메서드 컨테이너
  - `ConfigurationContainer` - @Configuration 클래스 컨테이너
  
- [x] **데코레이터**
  - `@Component` - 컴포넌트 등록
  - `@Service` - 서비스 등록
  - `@Handler` - 핸들러 메서드 등록 (CallScope 자동 적용)
  - `@Configuration` - 설정 클래스 등록
  - `@Factory` - 빈 팩토리 메서드
  - `@Scoped(Scope.XXX)` - 스코프 지정
  - `@Transactional` - 트랜잭션 스코프 래퍼

- [x] **스코프 관리**
  - `Scope.SINGLETON` - 앱 전체에서 하나의 인스턴스
  - `Scope.CALL` - 핸들러 호출마다 새 인스턴스, 종료 시 자동 close
  - `Scope.REQUEST` - HTTP 요청 단위 인스턴스 공유
  
- [x] **컨테이너 흡수/전이 시스템**
  - 데코레이터 순서에 관계없이 올바른 컨테이너 타입 결정
  - Container → HandlerContainer/FactoryContainer 자동 전이
  - Elements(메타데이터) 자동 흡수

- [x] **LazyProxy 기반 의존성 주입**
  - 순환 참조 자동 해결
  - 지연 초기화로 토폴로지 정렬 불필요

#### 🌐 Web - ASGI 웹 프레임워크
- [x] **ASGI Application**
  - Lifespan 프로토콜 지원
  - HTTP 요청 처리
  
- [x] **라우팅**
  - Trie 기반 라우터
  - Path parameter 지원 (`/users/{user_id}`)
  - `@Controller` - 컨트롤러 클래스 (path prefix)
  - `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`

- [x] **요청/응답**
  - `HttpRequest` - 요청 객체
  - `JSONResponse` - JSON 응답
  - Response 컨버터 레지스트리

- [x] **파라미터 리졸버**
  - Path parameter 자동 주입
  - Query parameter 자동 주입
  - Request body 파싱

---

## 🚀 Phase 1: Core 안정화 (v0.2.0)

### 의존성 주입 개선 ✅
- [x] `Autowired()` - 명시적 필드 주입 (qualifier, required, lazy 옵션)
- [x] `@Qualifier("name")` - 동일 타입 여러 빈 중 이름으로 선택
- [x] `@Primary` - 기본 빈 지정
- [x] `@Lazy` - 지연 초기화 명시
- [x] `Optional[T]` 의존성 - 빈이 없으면 None

### 라이프사이클 훅
- [ ] `@PostConstruct` - 초기화 후 콜백
- [ ] `@PreDestroy` - 종료 전 콜백
- [ ] `ApplicationEvent` - 이벤트 시스템

### 설정 관리
- [ ] `@Value("${config.key}")` - 환경변수/설정 주입
- [ ] YAML/JSON 설정 파일 지원
- [ ] Profile 기반 설정 (`@Profile("dev")`)

### 테스트 지원
- [ ] `@MockBean` - 테스트용 Mock 빈
- [ ] `@TestConfiguration` - 테스트 전용 설정
- [ ] 컨텍스트 격리 유틸리티

---

## 🌐 Phase 2: Web 기능 확장 (v0.3.0)

### 요청 처리
- [ ] `@RequestBody` - 요청 바디 파싱 (Pydantic 연동)
- [ ] `@RequestParam` - 쿼리 파라미터
- [ ] `@PathVariable` - 경로 변수
- [ ] `@Header` - 헤더 값 주입
- [ ] `@Cookie` - 쿠키 값 주입

### 응답 처리
- [ ] `@ResponseStatus` - HTTP 상태 코드 지정
- [ ] `StreamingResponse` - 스트리밍 응답
- [ ] `FileResponse` - 파일 다운로드
- [ ] `RedirectResponse` - 리다이렉트

### 미들웨어
- [ ] 미들웨어 체인 시스템
- [ ] CORS 미들웨어
- [ ] 인증 미들웨어 인터페이스
- [ ] 로깅 미들웨어

### 에러 처리
- [ ] `@ExceptionHandler` - 예외 핸들러
- [ ] `@ControllerAdvice` - 전역 예외 처리
- [ ] 커스텀 에러 응답 포맷

### 유효성 검사
- [ ] Pydantic 모델 통합
- [ ] `@Valid` - 요청 데이터 검증
- [ ] 커스텀 Validator

---

## 🔧 Phase 3: 데이터 접근 계층 (v0.4.0)

### ORM 통합
- [ ] SQLAlchemy 통합 모듈
- [ ] `@Repository` 데코레이터
- [ ] 트랜잭션 관리 (`@Transactional` 확장)
- [ ] Connection Pool 관리

### 캐싱
- [ ] `@Cacheable` - 결과 캐싱
- [ ] `@CacheEvict` - 캐시 무효화
- [ ] Redis 통합

### 비동기 작업
- [ ] `@Async` - 비동기 실행
- [ ] 백그라운드 태스크 큐
- [ ] 스케줄러 (`@Scheduled`)

---

## 🔒 Phase 4: 보안 (v0.5.0)

### 인증
- [ ] `@Authenticated` - 인증 필수
- [ ] JWT 토큰 처리
- [ ] OAuth2 클라이언트
- [ ] Session 기반 인증

### 인가
- [ ] `@Secured("ROLE_ADMIN")` - 역할 기반 접근
- [ ] `@PreAuthorize` - 표현식 기반 인가
- [ ] RBAC 시스템

---

## 📊 Phase 5: 관측성 (v0.6.0)

### 로깅
- [ ] 구조화된 로깅
- [ ] Request ID 추적
- [ ] 로그 레벨 동적 변경

### 메트릭
- [ ] Prometheus 메트릭 엔드포인트
- [ ] 요청/응답 시간 측정
- [ ] 커스텀 메트릭 API

### 트레이싱
- [ ] OpenTelemetry 통합
- [ ] 분산 트레이싱 지원

### 헬스 체크
- [ ] `/health` 엔드포인트
- [ ] Readiness/Liveness 프로브
- [ ] 커스텀 헬스 인디케이터

---

## 📦 Phase 6: 개발자 경험 (v1.0.0)

### CLI 도구
- [ ] `bloom new` - 프로젝트 생성
- [ ] `bloom run` - 개발 서버
- [ ] `bloom build` - 프로덕션 빌드

### 문서화
- [ ] OpenAPI (Swagger) 자동 생성
- [ ] ReDoc 통합
- [ ] API 문서 커스터마이징

### 개발 도구
- [ ] Hot Reload 지원
- [ ] 디버그 모드 강화
- [ ] VS Code 확장

### 배포
- [ ] Docker 이미지 최적화
- [ ] Kubernetes 매니페스트 생성
- [ ] 환경별 설정 관리

---

## 🎯 설계 원칙

1. **Spring 스타일 API** - Java/Spring 개발자에게 친숙한 인터페이스
2. **Python 관용구** - Pythonic한 구현과 타입 힌팅 활용
3. **비동기 우선** - async/await 네이티브 지원
4. **테스트 용이성** - 모든 컴포넌트의 쉬운 테스트
5. **최소 의존성** - 코어는 표준 라이브러리만 사용
6. **확장성** - 플러그인 시스템으로 기능 확장

---

## 📝 기여 가이드

1. Issue 생성 또는 기존 Issue 확인
2. Fork 후 feature 브랜치 생성
3. 테스트 작성 및 통과 확인
4. PR 생성

---

## 📜 버전 히스토리

### v0.1.0 (현재)
- 초기 릴리스
- Core DI 컨테이너
- 기본 ASGI 웹 프레임워크
- 스코프 시스템 (SINGLETON, CALL, REQUEST)
- 컨테이너 흡수/전이 시스템
