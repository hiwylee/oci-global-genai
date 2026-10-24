"""Probe Files / Vector stores / file_search availability per region.

Usage: app/.venv/bin/python scripts/vector_store_probe.py [--case A|B|both] [--keep]
Reads .env. For each case: upload a file (/openai/v1/files, OpenAI-Project header), create a vector store
(a) via inference /openai/v1/vector_stores with API key, (b) via control plane
https://generativeai.<region>.oci.oraclecloud.com/20231130/openai/v1 with OCI user-principal request signing
(oci.signer.Signer + requests, header opc-compartment-id), then attach the file, search, and call Responses with file_search.
Nothing is deleted unless --cleanup is passed explicitly.
"""
from __future__ import annotations

import argparse, json, os, sys, time, tempfile
from pathlib import Path

import oci, requests
from openai import OpenAI, APIStatusError

ROOT = Path(__file__).resolve().parents[1]
PROFILE = {"A": "YWDCLOUD_CHICAGO", "B": "YWDCLOUD"}
DOC = """OCI Global GenAI 데모 문서.
라우팅 프로파일(routing profile)은 온디맨드 모델 1개와 타깃 리전들을 묶어 요청을 라우팅한다.
Seoul(ap-seoul-1)은 로컬 모델 처리가 없는 30개 OC1 리전 중 하나다.
이 문서의 비밀 코드명은 'BLUE-TIGER-42' 이다.
"""


def load_env(p: Path) -> None:
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def attempt(label: str, fn, out: list[dict]):
    t0 = time.perf_counter()
    try:
        r = fn(); ms = round((time.perf_counter() - t0) * 1000)
        print(f"  [OK ] {label} ({ms} ms): {json.dumps(r, ensure_ascii=False, default=str)[:400]}")
        out.append({"step": label, "ok": True, "ms": ms, "result": r}); return r
    except APIStatusError as e:
        body = e.response.text[:400].replace("\n", " ")
        print(f"  [ERR] {label}: HTTP {e.status_code} {body}")
        out.append({"step": label, "ok": False, "status": e.status_code, "body": body}); return None
    except Exception as e:  # noqa: BLE001
        print(f"  [ERR] {label}: {repr(e)[:400]}")
        out.append({"step": label, "ok": False, "error": repr(e)[:400]}); return None


