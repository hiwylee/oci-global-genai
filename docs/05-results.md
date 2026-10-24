# 05. 테스트 결과 (2026-10-24)

예제: `examples/seoul-to-chicago-grok43/`. 원본 출력: `logs/raw/20261024-1324-smoke-test-initial.txt`, `logs/raw/20261024-1325-app-e2e.txt`, 스크린샷 `logs/raw/20261024-1327-ui-caseB-chat.png`, `logs/raw/20261024-1328-ui-caseB-probe.png`.

## 구성

| 항목 | Case A (튜토리얼 패턴) | Case B (Global availability) |
|------|------------------------|------------------------------|
| 엔드포인트 | `us-chicago-1` | `ap-seoul-1` |
| 라우팅 프로파일 | `chicago-grok43-multiregion` (타깃 Chicago/Ashburn/Phoenix) | `seoul-grok43-to-chicago` (타깃 Chicago) |
| 모델 | `xai.grok-4.3` | `xai.grok-4.3` |
| API 키 | Chicago에서 생성 | Seoul에서 생성 |
| 컴파트먼트 | `wonyong.lee` | `wonyong.lee` |

## 결과 요약

| 테스트 | Case A | Case B |
|--------|--------|--------|
| Chat Completions 스트리밍 (SDK 직접) | 성공, 서빙 `us-chicago-1` | 성공, 서빙 `us-chicago-1` |
| Responses API 스트리밍 (SDK 직접) | 성공, 서빙 `us-chicago-1` | 성공, 서빙 `us-chicago-1` |
| 앱 `/api/chat` SSE (두 API) | 성공 | 성공 |
| 앱 `/api/probe` n=6 (비스트리밍) | 6/6 `us-chicago-1` | 6/6 `us-chicago-1` |
| UI 채팅 + 프로브 n=5 (브라우저) | 미실행 | 성공, 5/5 `us-chicago-1` |

지연(1회 측정, 참고용):

| 측정 | Case A | Case B |
|------|--------|--------|
| 첫 토큰(스트리밍, Chat) | 4.8~6.2 s | 4.7~6.5 s |
| 첫 토큰(스트리밍, Responses) | 4.6~8.5 s | 5.3~10.6 s |
| 프로브 16토큰 비스트리밍 | 1.6~2.4 s | 1.5~2.3 s |

Seoul 경유 추가 지연은 측정 범위에서 유의미하게 드러나지 않았다. 변동 폭이 모델 측 지연에 지배된다.

## 확인된 사실

- Seoul 로컬 모델 목록(`model-collection list-models --region ap-seoul-1`)에는 Gemini 2.5 3종만 있고 Grok은 없다. Grok 사용은 라우팅 프로파일로만 가능하다.
- `xai.grok-4.3` 온디맨드 제공 리전: Ashburn, Chicago, Phoenix. Frankfurt/Osaka/London에는 없어 Seoul에서 가장 가까운 타깃은 Chicago(미국)다.
- 라우팅 정책 JSON: `{"allowedModels":["xai.grok-4.3"]}`, `{"allowedRegions":["us-chicago-1"]}`. 응답에서는 `allowed-models`, `allowed-regions`.
- 프로파일 OCID 형식: `ocid1.generativeairoutingprofile.oc1.<region>.…`. API 키 OCID: `ocid1.generativeaiapikey.oc1.<region>.…`.
- 응답 헤더 `x-genai-selected-region`은 두 API 모두에서 반환되었다. `opc-request-id`도 함께 반환.
- Responses API는 `project` 파라미터 없이 동작했다.
- Case A 타깃 3개 중 12회 관찰 모두 Chicago. 라운드로빈이 아니며 우선순위 정책은 비공개(문서와 일치). 다른 리전으로 분산되는 조건은 미확인.
- API 키 평문은 `create` 즉시 응답에서만 노출. `--wait-for-state` 사용 시 null. `renew`로 재발급 가능.
- 기존 컴파트먼트 정책 `allow any-user to use generative-ai-family ... where request.principal.type='generativeaiapikey'`만으로 라우팅 프로파일 read + 추론이 모두 허용되었다(별도 정책 추가 없음).

## 미확인 / 후속

- [ ] Case A에서 Ashburn/Phoenix로 라우팅되는 조건(부하, 장애 시) 관찰
- [ ] Seoul에서 임베딩 요청 거부 에러 코드 확인
- [ ] IAM 서명 인증(`oci-genai-auth`)으로 동일 호출
- [ ] 네이티브 Chat API(OCI Python SDK)에서 프로파일 OCID 지정 방식
- [ ] Playground에서 프로파일 선택 화면 확인(스크린샷)

## 생성 리소스 (삭제 시 사용자 확인 필수)

| 종류 | 리전 | 이름 | OCID |
|------|------|------|------|
| Routing profile | ap-seoul-1 | seoul-grok43-to-chicago | `ocid1.generativeairoutingprofile.oc1.ap-seoul-1.****vjsa` |
| Routing profile | us-chicago-1 | chicago-grok43-multiregion | `ocid1.generativeairoutingprofile.oc1.us-chicago-1.****wf3q` |
| API key | ap-seoul-1 | seoul-grok43-demo (만료 2026-11-23) | `ocid1.generativeaiapikey.oc1.ap-seoul-1.****ts7q` |
| API key | us-chicago-1 | chicago-grok43-demo (만료 2026-11-23) | `ocid1.generativeaiapikey.oc1.us-chicago-1.****sqka` |

