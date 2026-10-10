"""Appel au LLM de l'assistant (étape 72).

Fournisseurs : gemini, anthropic, ollama (variable LLM_PROVIDER).
Si le fournisseur choisi n'a pas de clé valide mais qu'un autre en a une, on bascule dessus :
un .env.local qui mélange plusieurs réglages ne casse donc pas l'assistant.
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Les noms de modèles Gemini changent vite : GEMINI_MODEL les fixe, sinon on essaie ceux-ci,
# puis on interroge la liste des modèles du compte.
GEMINI_CANDIDATES = [
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-2.0-flash",
]
_working_gemini_model: str | None = None


class LLMError(RuntimeError):
    pass


def _valid_key(name: str) -> bool:
    value = (os.getenv(name) or "").strip()
    return len(value) > 10 and value.lower() not in {"change_me", "votre_cle", "your_key"}


def resolve_provider() -> str:
    """Fournisseur effectivement utilisable (voir la docstring du module)."""
    wanted = (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    keys = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    if wanted == "ollama" or wanted not in keys:
        return "ollama" if wanted == "ollama" else wanted
    if _valid_key(keys[wanted]):
        return wanted
    for other, env_name in keys.items():
        if other != wanted and _valid_key(env_name):
            log.warning("LLM_PROVIDER=%s sans clé valide : bascule sur %s", wanted, other)
            return other
    return wanted


NO_KEY_MESSAGE = (
    "Aucune clé LLM valide : renseignez GEMINI_API_KEY (ou ANTHROPIC_API_KEY) dans .env.local, "
    "ou utilisez LLM_PROVIDER=ollama, puis redémarrez l'API."
)


def call_llm(prompt: str) -> str:
    provider = resolve_provider()
    needs_key = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    if provider in needs_key and not _valid_key(needs_key[provider]):
        raise LLMError(NO_KEY_MESSAGE)
    try:
        if provider == "ollama":
            return _call_ollama(prompt)
        if provider == "gemini":
            return _call_gemini(prompt)
        if provider == "anthropic":
            return _call_anthropic(prompt)
    except httpx.HTTPError as exc:
        raise LLMError(f"Appel LLM impossible ({provider}) : {exc}") from exc
    raise LLMError(f"LLM_PROVIDER inconnu : {provider} (gemini, anthropic ou ollama)")


# --------------------------------------------------------------------------- Gemini
def _gemini_generate(model: str, prompt: str, key: str) -> httpx.Response:
    return httpx.post(
        f"{GEMINI_BASE}/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "content-type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500},
        },
        timeout=60,
    )


def _discover_gemini_models(key: str) -> list[str]:
    resp = httpx.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": key}, timeout=30)
    if resp.status_code != 200:
        return []
    names = [
        m["name"].split("/", 1)[-1]
        for m in resp.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    flash = [n for n in names if "flash" in n and "image" not in n and "tts" not in n]
    return sorted(flash, reverse=True)[:5]


def _call_gemini(prompt: str) -> str:
    global _working_gemini_model
    if not _valid_key("GEMINI_API_KEY"):
        raise LLMError("GEMINI_API_KEY non renseignée dans .env / .env.local.")
    key = os.environ["GEMINI_API_KEY"].strip()
    forced = (os.getenv("GEMINI_MODEL") or "").strip()
    models = [forced] if forced else [_working_gemini_model, *GEMINI_CANDIDATES]
    tried, discovered = [], False
    queue = [m for m in models if m]
    while queue:
        model = queue.pop(0)
        if model in tried:
            continue
        tried.append(model)
        resp = _gemini_generate(model, prompt, key)
        if resp.status_code == 404:  # modèle retiré ou inconnu : on passe au suivant
            if not queue and not forced and not discovered:
                discovered = True
                queue = _discover_gemini_models(key)
            continue
        if resp.status_code in (400, 401, 403):
            detail = resp.json().get("error", {}).get("message", resp.text)[:200]
            raise LLMError(f"Clé Gemini refusée ou requête invalide : {detail}")
        if resp.status_code == 429:
            raise LLMError("Quota Gemini dépassé (429) : patientez ou changez de clé/modèle.")
        if resp.status_code == 503:
            if not queue and not forced and not discovered:
                discovered = True
                queue = _discover_gemini_models(key)
                continue
            raise LLMError(
                f"Gemini 503 sur {model} : modèle indisponible. "
                "Définissez GEMINI_MODEL=gemini-3.1-flash-lite dans .env"
            )
        resp.raise_for_status()
        _working_gemini_model = model
        candidates = resp.json().get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMError("Gemini n'a renvoyé aucun texte (réponse bloquée ou vide).")
        return text
    raise LLMError(f"Aucun modèle Gemini disponible (essayés : {', '.join(tried)}).")


# --------------------------------------------------------------------------- Anthropic
def _call_anthropic(prompt: str) -> str:
    if not _valid_key("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY non renseignée (ou utilisez LLM_PROVIDER=gemini).")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"].strip(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            "max_tokens": 700,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    if resp.status_code in (401, 403):
        raise LLMError("Clé Anthropic refusée (401/403).")
    resp.raise_for_status()
    return "".join(b.get("text", "") for b in resp.json()["content"] if b["type"] == "text")


# --------------------------------------------------------------------------- Ollama
def _call_ollama(prompt: str) -> str:
    base = os.getenv("OLLAMA_URL", "http://localhost:11434")
    resp = httpx.post(
        f"{base}/api/generate",
        json={"model": os.getenv("OLLAMA_MODEL", "llama3.1"), "prompt": prompt, "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")
