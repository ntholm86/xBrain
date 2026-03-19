"""Thin wrapper around the Anthropic API with JSON extraction."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import threading
import time

import anthropic


class LLMClient:
    """Sends prompts to Claude and returns parsed JSON."""

    # Rolling window for token-aware throttling (output tokens/min).
    _OUTPUT_TOKEN_LIMIT = 8000   # stay under 10k/min with headroom
    _WINDOW_SECONDS = 60

    def __init__(self, api_key: str, model: str, max_tokens: int = 16384):
        self.client = anthropic.Anthropic(api_key=api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._phase_token_log: list[dict] = []
        self._token_lock = threading.Lock()
        # Token-aware throttling: list of (timestamp, output_tokens)
        self._token_window: list[tuple[float, int]] = []

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        model_override: str | None = None,
        phase: str = "",
    ) -> dict | list:
        """Call the LLM and extract JSON from the response. Retries on transient errors."""
        use_model = model_override or self.model
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=use_model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                break
            except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                print(f"[RETRY] {type(e).__name__}, attempt {attempt + 1}/{max_retries}, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)

        self._record_usage(use_model, phase, response.usage)

        text = response.content[0].text
        truncated = response.stop_reason == "max_tokens"
        return self._extract_json(text, truncated=truncated)

    async def generate_json_async(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
        model_override: str | None = None,
        phase: str = "",
    ) -> dict | list:
        """Async version of generate_json for parallel LLM calls."""
        use_model = model_override or self.model
        max_retries = 6

        for attempt in range(max_retries):
            try:
                await self._throttle()
                response = await self._async_client.messages.create(
                    model=use_model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                break
            except anthropic.RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                wait = self._get_retry_after(e) or min(60, 15 * (2 ** attempt))
                print(f"[RETRY] RateLimitError, attempt {attempt + 1}/{max_retries}, waiting {wait:.0f}s...", file=sys.stderr)
                await asyncio.sleep(wait)
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                print(f"[RETRY] {type(e).__name__}, attempt {attempt + 1}/{max_retries}, waiting {wait}s...", file=sys.stderr)
                await asyncio.sleep(wait)

        self._record_usage(use_model, phase, response.usage)

        text = response.content[0].text
        truncated = response.stop_reason == "max_tokens"
        return self._extract_json(text, truncated=truncated)

    def _record_usage(self, model: str, phase: str, usage) -> None:
        with self._token_lock:
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
            self._phase_token_log.append({
                "phase": phase or "unknown",
                "model": model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            })
            self._token_window.append((time.time(), usage.output_tokens))

    def _tokens_in_window(self) -> int:
        """Return total output tokens in the rolling window."""
        cutoff = time.time() - self._WINDOW_SECONDS
        with self._token_lock:
            self._token_window = [(t, n) for t, n in self._token_window if t > cutoff]
            return sum(n for _, n in self._token_window)

    async def _throttle(self) -> None:
        """Wait if we're approaching the output token rate limit."""
        while True:
            used = self._tokens_in_window()
            if used < self._OUTPUT_TOKEN_LIMIT:
                return
            # Calculate how long until enough tokens expire from the window
            cutoff = time.time() - self._WINDOW_SECONDS
            with self._token_lock:
                oldest = min((t for t, _ in self._token_window if t > cutoff), default=time.time())
            wait = max(1.0, oldest + self._WINDOW_SECONDS - time.time() + 0.5)
            print(f"[THROTTLE] {used}/{self._OUTPUT_TOKEN_LIMIT} output tokens/min used, pausing {wait:.0f}s...", file=sys.stderr)
            await asyncio.sleep(wait)

    @staticmethod
    def _get_retry_after(e: anthropic.RateLimitError) -> float:
        """Extract retry-after from the API response headers, fallback to default."""
        try:
            val = e.response.headers.get("retry-after")
            if val:
                return max(1.0, float(val))
        except (AttributeError, ValueError):
            pass
        return 0

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str, *, truncated: bool = False) -> dict | list:
        """Extract JSON from an LLM response, handling code blocks and truncation."""
        # 1. Try ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 2. Try to find raw JSON starting with { or [
        for i, ch in enumerate(text):
            if ch in "{[":
                # Find the matching closing bracket
                depth = 0
                close = "}" if ch == "{" else "]"
                for j in range(i, len(text)):
                    if text[j] == ch:
                        depth += 1
                    elif text[j] == close:
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i : j + 1])
                        except json.JSONDecodeError:
                            break
                break

        # 3. Last resort: try the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 4. If truncated, try to repair by closing open brackets/braces
        if truncated:
            repaired = LLMClient._repair_truncated_json(text)
            if repaired is not None:
                print("[WARN] LLM response was truncated; recovered partial JSON.", file=sys.stderr)
                return repaired

        print("[ERROR] Could not parse JSON from LLM response. First 500 chars:", file=sys.stderr)
        print(text[:500], file=sys.stderr)
        raise ValueError("No valid JSON found in LLM response")

    @staticmethod
    def _repair_truncated_json(text: str) -> dict | list | None:
        """Attempt to recover usable JSON from a truncated response."""
        # Find the JSON start
        json_start = -1
        open_char = None
        for i, ch in enumerate(text):
            if ch in "{[":
                json_start = i
                open_char = ch
                break
        if json_start == -1:
            return None

        fragment = text[json_start:]

        # Strip trailing incomplete string values (cut mid-string)
        # Remove a dangling " that's not closed
        fragment = re.sub(r',\s*"[^"]*$', '', fragment)
        fragment = re.sub(r':"[^"]*$', ':""', fragment)
        fragment = re.sub(r',\s*$', '', fragment)

        # Count unclosed brackets/braces and close them
        stack = []
        in_string = False
        escape = False
        for ch in fragment:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in '{[':
                stack.append('}' if ch == '{' else ']')
            elif ch in '}]' and stack:
                stack.pop()

        # Close everything that's still open
        fragment += ''.join(reversed(stack))

        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            return None
