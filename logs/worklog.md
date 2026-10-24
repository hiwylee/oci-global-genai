# 작업 이력 (append-only)

규칙: 시각(KST) / 목적 / 명령 / 결과 / 산출물 / 생성·변경·삭제된 리소스 OCID. 삭제는 사용자 승인 기록을 함께 남긴다.

## 2026-10-24 13:00 KST — 프로젝트 초기화
- 목적: CLAUDE.md, docs/, logs/ 구조 생성. Oracle 공식 문서 조사.
- 명령: 로컬 도구 점검(`oci --version`, `python3 --version`, `uv --version`), 문서 WebFetch
- 결과: OCI CLI 3.76.1에 `routing-profile` 명령 없음(최신 3.95.1). Seoul/Chuncheon은 "로컬 모델 처리 없는 30개 리전"에 포함 확인.
- 산출물: CLAUDE.md, docs/01~04, docs/references.md
- 리소스: 없음 (OCI 리소스 생성/변경 없음)
- 비고: 이전 세션에서 `SEOUL` 프로파일로 `iam region-subscription list` 1회 시도 → 401 NotAuthenticated. 이후 프로파일은 `YWDCLOUD`로 고정.
- 추가(사용자 지시): Chicago 리전 작업 시 `YWDCLOUD_CHICAGO` 프로파일 사용. CLAUDE.md 규칙 1, docs/03-setup.md에 반영. scripts/ 에 튜토리얼 기반 스크립트 2개 생성.

## 2026-10-24 13:15~13:30 KST — Seoul→Chicago xai.grok-4.3 예제 구성 및 실측 (/goal)
- 목적: Seoul 엔드포인트 호출, Chicago 실행, OpenAI 호환 API, 두 케이스(A 튜토리얼 / B Global availability) 데모·검증
- 프로파일: Seoul 작업 `YWDCLOUD`, Chicago 작업 `YWDCLOUD_CHICAGO`. 컴파트먼트 `wonyong.lee` (ocid1.compartment.oc1..****m7ga)
- 명령/결과:
  - `brew upgrade oci-cli` 3.76.1 → 3.95.1 (routing-profile 명령 확보)
  - `iam region-subscription list`: 15개 리전 구독, 홈 ap-seoul-1 → logs/raw/20261024-1317-region-subscriptions.txt
  - `model-collection list-models` Chicago 75개(xai.grok-4.3 ACTIVE), Seoul 3개(Gemini만), Ashburn/Phoenix에 grok-4.3 있음, Frankfurt/Osaka/London 없음 → logs/raw/20261024-1319-models-*.json, 20261024-1320-models-*.json
  - `iam policy list` 컴파트먼트 wonyong.lee: generativeaiapikey principal 정책 기존 존재 → 정책 생성 없음
  - **생성** routing-profile Seoul `seoul-grok43-to-chicago` = ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****vjsa (ACTIVE)
  - **생성** routing-profile Chicago `chicago-grok43-multiregion` = ocid1.generativeairoutingprofile.oc1.us-chicago-1.****wf3q (ACTIVE)
  - **생성** api-key Seoul `seoul-grok43-demo` = ocid1.generativeaiapikey.oc1.ap-seoul-1.****ts7q (만료 2026-11-23)
  - **생성** api-key Chicago `chicago-grok43-demo` = ocid1.generativeaiapikey.oc1.us-chicago-1.****sqka (만료 2026-11-23)
  - **변경** 두 api-key `renew` (평문 재발급; create에 --wait-for-state를 써서 평문이 null이었음) → logs/raw/20261024-1322-api-key-renew-*-secret.json (gitignore)
  - smoke_test.py 4/4 성공, 모두 서빙 us-chicago-1 → logs/raw/20261024-1324-smoke-test-initial.txt
  - 앱 E2E(/api/config, /api/chat×4, /api/probe×2) 성공 → logs/raw/20261024-1325-app-e2e.txt; UI 스크린샷 logs/raw/20261024-1327-*.png, 20261024-1328-*.png
- 산출물: examples/seoul-to-chicago-grok43/{README.md, app/, scripts/smoke_test.py, .env}, docs/05-results.md, docs/02·03 갱신, CLAUDE.md 갱신
- 삭제: 없음
- 검증(verifier, sonnet): 시크릿 스캔 0건, smoke_test 4/4 (logs/raw/20261024-1330-smoke-test-verify.txt), 앱 E2E PASS, 문서 정합성 PASS. 후속 조치: .env의 공통 OCI_GENAI_API_KEY 제거(케이스별 키만 사용), docs/03·CLAUDE.md에 케이스별 키 설명 추가.
- 비고: 검증 중 Seoul API 키 평문이 에이전트 세션 로그에 1회 노출됨(파일은 gitignore). 대화 기록 공유 시 `api-key renew`로 키 교체 권장.

