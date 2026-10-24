# 02. 리전 가용성과 Seoul 지원 범위

출처: "Regions with no Local Model Processing", "Generative AI Regions", "Generative AI Models by Region", 릴리스 노트 2026-10-20 (2026-10-24 조회).

## Global Generative AI availability (2026-10-20)

> OCI Generative AI now supports access to on-demand models through routing profiles in 30 OC1 commercial regions.
> Call supported models processed in other regions from your region's playground or through the Chat API, OCI Chat Completions API, or OCI Responses API.
> These regions also support selected Enterprise AI Agents and Enterprise AI Governance features, including hosted deployments, projects, and API keys.

## 로컬 모델 처리가 있는 OC1 리전 (11개) — 라우팅 타깃 후보

| 리전 | 식별자 |
|------|--------|
| US East (Ashburn) | `us-ashburn-1` |
| US Midwest (Chicago) | `us-chicago-1` |
| US West (Phoenix) | `us-phoenix-1` |
| Brazil East (Sao Paulo) | `sa-saopaulo-1` |
| Germany Central (Frankfurt) | `eu-frankfurt-1` |
| UK South (London) | `uk-london-1` |
| India South (Hyderabad) | `ap-hyderabad-1` |
| Japan Central (Osaka) | `ap-osaka-1` |
| Saudi Arabia Central (Riyadh) | `me-riyadh-1` |
| UAE Central (Abu Dhabi) | `me-abudhabi-1` (전용 클러스터만 로컬, 온디맨드는 라우팅) |
| UAE East (Dubai) | `me-dubai-1` |

Seoul에서 지연 시간상 가장 가까운 타깃은 **Osaka(`ap-osaka-1`)** 이고, 그다음 Hyderabad, Chicago 순으로 검토한다. 모델별 가용 리전은 "Models by Region" 페이지에서 확인해야 한다(Asia Pacific 표에는 Hyderabad, Osaka만 있음).

## 로컬 모델 처리가 없는 OC1 리전 (30개) — 라우팅 프로파일 필수

`ap-sydney-1`, `ap-melbourne-1`, `sa-vinhedo-1`, `ca-montreal-1`, `ca-toronto-1`, `sa-santiago-1`, `sa-valparaiso-1`, `sa-bogota-1`,
`eu-paris-1`, `ap-mumbai-1`, `ap-batam-1`, `eu-milan-1`, `eu-turin-1`, `ap-tokyo-1`, `mx-queretaro-1`, `mx-monterrey-1`,
`af-casablanca-1`, `eu-amsterdam-1`, `ap-singapore-1`, `ap-singapore-2`, `af-johannesburg-1`,
**`ap-seoul-1` (South Korea Central, ICN)**, **`ap-chuncheon-1` (South Korea North, YNY)**,
`eu-madrid-1`, `eu-madrid-3`, `eu-stockholm-1`, `eu-zurich-1`, `me-abudhabi-1`, `uk-cardiff-1`, `us-sanjose-1`

## Seoul(`ap-seoul-1`)에서의 기능 지원표

### Enterprise AI Models

| 기능 | Seoul |
|------|-------|
| 라우팅 프로파일을 통한 온디맨드 추론 | 지원 |
| Chat API | 지원 (라우팅 프로파일 경유, 모델이 지원 시) |
| Google Gemini 추론 | 지원 (라우팅 프로파일, 지원 모델/리전 조합) |
| xAI Grok 추론 | 지원 (라우팅 프로파일, 지원 모델/리전 조합) |
| Meta·Cohere 추론 | 지원 (라우팅 프로파일). **임베딩 요청 미지원** |
| OpenAI gpt-oss-120b 추론 | 지원 (라우팅 프로파일) |
| 모델 retirement 정보 | 지원 |
| 전용 AI 클러스터 / 모델 엔드포인트 | **미지원** |
| 모델 임포트 및 임포트 모델 추론 | **미지원** |
| Embedding API | **미지원** |
| Private endpoint (Gemini, Grok) | 지원 |
| Private endpoint (호스팅/임포트 모델) | **미지원** |
| 파인튜닝 | 전용 클러스터 미지원이므로 **불가** |

### Enterprise AI Agents

| 기능 | Seoul |
|------|-------|
| Sandboxes | 지원 |
| Hosted deployments | 지원 |
| Projects | 지원 (숏텀 메모리만) |
| Short-term memory | 지원 |
| Long-term memory | **미지원** |
| Semantic/Vector store | **미지원** |
| File search | **미지원** |
| OCI Chat Completions API | 지원 (라우팅 프로파일 경유) |
| OCI Responses API | 지원 (라우팅 프로파일 경유; 툴 등은 위 표 따름) |
| Agent gateway (MCP 툴 호스팅) | **미지원** |
| Client-side MCP 툴 | **미지원** |
| NL2SQL | **미지원** |

### Enterprise AI Governance

| 기능 | Seoul |
|------|-------|
| API keys | 지원 |
| Guardrails | **미지원** |

## 데이터 레지던시

- 온디맨드 요청은 **모델이 호스팅된 타깃 리전에서 처리**된다. 요청 데이터는 Seoul을 벗어난다.
- 선택한 타깃 리전만 사용되며 모두 같은 realm이어야 한다.
- Gemini/Grok 모델은 각각 Google/xAI가 외부 호스팅하며 처리 위치가 모델·리전 조합에 따라 다르다(Models by Region 각주 확인).
- 프로파일 생성 전 타깃 리전을 레지던시 요구사항과 대조할 것.

## 검증 필요 항목 (테스트로 확인)

- [x] YWDCLOUD 테넌시가 `ap-seoul-1` 구독 중(홈 리전). CLI로 Seoul에 라우팅 프로파일 생성 성공 (Console 메뉴는 미확인)
- [x] Seoul 로컬 모델 목록(CLI): `google.gemini-2.5-flash`, `google.gemini-2.5-flash-lite`, `google.gemini-2.5-pro` 3종만. Grok/Llama/Cohere/gpt-oss 없음 → 라우팅 프로파일 필요
- [x] `xai.grok-4.3` 타깃 가능 리전: Ashburn, Chicago, Phoenix (Osaka/Frankfurt/London 없음)
- [x] `x-genai-selected-region` 반환됨. Seoul→Chicago 12/12, Chicago 멀티타깃 12/12 Chicago (`docs/05-results.md`)
- [ ] 임베딩 요청이 실제로 거부되는지(에러 코드 기록)
