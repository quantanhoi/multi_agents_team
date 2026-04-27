import json
import httpx

class OllamaError(Exception):
    pass

async def call_ollama(endpoint: str, model: str, messages: list, temperature: float = 0.3, max_retries: int = 2) -> dict:
    url = f"{endpoint}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature}
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
                return json.loads(content)
        except json.JSONDecodeError as e:
            last_error = e
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"Your response was not valid JSON. Error: {e}. Please return valid JSON only."})
            if attempt == max_retries:
                raise OllamaError(f"Failed to parse JSON after {max_retries} retries: {e}")
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            last_error = e
            if attempt == max_retries:
                raise OllamaError(f"Ollama API error after {max_retries} retries: {e}")
    raise OllamaError(f"Unexpected error: {last_error}")
