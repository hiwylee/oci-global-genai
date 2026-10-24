"""Use the OCI Responses API with a routing profile.

Source: Oracle tutorial "Route Model Requests Across OCI Regions".
Only works if the profile's model supports the Responses API.
Env: OCI_REGION (default ap-seoul-1), OCI_ROUTING_PROFILE_OCID, OCI_GENAI_API_KEY (optional, prompts if unset).
"""

from __future__ import annotations

import os
from getpass import getpass

from openai import OpenAI


def main() -> None:
    region = os.environ.get("OCI_REGION", "ap-seoul-1")
    profile_ocid = os.environ["OCI_ROUTING_PROFILE_OCID"]
    api_key = os.environ.get("OCI_GENAI_API_KEY") or getpass("OCI Generative AI API key: ")
    client = OpenAI(
        base_url=f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1",
        api_key=api_key,
    )

    messages: list[dict[str, str]] = []
    print(f"Responses API via routing profile. endpoint={region}. Type 'exit' to stop.\n")

    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if prompt.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not prompt:
            continue

        messages.append({"role": "user", "content": prompt})
        answer_parts: list[str] = []
        try:
            with client.responses.create(
                model=profile_ocid, input=messages, stream=True
            ) as stream:
                selected_region = stream.response.headers.get("x-genai-selected-region")
                print(f"Served from OCI region: {selected_region or 'not reported'}")
                print("Assistant: ", end="", flush=True)
                for event in stream:
                    if event.type == "response.output_text.delta":
                        answer_parts.append(event.delta)
                        print(event.delta, end="", flush=True)
        except Exception as error:  # noqa: BLE001
            messages.pop()
            print(f"\nRequest failed: {error}\n")
            continue

        answer = "".join(answer_parts)
        if answer:
            messages.append({"role": "assistant", "content": answer})
        else:
            messages.pop()
        print("\n")


if __name__ == "__main__":
    main()
