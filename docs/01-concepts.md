# 01. 개념: 라우팅 프로파일과 리전 간 모델 요청 라우팅

출처: Oracle 공식 문서 (2026-10-24 조회). URL은 `references.md`.

## 라우팅 프로파일(Routing Profile)이란

- OCI Generative AI가 **온디맨드 모델 요청을 사용자가 선택한 OCI 리전들 사이에서 라우팅**하는 방식을 정의하는 리소스.
- 프로파일 1개 = **지원되는 온디맨드 모델 1개** + **동일 realm 내 타깃 리전 1개 이상**(해당 모델이 제공되는 리전만 선택 가능).
- 요청에서 프로파일을 참조하면 서비스가 **프로파일의 타깃 리전 중 하나**에서 요청을 처리한다.
- 2026-09-23 "Smart model router" 릴리스로 도입. 2026-10-20 "Global Generative AI availability"로 30개 OC1 리전에서 사용 가능.

## 동작 방식

1. 애플리케이션은 **자기 리전의 Generative AI API 엔드포인트**(예: Seoul)로 요청을 보낸다.
2. 요청의 `model` 값에 **라우팅 프로파일의 전체 OCID**를 넣는다.
3. 서비스가 프로파일 타깃 리전 중 적격 리전을 골라 처리한다.
4. 응답 헤더 `x-genai-selected-region`에 **실제 서빙 리전**이 담긴다. 엔드포인트 리전과 다를 수 있으며 반드시 타깃 리전 중 하나다.

주의: 타깃 리전이 여러 개여도 **라운드로빈이나 고정 우선순위를 의미하지 않는다.** 라우팅 우선순위·로드밸런싱·페일오버 정책은 문서화되어 있지 않다.

## 제약

| 항목 | 내용 |
|------|------|
| 모드 | 온디맨드(on-demand) 전용. 전용 AI 클러스터 모델에는 적용 불가 |
| Realm | 타깃 리전은 모두 같은 realm(OC1 등) |
| 리전 | 선택한 리전으로만 라우팅. 선택하지 않은 리전은 사용되지 않음 |
| 모델 | 프로파일당 1개. 지원 온디맨드 모델 목록에 있어야 함 |
| API | 선택 모델이 해당 API를 지원할 때만 동작 |

## 지원 API

| API | 설명 | `model` 지정 |
|-----|------|--------------|
| Chat API (OCI SDK/REST, `generative-ai-inference` `Chat`) | 네이티브 OCI API | 라우팅 프로파일 OCID |
| OCI Chat Completions API | OpenAI 호환, 무상태. 기존 Chat Completions 코드 재사용용 | `model=<profile OCID>` |
| OCI Responses API | OpenAI 호환, 신규 앱 권장. Conversations API와 함께 서버 관리 멀티턴 가능 | `model=<profile OCID>` |

OpenAI 호환 엔드포인트: `https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1`

하나의 프로파일을 두 OpenAI 호환 API에 모두 쓰려면 모델이 Chat Completions와 Responses를 **둘 다** 지원해야 한다.
튜토리얼 예시 모델은 `openai.gpt-oss-120b`(타깃: Chicago, Frankfurt, Osaka).

## 로컬 모델 처리가 있는 리전에서의 활용

로컬 처리 리전이라도 특정 모델이 없으면 프로파일을 만들어 타 리전을 타깃으로 지정할 수 있다
(예: Ashburn에 없는 모델을 Chicago 타깃 프로파일로 Ashburn 엔드포인트에서 호출).

## 인증

- **OCI Generative AI API 키**: 테스트·초기 개발용. 기본 만료 생성일로부터 3개월. 키 이름 최대 2개. 생성 후 IAM 정책으로 API 키 권한 부여 필요.
- **IAM 서명**: 프로덕션 권장. OpenAI SDK와 함께 `oci-genai-auth` 패키지(`pip install oci-genai-auth`, GitHub `oracle-samples/oci-genai-auth-python`) 사용.

## 용어

- **CPU-only / 로컬 모델 처리 없는 리전**: GPU 모델 호스팅이 없는 리전. Seoul이 여기에 해당. 라우팅 프로파일로만 온디맨드 추론 가능.
- **Realm**: OC1(상용), OC2/OC3(미국 정부), OC4(영국 정부), OC19(EU 소버린) 등 격리 단위.
