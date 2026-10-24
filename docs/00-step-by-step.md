# 00. 처음부터 따라 하기 — Seoul 엔드포인트로 Chicago 모델 쓰기

각 단계마다 "사전 준비 → 실제 명령 → 이 프로젝트의 예시 → 확인 방법" 순서다. 실제 OCID는 `docs/05`, `docs/06` 참조.

## 1단계. 로컬 도구

사전 준비: macOS/Linux, Homebrew 또는 pip, Python 3.11+, `uv`.

- OCI CLI는 **3.95 이상**이어야 `routing-profile` 명령이 있다. 3.76에는 없다.
  ```bash
  brew upgrade oci-cli && oci --version            # 3.95.1
  oci generative-ai routing-profile --help         # create/get/update/delete/change-compartment
  ```
- Python 가상환경: `uv venv --python 3.11 .venv`, 패키지 `openai`, `fastapi`, `uvicorn`, `oci`(SDK), `requests`, `python-multipart`.
- 예시: `examples/seoul-to-chicago-grok43/app/run.sh` 가 이 과정을 자동으로 한다.

확인: `oci --version`, `app/.venv/bin/python -c "import oci, openai"`.

## 2단계. OCI 인증 프로파일 (`~/.oci/config`)

사전 준비: 테넌시 사용자, API 서명 키 쌍(사용자 설정에서 공개키 등록), 테넌시·사용자 OCID, fingerprint.

- 프로파일은 **리전별로 하나씩** 둔다. 이 프로젝트는 Seoul 작업에 `YWDCLOUD`(region=ap-seoul-1), Chicago 작업에 `YWDCLOUD_CHICAGO`(region=us-chicago-1)를 쓴다. 같은 사용자·키이고 region만 다르다.
- 모든 명령에 `--profile`과 `--region`을 명시한다. 예: `oci --profile YWDCLOUD generative-ai ... --region ap-seoul-1`.

확인:
```bash
oci --profile YWDCLOUD iam region-subscription list --output table   # ap-seoul-1(홈), us-chicago-1 포함 15개
```

## 3단계. 컴파트먼트와 IAM 정책

사전 준비: 리소스를 넣을 컴파트먼트 OCID, 정책을 쓸 권한(또는 관리자에게 요청).

- 이 프로젝트는 `wonyong.lee` 컴파트먼트를 쓴다. 이미 다음 정책이 있어 추가하지 않았다.
  ```
  allow any-user to manage generative-ai-family in compartment wonyong.lee
  allow any-user to use generative-ai-family in compartment wonyong.lee
    where ALL { request.principal.type='generativeaiapikey' }
  ```
  첫 줄은 CLI/SDK 사용자용, 둘째 줄은 **API 키 principal**용이다. 둘째 줄이 없으면 OpenAI 호환 API 키 호출이 전부 401/404가 난다.
- family 대신 최소 권한으로 하려면 `docs/07-minimal-iam-policies.md`(앱 "필요 정책" 탭)의 세트를 쓴다. 핵심은 `use generative-ai-chat` + `read generative-ai-routing-profile` + `manage generative-ai-apikey`.

확인: `oci iam policy list --compartment-id <컴파트먼트> --query 'data[].statements'`.

## 4단계. 모델이 어느 리전에 있는지 확인

사전 준비: 2·3단계 완료.

- Seoul은 **로컬 모델 처리가 없는 리전**(30개 중 하나)이다. 모델 목록을 찍어 보면 Gemini 3종만 보이고 그마저 직접 호출은 Google 서울 위치에 모델이 없어 실패한다.
- 쓰려는 모델이 실제로 있는 리전을 찾는다. `xai.grok-4.3`은 Ashburn·Chicago·Phoenix에만 있다.
  ```bash
  TEN=<테넌시 OCID>
  oci --profile YWDCLOUD_CHICAGO generative-ai model-collection list-models --compartment-id $TEN --region us-chicago-1 --all \
    --query 'data.items[?"display-name"==`xai.grok-4.3`].{name:"display-name",cap:capabilities}' --output table
  ```
  (`model list`가 아니라 `model-collection list-models`다.)

확인: Chicago 결과에 `xai.grok-4.3 | CHAT`, Seoul 결과에 Grok 없음.

## 5단계. 라우팅 프로파일 만들기 (핵심)

사전 준비: 컴파트먼트 OCID, 모델명, 모델이 있는 타깃 리전 목록. **온디맨드 채팅 모델만** 가능(임베딩·리랭크는 불가).

- 프로파일은 **요청을 받을 리전(Seoul)에** 만든다. 정책 JSON은 `{"allowedModels":[...]}`, `{"allowedRegions":[...]}`.
  ```bash
  COMP=<컴파트먼트 OCID>
  oci --profile YWDCLOUD generative-ai routing-profile create --region ap-seoul-1 --compartment-id $COMP \
    --display-name seoul-grok43-to-chicago \
    --model-routing-policy '{"allowedModels":["xai.grok-4.3"]}' \
    --region-routing-policy '{"allowedRegions":["us-chicago-1"]}' \
    --wait-for-state ACTIVE
  ```
  응답의 `data.id` = `ocid1.generativeairoutingprofile.oc1.ap-seoul-1....` 를 보관한다.
- 예시: Case B 프로파일 `seoul-grok43-to-chicago`(Seoul→Chicago만), Case A 프로파일 `chicago-grok43-multiregion`(Chicago에서 Chicago/Ashburn/Phoenix).
- 주의: 생성은 모델을 검증하지 않는다(임베딩 모델로도 만들어지지만 호출은 404). 생성 직후 약 1분은 400이 날 수 있다.

확인: `oci generative-ai routing-profile-collection list-routing-profiles --compartment-id $COMP --region ap-seoul-1`.

