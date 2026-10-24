# 06. 지원 범위 실측: OpenAI 호환 모델, 라우팅 프로파일, 임베딩, Files/Vector stores/Applications (2026-10-24)

원본 출력: `logs/raw/20261024-14*-openai-compat-*.txt`, `*-embed-*.json`, `*-vector-store-probe*.txt`, `*-profile-scope-*.txt`, `*-hosted-apps-list.txt`.
공식 문서 근거: "Regions with no Local Model Processing", "OCI OpenAI-Compatible Endpoints", "Using a Vector Store", "Projects" (`references.md`).

## 1. OpenAI 호환 API로 호출 가능한 모델 (Chicago 엔드포인트, 모델명 직접 지정)

| 모델 | Chat Completions | Responses | 비고 |
|------|------------------|-----------|------|
| `xai.grok-4.3` / `4.6` / `4.7` / `4.20-reasoning` / `4.20-non-reasoning` | O | O | xAI 외부 호스팅 |
| `openai.gpt-oss-120b` / `gpt-oss-20b` | O | O | 튜토리얼 기본 모델 |
| `google.gemini-2.5-flash` | O | O | Google 외부 호스팅 |
| `google.gemini-2.5-pro` | X (not found) | X | Chicago에서는 Interconnect 전용(✓G) |
| `meta.llama-3.3-70b-instruct`, `meta.llama-4-maverick-…` | O | X (not found) | Chat Completions 전용 |
| `cohere.command-a-03-2025`, `command-r-plus-08-2024` | X (unsupported / not found) | X | Cohere는 네이티브 Chat API만 |
| `cohere.embed-v4.0` (`/embeddings`) | X "Unsupported OpenAI operation" | - | 아래 3절 |

- `GET /openai/v1/models`는 **미지원**(404). 모델 목록은 `oci generative-ai model-collection list-models`로 확인한다.
- 문서상 OpenAI 호환 엔드포인트 지원 리전(로컬 처리 리전): Sao Paulo, Frankfurt, Hyderabad, Osaka, Riyadh, London, Ashburn, Chicago, Phoenix. Seoul은 **라우팅 프로파일 경유로만** 사용.

## 2. 라우팅 프로파일로 호출 가능한 범위 (Seoul 엔드포인트 → Chicago)

| 모델 (Seoul 프로파일, 타깃 Chicago) | Chat Completions | Responses |
|---|---|---|
| `xai.grok-4.3` | O (served `us-chicago-1`) | O |
| `openai.gpt-oss-120b` | O | O |
| `meta.llama-3.3-70b-instruct` | O | O (직접 호출 시엔 X였으나 프로파일 경유는 O) |
| `google.gemini-2.5-flash` | O | X (400 "Incorrect apiIdentifier") |
| `cohere.embed-v4.0` | X (404 entity not found) | - |

관찰:
- **프로파일 생성은 모델을 검증하지 않는다.** 임베딩 모델(`cohere.embed-v4.0`)로도 ACTIVE 프로파일이 만들어지지만 호출은 404. 범위는 "온디맨드 **채팅** 모델 + 모델이 해당 API 지원" 이다.
- **전파 지연**: 프로파일 생성 직후 약 1분간 `400 Routing profile …` 오류가 났고 이후 정상. 생성 후 60초 대기 또는 재시도 로직 필요.
- **모델이 file_search 호출을 생략할 수 있다.** 복합 질문에서 툴을 부르지 않고 "정보 없음"으로 답한 사례가 있어, 데모 앱은 `tool_choice={"type":"file_search"}`와 지시문으로 강제한다.
- **프로파일 OCID + 툴(file_search 등)은 불가**: Responses에 `tools`를 넣으면 `model=<profile OCID>`가 400 "Entity … not found". 툴을 쓰려면 모델명을 직접 지정해야 하므로 Seoul 엔드포인트에서는 툴 사용이 사실상 불가.
- Seoul 로컬 모델 목록(Gemini 2.5 3종)은 OpenAI 호환 API로 **직접 호출되지 않는다**(404). Gemini도 프로파일을 통해야 한다.

## 2b. OCI Python SDK 네이티브 API 실측 (embed / rerank / chat) — 2026-10-24 14:30

스크립트: `examples/seoul-to-chicago-grok43/scripts/sdk_native_probe.py`. 원본: `logs/raw/20261024-142*-sdk-native-probe-*.txt`, `*-gemini-*-error*.txt`.

