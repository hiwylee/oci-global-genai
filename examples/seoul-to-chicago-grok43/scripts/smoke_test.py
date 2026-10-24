"""Smoke test: call xai.grok-4.3 through routing profiles for Case A (Chicago) and Case B (Seoul).

Usage: python scripts/smoke_test.py [--case A|B|both] [--api chat|responses|both] [--n 1]
Reads ../.env (CASE_X_REGION, CASE_X_PROFILE_OCID, CASE_X_API_KEY). Prints endpoint region,
x-genai-selected-region, latency, and a short answer. Exit code 1 if any call fails.
"""
from __future__ import annotations

import argparse, os, sys, time, json
from pathlib import Path

from openai import OpenAI, APIStatusError

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def client_for(case: str) -> tuple[OpenAI, str, str]:
    region = os.environ[f"CASE_{case}_REGION"]
    profile = os.environ[f"CASE_{case}_PROFILE_OCID"]
    api_key = os.environ[f"CASE_{case}_API_KEY"]
    base = f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1"
    return OpenAI(base_url=base, api_key=api_key, timeout=120), region, profile


def run_chat(client: OpenAI, profile: str, prompt: str) -> dict:
    t0 = time.perf_counter(); first = None; parts = []
    with client.chat.completions.create(
        model=profile, messages=[{"role": "user", "content": prompt}], stream=True, max_tokens=120
    ) as stream:
        headers = stream.response.headers
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                if first is None:
                    first = time.perf_counter()
                parts.append(chunk.choices[0].delta.content)
    return {
        "api": "chat_completions",
        "selected_region": headers.get("x-genai-selected-region"),
        "request_id": headers.get("opc-request-id"),
        "first_token_ms": round((first - t0) * 1000) if first else None,
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "text": "".join(parts).strip()[:160],
    }


def run_responses(client: OpenAI, profile: str, prompt: str) -> dict:
    t0 = time.perf_counter(); first = None; parts = []
    with client.responses.create(model=profile, input=prompt, stream=True, max_output_tokens=120) as stream:
        headers = stream.response.headers
        for ev in stream:
            if ev.type == "response.output_text.delta":
                if first is None:
                    first = time.perf_counter()
                parts.append(ev.delta)
    return {
        "api": "responses",
        "selected_region": headers.get("x-genai-selected-region"),
        "request_id": headers.get("opc-request-id"),
        "first_token_ms": round((first - t0) * 1000) if first else None,
        "total_ms": round((time.perf_counter() - t0) * 1000),
        "text": "".join(parts).strip()[:160],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="both", choices=["A", "B", "both"])
    ap.add_argument("--api", default="both", choices=["chat", "responses", "both"])
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--prompt", default="Which model are you and in one sentence what is OCI? Answer briefly.")
    a = ap.parse_args()
    load_env(ROOT / ".env")
    cases = ["A", "B"] if a.case == "both" else [a.case]
    apis = ["chat", "responses"] if a.api == "both" else [a.api]
    failed = 0
    results = []
    for case in cases:
        client, region, profile = client_for(case)
        for api in apis:
            for i in range(a.n):
                try:
                    r = run_chat(client, profile, a.prompt) if api == "chat" else run_responses(client, profile, a.prompt)
                    r.update(case=case, endpoint_region=region, i=i, ok=True)
                except APIStatusError as e:
                    r = {"case": case, "endpoint_region": region, "api": api, "i": i, "ok": False,
                         "status": e.status_code, "body": e.response.text[:500]}
                    failed += 1
                except Exception as e:  # noqa: BLE001
                    r = {"case": case, "endpoint_region": region, "api": api, "i": i, "ok": False, "error": repr(e)[:500]}
                    failed += 1
                results.append(r)
                print(json.dumps(r, ensure_ascii=False))
    print(f"\n{len(results) - failed}/{len(results)} calls succeeded")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