## 6단계. OpenAI 호환용 API 키 만들기

사전 준비: 3단계의 API 키 principal 정책. 키는 **리전 리소스**라 호출할 엔드포인트 리전마다 하나씩 만든다.

```bash
EXP=$(date -u -v+30d +%Y-%m-%dT%H:%M:%SZ)
oci --profile YWDCLOUD generative-ai api-key create --region ap-seoul-1 --compartment-id $COMP \
  --display-name seoul-grok43-demo --key-details "[{\"keyName\":\"primary\",\"timeExpiry\":\"$EXP\"}]"
```
- 평문 키(`keys[].key`, `sk-...`)는 **create 즉시 응답에만** 나온다. `--wait-for-state`를 붙이면 null로 덮인다. 놓치면 `api-key renew`로 재발급.
- 예시: Seoul 키 `seoul-grok43-demo`, Chicago 키 `chicago-grok43-demo`(둘 다 2026-11-23 만료). `.env`에 `CASE_B_API_KEY`, `CASE_A_API_KEY`로 분리 저장. 커밋 금지.

확인: `oci generative-ai api-key-collection list-api-keys --compartment-id $COMP --region ap-seoul-1`.

## 7단계. 첫 호출 (OpenAI SDK만으로)

사전 준비: 5·6단계의 프로파일 OCID와 키.

```python
from openai import OpenAI
client = OpenAI(base_url="https://inference.generativeai.ap-seoul-1.oci.oraclecloud.com/openai/v1", api_key=SEOUL_KEY)
with client.chat.completions.create(model=PROFILE_OCID, messages=[{"role":"user","content":"안녕"}], stream=True) as s:
    print("served:", s.response.headers.get("x-genai-selected-region"))   # us-chicago-1
    for c in s:
        if c.choices and c.choices[0].delta.content: print(c.choices[0].delta.content, end="")
```
- `model`에 **프로파일 OCID**를 넣는 것이 전부다. Responses API도 같다(`client.responses.create(model=PROFILE_OCID, input=...)`).
- 예시: `scripts/smoke_test.py` (두 케이스 × 두 API, 4/4 성공).

확인: 응답 헤더 `x-genai-selected-region`이 `us-chicago-1`.

## 8단계. 데모 앱 실행

사전 준비: 1~7단계. `.env`에 다음을 채운다.
```
CASE_A_REGION=us-chicago-1  CASE_A_PROFILE_OCID=...  CASE_A_API_KEY=...
CASE_B_REGION=ap-seoul-1    CASE_B_PROFILE_OCID=...  CASE_B_API_KEY=...
```
```bash
cd examples/seoul-to-chicago-grok43/app && ./run.sh     # http://127.0.0.1:8765
```
- 화면: 케이스 설명 → 구성 상태 → 채팅 데모(Case A/B 전환) → 라우팅 분포 프로브. 여기까지가 **기본 구성**이다.

확인: 채팅 응답 아래 "엔드포인트 ap-seoul-1 → 서빙 us-chicago-1".

## 9단계(선택). Enterprise AI Agents: 프로젝트·파일·벡터 스토어

사전 준비: 8단계. Files/Responses에 **프로젝트 OCID**(헤더 `OpenAI-Project`)가 필요하다.
```bash
oci --profile YWDCLOUD_CHICAGO generative-ai generative-ai-project create --region us-chicago-1 --compartment-id $COMP \
  --display-name grok43-demo-us-chicago-1 --wait-for-state SUCCEEDED     # resources[0].identifier 가 프로젝트 OCID
```
- 벡터 스토어는 **Chicago에만** 만들 수 있다(Seoul은 403 `GenerativeAiVectorStore is not supported`). 생성은 컨트롤 플레인 `https://generativeai.us-chicago-1.oci.oraclecloud.com/20231130/openai/v1/vector_stores`에 **IAM 서명**으로, 파일 업로드·검색·질의는 추론 엔드포인트에 API 키로 한다.
- file_search를 쓸 때는 프로파일 OCID 대신 **모델명 직접**(`xai.grok-4.3`)을 지정하고, 앱은 `tool_choice`로 툴을 강제한다.
- 예시: 앱 Case C. `.env`에 `COMPARTMENT_OCID`, `CASE_A_PROJECT_OCID`, `CASE_B_PROJECT_OCID` 추가.

확인: `scripts/vector_store_probe.py --case A --vs-id <벡터 스토어 ID>` 가 "BLUE-TIGER-42"를 답한다.

## 10단계(선택). OCI SDK 네이티브(임베딩·리랭크·Cohere)

사전 준비: 2단계 프로파일(사용자 principal 서명), `COMPARTMENT_OCID`.

- 임베딩·리랭크는 Chicago 직접 호출만 된다. Seoul 직접도, 프로파일 경유도 404.
- Cohere Command A는 `api_format=COHERE`로만 되고 프로파일 경유도 된다. OpenAI 호환으로는 불가.
- Gemini 2.5 Pro는 카탈로그에 있어도 Google 측 NOT_FOUND(2026-10-24 기준).
- 예시: 앱 Case D "전체 매트릭스 실행", `scripts/sdk_native_probe.py --region both`.

## 정리 순서 요약

CLI 업그레이드 → `~/.oci/config` 리전별 프로파일 → 컴파트먼트·정책 → 모델 리전 확인 → **라우팅 프로파일(요청 받는 리전에 생성)** → API 키(리전별) → OpenAI SDK로 `model=프로파일 OCID` 호출 → 앱 실행 → (선택) 프로젝트/벡터 스토어는 Chicago에 → (선택) 임베딩·리랭크·Cohere는 SDK로 Chicago 직접.
