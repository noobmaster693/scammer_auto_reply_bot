from __future__ import annotations

import json
from typing import Callable

from google import genai
import requests

from .config import Settings
from .style import build_prompt


class AIResponder:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _gemini(self, prompt: str) -> str:
        if not self.settings.gemini_api_key:
            raise RuntimeError("Gemini key is not configured")
        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config={
                "temperature": self.settings.gemini_temperature,
                "max_output_tokens": 350,
            },
        )
        text = getattr(response, "text", "") or ""
        return text.strip()

    def _groq(self, prompt: str) -> str:
        if not self.settings.groq_api_key:
            raise RuntimeError("Groq key is not configured")
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.groq_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Follow the user's writing task exactly and return only the requested email body.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": self.settings.groq_temperature,
                "max_tokens": 350,
            },
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"Groq API {response.status_code}: {response.text[:500]}")
        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Groq response: {json.dumps(payload)[:500]}") from exc

    @staticmethod
    def _clean(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = cleaned[3:-3].strip()
            if cleaned.lower().startswith("text\n"):
                cleaned = cleaned[5:].strip()
        # Avoid accidental model-added subject labels.
        if cleaned.lower().startswith("objet:"):
            cleaned = "\n".join(cleaned.splitlines()[1:]).strip()
        return cleaned

    def generate(self, case_context: str, conversation: str, newest_body: str) -> tuple[str, str]:
        prompt = build_prompt(case_context, conversation, newest_body)
        providers: dict[str, Callable[[str], str]] = {
            "gemini": self._gemini,
            "groq": self._groq,
        }
        errors: list[str] = []

        for name in self.settings.ai_provider_order:
            if name == "gemini" and not self.settings.gemini_api_key:
                continue
            if name == "groq" and not self.settings.groq_api_key:
                continue
            try:
                text = self._clean(providers[name](prompt))
                if not text:
                    raise RuntimeError("model returned an empty response")
                if len(text) > 1800:
                    raise RuntimeError("model response was unexpectedly long")
                return text, name
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                print(f"AI provider {name} failed; trying fallback if configured: {exc}")

        raise RuntimeError("All configured AI providers failed: " + " | ".join(errors))
