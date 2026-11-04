"""Build Instantly reply body.html with paragraph breaks from plain text."""
from __future__ import annotations
import html

def text_to_html(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    paras = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        paras.append(html.escape(para).replace("\n", "<br>"))
    return "<br><br>".join(paras)

def ensure_body(data: dict) -> dict:
    body = dict(data.get("body") or {})
    text = body.get("text") or ""
    if text and not body.get("html"):
        body["html"] = text_to_html(text)
        body["text"] = text
        data["body"] = body
    return data
