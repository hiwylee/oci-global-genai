# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목적

OCI Seoul 리전(`ap-seoul-1`)에서 OCI Generative AI의 **Global Generative AI availability**(2026-10-20 릴리스)와
**Route Model Requests Across OCI Regions** 튜토리얼(2026-10-14)을 활용해 GenAI 서비스를 구성하고,
개념·지원 범위·기본 기능을 검증하는 테스트 프로젝트다.

핵심 사실 (상세는 `docs/`):
- Seoul(`ap-seoul-1`)과 Chuncheon(`ap-chuncheon-1`)은 **로컬 모델 처리가 없는 30개 OC1 리전**에 포함된다.
  온디맨드 추론은 반드시 **라우팅 프로파일(routing profile)** 을 통해 타 리전(Chicago, Frankfurt, Osaka 등) 모델로 라우팅된다.
- 라우팅 프로파일 = 온디맨드 모델 1개 + 동일 realm 내 타깃 리전 1개 이상. 요청은 Seoul 엔드포인트로 보내고 `model`에 프로파일 OCID를 넣는다.
- 지원 API: Chat API(OCI SDK), OCI Chat Completions API, OCI Responses API (모델이 해당 API를 지원할 때만).
- Seoul에서 **미지원**(문서+실측): 전용 AI 클러스터, 모델 임포트, Embedding API(네이티브·OpenAI 호환·프로파일 경유 모두 불가), 가드레일, 롱텀 메모리,
  벡터 스토어/Files/File Search(컨트롤 플레인 403 `GenerativeAiVectorStore is not supported`), MCP 툴. Projects·Applications(hosted deployments)는 Seoul에서 생성 가능.
- 라우팅 프로파일 OCID는 `tools`(file_search 등)와 함께 쓸 수 없다. RAG는 Chicago 엔드포인트 + 모델명 직접 지정으로 구성한다.
- 응답 헤더 `x-genai-selected-region`으로 실제 서빙 리전을 확인한다. 엔드포인트 리전으로 추정하지 말 것.

## 운영 규칙 (필수)

1. **OCI CLI/SDK 프로파일은 리전별로 고정한다.** 그 외 프로파일로는 명령을 실행하지 않는다.
   - Seoul(`ap-seoul-1`) 작업: `YWDCLOUD` (`--profile YWDCLOUD`, `OCI_CLI_PROFILE=YWDCLOUD`). 기본값.
   - Chicago(`us-chicago-1`) 작업이 필요할 때: `YWDCLOUD_CHICAGO` (`~/.oci/config`에 region=us-chicago-1로 등록됨).
   리전은 항상 `--region`으로 명시한다. 두 프로파일은 같은 테넌시의 리전 뷰만 다르다.
2. **모든 작업은 추적 가능하게 기록한다.** OCI 리소스를 조회·생성·변경·삭제하거나 테스트를 실행하면
   `logs/worklog.md`에 시각(KST)·목적·실행 명령·결과 요약·생성된 리소스 OCID를 append 한다.
   원본 CLI/API 출력은 `logs/raw/YYYYMMDD-HHMM-<작업명>.json|txt`로 저장한다. 기록 없이 작업을 끝내지 않는다.
3. **리소스 삭제는 반드시 사용자 확인 후 실행한다.** `delete`, `terminate`, 컴파트먼트 이동, API 키 폐기 등
   되돌리기 어려운 작업은 대상 OCID와 영향 범위를 먼저 보여주고 AskUserQuestion으로 승인을 받는다. 승인은 1건씩만 유효하다.
4. **시크릿 금지.** GenAI API 키, OCID가 포함된 `.env`는 커밋하지 않는다. 코드에는 환경변수만 사용한다
   (튜토리얼 스크립트: `OCI_GENAI_API_KEY`, `OCI_ROUTING_PROFILE_OCID`, `OCI_REGION`; 예제 앱: `CASE_A_API_KEY`, `CASE_B_API_KEY` 등 케이스별).
   API 키는 리전 리소스이므로 호출 엔드포인트 리전마다 따로 만든다.
5. **문서 분리 원칙.** 이 파일(CLAUDE.md)에는 기능별 **한두 줄 요약과 링크만** 둔다.
   개념 설명, 지원 범위 표, 명령어 상세, 테스트 절차, 조사 결과는 모두 `docs/` 아래 별도 md 파일에 작성한다.
   새 기능을 조사하거나 테스트하면 `docs/`에 파일을 추가/갱신하고 아래 문서 맵에 한 줄을 추가한다.

## 문서 맵 (`docs/`)