| API (SDK) | 모델 | Chicago 직접 | Seoul 직접 | Seoul 프로파일→Chicago |
|---|---|---|---|---|
| `embed_text` | cohere.embed-v4.0 | O 1536차원 | X 404 | X 404 (프로파일 대상 아님) |
| `rerank_text` | cohere.rerank-v4.0-fast | O top=1 score 0.884 | X 404 | X 404 |
| `rerank_text` | cohere.rerank-v3.5 | X 404 (카탈로그엔 있으나 deprecated) | X | - |
| `chat` GENERIC | google.gemini-2.5-pro | X Google NOT_FOUND (`us-central1`에 publisher model 없음) | X Google NOT_FOUND (`asia-northeast3`) | X Google NOT_FOUND |
| `chat` GENERIC | google.gemini-2.5-flash | O | X Google NOT_FOUND (`asia-northeast3`) | O |
| `chat` GENERIC | google.gemini-2.5-flash-lite | X Google NOT_FOUND | - | - |
| `chat` GENERIC | xai.grok-4.3 / openai.gpt-oss-120b | O | X 404 | O (gpt-oss는 `max_tokens`가 작으면 추론 토큰만 쓰고 본문이 빈 응답이 올 수 있음) |
| `chat` COHERE | cohere.command-a-03-2025 | O | X 404 | **O** |
| `chat` GENERIC | cohere.command-a-03-2025 | X 400 "Chat request type does not match serving model" | - | X 400 동일 |

OpenAI 호환 교차 확인:

| 모델 | Chicago 직접 Chat Completions / Responses | Seoul 프로파일 Chat Completions / Responses |
|---|---|---|
| cohere.command-a-03-2025 | X 400 "Unsupported OpenAI operation" / X 404 | X 400 Unsupported / X 400 |
| google.gemini-2.5-pro | X 404 Google NOT_FOUND / X 404 | X / X |

관찰:
- **Cohere Command A는 네이티브 Cohere Chat(`api_format=COHERE`)으로만 동작**하며, 라우팅 프로파일 경유(Seoul→Chicago)도 된다. OpenAI 호환 API로는 어느 경로로도 불가.
- **Gemini 2.5 Pro는 OCI 카탈로그(Chicago·Seoul 모델 목록)에는 있지만 Google 측이 NOT_FOUND를 반환**한다(2.5 Flash-Lite 동일). 2.5 Flash만 Chicago에서 동작. OCI 리전 문제가 아니라 Google publisher model 가용성 문제로 보이며, OCI 호출 프로젝트가 접근 권한이 없거나 모델이 해당 Google 리전에서 내려갔을 가능성이 있다. `opc-request-id`는 로그에 기록.
- **Seoul에서 Gemini를 직접 호출하면 OCI 404가 아니라 Google `asia-northeast3`(서울)로 전달**된다. Seoul 모델 목록에 Gemini 3종이 보이는 이유다. 그러나 현재 그 위치에 모델이 없어 실패하고, 프로파일로 Chicago를 거치면 2.5 Flash는 성공한다.
- 임베딩·리랭크는 라우팅 프로파일 대상이 아니다(둘 다 404). Chat 계열만 프로파일을 탄다.

## 3. 임베딩을 Seoul에서 호출할 수 있는가 → **불가**

| 방법 | Chicago | Seoul |
|------|---------|-------|
| 네이티브 `EmbedText` (`oci generative-ai-inference embed-text-result embed-text`, `cohere.embed-v4.0`) | O (1536차원) | X 404 "Entity with key cohere.embed-v4.0 not found" |
| 네이티브 EmbedText + 라우팅 프로파일 OCID(임베딩 모델) | - | X 404 |
| OpenAI 호환 `/openai/v1/embeddings` | X 400 "Unsupported OpenAI operation" | X 404 |

결론: 임베딩은 **로컬 처리 리전(Chicago, Osaka 등)의 네이티브 Embed API**로만 가능하다. 라우팅 프로파일은 Chat/Responses 전용이고, OpenAI 호환 `/embeddings`는 어느 리전에도 없다.
Seoul 앱이 임베딩이 필요하면 ① Chicago/Osaka 엔드포인트의 네이티브 EmbedText를 직접 호출하거나 ② 아래 Vector store(서비스가 내부 임베딩 수행)를 Chicago에 두는 방법뿐이다.

## 4. Applications / Vector stores 를 Seoul에서 쓰면 리소스가 Seoul에 생기는가

### Vector stores (Enterprise AI Agents, Console "Vector stores")

| 동작 | Chicago | Seoul |
|------|---------|-------|
| Files 업로드 `POST /openai/v1/files` (API 키 + `OpenAI-Project`) | O `file-ord-…` | X 404 "Authorization failed or requested resource not found" |
| Vector store 생성 (컨트롤 플레인 `https://generativeai.<region>…/20231130/openai/v1/vector_stores`, IAM 서명, `opc-compartment-id`) | O `vs_ord_…` (in_progress → completed 약 1분) | **X 403 `NotAllowed: GenerativeAiVectorStore is not supported`** |
| Vector store 목록 | O | X 403 동일 |
| 파일 연결 / 검색 (`/openai/v1/vector_stores/{id}/files`, `/search`, API 키) | O | - |
| Responses + `file_search` (`xai.grok-4.3`, `openai.gpt-oss-120b` 직접 지정) | O 정답 "BLUE-TIGER-42" | - |

