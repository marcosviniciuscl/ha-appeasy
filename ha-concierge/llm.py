"""Read-only chat adapters. Keys are configured in Supervisor App options."""
import base64
import json
import os
import ipaddress
import socket
import requests
from urllib.parse import urlparse


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


def _post(url, headers, body):
    try:
        r = requests.post(url, headers=headers, json=body, timeout=45)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("O provedor de IA não respondeu") from exc


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
        return result["choices"][0]["message"]["content"]
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
        return " ".join(x.get("text", "") for x in result["content"] if x.get("type") == "text")
    if provider == "gemini":
        key = key_for(provider)
        if not key:
            raise RuntimeError("Configure a chave Gemini nas opções do App")
        parts = [{"text": prompt}]
        if image:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}})
        result = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       {"x-goog-api-key": key}, {"contents": [{"parts": parts}]})
        return " ".join(x.get("text", "") for x in result["candidates"][0]["content"]["parts"])
    endpoint = allowed_endpoint(options().get("ollama_url", os.getenv("OLLAMA_URL", "http://localhost:11434")), local=True)
    message = {"role": "user", "content": prompt}
    if image:
        message["images"] = [base64.b64encode(image).decode()]
    result = _post(endpoint + "/api/chat", {}, {"model": model, "messages": [message], "stream": False})
    return result["message"]["content"]
