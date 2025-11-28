# bloom 프로젝트 로드맵

## 📊 현재 상태 (v0.1.0)

### ✅ 완료된 기능

#### Core DI Container
| 기능 | 상태 | 설명 |
|------|------|------|
| `@Component` | ✅ | 클래스 컴포넌트 등록 |
| `@Factory` | ✅ | 메서드 기반 인스턴스 생성 |
| `@Handler` | ✅ | 키 기반 핸들러 등록 |
| `@Qualifier` | ✅ | 동일 타입 다중 인스턴스 구분 |
| 필드 주입 | ✅ | 타입 어노테이션 기반 DI |
| 토폴로지컬 정렬 | ✅ | 순환 의존성 감지 |
| ContextVar 기반 매니저 | ✅ | 스레드 안전한 컨테이너 관리 |

#### Web Layer
| 기능 | 상태 | 설명 |
|------|------|------|
| `@Controller` | ✅ | 웹 컨트롤러 등록 |
| `@RequestMapping` | ✅ | 경로 prefix 지정 |
| `@Get/Post/Put/Patch/Delete` | ✅ | HTTP 메서드 핸들러 |
| Path Parameters | ✅ | `/users/{id}` 형식 지원 |
| Query Parameters | ✅ | 자동 파라미터 바인딩 |
| Request Body | ✅ | JSON → dataclass/pydantic 변환 |
| `HttpRequest` / `HttpResponse` | ✅ | 요청/응답 모델 |
| ASGI Application | ✅ | uvicorn 호환 |

#### Parameter Resolvers
| 기능 | 상태 | 설명 |
|------|------|------|
| `@RequestBody` | ✅ | JSON body 바인딩 |
| `@HttpHeader` | ✅ | 헤더 값 주입 |
| `@HttpCookie` | ✅ | 쿠키 값 주입 |
| `@UploadedFile` | ✅ | 파일 업로드 처리 |
| `Authentication` | ✅ | 인증 정보 주입 |
| Optional 파라미터 | ✅ | `param: str | None` 지원 |

#### Middleware
| 기능 | 상태 | 설명 |
|------|------|------|
| `MiddlewareChain` | ✅ | 미들웨어 체인 |
| `MiddlewareGroup` | ✅ | 경로별 미들웨어 그룹 |
| `CorsMiddleware` | ✅ | CORS 처리 |
| `AuthMiddleware` | ✅ | 인증 미들웨어 |
| `ErrorHandlerMiddleware` | ✅ | 예외 처리 |
| `@Authorize` | ✅ | 권한 검사 데코레이터 |
| `@ErrorHandler` | ✅ | 예외 핸들러 데코레이터 |

#### 테스트
- **181개 테스트** 작성 완료
- 모든 테스트 통과 ✅

---

## 🚀 로드맵

### Phase 1: 안정화 및 문서화 (v0.2.0)

#### 📚 문서화
- [ ] README.md 작성 (Quick Start, 설치 방법)
- [ ] API 문서 자동 생성 (pdoc / mkdocs)
- [ ] 예제 프로젝트 작성 (sample/)
- [ ] CONTRIBUTING.md 작성

#### 📦 패키징
- [ ] `pyproject.toml` 작성
- [ ] PyPI 배포 준비
- [ ] GitHub Actions CI/CD 구성
- [ ] 버전 관리 체계 수립

#### 🐛 안정화
- [ ] 엣지 케이스 테스트 추가
- [ ] 에러 메시지 개선
- [ ] 타입 힌트 100% 커버리지
- [ ] mypy/pyright strict 모드 통과

---

### Phase 2: 기능 확장 (v0.3.0)

#### 🔧 DI 확장
- [ ] `@Scope("prototype")` - 호출마다 새 인스턴스
- [ ] `@Lazy` - 지연 초기화
- [ ] `@PostConstruct` / `@PreDestroy` - 라이프사이클 훅
- [ ] 조건부 빈 등록 (`@ConditionalOnProperty`)

#### 🌐 Web 확장
- [ ] WebSocket 지원
- [ ] SSE (Server-Sent Events) 지원
- [ ] Response Streaming
- [ ] 파일 다운로드 (`FileResponse`)
- [ ] 정적 파일 서빙
- [ ] OpenAPI (Swagger) 자동 생성

#### 🔐 보안 확장
- [ ] JWT 내장 Authenticator
- [ ] OAuth2 지원
- [ ] Rate Limiting 미들웨어
- [ ] CSRF 보호

#### 📊 모니터링
- [ ] Request Logging 미들웨어
- [ ] Metrics 수집 (Prometheus 형식)
- [ ] Health Check 엔드포인트
- [ ] Distributed Tracing 지원

---

### Phase 3: 생태계 (v0.4.0)

#### 🗄️ 데이터베이스 통합
- [ ] `bloom-sqlalchemy` - SQLAlchemy 통합
- [ ] `bloom-tortoise` - Tortoise ORM 통합
- [ ] 트랜잭션 관리 (`@Transactional`)
- [ ] Connection Pool 관리

#### 🔄 비동기 작업
- [ ] Background Tasks
- [ ] `bloom-celery` - Celery 통합
- [ ] 스케줄링 (`@Scheduled`)

#### 🧪 테스팅
- [ ] `TestClient` 클래스
- [ ] Mock DI Container
- [ ] Fixture 자동 생성

#### 🔌 확장 플러그인
- [ ] 플러그인 시스템 설계
- [ ] `bloom-redis` - Redis 통합
- [ ] `bloom-kafka` - Kafka 통합

---

### Phase 4: 성능 및 프로덕션 (v1.0.0)

#### ⚡ 성능 최적화
- [ ] 라우터 매칭 최적화 (Trie 구조)
- [ ] 파라미터 리졸버 캐싱
- [ ] 컨테이너 초기화 병렬화
- [ ] 벤치마크 테스트 작성

#### 🏭 프로덕션 준비
- [ ] Graceful Shutdown
- [ ] 멀티 워커 지원
- [ ] 설정 관리 시스템 (`@ConfigurationProperties`)
- [ ] 환경별 프로필 (`@Profile`)

#### 🌍 국제화
- [ ] i18n 지원
- [ ] 다국어 에러 메시지

---

## 📈 우선순위 매트릭스

```
중요도 ↑
         │
    높음 │  📚 문서화        ⚡ 성능 최적화
         │  📦 PyPI 배포     🔧 Scope/Lazy
         │
    중간 │  🌐 WebSocket     🗄️ DB 통합
         │  📊 OpenAPI       🔐 JWT 내장
         │
    낮음 │  🔌 플러그인      🌍 i18n
         │
         └────────────────────────────────→ 긴급도
              낮음          중간          높음
```

---

## 🎯 다음 단계 (권장)

1. **README.md 작성** - 프로젝트 소개 및 Quick Start
2. **pyproject.toml 작성** - 패키지 메타데이터
3. **GitHub Actions** - CI 파이프라인 구성
4. **예제 프로젝트** - 실제 사용 예시

---

## 📊 통계

| 항목 | 수치 |
|------|------|
| Python 파일 | ~35개 |
| 테스트 케이스 | 181개 |
| 코드 라인 | ~4,000줄 (추정) |
| 외부 의존성 | 2개 (pydantic, uvicorn) |

---

## 🔗 참고 프레임워크

- **Spring Framework** (Java) - DI 컨테이너 설계 참고
- **FastAPI** (Python) - ASGI, 파라미터 리졸버 참고
- **NestJS** (TypeScript) - 데코레이터 패턴 참고
