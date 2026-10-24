# 03. 사전 준비와 구성 절차

모든 명령은 프로파일과 리전을 명시하고, 출력은 `logs/raw/`에 저장한 뒤 `logs/worklog.md`에 기록한다.

| 리전 | 프로파일 | 용도 |
|------|----------|------|
| `ap-seoul-1` | `YWDCLOUD` | 기본. 라우팅 프로파일 생성, Seoul 엔드포인트 호출 |
| `us-chicago-1` | `YWDCLOUD_CHICAGO` | 타깃 리전 측 확인(모델 가용성, 튜토리얼 원형 재현)이 필요할 때 |

## 1. 로컬 도구

| 도구 | 현재 | 필요 |
|------|------|------|
| OCI CLI | 3.76.1 (`routing-profile` 명령 없음) | 3.95.1+ (`brew upgrade oci-cli`) |
| Python | 3.13.9 | 3.11+ (튜토리얼은 `uv venv --python 3.11`) |
| uv | 0.9.11 | OK |
| openai SDK | 2.31.0 (시스템) | venv에 최신 설치 |
| oci SDK | 미설치 | Chat API(네이티브) 테스트 시 `uv pip install oci` |
| oci-genai-auth | 미설치 | IAM 인증 테스트 시 설치 |

```bash
brew upgrade oci-cli
oci --version
oci generative-ai routing-profile --help | tee logs/raw/$(date +%Y%m%d-%H%M)-cli-routing-profile-help.txt
```

## 2. 테넌시·컴파트먼트 확인

```bash
export OCI_CLI_PROFILE=YWDCLOUD
oci iam region-subscription list --output table
oci iam compartment list --compartment-id-in-subtree true --query 'data[].{name:name,id:id,state:"lifecycle-state"}' --output table
export COMPARTMENT_OCID=<테스트용 컴파트먼트 OCID>
```

## 3. IAM 정책

리소스 타입 `generative-ai-routing-profile` (family: `generative-ai-family`). 동사 계층 `manage ⊇ use ⊇ read ⊇ inspect`.

| 동사 | 포함 API |
|------|----------|
| inspect | ListRoutingProfiles |
| read | + GetRoutingProfile |
| use | + UpdateRoutingProfile |
| manage | + CreateRoutingProfile, DeleteRoutingProfile, ChangeRoutingProfileCompartment |

데이터 플레인 추론에 프로파일 OCID를 쓰려면 **`GENERATIVE_AI_ROUTING_PROFILE_READ` + 추론 권한** 둘 다 필요하다.

```
allow group <group> to manage generative-ai-routing-profile in compartment <compartment>
allow group <group> to use generative-ai-family in compartment <compartment>
```

API 키 사용 시 별도로 "API key permission"을 테넌시 또는 컴파트먼트 정책으로 부여해야 한다 (문서 `add-api-permission.htm`).

## 4. OCI Generative AI API 키 생성

- Console: Analytics & AI > Generative AI > API keys > Create API key. 이름, 컴파트먼트, 키 이름(최대 2개), 만료(기본 3개월, UTC).
- CLI: `oci generative-ai api-key create --compartment-id $COMP --display-name <name> --key-details '[{"keyName":"primary","timeExpiry":"<UTC ISO>"}]' --region <region>`.
  **평문 키(`keys[].key`)는 create 즉시 응답에만 한 번 포함된다.** `--wait-for-state`를 쓰면 null로 덮인다. 놓쳤으면 `api-key renew --api-key-id <id> --details '{"keyName":"primary","timeExpiry":"..."}'`로 재발급.
  API 키는 리전 리소스라 호출 엔드포인트 리전마다 만든다. 키 값은 `.env`에만 저장(커밋 금지).

```bash
# .env (gitignore 대상) — 튜토리얼 원형 스크립트(scripts/)용
export OCI_GENAI_API_KEY=...            # 호출 엔드포인트 리전에서 만든 키
export OCI_ROUTING_PROFILE_OCID=ocid1.generativeairoutingprofile....
export OCI_REGION=ap-seoul-1
# 예제 앱(examples/*/app)은 케이스별 CASE_A_API_KEY / CASE_B_API_KEY 를 쓴다 (키는 리전 리소스)
```

## 5. 라우팅 프로파일 생성

### Console (튜토리얼 방식, Seoul 적용)

