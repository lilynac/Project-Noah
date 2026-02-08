from __future__ import annotations

from typing import Optional

def responses_output_text(resp) -> str:
    """
    OpenAI Responses API の resp.output から output_text を連結して返す。
    """
    parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", None) == "output_text":
                    parts.append(getattr(c, "text", "") or "")
    return ("".join(parts)).strip()


def call_responses_text(
    client,
    *,
    model: str,
    prompt: str,
    temperature: float = 0.2,
    max_output_tokens: int = 520,
    log_prefix: str = "llm_utils",
) -> Optional[str]:
    """
    Responses API を叩いて、テキストだけ返す。
    失敗時はログを出して None。
    """
    try:
        resp = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except Exception as e:
        print(f"{log_prefix}: OpenAI error:", repr(e))
        return None

    text = responses_output_text(resp)
    return text or None
