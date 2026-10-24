# Seoul → Chicago 리전 간 라우팅 데모 앱 (xai.grok-4.3)

OCI Generative AI OpenAI 호환 API와 **라우팅 프로파일**로 두 가지 리전 간 라우팅 케이스를 비교하는 FastAPI 데모입니다.

| 케이스 | 근거 | 엔드포인트 | 라우팅 프로파일 타깃 |
|--------|------|-----------|----------------------|
| A | 튜토리얼 "Route Model Requests Across OCI Regions" (2026-10-14) | `us-chicago-1` (로컬 모델 처리 있음) | 여러 리전 가능 (예: Chicago + 기타) |
| B | 릴리스 "Global Generative AI availability" (2026-10-20) | `ap-seoul-1` (로컬 모델 처리 없음) | Chicago 단일 |

실제 서빙 리전은 응답 헤더 `x-genai-selected-region`으로 확인합니다. Case B에서 요청 데이터는 Seoul을 벗어나 Chicago에서 처리됩니다.

## 실행

```bash
cp .env.example .env        # CASE_A/B_PROFILE_OCID, CASE_A/B_API_KEY 입력 (키는 엔드포인트 리전별로 생성)
./run.sh                    # .venv 생성(uv, Python 3.11) → 의존성 설치 → uvicorn :8765
open http://127.0.0.1:8765
```

