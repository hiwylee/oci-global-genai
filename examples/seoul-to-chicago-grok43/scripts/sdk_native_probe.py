"""Native OCI Python SDK probe: embed / rerank / chat (Generic + Cohere) per region, plus OpenAI-compatible cross-check.

Usage: app/.venv/bin/python scripts/sdk_native_probe.py [--region chicago|seoul|both]
- Chicago: call models directly by name (user principal, profile YWDCLOUD_CHICAGO).
- Seoul: call models directly by name (expect 404 except Gemini?) AND via Seoul routing profiles targeting Chicago
  (profile OCIDs discovered from logs/raw/*-profile-scope-*.json + CASE_B_PROFILE_OCID).
Prints a matrix and writes nothing except stdout. Nothing is created.
"""
from __future__ import annotations

import argparse, glob, json, os, sys, time
from pathlib import Path

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference import models as M
from openai import OpenAI, APIStatusError

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {"chicago": ("us-chicago-1", "YWDCLOUD_CHICAGO", "A"), "seoul": ("ap-seoul-1", "YWDCLOUD", "B")}
DOCS = ["서울은 대한민국의 수도이다.", "시카고는 미국 일리노이주에 있다.", "OCI Generative AI는 라우팅 프로파일을 지원한다."]


def load_env(p: Path) -> None:
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def seoul_profiles() -> dict[str, str]:
    out = {"xai.grok-4.3": os.environ["CASE_B_PROFILE_OCID"]}
    for p in sorted(glob.glob(str(ROOT / "../../logs/raw/*-profile-scope-*.json"))):
        raw = open(p).read()
        try:
            d = json.loads(raw[raw.index("{"):])["data"]
            out[d["model-routing-policy"]["allowed-models"][0]] = d["id"]
        except Exception:  # noqa: BLE001
            pass
    return out


def call(fn):
    t0 = time.perf_counter()
    try:
        r = fn(); return "OK " + str(r)[:40], round((time.perf_counter() - t0) * 1000)
    except oci.exceptions.ServiceError as e:
        return f"{e.status} {e.code}: {str(e.message)[:50]}", round((time.perf_counter() - t0) * 1000)
    except APIStatusError as e:
        return f"{e.status_code} {e.response.text[:50].replace(chr(10), ' ')}", round((time.perf_counter() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return "ERR " + repr(e)[:60], round((time.perf_counter() - t0) * 1000)


def embed(client, comp, model_id):
    r = client.embed_text(M.EmbedTextDetails(inputs=["안녕하세요"], compartment_id=comp, serving_mode=M.OnDemandServingMode(model_id=model_id), input_type="SEARCH_DOCUMENT"))
    return f"dims={len(r.data.embeddings[0])}"


def rerank(client, comp, model_id):
    r = client.rerank_text(M.RerankTextDetails(input="시카고는 어디에 있나?", compartment_id=comp, serving_mode=M.OnDemandServingMode(model_id=model_id), documents=DOCS, top_n=2))
    return f"top={r.data.document_ranks[0].index} score={r.data.document_ranks[0].relevance_score:.3f}"


def chat_generic(client, comp, model_id):
    req = M.GenericChatRequest(api_format="GENERIC", messages=[M.UserMessage(content=[M.TextContent(text="Reply with the single word OK.")])], max_tokens=64)
    r = client.chat(M.ChatDetails(compartment_id=comp, serving_mode=M.OnDemandServingMode(model_id=model_id), chat_request=req))
    c = r.data.chat_response.choices[0].message.content
    return (c[0].text if c else "").strip()[:20] or "(empty)"


def chat_cohere(client, comp, model_id):
    req = M.CohereChatRequest(api_format="COHERE", message="Reply with the single word OK.", max_tokens=64)
    r = client.chat(M.ChatDetails(compartment_id=comp, serving_mode=M.OnDemandServingMode(model_id=model_id), chat_request=req))
    return r.data.chat_response.text.strip()[:20]


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--region", default="both", choices=["chicago", "seoul", "both"]); a = ap.parse_args()
    load_env(ROOT / ".env"); comp = os.environ["COMPARTMENT_OCID"]
    tests = [("embed", "cohere.embed-v4.0", embed), ("rerank", "cohere.rerank-v4.0-fast", rerank), ("rerank", "cohere.rerank-v3.5", rerank),
             ("chat.generic", "google.gemini-2.5-pro", chat_generic), ("chat.generic", "google.gemini-2.5-flash", chat_generic),
             ("chat.generic", "xai.grok-4.3", chat_generic), ("chat.generic", "openai.gpt-oss-120b", chat_generic),
             ("chat.cohere", "cohere.command-a-03-2025", chat_cohere), ("chat.generic", "cohere.command-a-03-2025", chat_generic)]
    profiles = seoul_profiles()
    for key in (["chicago", "seoul"] if a.region == "both" else [a.region]):
        region, prof, case = REGIONS[key]
        cfg = oci.config.from_file(profile_name=prof); cfg["region"] = region
        client = GenerativeAiInferenceClient(cfg, service_endpoint=f"https://inference.generativeai.{region}.oci.oraclecloud.com", timeout=(10, 120))
        print(f"\n===== OCI SDK native @ {region} (profile {prof})")
        print(f"{'api':13} {'model':30} {'direct by name':>42} {'via Seoul routing profile':>42}")
        for api, model, fn in tests:
            direct, ms1 = call(lambda: fn(client, comp, model))
            if key == "seoul" and model in profiles:
                via, ms2 = call(lambda: fn(client, comp, profiles[model])); via = f"{via} ({ms2}ms)"
            else:
                via = "-"
            print(f"{api:13} {model:30} {direct + f' ({ms1}ms)':>42} {via:>42}")
        # OpenAI-compatible cross-check for Cohere command-a and Gemini 2.5 Pro
        key_env = f"CASE_{case}_API_KEY"; proj = os.environ.get(f"CASE_{case}_PROJECT_OCID")
        oa = OpenAI(base_url=f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1", api_key=os.environ[key_env], project=proj, timeout=90)
        print(f"----- OpenAI-compatible @ {region}")
        for model in ("cohere.command-a-03-2025", "google.gemini-2.5-pro"):
            ids = [("direct", model)] + ([("profile", profiles[model])] if key == "seoul" and model in profiles else [])
            for label, mid in ids:
                cc, _ = call(lambda: oa.chat.completions.create(model=mid, messages=[{"role": "user", "content": "Reply with the single word OK."}], max_tokens=32).choices[0].message.content)
                rs, _ = call(lambda: oa.responses.create(model=mid, input="Reply with the single word OK.", max_output_tokens=32).output_text)
                print(f"{model:30} {label:8} chat_completions: {cc:45} responses: {rs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