| 파일 | 내용 |
|------|------|
| `docs/00-step-by-step.md` | 처음부터 따라 하기: 10단계, 단계별 사전 준비·명령·예시·확인 |
| `docs/01-concepts.md` | 라우팅 프로파일 개념, 동작 방식, 제약, 지원 API, 서빙 리전 헤더 |
| `docs/02-regions-and-features.md` | Global availability 30개 리전 목록, Seoul 지원/미지원 기능표, 데이터 레지던시 |
| `docs/03-setup.md` | 사전 준비: CLI 업그레이드, IAM 정책, API 키 생성, 라우팅 프로파일 생성(Console/CLI), Python 환경 |
| `docs/04-test-plan.md` | 테스트 시나리오와 체크리스트(개념 검증, 기본 기능, 경계 조건) |
| `docs/05-results.md` | 2026-10-24 실측 결과: 두 케이스 성공, 서빙 리전 분포, 지연, 생성 리소스 OCID |
| `docs/06-scope-embeddings-vectorstores.md` | 실측 범위: OpenAI 호환 모델표, 프로파일 호출 범위, Seoul 임베딩 불가, Vector stores/Files/Applications 리전 동작 |
| `docs/07-minimal-iam-policies.md` | family 없이 기능별 최소 IAM 정책 (실측 ✔ / 추정 구분) |
| `docs/references.md` | 참조한 Oracle 공식 문서 URL 목록 |
| `examples/seoul-to-chicago-grok43/README.md` | Seoul→Chicago `xai.grok-4.3` 예제: 재현 절차, 주의사항, 두 케이스 비교 |
| `logs/worklog.md` | 작업 이력 (append-only) |

## 환경 및 자주 쓰는 명령

로컬 상태(2026-10-24 기준): OCI CLI **3.95.1**로 업그레이드 완료(`routing-profile` 명령 있음). Python 3.13, `uv`, `openai` 2.31.0 설치됨. `oci` Python SDK는 미설치.
컴파트먼트: 테스트 리소스는 `wonyong.lee`(OCID 끝 `****`)에 만든다. 이 컴파트먼트에 API 키 principal용 GenAI 정책이 이미 있다.

```bash
# 프로파일/리전 고정
export OCI_CLI_PROFILE=YWDCLOUD
export OCI_REGION=ap-seoul-1

# 조회 명령은 *-collection 하위에 있다 (상세: docs/03-setup.md)
oci generative-ai routing-profile-collection list-routing-profiles --compartment-id "$COMPARTMENT_OCID" --region ap-seoul-1
oci generative-ai model-collection list-models --compartment-id "$TENANCY_OCID" --region us-chicago-1 --all
oci generative-ai api-key-collection list-api-keys --compartment-id "$COMPARTMENT_OCID" --region ap-seoul-1
# 생성: routing-profile create --model-routing-policy '{"allowedModels":[..]}' --region-routing-policy '{"allowedRegions":[..]}'
# API 키 평문은 create 즉시 응답에만 나온다(--wait-for-state 쓰면 null). 놓치면 api-key renew.

# 예제 앱 실행/검증 (examples/seoul-to-chicago-grok43)
cd examples/seoul-to-chicago-grok43 && python3 scripts/smoke_test.py      # SDK 직접 호출, 두 케이스 × 두 API
app/.venv/bin/python scripts/vector_store_probe.py --case A              # Files/Vector store/file_search (Chicago O, --case B 로 Seoul 오류 확인)
app/.venv/bin/python scripts/sdk_native_probe.py --region both            # OCI SDK embed/rerank/chat 직접 vs 프로파일 매트릭스
cd app && ./run.sh                                                         # http://127.0.0.1:8765 데모 UI
python scripts/routing-chat-completion.py     # (루트) 튜토리얼 원형 스크립트
```

엔드포인트 형식: `https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1` (Seoul이면 `ap-seoul-1`).

## 구조

```
CLAUDE.md          운영 규칙 + 요약 + 문서 맵 (상세 내용 금지)
docs/              개념·범위·절차·테스트 계획·결과 (조사/검증 결과의 단일 출처)
scripts/           튜토리얼 원형 스크립트 (Python, openai SDK)
examples/<name>/   재현 가능한 예제. README(절차) + app/(FastAPI+UI) + scripts/(smoke test) + .env(gitignore)
logs/worklog.md    작업 이력, logs/raw/ 원본 출력 (*secret* 파일은 gitignore)
```

예제 규칙: 새 시나리오는 `examples/<리전-목적-모델>/` 로 만들고 README에 재현 절차·주의사항·생성 리소스 표를 둔다.
두 케이스 구분: **Case A** = 튜토리얼(로컬 처리 있는 리전에서 다중 타깃), **Case B** = Global availability(로컬 처리 없는 Seoul에서 라우팅). 같은 라우팅 프로파일 기능이지만 용도가 다르므로 문서·데모에서 항상 구분한다.
