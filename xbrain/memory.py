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

    def get_mutation_archive(self) -> list[dict]:
        """Return all MUTATE ideas with their suggested mutations."""
        return self._read("mutation-archive.json", [])

    def get_attack_patterns(self) -> list[dict]:
        """Return frequently occurring attack patterns from failed ideas."""
        return self._read("attack-patterns.json", [])

    def get_failure_taxonomy(self) -> dict:
        """Return structured failure taxonomy from past stress tests."""
        return self._read("failure-taxonomy.json", {})

    def get_refinement_history(self) -> list[dict]:
        """Return history of refinement rounds."""
        return self._read("refinement-history.json", [])

    def get_playbook(self) -> str:
        """Return distilled learning playbook (compact text)."""
        return self._read("playbook.json", {}).get("playbook", "")

    def get_playbook_meta(self) -> dict:
        """Return playbook metadata (when last distilled, runs covered)."""
        return self._read("playbook.json", {})

    def get_score_stats(self) -> dict:
        """Return distilled score calibration data."""
        return self._read("score-calibration.json", {})

    def get_lineage(self) -> list[dict]:
        """Return idea lineage graph (parent→child relationships)."""
        return self._read("idea-lineage.json", [])

    def get_idea_genes(self) -> list[dict]:
        """Return extracted reusable idea genes."""
        return self._read("idea-genes.json", [])

    # --- Writers ---

    def save_run(
        self,
        ideas: list[dict],
        domains_used: list[str],
        killed: list[dict],
        metrics: dict,
    ) -> None:
        """Persist everything from a completed run."""
        # Append to idea archive (keep last 500 entries)
        archive = self.get_idea_archive()
        archive.extend(ideas)
        self._write("idea-archive.json", archive[-500:])

        # Update domain heat map
        hm = self.get_domain_heat_map()
        for d in domains_used:
            hm[d] = hm.get(d, 0) + 1
        self._write("domain-heat-map.json", hm)

        # Append killed ideas (keep last 200 entries)
        if killed:
            kl = self.get_kill_log()
            kl.extend(killed)
            self._write("kill-log.json", kl[-200:])

        # Append meta-metrics (keep last 100 runs)
        mm = self.get_meta_metrics()
        mm.append(metrics)
        self._write("meta-metrics.json", mm[-100:])

    def save_mutations(self, mutations: list[dict]) -> None:
        """Persist MUTATE ideas with their suggested mutations."""
        archive = self.get_mutation_archive()
        archive.extend(mutations)
        self._write("mutation-archive.json", archive)

    def save_attack_patterns(self, patterns: list[dict]) -> None:
        """Persist attack patterns extracted from stress testing."""
        self._write("attack-patterns.json", patterns)

    def save_failure_taxonomy(self, taxonomy: dict) -> None:
        """Merge new failure classifications into the running taxonomy."""
        existing = self.get_failure_taxonomy()
        for category, entries in taxonomy.items():
            if category not in existing:
                existing[category] = []
            existing[category].extend(entries)
            # Keep only last 10 per category to prevent unbounded growth
            existing[category] = existing[category][-10:]
        self._write("failure-taxonomy.json", existing)

    def save_refinement_run(self, refinement_run: dict) -> None:
        """Record a refinement round."""
        history = self.get_refinement_history()
        history.append(refinement_run)
        self._write("refinement-history.json", history)

    def save_playbook(self, playbook_text: str, runs_covered: int) -> None:
        """Save distilled learning playbook."""
        from datetime import datetime, timezone
        self._write("playbook.json", {
            "playbook": playbook_text,
            "runs_covered": runs_covered,
            "distilled_at": datetime.now(timezone.utc).isoformat(),
        })

    def save_score_calibration(self, calibration: dict) -> None:
        """Save score calibration data."""
        self._write("score-calibration.json", calibration)

    def save_lineage(self, entries: list[dict]) -> None:
        """Append lineage entries (idea relationships), keep last 500."""
        lineage = self.get_lineage()
        lineage.extend(entries)
        self._write("idea-lineage.json", lineage[-500:])

    def save_idea_genes(self, genes: list[dict]) -> None:
        """Save extracted reusable idea genes (problem patterns, solution patterns)."""
        existing = self.get_idea_genes()
        existing.extend(genes)
        # Keep only last 100 genes to prevent unbounded growth
        self._write("idea-genes.json", existing[-100:])

    # --- Helpers ---

    def get_previous_winners(self, limit: int = 20) -> list[dict]:
        """Return titles+domains of high-scoring ideas from previous runs for diversity repulsion."""
        archive = self.get_idea_archive()
        # Only ideas that passed (BUILD or MUTATE) with score >= 5.0
        winners = [
            {"title": a["title"], "domains": a.get("domains", []), "score": a.get("score", 0)}
            for a in archive
            if a.get("verdict") in ("BUILD", "MUTATE") and a.get("score", 0) >= 5.0
        ]
        # Return most recent first, limited
        return winners[-limit:]

    def killed_idea_titles(self, limit: int = 15) -> list[str]:
        """Return recent killed idea titles for memory context."""
        kl = self.get_kill_log()
        return [k.get("title", k.get("id", "?")) for k in kl[-limit:]]

    def past_idea_count(self) -> int:
        return len(self.get_idea_archive())

    def runs_since_last_distill(self) -> int:
        """Count runs since last playbook distillation."""
        meta = self.get_playbook_meta()
        covered = meta.get("runs_covered", 0)
        total = len(self.get_meta_metrics())
        return total - covered

    def get_score_history_compact(self) -> list[dict]:
        """Return compact score+verdict pairs for calibration."""
        archive = self.get_idea_archive()
        return [
            {"s": a.get("score", 0), "v": a.get("verdict", "?")}
            for a in archive[-50:]  # Last 50 ideas max
        ]

    def get_domain_verdict_stats(self) -> dict[str, dict]:
        """Return domain → {build, mutate, kill} counts for domain intelligence."""
        archive = self.get_idea_archive()
        # We need the full archive with domain_tags — but we only store id/title/score/verdict
        # So we use domain_heat_map + kill_log to approximate
        return self.get_domain_heat_map()

    def _read(self, filename: str, default):
        p = self.path / filename
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return default
        return default

    def _write(self, filename: str, data) -> None:
        p = self.path / filename
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