def run_case(case: str, cleanup: bool, reuse_vs: str | None = None) -> list[dict]:
    region = os.environ[f"CASE_{case}_REGION"]; key = os.environ[f"CASE_{case}_API_KEY"]
    project = os.environ[f"CASE_{case}_PROJECT_OCID"]; comp = os.environ["COMPARTMENT_OCID"]
    profile_ocid = os.environ[f"CASE_{case}_PROFILE_OCID"]
    inf = f"https://inference.generativeai.{region}.oci.oraclecloud.com"
    cp = f"https://generativeai.{region}.oci.oraclecloud.com"
    print(f"\n===== Case {case} region={region} project=…{project[-8:]}")
    out: list[dict] = []
    dp = OpenAI(base_url=f"{inf}/openai/v1", api_key=key, project=project, timeout=120)
    cfg = oci.config.from_file(profile_name=PROFILE[case])
    signer = oci.signer.Signer(tenancy=cfg["tenancy"], user=cfg["user"], fingerprint=cfg["fingerprint"],
                               private_key_file_location=cfg["key_file"], pass_phrase=cfg.get("pass_phrase"))
    hdr = {"opc-compartment-id": comp, "CompartmentId": comp, "OpenAI-Project": project, "Content-Type": "application/json"}

    def signed(method: str, url: str, body: dict | None = None) -> dict:
        r = requests.request(method, url, json=body, headers=hdr, auth=signer, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} {r.text[:300]}")
        return r.json() if r.text else {}

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, prefix=f"genai-demo-{case}-") as f:
        f.write(DOC); fpath = f.name
    fobj = attempt("files.create (openai/v1, API key)", lambda: dp.files.create(file=open(fpath, "rb"), purpose="user_data").model_dump(), out)
    attempt("files.list (openai/v1, API key)", lambda: [x.id for x in dp.files.list().data][:5], out)

    vs = {"id": reuse_vs} if reuse_vs else None
    if vs is None:
        vs = attempt("vector_stores.create via /openai/v1 (API key)", lambda: dp.vector_stores.create(name=f"probe-{case}-{region}").model_dump(), out)
    if vs is None:
        vs = attempt("vector_stores.create via control plane /20231130/openai/v1 (IAM signed)", lambda: signed("POST", f"{cp}/20231130/openai/v1/vector_stores",
            {"name": f"probe-{case}-{region}", "description": "oci-global-genai probe", "expires_after": {"anchor": "last_active_at", "days": 7}}), out)
    attempt("vector_stores.list via control plane (IAM signed)", lambda: [(v.get("id"), v.get("name")) for v in signed("GET", f"{cp}/20231130/openai/v1/vector_stores").get("data", [])][:5], out)
    vs_id = vs["id"] if vs else None
    print(f"  vector_store_id={vs_id}")
    if vs_id:  # control plane create is async: wait until status == completed before attaching files
        for _ in range(24):
            st = attempt("vector_stores.retrieve status (CP, IAM signed)", lambda: signed("GET", f"{cp}/20231130/openai/v1/vector_stores/{vs_id}").get("status"), out)
            if st == "completed": break
            time.sleep(5)

    if vs_id and fobj:
        attempt("vector_stores.files.create (openai/v1, API key)", lambda: dp.vector_stores.files.create(vector_store_id=vs_id, file_id=fobj["id"]).model_dump(), out) \
            or attempt("vector_stores.files.create (/20231130/openai/v1, IAM signed)", lambda: signed("POST", f"{inf}/20231130/openai/v1/vector_stores/{vs_id}/files", {"file_id": fobj["id"]}), out)
        for _ in range(12):
            st = attempt("vector_stores.files.list status", lambda: [(x.id, x.status) for x in dp.vector_stores.files.list(vector_store_id=vs_id).data], out)
            if st and all(s in ("completed", "failed", "cancelled") for _, s in st): break
            time.sleep(5)
        attempt("vector_stores.search (openai/v1, API key)", lambda: [(r.score, r.content[0].text[:80]) for r in dp.vector_stores.search(vector_store_id=vs_id, query="비밀 코드명은?").data], out) \
            or attempt("vector_stores.search (/20231130/openai/v1, IAM signed)", lambda: [(r.get("score"), r["content"][0]["text"][:80]) for r in signed("POST", f"{inf}/20231130/openai/v1/vector_stores/{vs_id}/search", {"query": "비밀 코드명은?", "max_num_results": 3}).get("data", [])], out)
        for model in ("openai.gpt-oss-120b", "xai.grok-4.3", profile_ocid):
            attempt(f"responses+file_search model={model[:40]}", lambda m=model: dp.responses.create(
                model=m, input="문서의 비밀 코드명이 뭐야? 코드명만 답해.",
                tools=[{"type": "file_search", "vector_store_ids": [vs_id]}]).output_text, out)
    if cleanup and vs_id:
        attempt("cleanup vector_stores.delete", lambda: dp.vector_stores.delete(vs_id).model_dump(), out)
    if cleanup and fobj:
        attempt("cleanup files.delete", lambda: dp.files.delete(fobj["id"]).model_dump(), out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--case", default="both", choices=["A", "B", "both"]); ap.add_argument("--cleanup", action="store_true"); ap.add_argument("--vs-id", default=None, help="reuse an existing vector store id")
    a = ap.parse_args(); load_env(ROOT / ".env")
    results = {c: run_case(c, a.cleanup, a.vs_id) for c in (["A", "B"] if a.case == "both" else [a.case])}
    print("\nSUMMARY"); [print(f"  Case {c}: {sum(r['ok'] for r in rs)}/{len(rs)} steps ok") for c, rs in results.items()]
    return 0


if __name__ == "__main__":
    sys.exit(main())
