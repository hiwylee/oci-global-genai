# oci-global-genai

OCI Generative AI **Global Generative AI availability**(2026-10-20)와 **Route Model Requests Across OCI Regions** 튜토리얼(2026-10-14)을
Seoul 리전(`ap-seoul-1`)에서 검증한 프로젝트입니다. Seoul 엔드포인트로 요청을 보내고 실제 모델 실행은 Chicago(`us-chicago-1`)에서 하도록
**라우팅 프로파일**을 구성하고, OpenAI 호환 API·OCI SDK·Enterprise AI Agents 기능의 지원 범위를 실측했습니다.

- 모델: `xai.grok-4.3` (OpenAI 호환), Cohere Embed/Rerank/Command, Gemini, gpt-oss (범위 테스트)
- 검증일: 2026-10-24 · 공개 저장소에는 OCID·API 키·원본 로그가 포함되어 있지 않습니다.

## 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [요구 사항](#요구-사항)
4. [빠른 시작](#빠른-시작)
5. [프로젝트 구조](#프로젝트-구조)
6. [문서](#문서)
7. [검증 결과 요약](#검증-결과-요약)
8. [주의 사항](#주의-사항)
9. [라이선스](#라이선스)

## 개요

| 케이스 | 의미 | 프로파일 생성 리전 | 호출 엔드포인트 | 타깃 리전 |
|--------|------|-------------------|-----------------|-----------|
| **A** | 튜토리얼 패턴. 로컬 모델 처리가 있는 리전에서 다중 타깃 | Chicago | Chicago | Chicago, Ashburn, Phoenix |
| **B** | Global availability. 로컬 모델 처리가 없는 Seoul에서 라우팅 (주 시나리오) | Seoul | Seoul | Chicago |
| **C** | Enterprise AI Agents: Files / Vector stores / file_search | Chicago (Seoul 미지원) | Chicago | - |
| **D** | OCI SDK 네이티브: embed / rerank / chat(Generic·Cohere) | - | Chicago, Seoul | 프로파일 경유 비교 |

라우팅 프로파일은 **리전 리소스**입니다. Seoul에서 만든 프로파일은 Seoul 엔드포인트에서만, Chicago에서 만든 프로파일은 Chicago 엔드포인트에서만 쓸 수 있습니다.

## 아키텍처

```
Client (OpenAI SDK, API key)
   │  model = <routing profile OCID>
   ▼
https://inference.generativeai.ap-seoul-1.oci.oraclecloud.com/openai/v1   ← Seoul 엔드포인트 (로컬 모델 없음)
   │  routing profile: allowedModels=[xai.grok-4.3], allowedRegions=[us-chicago-1]
   ▼
us-chicago-1 에서 추론 → 응답 헤더 x-genai-selected-region: us-chicago-1
```

Files·Vector store·file_search는 Seoul이 지원하지 않아 Chicago 엔드포인트에 프로젝트와 벡터 스토어를 두고 모델명을 직접 지정해 호출합니다.

## 요구 사항

| 항목 | 버전 / 조건 |
|------|-------------|
| OCI CLI | **3.95 이상** (`routing-profile` 명령 필요) |
| Python | 3.11 이상, `uv` |
| OCI 인증 | `~/.oci/config` 프로파일. Seoul용과 Chicago용 리전별 프로파일 권장 |
| IAM | 사용자 그룹: `generative-ai-chat` use, `generative-ai-routing-profile` manage, `generative-ai-apikey` manage 등. API 키 principal: `request.principal.type='generativeaiapikey'` 조건 정책. 최소 세트는 [docs/07](docs/07-minimal-iam-policies.md) |
| 모델 가용성 | 타깃 리전에 모델이 있어야 함. `xai.grok-4.3`은 Ashburn·Chicago·Phoenix |

## 빠른 시작

```bash
# 1. CLI 업그레이드 및 확인
brew upgrade oci-cli && oci generative-ai routing-profile --help

# 2. Seoul에 라우팅 프로파일 생성 (타깃 Chicago)
oci --profile <SEOUL_PROFILE> generative-ai routing-profile create --region ap-seoul-1 --compartment-id <COMPARTMENT_OCID> \
  --display-name seoul-grok43-to-chicago \
  --model-routing-policy '{"allowedModels":["xai.grok-4.3"]}' \
  --region-routing-policy '{"allowedRegions":["us-chicago-1"]}' --wait-for-state ACTIVE

# 3. Seoul에 API 키 생성 (평문 키는 create 즉시 응답에만 노출)
oci --profile <SEOUL_PROFILE> generative-ai api-key create --region ap-seoul-1 --compartment-id <COMPARTMENT_OCID> \
  --display-name seoul-grok43-demo --key-details '[{"keyName":"primary","timeExpiry":"2026-11-23T00:00:00Z"}]'

# 4. 데모 앱
cd examples/seoul-to-chicago-grok43/app
cp .env.example .env        # CASE_B_PROFILE_OCID, CASE_B_API_KEY 등 입력
./run.sh                    # http://127.0.0.1:8765

# 5. 앱 없이 바로 검증
cd .. && python3 scripts/smoke_test.py
```

단계별 사전 준비와 확인 방법은 [docs/00-step-by-step.md](docs/00-step-by-step.md)에 있습니다.

## 프로젝트 구조

```
.
├── CLAUDE.md                       운영 규칙, 요약, 문서 맵
├── README.md
├── docs/                           개념·범위·절차·결과·정책 (단일 출처)
├── examples/seoul-to-chicago-grok43/
│   ├── README.md                   재현 절차, 주의사항, 케이스 비교
│   ├── app/                        FastAPI 데모 (Case A/B/C/D + 최소 정책 탭)
│   │   ├── server.py  static/index.html  policies.json  run.sh  .env.example
│   └── scripts/                    smoke_test.py, vector_store_probe.py, sdk_native_probe.py
├── scripts/                        튜토리얼 원형 스크립트 (Chat Completions / Responses)
└── logs/worklog.md                 작업 이력 (원본 출력 logs/raw/ 는 비공개)
```

## 문서

| 문서 | 내용 |
|------|------|
| [docs/00-step-by-step.md](docs/00-step-by-step.md) | 처음부터 따라 하기 10단계 |
| [docs/01-concepts.md](docs/01-concepts.md) | 라우팅 프로파일 개념, 동작, 제약, 지원 API |
| [docs/02-regions-and-features.md](docs/02-regions-and-features.md) | Global availability 30개 리전, Seoul 지원/미지원 기능표 |
| [docs/03-setup.md](docs/03-setup.md) | CLI, IAM, API 키, 프로파일 생성, Python 환경, 트러블슈팅 |
| [docs/04-test-plan.md](docs/04-test-plan.md) | 테스트 시나리오 체크리스트 |
| [docs/05-results.md](docs/05-results.md) | 실측 결과(A/B/C/D), 지연, 생성 리소스 |
| [docs/06-scope-embeddings-vectorstores.md](docs/06-scope-embeddings-vectorstores.md) | OpenAI 호환 모델표, 프로파일 호출 범위, 임베딩, Vector stores/Applications 리전 동작 |
| [docs/07-minimal-iam-policies.md](docs/07-minimal-iam-policies.md) | family 없이 기능별 최소 IAM 정책 |
| [docs/references.md](docs/references.md) | Oracle 공식 문서 링크 |

## 검증 결과 요약

| 항목 | 결과 |
|------|------|
| Seoul 엔드포인트 → Chicago 실행 (Chat Completions, Responses) | 성공. `x-genai-selected-region: us-chicago-1` |
| 라우팅 프로파일로 호출 가능한 모델 | 온디맨드 **채팅** 모델. Grok 4.3, gpt-oss-120b, Llama 3.3, Gemini 2.5 Flash(Chat Completions만), Cohere Command A(네이티브 Cohere Chat만) |
| 임베딩·리랭크 | 프로파일 대상 아님. Seoul 불가, Chicago 네이티브 SDK만 가능. OpenAI 호환 `/embeddings`는 전 리전 미지원 |
| Files / Vector stores / file_search | Seoul 미지원(403 `GenerativeAiVectorStore is not supported`). Chicago에서 생성·검색·질의 성공 |
| Projects / Applications | Seoul에서 생성 가능 (Applications는 컨테이너 배포 필요, 데모 제외) |
| 프로파일 OCID + `tools` | 불가(400). 툴 사용 시 모델명 직접 지정 |
| Gemini 2.5 Pro | OCI 카탈로그에 있으나 Google 측 NOT_FOUND (2026-10-24) |

## 주의 사항

- API 키 평문은 `create` 응답에만 나옵니다. `--wait-for-state`를 쓰면 null이 되며 `api-key renew`로 재발급합니다.
- 프로파일 생성 직후 약 1분간 `400 Routing profile …` 오류가 날 수 있습니다.
- 벡터 스토어는 생성 후 `completed`가 될 때까지(약 1분) 파일을 연결할 수 없습니다.
- 모델이 `file_search`를 생략할 수 있어 앱은 `tool_choice`로 강제합니다.
- 요청 데이터는 타깃 리전(Chicago)에서 처리됩니다. 데이터 레지던시 요건을 확인하세요.
- 생성한 OCI 리소스(프로파일, 키, 프로젝트, 벡터 스토어)는 문서에 마스킹된 ID로만 기록되어 있습니다.

## 라이선스

MIT
