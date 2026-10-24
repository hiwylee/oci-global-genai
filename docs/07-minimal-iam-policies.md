# 07. 기능별 최소 IAM 정책 (family 미사용)

출처: Oracle 공식 IAM 권한 페이지(2026-10-24 조회, `references.md` 참조). 동사 계층 `manage ⊇ use ⊇ read ⊇ inspect`.
`generative-ai-family`는 아래 21개 리소스 타입을 모두 포함하므로, 최소 권한은 **필요한 타입에 필요한 동사만** 준다.
`<group>`은 사용자 그룹, `<compartment>`는 리소스가 있는 컴파트먼트. 실측으로 확인된 항목은 ✔ 표시, 문서에 명시되지 않아 추정인 항목은 "추정".

## A. 모델 호출 (사용자/그룹 principal)

| 기능 | 리소스 타입 | 최소 동사 | 정책 | 비고 |
|------|-------------|-----------|------|------|
| Chat (네이티브 Chat API, OpenAI 호환 Chat Completions/Responses) | `generative-ai-chat` | `use` | `allow group <group> to use generative-ai-chat in compartment <compartment>` | 권한명 `GENERATIVE_AI_CHAT` |
| 임베딩 (EmbedText) | `generative-ai-text-embedding` | `use` | `allow group <group> to use generative-ai-text-embedding in compartment <compartment>` | `GENERATIVE_AI_TEXT_EMBED`. Seoul 불가(리전 제약) |
| 리랭크 (RerankText) | `generative-ai-text-rerank` | `use` (추정) | `allow group <group> to use generative-ai-text-rerank in compartment <compartment>` | 권한 페이지 없음. 타입명은 iam-policies 명시 |
| 모델 목록 (Console/CLI `ListModels`) | `generative-ai-model` | `inspect` | `allow group <group> to inspect generative-ai-model in tenancy` | `target.model.id` 조건이 ListModels엔 적용 안 됨 |
| 라우팅 프로파일로 호출 | `generative-ai-routing-profile` + 위 chat | `read` + `use` | `allow group <group> to read generative-ai-routing-profile in compartment <compartment>` | 프로파일 OCID를 model로 쓰면 READ 추가 필요 ✔ |
| 모델 제한 | 조건 | - | `... to use generative-ai-chat in compartment <compartment> where ANY {target.model.id='xai.grok-4.3', target.model.id='openai.gpt-oss-120b'}` | chat/embedding/rerank에만 적용. 패턴 `/google.gemini-.*/` 가능 |

## B. OpenAI 호환 API 키 (`generativeaiapikey` principal)

| 기능 | 정책 |
|------|------|
| 키 관리 (생성/갱신/삭제) | `allow group <group> to manage generative-ai-apikey in compartment <compartment>` |
| 키로 채팅만 허용 (모델 제한) | `allow any-user to use generative-ai-chat in compartment <compartment> where ALL {request.principal.type='generativeaiapikey', target.model.id in ('xai.grok-4.3')}` |
| 키로 라우팅 프로파일 사용 | `allow any-user to read generative-ai-routing-profile in compartment <compartment> where ALL {request.principal.type='generativeaiapikey'}` |
| 특정 키 1개만 | `... where ALL {request.principal.type='generativeaiapikey', request.principal.id='<api-key-OCID>'}` |
| 키로 Files/Vector store/Responses(file_search) | 문서 미명시. 실측 ✔: 이 테넌시는 `use generative-ai-family where principal=generativeaiapikey` 로 Files 업로드·벡터 스토어 파일 연결·검색·Responses가 모두 동작. 최소화하려면 `generative-ai-chat`, `generative-ai-file`, `generative-ai-vectorstore-file`, `generative-ai-project`(read) 를 같은 조건으로 각각 부여(추정) |

주의: 키 principal 정책은 `any-user` + `request.principal.type` 조건이 핵심이다. 키 자체의 리전과 엔드포인트 리전이 같아야 한다 ✔.

## C. Enterprise AI Agents (Projects / Files / Vector stores / Containers)