## 2026-10-24 13:38~14:00 KST — 범위 실측: OpenAI 호환 모델, 임베딩, Vector stores/Applications (사용자 추가 요청)
- 목적: OpenAI 호환 모델 범위, 프로파일 호출 범위, Seoul 임베딩 가능 여부, Vector stores/Applications 리전 동작 확인 → docs/06
- 명령/결과 (원본 logs/raw/20261024-13[4-5]*, 14*):
  - OpenAI 호환 프로브(Chicago/Seoul): `/models` 404, `/embeddings` 미지원, `/vector_stores`(추론 엔드포인트) 404, Files는 프로젝트 헤더 필요
  - 네이티브 EmbedText: Chicago O(1536d), Seoul X 404, 프로파일 경유 X
  - **생성** 라우팅 프로파일 `probe-embed-v4-seoul`(ap-seoul-1, …pp7djq) → 호출 404, 무용
  - **생성** Project Chicago `grok43-demo-us-chicago-1`(…****), Seoul `grok43-demo-ap-seoul-1`(…****)
  - Vector store: Chicago 컨트롤 플레인 생성 O → **생성** `vs_ord_****ebq2`; Seoul 403 NotAllowed "GenerativeAiVectorStore is not supported"; Seoul Files 404
  - **생성** Files(Chicago) 3개: file-ord-0c55305d…, 0a3293a6…(미연결), da75852b…(벡터 스토어 연결, completed)
  - file_search: gpt-oss-120b O, xai.grok-4.3 O ("BLUE-TIGER-42"), 프로파일 OCID X(400)
  - 모델 매트릭스(Chicago 직접): Grok 4.x/gpt-oss/gemini-flash 양 API O, llama Chat만, cohere X, gemini-pro X
  - **생성** 범위 프로브 프로파일 3개(ap-seoul-1): gpt-oss-120b(…nyr4va), gemini-2.5-flash(…r25qdq), llama-3.3-70b(…jnxbdq) → 생성 직후 1분 400, 이후 grok/gpt-oss/llama 양 API O, gemini Chat만
  - hosted-application list: Seoul 0건(정상 응답), Chicago 1건(AgentFromScratchUI, 기존)
- 산출물: docs/06-scope-embeddings-vectorstores.md, scripts/vector_store_probe.py, CLAUDE.md 갱신. 앱 Case C 확장은 executor 진행 중.
- 삭제: 없음 (삭제 후보는 docs/06 §5)
- 14:50~14:59 앱 Case C 확장(executor) 후 실제 E2E: Seoul vs/create·list 403, Chicago list/get/upload(**생성** file-ord-26da22fc…)/attach/search/ask 성공. ask가 "정보 없음"을 내는 문제 → `tool_choice=file_search` + 지시문 강제로 수정 후 정답. UI(브라우저) Chicago 흐름·Seoul 오류 패널 확인, 스크린샷 logs/raw/20261024-1358-*, 1359-*. 원본 logs/raw/20261024-1353-app-e2e-caseC.txt
- 추가 패키지: app venv에 oci, requests, python-multipart, oci-genai-auth, oci-openai(미사용; openai 3.x와 비호환 확인)
- 삭제: 없음
- 검증(verifier 2차, sonnet): 시크릿 0건, Chicago 프로브 16/17(프로파일+툴 400은 기대값), Seoul 프로브 403/404 확인, 앱 config/create/ask PASS, 문서 정합성 PASS. 검증 중 **생성** 파일 file-ord-4fdbc03f…(벡터 스토어 연결). 지적 반영: 파일 개수 5개로 정정, 벡터 스토어 ID·프로젝트 OCID 전체값 docs/05·README에 명시.
- 프로젝트 OCID 전체값: Chicago ocid1.generativeaiproject.oc1.us-chicago-1.****fybq / Seoul ocid1.generativeaiproject.oc1.ap-seoul-1.****mmgq

## 2026-10-24 14:20~14:35 KST — OCI SDK 네이티브(embed/rerank/chat) 실측, 최소 IAM 정책 정리 (사용자 추가 요청)
- **생성** 라우팅 프로파일(ap-seoul-1, 범위 프로브): gemini-2.5-pro(…****), command-a-03-2025(…****), rerank-v4.0-fast(…****, 무용) → logs/raw/20261024-1426-profile-scope-*.json
- SDK 프로브 Chicago/Seoul → logs/raw/20261024-142*-sdk-native-probe-*.txt: embed/rerank Chicago O·Seoul X·프로파일 X, command-a는 Cohere Chat으로만(프로파일 경유 O), Gemini 2.5 Pro/Flash-Lite는 Google NOT_FOUND(Chicago us-central1, Seoul asia-northeast3), Seoul Gemini 직접 호출은 Google 서울 위치로 감
- 최소 정책: document-specialist 조사 → docs/07-minimal-iam-policies.md, app/policies.json (앱 탭용)
- 삭제: 없음
- 14:34~14:38 앱 Case D(SDK embed/rerank/chat) + 정책 탭 E2E: Chicago 매트릭스 6/6 OK, Seoul 직접 전부 실패·프로파일 경유 chat 4/4 OK, Gemini 직접은 Google asia-northeast3 NOT_FOUND. 정책 탭 렌더링 확인. 원본 logs/raw/20261024-1434-app-e2e-caseD.txt, 스크린샷 1435/1436/1437. .env에 CASE_B_PROFILES_JSON 추가. 삭제: 없음
- 검증(verifier 3차, sonnet): 시크릿 0건, SDK 프로브 Chicago/Seoul 기대값 일치, 앱 policies/sdk 엔드포인트 PASS, 문서 정합성 PASS. 지적 반영: docs/06 임베딩 프로파일 표기 통일, gpt-oss 빈 응답 주석 추가. 원본 logs/raw/20261024-1436-sdk-native-probe-verify.txt
- 로그: 14:48 데모 서버 기동(사용자 열람용), 포트 8765
- 15:06 git init + 공개 저장소 push: https://github.com/hiwylee/oci-global-genai (commit 12716e8). .gitignore로 .env, logs/raw/ 제외
- 15:07 OCID/리소스 ID 마스킹 후 이력 재작성(orphan 1커밋) force push: ddb3bb1. 실제 ID 매핑은 logs/raw/ocid-map-secret.json(gitignore)