`.env`는 커밋하지 마세요. 서버는 API 키를 로그나 응답에 포함하지 않습니다.

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CASE_A_API_KEY` | | Chicago(`us-chicago-1`)에서 만든 API 키. 없으면 `OCI_GENAI_API_KEY` 사용 |
| `CASE_B_API_KEY` | | Seoul(`ap-seoul-1`)에서 만든 API 키. 없으면 `OCI_GENAI_API_KEY` 사용 |
| `OCI_GENAI_API_KEY` | | 공통 폴백 키. API 키는 리전 리소스라 두 케이스를 한 키로 쓰면 한쪽은 인증 실패한다 |
| `CASE_A_REGION` | `us-chicago-1` | Case A 엔드포인트 리전 |
| `CASE_A_PROFILE_OCID` | | Case A 라우팅 프로파일 OCID |
| `CASE_B_REGION` | `ap-seoul-1` | Case B 엔드포인트 리전 |
| `CASE_B_PROFILE_OCID` | | Case B 라우팅 프로파일 OCID (타깃: Chicago) |
| `CASE_A_MODEL_LABEL` / `CASE_B_MODEL_LABEL` | `xai.grok-4.3` | 화면 표시용 모델 이름 |
| `COMPARTMENT_OCID` | | Case C 컨트롤 플레인 호출(벡터 스토어 생성/목록/조회)에 필요 (`opc-compartment-id`, `CompartmentId` 헤더) |
| `CASE_A_PROJECT_OCID` / `CASE_B_PROJECT_OCID` | | `OpenAI-Project` 헤더(클라이언트 `project=`). Files API에 필요, 채팅에는 무해 |
| `CASE_A_OCI_PROFILE` / `CASE_B_OCI_PROFILE` | `YWDCLOUD_CHICAGO` / `YWDCLOUD` | 컨트롤 플레인 요청 서명용 `~/.oci/config` 프로파일 |
| `CASE_C_VECTOR_STORE_ID` | | UI에 미리 선택할 벡터 스토어 ID (선택) |
| `CASE_C_MODEL` | `xai.grok-4.3` | Case C file_search 모델. 라우팅 프로파일 OCID는 tools와 함께 쓸 수 없다(400) |
| `CASE_B_PROFILES_JSON` | | Case D: Seoul 라우팅 프로파일 매핑 JSON 객체 `{"<모델 이름>": "<프로파일 OCID>"}` (선택). `xai.grok-4.3`은 없으면 `CASE_B_PROFILE_OCID` 사용 |

엔드포인트: `https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1`, `model`에는 프로파일 OCID를 넣습니다.

## API

| 메서드/경로 | 설명 |
|-------------|------|
| `GET /` | 데모 UI (`static/index.html`) |
| `GET /api/config` | 케이스별 리전, 엔드포인트, 마스킹된 프로파일 OCID(끝 8자), 모델 라벨, 구성 여부. `C`(벡터 스토어), `D`(`profiles` 마스킹, `oci_profiles`, `compartment_set`) 블록 포함 |
| `GET /api/policies` | `policies.json`(최소 IAM 정책, 출처 `docs/07-minimal-iam-policies.md`)을 그대로 반환. UI "필요 정책 (최소)" 탭(`#policies`)에서 사용 |
| `POST /api/chat` | `{case: "A"\|"B", api: "chat_completions"\|"responses", messages: [{role, content}]}` → SSE 스트림 |
| `POST /api/probe` | `{case, n: 1..20}` → n회 짧은 비스트리밍 요청의 서빙 리전·지연·상태 목록과 리전별 히스토그램 |
| `GET /api/vs/list?case=A` | Case C: 벡터 스토어 목록 (컨트롤 플레인, OCI 서명) → `id, name, status, file_counts, created_at` |
| `POST /api/vs/create` | `{case, name, expires_days=7}` → 벡터 스토어 생성 (컨트롤 플레인, OCI 서명). 처음엔 `in_progress` |
| `GET /api/vs/{vs_id}?case=A` | 벡터 스토어 상태 조회 (컨트롤 플레인, OCI 서명). `completed`가 될 때까지 폴링 |
| `POST /api/vs/{vs_id}/files` | multipart `file`, `case` → `files.create(purpose="user_data")` 후 `vector_stores.files.create` (API 키) |
| `GET /api/vs/{vs_id}/files?case=A` | 연결된 파일과 상태 (`queued` → `in_progress` → `completed`) |
| `POST /api/vs/{vs_id}/search` | `{case, query, max_num_results=5}` → `[{score, filename, text}]` |
| `POST /api/vs/{vs_id}/ask` | `{case, question, model?}` → SSE (`/api/chat`와 동일 이벤트, `meta`에 `model`, `vector_store_id` 추가). Responses + `file_search` |
| `GET /api/sdk/models?case=A` | Case D: UI에 제시할 모델 카탈로그(고정) `{embed, rerank, chat: {GENERIC, COHERE}, profiles}`. `profiles`는 Case B에서만 모델 → Seoul 프로파일 OCID |
| `POST /api/sdk/embed` | `{case, model_id, inputs: [str], input_type="SEARCH_DOCUMENT"}` → `embed_text`. `data: {dims, first_values(5), count}` |
| `POST /api/sdk/rerank` | `{case, model_id, query, documents: [str], top_n=3}` → `rerank_text`. `data: [{index, relevance_score, document}]` |
| `POST /api/sdk/chat` | `{case, model_id, api_format: "GENERIC"\|"COHERE", message, max_tokens=200}` → `chat`. `data: {text, api_format}`, `opc_request_id` |

`/api/chat` SSE 이벤트:

- `meta`: `{endpoint_region, selected_region, latency_first_token_ms, request_id}` (첫 토큰 시점에 1회)
- `delta`: `{text}`
- `done`: `{total_ms, output_chars}`
- `error`: `{status, message, body}` (OCI 오류 응답 본문 포함)

프로브는 타깃이 여러 개인 프로파일(Case A)에서 분포를 보기 위한 기능입니다. 라우팅은 라운드로빈이 아니며 정책은 문서화되어 있지 않습니다.

## Case C — 벡터 스토어 / File Search

Files, Vector stores, `file_search`(Enterprise AI Agents 기능)는 **엔드포인트 리전에 생성되는 리전 리소스**입니다. 라우팅 프로파일로 다른 리전에 넘길 수 없습니다.

