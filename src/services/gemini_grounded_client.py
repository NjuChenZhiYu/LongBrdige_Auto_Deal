"""Gemini grounded search helper for peer benchmarking."""
from __future__ import annotations

import logging
from typing import Dict, Optional

from config.settings import Settings

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - optional dependency
    genai = None
    types = None


class GeminiGroundedClient:
    """Minimal grounded-search client for industry peer benchmarking."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> None:
        self.api_key = (api_key or Settings.LLM_API_KEY or "").strip()
        self.model = (model or Settings.LLM_MODEL or "gemini-2.5-pro").strip()
        self.temperature = temperature
        self._client = None

        if not self.api_key:
            logger.warning("[Grounded] API key is empty, grounded search disabled.")
            return
        if genai is None or types is None:
            logger.warning("[Grounded] google-genai is not installed, grounded search disabled.")
            return
        try:
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.warning(f"[Grounded] Failed to init Gemini client: {e}")
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def generate_grounded_content(self, prompt_text: str) -> Dict[str, Any]:
        """
        Single-call grounded generation: one prompt in, one grounded answer out.
        """
        if not self.enabled:
            return {"ok": False, "text": "", "error": "grounded client disabled"}
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=self.temperature,
                ),
            )
            text = (getattr(response, "text", None) or "").strip()
            if not text:
                return {"ok": False, "text": "", "error": "empty grounded response"}
            return {"ok": True, "text": text, "error": None}
        except Exception as e:
            logger.warning(f"[Grounded] grounded generation failed: {e}")
            return {"ok": False, "text": "", "error": str(e)}
