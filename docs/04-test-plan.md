# 04. 테스트 계획

목표: Seoul 리전에서 라우팅 프로파일 기반 OCI GenAI 구성의 **개념 검증 → 기본 기능 → 지원 범위 경계** 순으로 확인한다.
각 테스트는 실행 시 `logs/worklog.md`에 결과를 기록하고 원본 출력을 `logs/raw/`에 남긴다.

## Phase 0. 환경 준비
- [ ] OCI CLI 3.95.1+ 업그레이드, `routing-profile` 명령 확인
- [ ] `YWDCLOUD` 프로파일로 `ap-seoul-1` 구독 확인
- [ ] 테스트 컴파트먼트 선정, IAM 정책 확인(필요 시 정책 문구 기록)
- [ ] GenAI API 키 생성(만료일 기록), `.env` 작성

## Phase 1. 개념 검증 (Console)
- [ ] Seoul Console에 Routing profiles 메뉴 존재 확인(스크린샷 경로 기록)
- [ ] Model select에 표시되는 온디맨드 모델 전체 목록 기록 → `docs/02-regions-and-features.md`에 반영
- [ ] 모델별 선택 가능 타깃 리전 기록(Osaka 포함 여부)
- [ ] 프로파일 1개 생성(`openai.gpt-oss-120b` 또는 Seoul에서 선택 가능한 모델), Active 확인
- [ ] Seoul Playground에서 프로파일 선택 후 채팅 1회 성공

## Phase 2. 기본 기능 (API)
- [ ] CLI: `routing-profile list/get` 성공, 응답 JSON 필드 구조 기록
- [ ] Chat Completions(OpenAI SDK, API 키): 스트리밍 응답 + `x-genai-selected-region` 출력
- [ ] Responses API: 동일 프로파일로 성공 여부(모델이 Responses 지원 시)
- [ ] 반복 호출 20회: 서빙 리전 분포 기록(라운드로빈 아님을 확인)
- [ ] 단일 타깃 리전 프로파일(Osaka만) vs 다중 타깃 프로파일 지연 시간 비교(간단 평균)
- [ ] IAM 서명 인증(`oci-genai-auth`)으로 동일 호출 성공
- [ ] 네이티브 Chat API(OCI Python SDK)에서 프로파일 OCID 지정 방식 확인 및 성공

## Phase 3. 지원 범위 경계
- [ ] 임베딩 요청 → 거부되는지(에러 코드/메시지 기록)
- [ ] 타깃 리전에 없는 모델로 프로파일 생성 시도 → 실패 메시지 기록
- [ ] 다른 realm 리전 선택 가능 여부(Console UI에서 노출되는지)
- [ ] 전용 AI 클러스터 메뉴가 Seoul에서 비활성인지
- [ ] Responses API에서 File search 등 미지원 툴 호출 시 에러 기록
- [ ] API 키 만료/권한 누락 시 오류 메시지(트러블슈팅 표 검증)

## Phase 4. 정리
- [ ] 생성한 리소스 목록(OCID) 정리 → 사용자 승인 후 삭제
- [ ] 결과 요약을 `docs/05-results.md`로 작성(관찰된 모델 목록, 리전 분포, 지연, 제약 사항)

## 결과 기록 양식 (worklog)

```
## 2026-10-24 14:05 KST — Phase 2 / Chat Completions 스트리밍
- 목적: Seoul 엔드포인트 + 프로파일 OCID로 응답 수신, 서빙 리전 확인
- 명령: python scripts/routing-chat-completion.py (OCI_REGION=ap-seoul-1)
- 결과: 성공. x-genai-selected-region=ap-osaka-1
- 산출물: logs/raw/20261024-1405-chat-completion.txt
- 리소스: (생성/변경 없음)
```
