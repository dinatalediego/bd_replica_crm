from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from replica_cygnus.settings import load_settings


def ollama_generate(model: str, prompt: str, host: str) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.15},
    }).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--mode", choices=["prompt-only", "ollama"], default="prompt-only")
    p.add_argument("--model", default="qwen2.5:7b")
    p.add_argument("--host", default="http://localhost:11434")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)
    folder = root / "artifacts" / "project_intelligence_v290" / args.project
    prompt_path = folder / "ai_prompt.md"
    context_path = folder / "context.json"

    if not prompt_path.exists() or not context_path.exists():
        raise SystemExit(
            f"Falta contexto para {args.project}. Ejecuta primero project_intelligence_context_v290.py refresh."
        )

    prompt = prompt_path.read_text(encoding="utf-8")
    context = context_path.read_text(encoding="utf-8")
    full_prompt = prompt + "\n\n# CONTEXT.JSON\n\n" + context

    if args.mode == "prompt-only":
        out = folder / "ai_input_bundle.md"
        out.write_text(full_prompt, encoding="utf-8")
        print(f"[V2.9.0] AI bundle ready: {out}")
        return

    result = ollama_generate(args.model, full_prompt, args.host)
    out = folder / "ai_brief.md"
    out.write_text(result.strip() + "\n", encoding="utf-8")
    print(f"[V2.9.0] local AI brief written: {out}")


if __name__ == "__main__":
    main()
