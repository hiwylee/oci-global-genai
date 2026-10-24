# Seoul → Chicago: xai.grok-4.3 리전 간 라우팅 예제 (OpenAI 호환 API)

OCI Generative AI 호출은 **Seoul(`ap-seoul-1`) 엔드포인트**로 보내고, 실제 모델 실행은 **Chicago(`us-chicago-1`)** 에서 되도록
**라우팅 프로파일**로 구성한 예제다. 앱은 OpenAI Python SDK만 사용한다(OCI SDK 불필요).
모델은 `xai.grok-4.3`. 검증 완료: 2026-10-24 (`../../logs/raw/20261024-1325-app-e2e.txt`).

## 두 케이스의 차이

| | Case A — 튜토리얼 "Route Model Requests Across OCI Regions" (2026-10-14) | Case B — "Global Generative AI availability" (2026-10-20) |
|---|---|---|
| 호출 엔드포인트 | 로컬 모델 처리가 **있는** 리전 (Chicago) | 로컬 모델 처리가 **없는** 리전 (Seoul) |
| 라우팅 프로파일 | 타깃 여러 개 (Chicago + Ashburn + Phoenix) | 타깃 1개 (Chicago) |
| 목적 | 용량 분산, 앱 측 라우팅 코드 제거 | Seoul에 없는 모델을 Seoul 엔드포인트로 사용 |
| 프로파일 생성 리전 | `us-chicago-1` (`YWDCLOUD_CHICAGO`) | `ap-seoul-1` (`YWDCLOUD`) |
| API 키 생성 리전 | `us-chicago-1` | `ap-seoul-1` |
| 관찰된 서빙 리전 | `us-chicago-1` (12/12) | `us-chicago-1` (12/12) |

같은 메커니즘(라우팅 프로파일)을 쓰지만, A는 "있는 리전에서 더 넓게", B는 "없는 리전에서 쓰게 하는" 용도다.
공통 제약: 온디맨드 전용, 같은 realm, 타깃 리전은 모델이 제공되는 곳만. 데이터는 타깃 리전에서 처리된다(Seoul을 벗어남).

## 사전 조건

- OCI CLI **3.95.1+** (`routing-profile` 명령은 3.76에는 없음): `brew upgrade oci-cli`
- 프로파일: Seoul 작업 `YWDCLOUD`, Chicago 작업 `YWDCLOUD_CHICAGO` (`~/.oci/config`)
- 컴파트먼트 `wonyong.lee` 에 다음 정책이 이미 존재(없으면 추가):
  ```
  allow any-user to use generative-ai-family in compartment wonyong.lee
    where ALL { request.principal.type='generativeaiapikey' }
  ```
  관리 작업(프로파일/키 생성)은 사용자 그룹에 `manage generative-ai-family` 가 필요하다.
- Python 3.11+, `uv`

## 구성 절차 (재현)

### 0. 모델 가용성 확인
```bash
TEN=<tenancy OCID>
oci --profile YWDCLOUD_CHICAGO generative-ai model-collection list-models --compartment-id $TEN --region us-chicago-1 --all \
  --query 'data.items[?"display-name"==`xai.grok-4.3`].{name:"display-name",state:"lifecycle-state",cap:capabilities}' --output table
oci --profile YWDCLOUD generative-ai model-collection list-models --compartment-id $TEN --region ap-seoul-1 --all \
  --query 'data.items[].{name:"display-name"}' --output table      # Seoul 로컬 목록에는 Gemini 3종만, Grok 없음
```
`xai.grok-4.3` 온디맨드 제공 리전: `us-ashburn-1`, `us-chicago-1`, `us-phoenix-1` (Frankfurt/Osaka/London 없음).

### 1. 라우팅 프로파일 생성
정책 JSON 스키마(CLI `--generate-param-json-input`으로 확인): `{"allowedModels":[...]}`, `{"allowedRegions":[...]}`.

