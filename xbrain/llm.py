"""Thin wrapper around the Anthropic API with JSON extraction."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time

import anthropic

from xbrain.log import log as _log, log_warn as _log_warn, log_error as _log_error


class LLMClient:
    """Sends prompts to Claude and returns parsed JSON."""

    # Rolling window for token-aware throttling (output tokens/min).
    _OUTPUT_TOKEN_LIMIT = 40_000  # generous; retry-after handles real 429s
    _WINDOW_SECONDS = 60

    def __init__(self, api_key: str, model: str, max_tokens: int = 16384):
        self.client = anthropic.Anthropic(api_key=api_key, timeout=300.0)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key, timeout=300.0)
        self.model = model
        self.max_tokens = max_tokens
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._phase_token_log: list[dict] = []
        self._token_lock = threading.Lock()
        self._async_token_lock = asyncio.Lock()
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
        max_tokens: int | None = None,
    ) -> dict | list:
        """Call the LLM and extract JSON from the response. Retries on transient errors."""
        use_model = model_override or self.model
        use_max_tokens = max_tokens or self.max_tokens
        max_retries = 6

        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=use_model,
                    max_tokens=use_max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                break
            except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = min(60, 5 * (2 ** attempt))
                _log_warn("LLM", f"{type(e).__name__}, attempt {attempt + 1}/{max_retries}, waiting {wait}s...")
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
        max_tokens: int | None = None,
    ) -> dict | list:
        """Async version of generate_json for parallel LLM calls."""
        use_model = model_override or self.model
        use_max_tokens = max_tokens or self.max_tokens
        max_retries = 6

        for attempt in range(max_retries):
            try:
                await self._throttle()
                response = await self._async_client.messages.create(
                    model=use_model,
                    max_tokens=use_max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                break
            except anthropic.RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                wait = self._get_retry_after(e) or min(60, 15 * (2 ** attempt))
                _log_warn("LLM", f"RateLimitError, attempt {attempt + 1}/{max_retries}, waiting {wait:.0f}s...")
                await asyncio.sleep(wait)
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = min(60, 5 * (2 ** attempt))
                _log_warn("LLM", f"{type(e).__name__}, attempt {attempt + 1}/{max_retries}, waiting {wait}s...")
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
            _log_warn("LLM", f"{used}/{self._OUTPUT_TOKEN_LIMIT} output tokens/min used, pausing {wait:.0f}s...")
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
        # 0. Strip leading/trailing fences unconditionally — LLMs sometimes
        #    wrap JSON in ```json despite instructions.  This normalisation
        #    prevents edge-cases where backticks inside string values confuse
        #    the fence-aware regex below.
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove opening fence line
            first_nl = stripped.find("\n")
            if first_nl != -1:
                stripped = stripped[first_nl + 1:]
            # Remove trailing fence if present
            if stripped.rstrip().endswith("```"):
                stripped = stripped.rstrip()[:-3].rstrip()
            text_defenced = stripped
        else:
            text_defenced = text

        # 1. Try parsing the defenced text directly
        try:
            return json.loads(text_defenced.strip())
        except json.JSONDecodeError:
            pass

        # 1b. Try fixing unescaped quotes
        try:
            return json.loads(LLMClient._fix_unescaped_quotes(text_defenced.strip()))
        except (json.JSONDecodeError, Exception):
            pass

        # 1c. Try truncation repair on defenced text
        repaired = LLMClient._repair_truncated_json(text_defenced.strip())
        if repaired is not None:
            _log_warn("LLM", "JSON was truncated; recovered partial JSON.")
            return repaired

        # Strip remaining markdown fences so they don't interfere with raw search
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = re.sub(r"\n?\s*```", "", cleaned).strip()

        # 3. Try to find raw JSON starting with { or [
        for i, ch in enumerate(cleaned):
            if ch in "{[":
                # Find the matching closing bracket
                depth = 0
                close = "}" if ch == "{" else "]"
                for j in range(i, len(cleaned)):
                    if cleaned[j] == ch:
                        depth += 1
                    elif cleaned[j] == close:
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[i : j + 1])
                        except json.JSONDecodeError:
                            break
                # Brackets never balanced — try truncation repair on everything from { onwards
                repaired = LLMClient._repair_truncated_json(cleaned[i:])
                if repaired is not None:
                    _log_warn("LLM", "Unbalanced JSON brackets; recovered partial JSON.")
                    return repaired
                break

        # 4. Last resort: try the whole cleaned text
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 5. Final fallback: try repair on cleaned text
        repaired = LLMClient._repair_truncated_json(cleaned)
        if repaired is not None:
            _log_warn("LLM", "LLM response was truncated; recovered partial JSON.")
            return repaired

        _log_error("LLM", f"Could not parse JSON from LLM response. First 500 chars: {text[:500]}")
        raise ValueError("No valid JSON found in LLM response")

    @staticmethod
    def _fix_unescaped_quotes(text: str) -> str:
        """Fix unescaped double quotes inside JSON string values.

        Heuristic: a closing \" is real if the next non-whitespace char is
        one of , } ] : or end-of-text.  Otherwise it's an unescaped internal
        quote and gets escaped to \\\".
        """
        result: list[str] = []
        i = 0
        in_string = False
        while i < len(text):
            ch = text[i]
            if not in_string:
                result.append(ch)
                if ch == '"':
                    in_string = True
                i += 1
            else:
                if ch == '\\':
                    result.append(text[i:i + 2] if i + 1 < len(text) else ch)
                    i += 2 if i + 1 < len(text) else 1
                elif ch == '"':
                    j = i + 1
                    while j < len(text) and text[j] in ' \t\n\r':
                        j += 1
                    if j >= len(text) or text[j] in ',}]:':
                        result.append('"')
                        in_string = False
                        i += 1
                    else:
                        result.append('\\"')
                        i += 1
                else:
                    result.append(ch)
                    i += 1
        return ''.join(result)

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
