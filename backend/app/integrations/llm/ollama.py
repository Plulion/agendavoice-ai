import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from app.core.config import settings

class OllamaChatProvider:
    """Local-model adapter. It has no database access and exposes no business tools."""
    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps({"model": settings.ollama_model, "messages": messages, "stream": False}).encode("utf-8")
        request = Request(settings.ollama_base_url.rstrip("/") + "/api/chat", data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"No se pudo conectar con Ollama local: {exc}") from exc
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama devolvió una respuesta vacía o inválida")
        return content.strip()