```bash
COMP=<compartment OCID>
# Case B: Seoul에서 생성, 타깃 Chicago만
oci --profile YWDCLOUD generative-ai routing-profile create --region ap-seoul-1 --compartment-id $COMP \
  --display-name seoul-grok43-to-chicago \
  --model-routing-policy '{"allowedModels":["xai.grok-4.3"]}' \
  --region-routing-policy '{"allowedRegions":["us-chicago-1"]}' \
  --wait-for-state ACTIVE
# Case A: Chicago에서 생성, 타깃 3개
oci --profile YWDCLOUD_CHICAGO generative-ai routing-profile create --region us-chicago-1 --compartment-id $COMP \
  --display-name chicago-grok43-multiregion \
  --model-routing-policy '{"allowedModels":["xai.grok-4.3"]}' \
  --region-routing-policy '{"allowedRegions":["us-chicago-1","us-ashburn-1","us-phoenix-1"]}' \
  --wait-for-state ACTIVE
```
각 응답의 `data.id`(`ocid1.generativeairoutingprofile.oc1.<region>....`)를 `.env`에 넣는다.
조회: `oci generative-ai routing-profile-collection list-routing-profiles --compartment-id $COMP --region <region>` (`list`가 아니라 `-collection list-routing-profiles`).

### 2. API 키 생성 (리전별)
API 키는 **리전 리소스**다. 호출할 엔드포인트 리전마다 하나씩 만든다.

```bash
EXP=$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ)
oci --profile YWDCLOUD generative-ai api-key create --region ap-seoul-1 --compartment-id $COMP \
  --display-name seoul-grok43-demo --key-details "[{\"keyName\":\"primary\",\"timeExpiry\":\"$EXP\"}]"
oci --profile YWDCLOUD_CHICAGO generative-ai api-key create --region us-chicago-1 --compartment-id $COMP \
  --display-name chicago-grok43-demo --key-details "[{\"keyName\":\"primary\",\"timeExpiry\":\"$EXP\"}]"
```
**주의:** 평문 키(`keys[].key`, `sk-...`)는 `create` 응답에만 한 번 나온다. `--wait-for-state`를 붙이면 GET 결과로 덮여 `key: null`이 된다.
놓쳤으면 `api-key renew --api-key-id <id> --details '{"keyName":"primary","timeExpiry":"..."}'` 로 재발급하면 평문이 다시 반환된다.
키 기본 만료는 3개월, 이 예제는 30일로 지정했다.

### 3. 앱 설정과 실행
```bash
cd app
cp .env.example .env     # CASE_A/B_PROFILE_OCID, CASE_A/B_API_KEY 채우기
./run.sh                 # http://127.0.0.1:8765
```
앱과 무관하게 바로 검증하려면:
```bash
python3 scripts/smoke_test.py            # 두 케이스 × 두 API, 서빙 리전 헤더 출력
python3 scripts/smoke_test.py --case B --api chat --n 5
```

### 4. 확인 포인트
- 응답 헤더 `x-genai-selected-region` 이 Case B에서도 `us-chicago-1` 이어야 한다(엔드포인트는 `ap-seoul-1`).
- Case A는 타깃이 3개지만 관찰 범위(12회)에서는 모두 `us-chicago-1`. 라운드로빈이 아님(문서와 일치).
- Chat Completions와 Responses API 둘 다 `model=<프로파일 OCID>` 로 동작했다.
- 첫 토큰 지연: Seoul→Chicago 약 4.7~5.3초, Chicago 직접 약 4.6~4.8초(스트리밍, 1회 측정). 프로브(비스트리밍 16토큰) 1.6~2.4초.

## Case C — 벡터 스토어 / File Search (Enterprise AI Agents) 추가 (2026-10-24)

질문: Seoul에서 Console의 **Applications / Vector stores** 를 쓰면 리소스가 Seoul에 생기는가? → **Vector stores·Files는 Seoul에 생기지 않는다.**
Seoul 컨트롤 플레인은 403 `GenerativeAiVectorStore is not supported`, Files API는 404를 반환한다. Projects와 Applications(hosted deployments)는 Seoul에서 생성된다.
상세 실측표: `../../docs/06-scope-embeddings-vectorstores.md`.

데모 구조(앱 "Case C" 섹션): 리전 토글로 Seoul을 선택하면 실제 오류를 그대로 보여 주고, Chicago를 선택하면 다음 흐름이 동작한다.