## 추가 (2026-10-24 14:00) — Case C 벡터 스토어 / File Search, 범위 실측

상세 표는 `docs/06-scope-embeddings-vectorstores.md`. 앱 E2E 원본: `logs/raw/20261024-1353-app-e2e-caseC.txt`, UI 스크린샷 `logs/raw/20261024-1358-ui-caseC-chicago.png`, `20261024-1359-ui-caseC-seoul-errors.png`.

| 테스트 | Chicago (`us-chicago-1`) | Seoul (`ap-seoul-1`) |
|--------|---------|-------|
| 벡터 스토어 생성/목록 (컨트롤 플레인, IAM 서명) | 성공 (`vs_ord_****ebq2`, 약 1분 후 completed) | 403 `NotAllowed: GenerativeAiVectorStore is not supported` |
| 파일 업로드 (`/openai/v1/files`, API 키 + 프로젝트) | 성공 (`file-ord-…`) | 404 Authorization failed or requested resource not found |
| 파일 연결 → completed | 성공 (약 35초) | - |
| 벡터 스토어 검색 | 성공 (score 0.88) | - |
| Responses + file_search, `xai.grok-4.3` 직접 | 성공 "부산 신항 7번 게이트 / BLUE-TIGER-42" | 400 Entity with key xai.grok-4.3 not found |
| Responses + file_search, 라우팅 프로파일 OCID | 400 Entity … not found | - |
| UI (브라우저) 생성·목록·검색·질문 | 성공 | 오류 패널에 403 표시 확인 |

관찰:
- 질문에 따라 모델이 file_search 호출을 생략하고 "정보 없음"으로 답하는 경우가 있었다(두 가지를 묻는 질문). 앱은 `tool_choice={"type":"file_search"}` + 검색 근거 지시문을 강제해 해결했다.
- gpt-oss-120b 응답은 하이픈을 U+2011(non-breaking hyphen)으로 출력해 "BLUE‑TIGER‑42" 리터럴 비교가 실패할 수 있다. grok-4.3은 ASCII 하이픈.
- 모델명을 직접 지정한 호출에는 `x-genai-selected-region` 헤더가 없다(라우팅 프로파일 호출에만 존재). UI는 "헤더 없음"으로 표시.
- 프로파일 생성 직후 약 1분간 400 오류(전파 지연) 후 정상.
- OpenAI 호환 임베딩·`/models`는 모든 리전에서 미지원. Seoul 임베딩은 네이티브 API로도 불가.

## 추가 생성 리소스 (삭제 시 사용자 확인 필수)
`docs/06-scope-embeddings-vectorstores.md` §5 참조: 프로젝트 2개(`ocid1.generativeaiproject.oc1.us-chicago-1.****fybq`, `ocid1.generativeaiproject.oc1.ap-seoul-1.****mmgq`), 벡터 스토어 1개(`vs_ord_****ebq2`), 파일 5개(연결 3 + 미연결 2, 검증 재실행분 1개 포함), 범위 프로브 라우팅 프로파일 4개(그중 `probe-embed-v4-seoul`은 동작하지 않음).

## 추가 (2026-10-24 14:35) — Case D OCI SDK 네이티브, 정책 탭

앱 E2E 원본: `logs/raw/20261024-1434-app-e2e-caseD.txt`. UI 스크린샷: `logs/raw/20261024-1435-ui-policies-tab.png`, `20261024-1436-ui-caseD-matrix-chicago.png`, `20261024-1437-ui-caseD-matrix-seoul.png`. SDK 스크립트 원본: `logs/raw/20261024-142*-sdk-native-probe-*.txt`.

| SDK 호출 (사용자 principal) | Chicago 직접 | Seoul 직접 | Seoul 프로파일→Chicago |
|---|---|---|---|
| embed cohere.embed-v4.0 | 성공 1536d (0.8~1.6s) | 404 | 404 (프로파일 대상 아님) |
| rerank cohere.rerank-v4.0-fast | 성공 (0.8s) | 404 | 404 |
| chat xai.grok-4.3 / gpt-oss-120b / gemini-2.5-flash | 성공 | 404 / 404 / Google NOT_FOUND(asia-northeast3) | 성공 |
| chat cohere.command-a-03-2025 (COHERE 형식) | 성공 "OK!" | 404 | 성공 "OK!" |
| chat google.gemini-2.5-pro | Google NOT_FOUND(us-central1) | Google NOT_FOUND | Google NOT_FOUND |
| command-a OpenAI 호환 (Chat Completions/Responses) | 400 Unsupported / 404 | - | 400 / 400 |

- 정책 탭: `/api/policies`가 5개 그룹 22개 항목과 최소 세트 19줄을 반환하고 UI가 복사 버튼과 함께 렌더링됨을 확인.
- gemini-2.5-flash를 프로파일로 `max_tokens=16` 호출 시 본문이 비어 있었다(사고 토큰 소모 추정). 매트릭스(기본 max_tokens)는 정상.