| 기능 | 리소스 타입 | 최소 동사 | 정책 |
|------|-------------|-----------|------|
| 프로젝트 생성 | `generative-ai-project` | `manage` | `allow group <group> to manage generative-ai-project in compartment <compartment>` |
| 프로젝트 사용(헤더만) | `generative-ai-project` | `read` (추정) | `allow group <group> to read generative-ai-project in compartment <compartment>` |
| 파일 업로드/삭제 | `generative-ai-file` | `manage` (동사 매핑 미명시) | `allow group <group> to manage generative-ai-file in compartment <compartment>` |
| 벡터 스토어 생성/목록 (컨트롤 플레인, IAM 서명 필수 ✔) | `generative-ai-vector-store` | `manage` | `allow group <group> to manage generative-ai-vector-store in compartment <compartment>` |
| 벡터 스토어에 파일 연결/검색 | `generative-ai-vectorstore-file` | `manage` | `allow group <group> to manage generative-ai-vectorstore-file in compartment <compartment>` |
| Object Storage 커넥터 | `generative-ai-vectorstore-connector` + 동적 그룹 | - | DG 규칙 `all {resource.type='generativeaivectorconnector'}` / `allow dynamic-group <dg> to read object-family in compartment <compartment>` |
| Code Interpreter 컨테이너 | `generative-ai-container` | `manage` | `allow group <group> to manage generative-ai-container in compartment <compartment>` |
| Sandboxes | `generative-ai-sandbox` | `manage` | `allow group <group> to manage generative-ai-sandbox in compartment <compartment>` |

Seoul 제약 ✔: vector-store/file 타입은 정책이 있어도 Seoul 컨트롤 플레인이 403 `GenerativeAiVectorStore is not supported` 를 반환한다. 정책 문제가 아니라 리전 기능 제한이다.

## D. Applications (Hosted applications / deployments)

```
allow group <group> to manage generative-ai-hosted-application in compartment <compartment>
allow group <group> to manage generative-ai-hosted-application-iam in compartment <compartment>   # IAM 인증 앱일 때
allow group <group> to manage generative-ai-hosted-deployment in compartment <compartment>
# 조회만: use 대신 read
```
런타임이 OCIR 이미지를 받기 위한 동적 그룹:
```
# 동적 그룹 규칙
any {resource.type='generativeaihostedapplication', resource.type='generativeaihostedapplicationiam', resource.type='generativeaihosteddeployment'}
# 정책
allow dynamic-group <dg> to read repos in compartment <compartment>
allow dynamic-group <dg> to read vss-family in compartment <compartment>     # 이미지 취약점 스캔 결과 확인
allow dynamic-group <dg> to use generative-ai-chat in compartment <compartment>   # 앱이 모델을 호출할 때 (추정)
allow dynamic-group <dg> to read generative-ai-routing-profile in compartment <compartment>  # 프로파일 사용 시
```
문서 불일치: deploy-permissions 페이지는 `generativeaihosteddeployment`(하이픈 없음) 표기를 쓴다. 적용 전 어느 표기가 통하는지 확인.

## E. 관리 작업

| 기능 | 정책 |
|------|------|
| 라우팅 프로파일 생성/삭제 | `allow group <group> to manage generative-ai-routing-profile in compartment <compartment>` |
| 작업 요청 조회 (프로젝트 생성 등 비동기 작업) | `allow group <group> to read generative-ai-work-request in compartment <compartment>` |

## F. 이 프로젝트 예제에 필요한 최소 세트 (실측 기준, family 없이)

```
# 사용자 그룹 (CLI/SDK, 프로파일 YWDCLOUD / YWDCLOUD_CHICAGO)
allow group <group> to inspect generative-ai-model in tenancy
allow group <group> to use generative-ai-chat in compartment <c>
allow group <group> to use generative-ai-text-embedding in compartment <c>
allow group <group> to use generative-ai-text-rerank in compartment <c>
allow group <group> to manage generative-ai-routing-profile in compartment <c>
allow group <group> to manage generative-ai-apikey in compartment <c>
allow group <group> to manage generative-ai-project in compartment <c>
allow group <group> to manage generative-ai-vector-store in compartment <c>
allow group <group> to manage generative-ai-vectorstore-file in compartment <c>
allow group <group> to manage generative-ai-file in compartment <c>
allow group <group> to read generative-ai-work-request in compartment <c>

# API 키 principal (앱의 OpenAI 호환 호출)
allow any-user to use generative-ai-chat in compartment <c> where ALL {request.principal.type='generativeaiapikey'}
allow any-user to read generative-ai-routing-profile in compartment <c> where ALL {request.principal.type='generativeaiapikey'}
allow any-user to read generative-ai-project in compartment <c> where ALL {request.principal.type='generativeaiapikey'}
allow any-user to manage generative-ai-file in compartment <c> where ALL {request.principal.type='generativeaiapikey'}
allow any-user to manage generative-ai-vectorstore-file in compartment <c> where ALL {request.principal.type='generativeaiapikey'}
```
현재 테넌시(`wonyong.lee` 컴파트먼트)는 `manage generative-ai-family`(사용자)와 `use generative-ai-family`(키 principal)로 운영 중이라 위 최소 세트는 **미적용·미검증**이다. 적용 시 테스트 컴파트먼트에서 한 줄씩 검증할 것.