1. 벡터 스토어 생성: 컨트롤 플레인 `https://generativeai.us-chicago-1.oci.oraclecloud.com/20231130/openai/v1/vector_stores`, **IAM 서명**(`~/.oci/config` 프로파일 `YWDCLOUD_CHICAGO`), 헤더 `opc-compartment-id`. 생성 후 `completed`까지 약 1분.
2. 파일 업로드·연결: 추론 엔드포인트 `/openai/v1/files`(API 키 + `OpenAI-Project`) → `/vector_stores/{id}/files`. 파일 상태 queued → in_progress → completed(약 30초).
3. 검색: `/vector_stores/{id}/search`.
4. 질의: Responses API + `tools=[{"type":"file_search","vector_store_ids":[...]}]`, 모델은 **`xai.grok-4.3` 직접 지정**. 라우팅 프로파일 OCID는 툴과 함께 쓰면 400이 난다.

사전 준비(추가):
```bash
# 프로젝트(OpenAI-Project 헤더용). Seoul에서도 생성은 된다.
oci --profile YWDCLOUD_CHICAGO generative-ai generative-ai-project create --region us-chicago-1 --compartment-id $COMP \
  --display-name grok43-demo-us-chicago-1 --wait-for-state SUCCEEDED      # 응답 resources[0].identifier 가 프로젝트 OCID
# .env 추가
CASE_A_PROJECT_OCID=ocid1.generativeaiproject.oc1.us-chicago-1....
CASE_B_PROJECT_OCID=ocid1.generativeaiproject.oc1.ap-seoul-1....
COMPARTMENT_OCID=ocid1.compartment.oc1....
```
앱 없이 바로 검증: `app/.venv/bin/python scripts/vector_store_probe.py --case A --vs-id vs_ord_****ebq2` (기존 스토어 재사용; `--vs-id` 생략 시 새로 생성) (Seoul 오류 확인은 `--case B`).

## 범위 요약 (실측, 상세는 docs/06)

| 질문 | 답 |
|------|----|
| OpenAI 호환 API로 되는 모델 | Grok 4.x, gpt-oss-120b/20b, Gemini 2.5 Flash는 Chat Completions·Responses 모두. Llama 3.x/4는 Chat Completions만. Cohere Command/Embed, Gemini 2.5 Pro(Chicago)는 불가. `/models` 미지원 |
| 라우팅 프로파일로 호출 가능한 범위 | 온디맨드 채팅 모델 + 모델이 지원하는 API. Seoul→Chicago로 grok-4.3, gpt-oss-120b, llama-3.3 양 API, gemini-2.5-flash Chat만 확인. 임베딩 모델 프로파일은 만들어지지만 호출 404. 생성 직후 약 1분 전파 지연. 툴 사용 불가 |
| Seoul에서 임베딩 | 불가. 네이티브 EmbedText·OpenAI `/embeddings`·프로파일 경유 모두 실패. Chicago/Osaka 네이티브 EmbedText만 가능 |
| Vector stores/Files를 Seoul에서 | 불가(403/404). Chicago에 생성되며 ID에 리전 키 포함(`vs_ord_`, `file-ord-`) |
| Applications를 Seoul에서 | 가능(문서 "Hosted deployments: Available", CLI 목록 정상). 컨테이너 배포가 필요해 이번 예제에서는 데모 제외 |

## Case D — OCI SDK 네이티브 API 비교 (embed / rerank / chat) 추가 (2026-10-24)

같은 기능을 OCI Python SDK(`oci.generative_ai_inference`, 사용자 principal 서명)로 호출한 결과. 스크립트 `scripts/sdk_native_probe.py`, 앱 "Case D" 섹션. 상세표는 `../../docs/06-scope-embeddings-vectorstores.md` §2b.