결론: **Seoul에는 Vector store/Files가 생성되지 않는다.** 서비스가 리전 단위로 기능을 막아 두었다(문서 "Semantic stores and vector stores: Not available", "File search: Not available"와 일치).
Seoul 리전 Console에 "Vector stores" 메뉴가 보여도 생성은 실패한다(실측은 API 기준; Console 화면은 미확인). 벡터 스토어와 파일은 **엔드포인트 리전(Chicago)에 리전 리소스로** 생성되며 ID 접두사가 리전 키를 포함한다(`vs_ord_`, `file-ord-` = Chicago ORD).
따라서 "Seoul 앱 + RAG"는 Chicago 엔드포인트에 프로젝트·벡터 스토어를 두고 Chicago 엔드포인트로 `file_search`를 호출하는 구조가 된다. 라우팅 프로파일은 이 경로에 쓸 수 없다.

주의: `POST {inference}/openai/v1/vector_stores`(API 키)는 404. 생성·목록·조회는 **컨트롤 플레인 + IAM 서명**이 필요하다(`oci.signer.Signer` 또는 `oci-openai` 라이브러리). 파일 업로드·연결·검색·질의는 추론 엔드포인트 + API 키로 된다.

### Projects
- `oci generative-ai generative-ai-project create` 는 **Seoul에서도 성공**(ACTIVE). OpenAI 호환 API의 Files/Responses에는 `OpenAI-Project` 헤더(SDK `project=`)가 필요하다.
- Seoul 프로젝트는 숏텀 메모리만 지원(문서). 롱텀 메모리(임베딩 필요)·벡터 스토어·File search 불가.

### Applications (Hosted applications / deployments, Console "Applications")
- 문서상 로컬 처리 없는 30개 리전에서 **"Hosted deployments: Available"**. CLI `hosted-application-collection list-hosted-applications --region ap-seoul-1` 정상 응답(0건) → Seoul에서 리소스 타입 사용 가능.
- 실체: OCIR 컨테이너 이미지(linux/amd64, 0.0.0.0:8080, health 엔드포인트)를 서비스 관리 런타임에 배포하는 기능. 인증(IDCS/IAM/없음), 네트워킹(기본 또는 VCN), 스토리지(50GB 파일, PostgreSQL, Cache, ADB). 생성 시 프로젝트 불필요.
- 즉 Seoul에 Application을 만들면 **런타임은 Seoul에 생긴다.** 다만 그 앱이 모델을 쓰려면 라우팅 프로파일, RAG를 쓰려면 Chicago 벡터 스토어를 원격 호출해야 한다.
- 이번 예제에서는 컨테이너 빌드·OCIR 푸시가 필요해 **데모를 만들지 않았다.** Chicago 테넌시에 기존 `AgentFromScratchUI` 앱 1개 확인.

## 5. 생성/변경된 리소스 (삭제 시 사용자 확인 필수)

| 종류 | 리전 | 이름 | OCID / ID |
|------|------|------|-----------|
| Project | us-chicago-1 | grok43-demo-us-chicago-1 | `ocid1.generativeaiproject.oc1.us-chicago-1.****fybq` |
| Project | ap-seoul-1 | grok43-demo-ap-seoul-1 | `ocid1.generativeaiproject.oc1.ap-seoul-1.****mmgq` |
| Routing profile (프로브, 무용) | ap-seoul-1 | probe-embed-v4-seoul | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****7djq` |
| Routing profile (범위 프로브) | ap-seoul-1 | seoul-openai-gpt-oss-120b-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****r4va` |
| Routing profile (범위 프로브) | ap-seoul-1 | seoul-google-gemini-2-5-flash-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****5qdq` |
| Routing profile (범위 프로브) | ap-seoul-1 | seoul-google-gemini-2-5-pro-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****yhbq` |
| Routing profile (범위 프로브) | ap-seoul-1 | seoul-cohere-command-a-03-2025-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****rljq` |
| Routing profile (범위 프로브, 무용) | ap-seoul-1 | seoul-cohere-rerank-v4-0-fast-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****wpvq` |
| Routing profile (범위 프로브) | ap-seoul-1 | seoul-meta-llama-3-3-70b-instruct-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****xbdq` |
| Vector store | us-chicago-1 | probe-A-us-chicago-1 (7일 비활성 시 만료) | `vs_ord_****ebq2` |
| Files | us-chicago-1 | genai-demo-A-*.txt ×4 (299 bytes), doc2.txt (101 bytes) — 총 5개 | 미연결 2: `file-ord-****`, `file-ord-****` / 벡터 스토어 연결 3: `file-ord-****`, `file-ord-****`, `file-ord-****`(검증 실행분) |

삭제 후보: 무용 프로파일 2개(`probe-embed-v4-seoul`, `seoul-cohere-rerank-v4-0-fast-to-chicago`), 범위 프로브 프로파일 5개(gpt-oss, gemini-flash, llama, gemini-pro, command-a), 미연결 파일 2개(`0c55305d`, `0a3293a6`).