| 단계 | 경로 | 인증 | Chicago | Seoul |
|------|------|------|---------|-------|
| 벡터 스토어 생성/목록/조회 | `https://generativeai.{region}.oci.oraclecloud.com/20231130/openai/v1/vector_stores` | OCI 요청 서명 | 동작 (생성 후 30~60초 뒤 `completed`) | `403 NotAllowed: GenerativeAiVectorStore is not supported` |
| 파일 업로드 | `{inference}/openai/v1/files` | API 키 + `OpenAI-Project` | 동작 | `404` |
| 파일 연결, 검색 | `{inference}/openai/v1/vector_stores/...` | API 키 | 동작 | — |
| Responses + `file_search` | `{inference}/openai/v1/responses` | API 키 | `xai.grok-4.3` 직접 지정 시 동작 | — |

- `POST {inference}/openai/v1/vector_stores`(API 키)는 404입니다. 생성은 컨트롤 플레인으로만 됩니다.
- 라우팅 프로파일 OCID를 `model`로 쓰면서 `tools`를 붙이면 400(entity not found)이 나므로 `CASE_C_MODEL`을 직접 씁니다.
- `/api/vs/*`는 업스트림 실패를 HTTP 200 `{ok: false, status, message, body, endpoint_region}`으로 돌려줍니다(UI가 Seoul 오류를 데모 결과로 표시). 성공은 `{ok: true, endpoint_region, data}`.
- 서명에는 `~/.oci/config`의 `CASE_X_OCI_PROFILE` 프로파일이 필요합니다. 프로파일이 없으면 `OCI 서명 구성 오류 (ProfileNotFound)`가 JSON으로 반환됩니다.
- UI의 리전 토글(A=Chicago / B=Seoul)로 Seoul을 직접 시도해 실제 오류를 볼 수 있습니다. 서버는 생성한 리소스를 삭제하지 않습니다.


## Case D — OCI SDK 네이티브 API (embed / rerank / chat)

OpenAI 호환 API 대신 OCI Python SDK `oci.generative_ai_inference.GenerativeAiInferenceClient`로 같은 기능을 호출합니다.

- 인증: API 키가 아니라 `~/.oci/config` 프로파일의 **OCI 요청 서명**(사용자 principal). A → `CASE_A_OCI_PROFILE`(기본 `YWDCLOUD_CHICAGO`), B → `CASE_B_OCI_PROFILE`(기본 `YWDCLOUD`). 리전은 케이스 리전, 컴파트먼트는 `COMPARTMENT_OCID`.
- 엔드포인트: `https://inference.generativeai.{region}.oci.oraclecloud.com` (`serving_mode=OnDemandServingMode(model_id)`). `model_id`에는 모델 이름 또는 라우팅 프로파일 OCID를 넣습니다.
- 응답: 성공 `{ok: true, endpoint_region, auth: "user-principal", oci_profile, model_id, latency_ms, data}`, 실패도 HTTP 200 `{ok: false, status, code, message, request_id?}` (`oci.exceptions.ServiceError`, 프로파일 없음 `ProfileNotFound`, `COMPARTMENT_OCID` 미설정 등).
- 관찰 사항(`../scripts/sdk_native_probe.py`):
  - embed / rerank는 라우팅 프로파일로 라우팅되지 않습니다. Seoul에서는 실패합니다.
  - `cohere.command-a-03-2025`는 `api_format=COHERE`(`CohereChatRequest`)가 필요합니다. UI는 `cohere.*`이면 COHERE, 아니면 GENERIC을 자동 선택합니다.
  - `google.gemini-2.5-pro`는 현재 Chicago에서도 Google `NOT_FOUND`.
  - Seoul에서 Gemini를 모델 이름으로 직접 호출하면 Google `asia-northeast3`로 가서 실패합니다.
- UI의 "전체 매트릭스 실행"은 선택한 케이스에서 embed, rerank, chat(grok-4.3, gpt-oss-120b, gemini-2.5-flash, command-a)을 차례로 호출하고, Case B는 `CASE_B_PROFILES_JSON`/`CASE_B_PROFILE_OCID`에 있는 프로파일 경유 호출도 함께 표시합니다.
