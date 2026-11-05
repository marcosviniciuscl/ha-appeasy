"""Read-only chat adapters. Keys are configured in Supervisor App options."""
import base64
import json
import logging
import os
import ipaddress
import re
import socket
import time
import requests
from urllib.parse import urlparse


LOGGER = logging.getLogger("concierge.llm")
DEFAULT_MODELS = {"openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-latest",
                  "gemini": "gemini-2.0-flash", "ollama": "llama3.2",
                  "compatible": "default", "openrouter": "openrouter/auto"}


def options():
    try:
        with open("/data/options.json", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return {}


def key_for(provider):
    field = {"openai": "openai_api_key", "anthropic": "anthropic_api_key",
             "gemini": "gemini_api_key", "compatible": "compatible_api_key",
             "openrouter": "openrouter_api_key"}.get(provider)
    return options().get(field, "") if field else ""


def _redact(text):
    text = str(text or "")
    text = re.sub(r"(?i)(sk-[A-Za-z0-9_-]{6,}|AIza[0-9A-Za-z_-]{10,}|Bearer\s+[A-Za-z0-9._-]+)",
                  "[redacted]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|authorization|x-api-key|key)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+",
                  r"\1[redacted]", text)
    return text[:400]


def _post(url, headers, body):
    started = time.monotonic()
    try:
        r = requests.post(url, headers=headers, json=body, timeout=45)
        elapsed = int((time.monotonic() - started) * 1000)
        LOGGER.debug("LLM POST %s status=%s elapsed_ms=%d response_bytes=%d",
                     url, r.status_code, elapsed, len(r.content or b""))
        if not r.ok:
            LOGGER.debug("LLM POST %s error_body=%r", url, _redact(r.text))
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            LOGGER.debug("LLM POST %s returned non-object JSON: %s", url, type(data).__name__)
            raise RuntimeError("O provedor de IA não respondeu")
        return data
    except requests.RequestException as exc:
        LOGGER.debug("LLM POST %s failed after %dms: %s", url,
                     int((time.monotonic() - started) * 1000), exc)
        raise RuntimeError("O provedor de IA não respondeu") from exc
    except ValueError as exc:
        LOGGER.debug("LLM POST %s returned invalid JSON: %s", url, exc)
        raise RuntimeError("O provedor de IA não respondeu") from exc


def _text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(str(part.get("text", "")) for part in value
                        if isinstance(part, dict)).strip()
    return ""


def available_models(provider):
    """Return chat models exposed by the selected provider, with a safe fallback."""
    cfg = options()
    try:
        if provider in ("openai", "openrouter", "compatible"):
            if provider == "openai":
                endpoint, key = "https://api.openai.com/v1", key_for(provider)
            elif provider == "openrouter":
                endpoint, key = "https://openrouter.ai/api/v1", key_for(provider)
            else:
                endpoint, key = allowed_endpoint(cfg.get("compatible_url", "")), key_for(provider)
            headers = {"Authorization": "Bearer " + key} if key else {}
            response = requests.get(endpoint + "/models", headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json().get("data", [])
            items = [{"id": m["id"], "name": m.get("name") or m["id"]}
                     for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]
        elif provider == "anthropic":
            key = key_for(provider)
            if not key:
                raise RuntimeError("Configure a chave Anthropic nas opções do App")
            response = requests.get("https://api.anthropic.com/v1/models",
                                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=20)
            response.raise_for_status()
            data = response.json().get("data", [])
            items = [{"id": m["id"], "name": m.get("display_name") or m["id"]}
                     for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]
        elif provider == "gemini":
            key = key_for(provider)
            if not key:
                raise RuntimeError("Configure a chave Gemini nas opções do App")
            response = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                                    params={"key": key, "pageSize": 1000}, timeout=20)
            response.raise_for_status()
            data = response.json().get("models", [])
            items = [{"id": m["name"].removeprefix("models/"), "name": m.get("displayName") or m["name"]}
                     for m in data if isinstance(m, dict) and "generateContent" in m.get("supportedGenerationMethods", [])]
        elif provider == "ollama":
            endpoint = allowed_endpoint(cfg.get("ollama_url", os.getenv("OLLAMA_URL", "http://localhost:11434")), local=True)
            response = requests.get(endpoint + "/api/tags", timeout=20)
            response.raise_for_status()
            data = response.json().get("models", [])
            items = [{"id": m["name"], "name": m.get("details", {}).get("family", m["name"])}
                     for m in data if isinstance(m, dict) and isinstance(m.get("name"), str)]
        elif provider == "local":
            items = []
        else:
            raise ValueError("Provedor desconhecido")
        deduped = {m["id"]: m for m in items if m["id"]}
        return {"models": sorted(deduped.values(), key=lambda m: m["id"].lower()), "source": "provider"}
    except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
        LOGGER.debug("Model catalog failed provider=%s: %s", provider, exc)
        return {"models": [{"id": model, "name": model} for model in [DEFAULT_MODELS[provider]]],
                "source": "fallback", "message": str(exc) if isinstance(exc, RuntimeError) else "Catálogo indisponível; usando modelo padrão."}


def allowed_endpoint(url, local=False):
    parsed = urlparse(url)
    if parsed.scheme not in (("http", "https") if local else ("https",)) or not parsed.hostname:
        raise ValueError("URL do provedor inválida")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        ips = [ipaddress.ip_address(entry[4][0]) for entry in addresses]
    except (OSError, ValueError) as exc:
        raise ValueError("Não foi possível validar o host do provedor") from exc
    local_ips = all((ip.is_private or ip.is_loopback) and not ip.is_link_local for ip in ips)
    public_ips = all(not (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved) for ip in ips)
    if not ips or not (local_ips if local else public_ips):
        raise ValueError("O endereço do provedor não é permitido")
    return url.rstrip("/")


def ask(provider, model, prompt, image=None, mime="image/jpeg"):
    if provider not in DEFAULT_MODELS:
        raise ValueError("Provedor desconhecido")
    model = model or DEFAULT_MODELS[provider]
    if not model or len(model) > 100:
        raise ValueError("Modelo inválido")
    LOGGER.debug("LLM ask provider=%s model=%s prompt_chars=%d image=%s",
                 provider, model, len(prompt), bool(image))
    if provider in ("openai", "compatible", "openrouter"):
        key = key_for(provider)
        if not key:
            raise RuntimeError("Configure a chave do provedor nas opções do App")
        if provider == "openai":
            endpoint = "https://api.openai.com/v1"
        elif provider == "openrouter":
            endpoint = "https://openrouter.ai/api/v1"
        else:
            endpoint = allowed_endpoint(options().get("compatible_url", ""))
        content = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image_url", "image_url": {"url":
                            f"data:{mime};base64,{base64.b64encode(image).decode()}"}})
        result = _post(endpoint + "/chat/completions",
                       {"Authorization": "Bearer " + key},
                       {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 500})
        choices = result.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        text = _text(message.get("content"))
        if not text:
            LOGGER.debug("LLM empty response provider=%s choices=%d message_keys=%s finish_reason=%s",
                         provider, len(choices), sorted(message.keys()),
                         choices[0].get("finish_reason") if choices else None)
            raise RuntimeError("O provedor retornou uma resposta vazia")
        return text
    if provider == "anthropic":
        key = key_for(provider)
        if not key:
            raise RuntimeError("Configure a chave Anthropic nas opções do App")
        content = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                            "data": base64.b64encode(image).decode()}})
        result = _post("https://api.anthropic.com/v1/messages",
                       {"x-api-key": key, "anthropic-version": "2023-06-01"},
                       {"model": model, "max_tokens": 500,
                        "messages": [{"role": "user", "content": content}]})
        blocks = result.get("content") or []
        text = " ".join(x.get("text", "") for x in blocks
                        if isinstance(x, dict) and x.get("type") == "text").strip()
        if not text:
            LOGGER.debug("LLM empty response provider=anthropic stop_reason=%s blocks=%s",
                         result.get("stop_reason"),
                         [x.get("type") for x in blocks if isinstance(x, dict)])
            raise RuntimeError("O provedor retornou uma resposta vazia")
        return text
    if provider == "gemini":
        key = key_for(provider)
        if not key:
            raise RuntimeError("Configure a chave Gemini nas opções do App")
        parts = [{"text": prompt}]
        if image:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}})
        result = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       {"x-goog-api-key": key}, {"contents": [{"parts": parts}]})
        candidates = result.get("candidates") or []
        content = (candidates[0].get("content") or {}) if candidates else {}
        text = " ".join(x.get("text", "") for x in (content.get("parts") or [])
                        if isinstance(x, dict)).strip()
        if not text:
            reason = candidates[0].get("finishReason") if candidates else None
            LOGGER.debug("LLM empty response provider=gemini finish_reason=%s prompt_feedback=%s",
                         reason, result.get("promptFeedback"))
            suffix = f" ({reason})" if reason else ""
            raise RuntimeError("O provedor retornou uma resposta vazia" + suffix)
        return text
    endpoint = allowed_endpoint(options().get("ollama_url", os.getenv("OLLAMA_URL", "http://localhost:11434")), local=True)
    message = {"role": "user", "content": prompt}
    if image:
        message["images"] = [base64.b64encode(image).decode()]
    result = _post(endpoint + "/api/chat", {}, {"model": model, "messages": [message], "stream": False})
    text = _text((result.get("message") or {}).get("content"))
    if not text:
        LOGGER.debug("LLM empty response provider=ollama done=%s keys=%s",
                     result.get("done"), sorted(result.keys()))
        raise RuntimeError("O provedor retornou uma resposta vazia")
    return text
