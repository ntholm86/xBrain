"""Cross-session memory management for xBrain."""

from __future__ import annotations

import json
from pathlib import Path


class MemoryStore:
    """Read/write persistent memory for idea archive, domain heat map, etc."""

    def __init__(self, persistent_path: str | Path = "./xbrain-memory/persistent"):
        self.path = Path(persistent_path)
        self.path.mkdir(parents=True, exist_ok=True)

    # --- Readers ---

    def get_idea_archive(self) -> list[dict]:
        return self._read("idea-archive.json", [])

    def get_domain_heat_map(self) -> dict[str, int]:
        return self._read("domain-heat-map.json", {})

    def get_kill_log(self) -> list[dict]:
        return self._read("kill-log.json", [])

    def get_meta_metrics(self) -> list[dict]:
        return self._read("meta-metrics.json", [])

    # --- Writers ---

    def save_run(
        self,
        ideas: list[dict],
        domains_used: list[str],
        killed: list[dict],
        metrics: dict,
    ) -> None:
        """Persist everything from a completed run."""
        # Append to idea archive
        archive = self.get_idea_archive()
        archive.extend(ideas)
        self._write("idea-archive.json", archive)

        # Update domain heat map
        hm = self.get_domain_heat_map()
        for d in domains_used:
            hm[d] = hm.get(d, 0) + 1
        self._write("domain-heat-map.json", hm)

        # Append killed ideas
        if killed:
            kl = self.get_kill_log()
            kl.extend(killed)
            self._write("kill-log.json", kl)

        # Append meta-metrics
        mm = self.get_meta_metrics()
        mm.append(metrics)
        self._write("meta-metrics.json", mm)

    # --- Helpers ---

    def killed_idea_titles(self, limit: int = 15) -> list[str]:
        """Return recent killed idea titles for memory context."""
        kl = self.get_kill_log()
        return [k.get("title", k.get("id", "?")) for k in kl[-limit:]]

    def past_idea_count(self) -> int:
        return len(self.get_idea_archive())

    def _read(self, filename: str, default):
        p = self.path / filename
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return default

    def _write(self, filename: str, data) -> None:
        p = self.path / filename
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