1. Console 리전을 **South Korea Central (Seoul)** 로 선택.
2. Analytics & AI > Generative AI > **Routing profiles** > Create routing profile.
3. 이름(예: `seoul-gpt-oss-multiregion`), 컴파트먼트.
4. Configuration > Model select에서 온디맨드 모델 선택(예: `openai.gpt-oss-120b`).
5. Target OCI regions에서 모델이 제공되는 리전 선택(예: `ap-osaka-1`, `us-chicago-1`, `eu-frankfurt-1`).
6. Create 후 상태 **Active** 확인, **전체 OCID** 복사 → `.env`.

### CLI

```bash
# 정책 JSON 템플릿 생성 (스키마는 CLI가 제공; 문서에 필드명 미기재)
oci generative-ai routing-profile create --generate-param-json-input model-routing-policy  > model-policy.json
oci generative-ai routing-profile create --generate-param-json-input region-routing-policy > region-policy.json
# 편집 후 생성
oci generative-ai routing-profile create \
  --compartment-id "$COMPARTMENT_OCID" \
  --display-name "seoul-gpt-oss-multiregion" \
  --description "Seoul test: route on-demand requests to Osaka/Chicago/Frankfurt" \
  --model-routing-policy file://model-policy.json \
  --region-routing-policy file://region-policy.json \
  --region ap-seoul-1 \
  --wait-for-state ACTIVE --max-wait-seconds 600 \
  | tee logs/raw/$(date +%Y%m%d-%H%M)-routing-profile-create.json

oci generative-ai routing-profile-collection list-routing-profiles --compartment-id "$COMPARTMENT_OCID" --region ap-seoul-1
oci generative-ai routing-profile get  --routing-profile-id "$OCI_ROUTING_PROFILE_OCID"
```

API: `CreateRoutingProfile` (generative-ai 관리 API, `RoutingProfile` 리소스).
확인된 정책 JSON 스키마(CLI 3.95.1): `--model-routing-policy '{"allowedModels":["xai.grok-4.3"]}'`, `--region-routing-policy '{"allowedRegions":["us-chicago-1"]}'`.
모델 목록은 `oci generative-ai model-collection list-models --compartment-id <tenancy> --region <region> --all` (`model list` 아님).

## 6. Python 테스트 환경

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install --upgrade openai oci-genai-auth
source .env
python scripts/routing-chat-completion.py
python scripts/routing-responses-api.py
```

스크립트는 튜토리얼 코드를 기반으로 하며 핵심은 다음과 같다.

```python
client = OpenAI(
    base_url=f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
    api_key=api_key,
)
with client.chat.completions.create(model=profile_ocid, messages=messages, stream=True) as stream:
    served = stream.response.headers.get("x-genai-selected-region")
```

Responses API는 `client.responses.create(model=profile_ocid, input=messages, stream=True)`를 쓰고
`response.output_text.delta` 이벤트를 출력한다. 튜토리얼 스크립트는 히스토리를 로컬에 유지하며 `previous_response_id`를 쓰지 않는다.

## 7. 트러블슈팅 (튜토리얼 표)

| 증상 | 확인 |
|------|------|
| 인증/인가 오류 | API 키와 그 리전/권한, 프로파일 read 권한, 추론 권한 |
| Profile not found / invalid model | 전체 OCID 사용 여부, 프로파일 Active 상태, `OCI_REGION` 엔드포인트 |
| Unsupported API/parameter | 모델이 해당 API 지원하는지. `reasoning` 파라미터 불필요 |
| Request can't be served | 모델이 타깃 리전에서 제공되는지, 반환 오류 본문 |
| 서빙 리전 `not reported` | `x-genai-selected-region` 헤더 부재. 응답 전체 기록 |

## 8. 정리(삭제) 절차 — 사용자 확인 필수

삭제 전 대상 OCID·이름·컴파트먼트를 출력하고 승인받은 뒤 실행한다.

```bash
oci generative-ai routing-profile get --routing-profile-id "$ID" --query 'data.{name:"display-name",state:"lifecycle-state"}'
# (승인 후)
oci generative-ai routing-profile delete --routing-profile-id "$ID" --region ap-seoul-1 | tee logs/raw/$(date +%Y%m%d-%H%M)-routing-profile-delete.json
```