| 기능 | Chicago 직접 | Seoul 직접 | Seoul 프로파일→Chicago |
|------|------|------|------|
| embed `cohere.embed-v4.0` | O (1536차원) | X 404 | X (프로파일 대상 아님) |
| rerank `cohere.rerank-v4.0-fast` | O | X 404 | X |
| chat `xai.grok-4.3`, `openai.gpt-oss-120b`, `google.gemini-2.5-flash` | O | X (Gemini는 Google 서울 위치로 가서 NOT_FOUND) | O |
| chat `google.gemini-2.5-pro` | X Google NOT_FOUND | X | X |
| chat `cohere.command-a-03-2025` (`api_format=COHERE`) | O | X 404 | **O** |
| 위 command-a를 OpenAI 호환으로 | X (Unsupported OpenAI operation) | X | X |

요점: 임베딩·리랭크는 라우팅 프로파일을 타지 않는다. Cohere Command는 네이티브 Cohere Chat 형식으로만, 단 프로파일 경유는 된다. Gemini 2.5 Pro는 OCI 카탈로그에 있어도 Google 측에서 NOT_FOUND다(2026-10-24 기준).

## 필요 IAM 정책 (최소)

앱 상단 "필요 정책 (최소)" 탭과 `../../docs/07-minimal-iam-policies.md`. `generative-ai-family` 대신 리소스 타입별 최소 동사만 쓴 정책 모음이며, 문서에 동사 매핑이 없는 항목은 "추정"으로 표시했다. 현재 테넌시는 family 정책으로 운영 중이라 최소 세트 자체는 미검증이다.

## 주의사항 / 삽질 포인트
- OCI CLI 구버전에는 `routing-profile`이 없다. 업그레이드 중에는 `oci` 심볼릭 링크가 잠시 사라진다.
- `oci generative-ai model list`가 아니라 `model-collection list-models`, 프로파일 목록은 `routing-profile-collection list-routing-profiles`.
- 키 리전 불일치(Chicago 키로 Seoul 엔드포인트 호출)는 인증 오류가 난다. 케이스별 키를 분리했다(`CASE_A_API_KEY`, `CASE_B_API_KEY`).
- Responses API에 `project` 파라미터는 필요 없었다(없이 성공).
- Seoul 리전 제약: 임베딩, 전용 클러스터, 가드레일, 벡터 스토어/File Search, MCP 툴 미지원 (`docs/02-regions-and-features.md`).
- 벡터 스토어 생성은 비동기다. `in_progress` 상태에서 파일을 연결하면 404 "Entity … not found" 가 난다. `completed` 확인 후 연결할 것.
- 프로파일 생성 직후 호출하면 `400 Routing profile …` 가 날 수 있다(약 1분). 재시도하면 된다.
- `oci-openai` 라이브러리는 openai SDK 3.x(httpx2)와 호환되지 않아 `TypeError: Invalid "auth"`가 난다. 이 예제는 `oci.signer.Signer` + `requests`로 서명한다.
- 생성 리소스는 과금 대상이 아니지만(온디맨드 토큰만 과금) 정리 시 삭제는 **사용자 확인 후** 진행한다.

## 생성된 리소스 (컴파트먼트 `wonyong.lee`)

| 종류 | 리전 | 이름 | OCID 끝 8자리 |
|------|------|------|---------------|
| Routing profile | ap-seoul-1 | seoul-grok43-to-chicago | n3pmvjsa |
| Routing profile | us-chicago-1 | chicago-grok43-multiregion | notswf3q |
| API key | ap-seoul-1 | seoul-grok43-demo (만료 2026-11-23) | 3vyts7q |
| API key | us-chicago-1 | chicago-grok43-demo (만료 2026-11-23) | pfxsqka |

Case C 추가분: 프로젝트 2개(Chicago `…****`, Seoul `…****`), 벡터 스토어 `vs_ord_****ebq2`, 파일 5개, 범위 프로브 프로파일 4개 — 전체 OCID는 `../../docs/06-scope-embeddings-vectorstores.md` §5 참조. 전체 OCID는 `../../logs/worklog.md`.

## 디렉터리
```
app/            FastAPI 서버 + 단일 페이지 UI (설명 + 두 케이스 데모 + 라우팅 분포 프로브)
scripts/        smoke_test.py (두 케이스 채팅 검증), vector_store_probe.py (Files/Vector store/file_search), sdk_native_probe.py (OCI SDK embed/rerank/chat 매트릭스)
.env            실제 값 (gitignore)
```
