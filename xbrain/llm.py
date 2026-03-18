"""Thin wrapper around the Anthropic API with JSON extraction."""

from __future__ import annotations

import json
import re
import sys

import anthropic


class LLMClient:
    """Sends prompts to Claude and returns parsed JSON."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 16384):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> dict | list:
        """Call the LLM and extract JSON from the response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens

        text = response.content[0].text
        truncated = response.stop_reason == "max_tokens"
        return self._extract_json(text, truncated=truncated)

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
