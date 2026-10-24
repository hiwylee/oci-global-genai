"""OCI Generative AI 리전 간 라우팅 데모 서버 (Case A: Chicago 엔드포인트, Case B: Seoul → Chicago,
Case C: 벡터 스토어 / File Search — 엔드포인트 리전에 묶인 리소스, Case D: OCI SDK 네이티브 embed/rerank/chat)."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator, Literal

import oci
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference import models as genai_models
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_API_KEY = os.getenv("OCI_GENAI_API_KEY", "")

SELECTED_REGION_HEADER = "x-genai-selected-region"
REQUEST_ID_HEADERS = ("opc-request-id", "x-request-id", "request-id")
PROBE_PROMPT = "Reply with the single word OK."

CASES: dict[str, dict[str, str]] = {
    "A": {
        "region": os.getenv("CASE_A_REGION", "us-chicago-1"),
        "profile_ocid": os.getenv("CASE_A_PROFILE_OCID", ""),
        # API 키는 리전 리소스: 엔드포인트 리전(Chicago)에서 만든 키가 필요하다.
        "api_key": os.getenv("CASE_A_API_KEY") or DEFAULT_API_KEY,
        "model_label": os.getenv("CASE_A_MODEL_LABEL", "xai.grok-4.3"),
        # Files / 벡터 스토어용 OpenAI-Project 헤더, 컨트롤 플레인 서명용 ~/.oci/config 프로파일.
        "project_ocid": os.getenv("CASE_A_PROJECT_OCID", ""),
        "oci_profile": os.getenv("CASE_A_OCI_PROFILE", "YWDCLOUD_CHICAGO"),
    },
    "B": {
        "region": os.getenv("CASE_B_REGION", "ap-seoul-1"),
        "profile_ocid": os.getenv("CASE_B_PROFILE_OCID", ""),
        # Seoul 엔드포인트에서 만든 키.
        "api_key": os.getenv("CASE_B_API_KEY") or DEFAULT_API_KEY,
        "model_label": os.getenv("CASE_B_MODEL_LABEL", "xai.grok-4.3"),
        "project_ocid": os.getenv("CASE_B_PROJECT_OCID", ""),
        "oci_profile": os.getenv("CASE_B_OCI_PROFILE", "YWDCLOUD"),
    },
}

# Case C: 벡터 스토어 / File Search. 라우팅 프로파일 OCID는 tools와 함께 쓸 수 없어(400) 모델 이름을 직접 쓴다.
COMPARTMENT_OCID = os.getenv("COMPARTMENT_OCID", "")
CASE_C_MODEL = os.getenv("CASE_C_MODEL", "xai.grok-4.3")
CASE_C_INSTRUCTIONS = os.getenv(
    "CASE_C_INSTRUCTIONS",
    "항상 file_search 도구로 첨부 문서를 검색한 뒤 검색 결과에 근거해서만 답하라. 문서에 없으면 '문서에 없음'이라고 답하라.",
)
CASE_C_VECTOR_STORE_ID = os.getenv("CASE_C_VECTOR_STORE_ID", "")


# Case D: OCI SDK 네이티브 API. Seoul 라우팅 프로파일 매핑(모델 이름 → 프로파일 OCID).
def load_case_b_profiles() -> dict[str, str]:
    try:
        profiles = json.loads(os.getenv("CASE_B_PROFILES_JSON") or "{}")
    except ValueError:
        profiles = {}
    profiles = {str(k): str(v) for k, v in profiles.items() if v} if isinstance(profiles, dict) else {}
    if os.getenv("CASE_B_PROFILE_OCID"):
        profiles.setdefault("xai.grok-4.3", os.environ["CASE_B_PROFILE_OCID"])
    return profiles


CASE_B_PROFILES = load_case_b_profiles()
SDK_MODELS: dict[str, Any] = {
    "embed": ["cohere.embed-v4.0"],
    "rerank": ["cohere.rerank-v4.0-fast"],
    "chat": {
        "GENERIC": ["xai.grok-4.3", "openai.gpt-oss-120b", "google.gemini-2.5-flash", "google.gemini-2.5-pro",
                    "meta.llama-3.3-70b-instruct"],
        "COHERE": ["cohere.command-a-03-2025"],
    },
}


def base_url(region: str) -> str:
    return f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1"


def control_plane_url(region: str) -> str:
    return f"https://generativeai.{region}.oci.oraclecloud.com/20231130/openai/v1"


def mask(value: str, keep: int = 8) -> str:
    if not value:
        return ""
    return "…" + value[-keep:] if len(value) > keep else value


def get_case(case: str) -> dict[str, str]:
    cfg = CASES.get(case)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 case: {case}")
    if not cfg["profile_ocid"]:
        raise HTTPException(status_code=400, detail=f"CASE_{case}_PROFILE_OCID가 설정되지 않았습니다.")
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail=f"CASE_{case}_API_KEY 또는 OCI_GENAI_API_KEY가 설정되지 않았습니다.")
    return cfg


def make_client(cfg: dict[str, str]) -> OpenAI:
    return OpenAI(
        base_url=base_url(cfg["region"]), api_key=cfg["api_key"], project=cfg["project_ocid"] or None
    ).with_options(timeout=120)


def request_id(headers: Any) -> str | None:
    for name in REQUEST_ID_HEADERS:
        value = headers.get(name)
        if value:
            return value
    return None


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, APIStatusError):
        return {"status": exc.status_code, "message": exc.message, "body": exc.response.text}
    if isinstance(exc, APIConnectionError):
        return {"status": None, "message": f"연결 오류: {exc}", "body": None}
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        resp = exc.response
        try:
            message = resp.json().get("message") or resp.reason
        except ValueError:
            message = resp.reason
        return {"status": resp.status_code, "message": message, "body": resp.text}
    if isinstance(exc, requests.RequestException):
        return {"status": None, "message": f"연결 오류: {exc}", "body": None}
    if isinstance(exc, (oci.exceptions.ClientError, oci.exceptions.InvalidConfig)):
        return {"status": None, "message": f"OCI 서명 구성 오류 ({type(exc).__name__}): {exc}", "body": None}
    return {"status": None, "message": f"{type(exc).__name__}: {exc}", "body": None}


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    case: Literal["A", "B"]
    messages: list[Message] = Field(min_length=1)
    api: Literal["chat_completions", "responses"] = "chat_completions"


class ProbeRequest(BaseModel):
    case: Literal["A", "B"]
    n: int = Field(default=5, ge=1, le=20)


app = FastAPI(title="OCI GenAI Cross-Region Routing Demo")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        name: {
            "region": cfg["region"],
            "base_url": base_url(cfg["region"]),
            "profile_ocid_masked": mask(cfg["profile_ocid"]),
            "model_label": cfg["model_label"],
            "configured": bool(cfg["profile_ocid"] and cfg["api_key"]),
            "api_key_source": "case" if os.getenv(f"CASE_{name}_API_KEY") else ("default" if DEFAULT_API_KEY else "none"),
        }
        for name, cfg in CASES.items()
    } | {
        "C": {
            "model": CASE_C_MODEL,
            "default_vector_store_id": CASE_C_VECTOR_STORE_ID,
            "compartment_set": bool(COMPARTMENT_OCID),
            "regions": {
                name: {
                    "region": cfg["region"],
                    "base_url": base_url(cfg["region"]),
                    "control_plane_url": control_plane_url(cfg["region"]),
                    "project_set": bool(cfg["project_ocid"]),
                    "api_key_set": bool(cfg["api_key"]),
                    "oci_profile": cfg["oci_profile"],
                }
                for name, cfg in CASES.items()
            },
        },
        "D": {
            "profiles": {"B": {model: mask(ocid) for model, ocid in CASE_B_PROFILES.items()}},
            "oci_profiles": {name: cfg["oci_profile"] for name, cfg in CASES.items()},
            "compartment_set": bool(COMPARTMENT_OCID),
        },
    }


@app.get("/api/policies")
def policies() -> Any:
    return json.loads((BASE_DIR / "policies.json").read_text(encoding="utf-8"))


def text_deltas(stream: Any, api: str) -> Iterator[str]:
    for chunk in stream:
        if api == "chat_completions":
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        elif getattr(chunk, "type", "") == "response.output_text.delta":
            yield chunk.delta


def open_stream(client: OpenAI, req: ChatRequest, model: str) -> Any:
    messages = [m.model_dump() for m in req.messages]
    if req.api == "chat_completions":
        return client.chat.completions.create(model=model, messages=messages, stream=True)
    return client.responses.create(model=model, input=messages, stream=True)


def stream_events(open_fn: Any, region: str, api: str, extra_meta: dict[str, Any] | None = None) -> Iterator[str]:
    start = time.perf_counter()
    output_chars = 0
    meta_sent = False
    try:
        with open_fn() as stream:
            headers = stream.response.headers
            meta = {
                "endpoint_region": region,
                "selected_region": headers.get(SELECTED_REGION_HEADER),
                "latency_first_token_ms": None,
                "request_id": request_id(headers),
                **(extra_meta or {}),
            }
            for text in text_deltas(stream, api):
                if not meta_sent:
                    meta["latency_first_token_ms"] = round((time.perf_counter() - start) * 1000)
                    yield sse("meta", meta)
                    meta_sent = True
                output_chars += len(text)
                yield sse("delta", {"text": text})
            if not meta_sent:
                yield sse("meta", meta)
                meta_sent = True
        yield sse("done", {"total_ms": round((time.perf_counter() - start) * 1000), "output_chars": output_chars})
    except Exception as exc:  # noqa: BLE001 - 모든 오류를 SSE error 이벤트로 전달
        yield sse("error", error_payload(exc))


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    cfg = get_case(req.case)
    client = make_client(cfg)
    return StreamingResponse(
        stream_events(lambda: open_stream(client, req, cfg["profile_ocid"]), cfg["region"], req.api),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def probe_once(client: OpenAI, model: str, i: int) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        raw = client.chat.completions.with_raw_response.create(
            model=model,
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            max_tokens=16,
        )
        raw.parse()
        return {
            "i": i,
            "selected_region": raw.headers.get(SELECTED_REGION_HEADER),
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "status": raw.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        err = error_payload(exc)
        return {
            "i": i,
            "selected_region": None,
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "status": err["status"] or "error",
            "error": err["message"],
        }


@app.post("/api/probe")
def probe(req: ProbeRequest) -> dict[str, Any]:
    cfg = get_case(req.case)
    client = make_client(cfg)
    results = [probe_once(client, cfg["profile_ocid"], i) for i in range(1, req.n + 1)]
    histogram = Counter(r["selected_region"] or "(헤더 없음/오류)" for r in results)
    return {"endpoint_region": cfg["region"], "results": results, "histogram": dict(histogram)}


# ---------------------------------------------------------------------------
# Case C — 벡터 스토어 / File Search (Enterprise AI Agents)
# 생성/목록/조회: 컨트롤 플레인 + OCI 요청 서명. 파일 업로드/연결/검색/Responses: 추론 엔드포인트 + API 키.
# 업스트림 실패(예: Seoul 403 NotAllowed, Files 404)는 데모 결과로 보여주기 위해 HTTP 200 + {ok: false, ...}로 반환한다.
# ---------------------------------------------------------------------------


class VSCreateRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    name: str = Field(min_length=1, max_length=200)
    expires_days: int = Field(default=7, ge=1, le=365)


class VSSearchRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    query: str = Field(min_length=1)
    max_num_results: int = Field(default=5, ge=1, le=50)


class VSAskRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    question: str = Field(min_length=1)
    model: str | None = None


def get_case_c(case: str) -> dict[str, str]:
    cfg = CASES.get(case)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"알 수 없는 case: {case}")
    return cfg


def make_dp_client(cfg: dict[str, str]) -> OpenAI:
    if not cfg["api_key"]:
        raise ValueError("API 키(CASE_X_API_KEY 또는 OCI_GENAI_API_KEY)가 설정되지 않았습니다.")
    return make_client(cfg)


def signed(cfg: dict[str, str], method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    if not COMPARTMENT_OCID:
        raise ValueError("COMPARTMENT_OCID가 설정되지 않았습니다 (컨트롤 플레인 호출에 필요).")
    oc = oci.config.from_file(profile_name=cfg["oci_profile"])
    signer = oci.signer.Signer(
        tenancy=oc["tenancy"], user=oc["user"], fingerprint=oc["fingerprint"],
        private_key_file_location=oc["key_file"], pass_phrase=oc.get("pass_phrase"),
    )
    headers = {"opc-compartment-id": COMPARTMENT_OCID, "CompartmentId": COMPARTMENT_OCID, "Content-Type": "application/json"}
    if cfg["project_ocid"]:
        headers["OpenAI-Project"] = cfg["project_ocid"]
    r = requests.request(method, control_plane_url(cfg["region"]) + path, json=body, headers=headers, auth=signer, timeout=60)
    r.raise_for_status()
    return r.json() if r.text else {}


def upstream(cfg: dict[str, str], fn: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "endpoint_region": cfg["region"], "data": fn()}
    except Exception as exc:  # noqa: BLE001 - 업스트림 오류를 데모 결과로 표시
        return {"ok": False, "endpoint_region": cfg["region"], **error_payload(exc)}


def vs_summary(v: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "name", "status", "file_counts", "created_at", "usage_bytes", "expires_at")
    return {k: v.get(k) for k in keys}


@app.post("/api/vs/create")
def vs_create(req: VSCreateRequest) -> dict[str, Any]:
    cfg = get_case_c(req.case)
    body = {"name": req.name, "expires_after": {"anchor": "last_active_at", "days": req.expires_days}}
    return upstream(cfg, lambda: signed(cfg, "POST", "/vector_stores", body))


@app.get("/api/vs/list")
def vs_list(case: Literal["A", "B"] = "A") -> dict[str, Any]:
    cfg = get_case_c(case)
    return upstream(cfg, lambda: [vs_summary(v) for v in signed(cfg, "GET", "/vector_stores").get("data", [])])


@app.get("/api/vs/{vs_id}")
def vs_get(vs_id: str, case: Literal["A", "B"] = "A") -> dict[str, Any]:
    cfg = get_case_c(case)
    return upstream(cfg, lambda: vs_summary(signed(cfg, "GET", f"/vector_stores/{vs_id}")))


@app.post("/api/vs/{vs_id}/files")
def vs_upload(vs_id: str, file: UploadFile = File(...), case: Literal["A", "B"] = Form("A")) -> dict[str, Any]:
    cfg = get_case_c(case)
    content = file.file.read()

    def run() -> dict[str, Any]:
        dp = make_dp_client(cfg)
        fobj = dp.files.create(file=(file.filename or "upload.txt", content, file.content_type), purpose="user_data")
        vf = dp.vector_stores.files.create(vector_store_id=vs_id, file_id=fobj.id)
        return {"file_id": fobj.id, "filename": fobj.filename, "bytes": fobj.bytes, "status": vf.status}

    return upstream(cfg, run)


@app.get("/api/vs/{vs_id}/files")
def vs_files(vs_id: str, case: Literal["A", "B"] = "A") -> dict[str, Any]:
    cfg = get_case_c(case)

    def run() -> list[dict[str, Any]]:
        rows = make_dp_client(cfg).vector_stores.files.list(vector_store_id=vs_id).data
        return [
            {"id": f.id, "status": f.status, "created_at": f.created_at, "usage_bytes": f.usage_bytes,
             "last_error": f.last_error.message if f.last_error else None}
            for f in rows
        ]

    return upstream(cfg, run)


@app.post("/api/vs/{vs_id}/search")
def vs_search(vs_id: str, req: VSSearchRequest) -> dict[str, Any]:
    cfg = get_case_c(req.case)

    def run() -> list[dict[str, Any]]:
        page = make_dp_client(cfg).vector_stores.search(
            vector_store_id=vs_id, query=req.query, max_num_results=req.max_num_results
        )
        return [
            {"score": r.score, "filename": r.filename, "text": "\n".join(c.text for c in r.content)}
            for r in page.data
        ]

    return upstream(cfg, run)


@app.post("/api/vs/{vs_id}/ask")
def vs_ask(vs_id: str, req: VSAskRequest) -> StreamingResponse:
    cfg = get_case_c(req.case)
    model = req.model or CASE_C_MODEL

    def open_fn() -> Any:
        # 모델이 툴 호출을 생략하면 "정보 없음"으로 답하므로 file_search 를 강제한다 (실측: tool_choice 없이는 미호출 사례 있음).
        return make_dp_client(cfg).responses.create(
            model=model, input=req.question, stream=True,
            instructions=CASE_C_INSTRUCTIONS,
            tools=[{"type": "file_search", "vector_store_ids": [vs_id]}],
            tool_choice={"type": "file_search"},
        )

    return StreamingResponse(
        stream_events(open_fn, cfg["region"], "responses", {"model": model, "vector_store_id": vs_id}),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



# ---------------------------------------------------------------------------
# Case D — OCI SDK 네이티브 API (embed / rerank / chat)
# GenerativeAiInferenceClient + ~/.oci/config 사용자 principal 서명(API 키 아님).
# model_id에는 모델 이름 또는 라우팅 프로파일 OCID를 넣는다. 실패는 HTTP 200 + {ok: false, status, code, message}.
# ---------------------------------------------------------------------------


class SDKEmbedRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    model_id: str = Field(min_length=1)
    inputs: list[str] = Field(min_length=1, max_length=96)
    input_type: str = "SEARCH_DOCUMENT"


class SDKRerankRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    model_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)
    top_n: int = Field(default=3, ge=1, le=100)


class SDKChatRequest(BaseModel):
    case: Literal["A", "B"] = "A"
    model_id: str = Field(min_length=1)
    api_format: Literal["GENERIC", "COHERE"] = "GENERIC"
    message: str = Field(min_length=1)
    max_tokens: int = Field(default=200, ge=1, le=4000)


def sdk_client(cfg: dict[str, str]) -> GenerativeAiInferenceClient:
    if not COMPARTMENT_OCID:
        raise ValueError("COMPARTMENT_OCID가 설정되지 않았습니다 (네이티브 SDK 호출에 필요).")
    oc = oci.config.from_file(profile_name=cfg["oci_profile"])
    oc["region"] = cfg["region"]
    return GenerativeAiInferenceClient(
        oc, service_endpoint=f"https://inference.generativeai.{cfg['region']}.oci.oraclecloud.com", timeout=(10, 120)
    )


def sdk_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, oci.exceptions.ServiceError):
        return {"status": exc.status, "code": exc.code, "message": exc.message, "request_id": exc.request_id}
    err = error_payload(exc)
    return {"status": err["status"], "code": type(exc).__name__, "message": err["message"]}


def sdk_call(case: str, model_id: str, fn: Any) -> dict[str, Any]:
    cfg = get_case_c(case)
    start = time.perf_counter()
    meta = {"endpoint_region": cfg["region"], "auth": "user-principal", "oci_profile": cfg["oci_profile"], "model_id": model_id}
    try:
        data, extra = fn(sdk_client(cfg))
        return {"ok": True, **meta, "latency_ms": round((time.perf_counter() - start) * 1000), "data": data, **extra}
    except Exception as exc:  # noqa: BLE001 - 업스트림/구성 오류를 데모 결과로 표시
        return {"ok": False, **meta, "latency_ms": round((time.perf_counter() - start) * 1000), **sdk_error(exc)}


def opc_request_id(response: Any) -> dict[str, Any]:
    rid = (getattr(response, "headers", None) or {}).get("opc-request-id")
    return {"opc_request_id": rid} if rid else {}


@app.get("/api/sdk/models")
def sdk_models(case: Literal["A", "B"] = "A") -> dict[str, Any]:
    cfg = get_case_c(case)
    return {
        "ok": True, "case": case, "endpoint_region": cfg["region"], **SDK_MODELS,
        "profiles": CASE_B_PROFILES if case == "B" else {},
    }


@app.post("/api/sdk/embed")
def sdk_embed(req: SDKEmbedRequest) -> dict[str, Any]:
    def run(client: GenerativeAiInferenceClient) -> tuple[Any, dict[str, Any]]:
        r = client.embed_text(genai_models.EmbedTextDetails(
            inputs=req.inputs, compartment_id=COMPARTMENT_OCID, input_type=req.input_type,
            serving_mode=genai_models.OnDemandServingMode(model_id=req.model_id),
        ))
        emb = r.data.embeddings or []
        data = {"dims": len(emb[0]) if emb else 0, "first_values": list(emb[0][:5]) if emb else [], "count": len(emb)}
        return data, opc_request_id(r)

    return sdk_call(req.case, req.model_id, run)


@app.post("/api/sdk/rerank")
def sdk_rerank(req: SDKRerankRequest) -> dict[str, Any]:
    def run(client: GenerativeAiInferenceClient) -> tuple[Any, dict[str, Any]]:
        r = client.rerank_text(genai_models.RerankTextDetails(
            input=req.query, documents=req.documents, top_n=req.top_n, compartment_id=COMPARTMENT_OCID,
            serving_mode=genai_models.OnDemandServingMode(model_id=req.model_id),
        ))
        data = [
            {"index": d.index, "relevance_score": d.relevance_score,
             "document": d.document.text if d.document else req.documents[d.index]}
            for d in r.data.document_ranks or []
        ]
        return data, opc_request_id(r)

    return sdk_call(req.case, req.model_id, run)


@app.post("/api/sdk/chat")
def sdk_chat(req: SDKChatRequest) -> dict[str, Any]:
    def run(client: GenerativeAiInferenceClient) -> tuple[Any, dict[str, Any]]:
        if req.api_format == "COHERE":
            chat_request: Any = genai_models.CohereChatRequest(api_format="COHERE", message=req.message, max_tokens=req.max_tokens)
        else:
            chat_request = genai_models.GenericChatRequest(
                api_format="GENERIC", max_tokens=req.max_tokens,
                messages=[genai_models.UserMessage(content=[genai_models.TextContent(text=req.message)])],
            )
        r = client.chat(genai_models.ChatDetails(
            compartment_id=COMPARTMENT_OCID, chat_request=chat_request,
            serving_mode=genai_models.OnDemandServingMode(model_id=req.model_id),
        ))
        resp = r.data.chat_response
        if req.api_format == "COHERE":
            text = resp.text or ""
        else:
            content = resp.choices[0].message.content if resp.choices and resp.choices[0].message else None
            text = "".join(getattr(c, "text", "") or "" for c in content or [])
        return {"text": text, "api_format": req.api_format}, opc_request_id(r)

    return sdk_call(req.case, req.model_id, run)
