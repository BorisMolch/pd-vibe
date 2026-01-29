"""
Enrichment Layer for Pure Data IR.

This module provides infrastructure for attaching LLM-generated or
human-provided semantic annotations to IR patches.
"""

import json
import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from .core import IRPatch, IREnrichment


@dataclass
class EnrichmentData:
    """Complete enrichment data for a patch."""
    schema: str = "pd-enrichment-0.1"
    patch: str = ""
    based_on_ir_sha: Optional[str] = None
    generated_at: Optional[str] = None
    generator: Optional[str] = None
    summary: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    node_roles: Dict[str, List[str]] = field(default_factory=dict)
    inlet_semantics: Dict[str, str] = field(default_factory=dict)
    outlet_semantics: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema": self.schema,
            "patch": self.patch,
            "based_on_ir_sha": self.based_on_ir_sha,
            "generated_at": self.generated_at,
            "generator": self.generator,
            "summary": self.summary,
            "roles": self.roles,
            "node_roles": self.node_roles,
            "inlet_semantics": self.inlet_semantics,
            "outlet_semantics": self.outlet_semantics,
            "notes": self.notes,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnrichmentData':
        """Create from dictionary."""
        return cls(
            schema=data.get('schema', 'pd-enrichment-0.1'),
            patch=data.get('patch', ''),
            based_on_ir_sha=data.get('based_on_ir_sha'),
            generated_at=data.get('generated_at'),
            generator=data.get('generator'),
            summary=data.get('summary'),
            roles=data.get('roles', []),
            node_roles=data.get('node_roles', {}),
            inlet_semantics=data.get('inlet_semantics', {}),
            outlet_semantics=data.get('outlet_semantics', {}),
            notes=data.get('notes', []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'EnrichmentData':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))


class EnrichmentCache:
    """
    Cache for enrichment data.

    Manages storage and retrieval of enrichment files alongside IR files.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize the enrichment cache.

        Args:
            cache_dir: Directory for storing enrichment files.
                      If None, enrichment files are stored alongside patches.
        """
        self.cache_dir = cache_dir

    def _get_enrichment_path(self, patch_path: str) -> str:
        """Get the enrichment file path for a patch."""
        if self.cache_dir:
            basename = os.path.basename(patch_path)
            name = os.path.splitext(basename)[0]
            return os.path.join(self.cache_dir, f"{name}.enrichment.json")
        else:
            base = os.path.splitext(patch_path)[0]
            return f"{base}.enrichment.json"

    def get(self, patch_path: str) -> Optional[EnrichmentData]:
        """Get enrichment data for a patch."""
        enrich_path = self._get_enrichment_path(patch_path)

        if not os.path.exists(enrich_path):
            return None

        with open(enrich_path, 'r') as f:
            return EnrichmentData.from_json(f.read())

    def save(self, patch_path: str, enrichment: EnrichmentData):
        """Save enrichment data for a patch."""
        enrich_path = self._get_enrichment_path(patch_path)

        # Ensure directory exists
        os.makedirs(os.path.dirname(enrich_path) or '.', exist_ok=True)

        with open(enrich_path, 'w') as f:
            f.write(enrichment.to_json())

    def invalidate(self, patch_path: str):
        """Remove cached enrichment for a patch."""
        enrich_path = self._get_enrichment_path(patch_path)
        if os.path.exists(enrich_path):
            os.remove(enrich_path)

    def is_valid(self, patch_path: str, ir_sha: str) -> bool:
        """
        Check if cached enrichment is still valid.

        Returns True if enrichment exists and matches the IR SHA.
        """
        enrichment = self.get(patch_path)
        if enrichment is None:
            return False
        return enrichment.based_on_ir_sha == ir_sha


class EnrichmentManager:
    """
    Manager for IR enrichment.

    Handles the lifecycle of enrichment data including validation,
    application to IR, and cache management.
    """

    def __init__(self, cache: Optional[EnrichmentCache] = None):
        """
        Initialize the enrichment manager.

        Args:
            cache: EnrichmentCache instance. Creates default if None.
        """
        self.cache = cache or EnrichmentCache()

    def create_enrichment(self, ir_patch: IRPatch,
                          generator: str = "manual") -> EnrichmentData:
        """
        Create a new enrichment data object for an IR patch.

        Args:
            ir_patch: The IR patch to enrich
            generator: Identifier for the enrichment generator

        Returns:
            New EnrichmentData instance with metadata filled in
        """
        patch_path = ir_patch.patch.path if ir_patch.patch else ""
        ir_sha = ir_patch.patch.graph_hash if ir_patch.patch else None

        return EnrichmentData(
            patch=patch_path,
            based_on_ir_sha=ir_sha,
            generated_at=datetime.now().isoformat(),
            generator=generator,
        )

    def apply_enrichment(self, ir_patch: IRPatch,
                         enrichment: EnrichmentData) -> IRPatch:
        """
        Apply enrichment data to an IR patch.

        Args:
            ir_patch: The IR patch to enrich
            enrichment: The enrichment data to apply

        Returns:
            The IR patch with enrichment applied
        """
        ir_patch.enrichment = IREnrichment(
            summary=enrichment.summary,
            roles=enrichment.roles,
            inlet_semantics=enrichment.inlet_semantics,
            outlet_semantics=enrichment.outlet_semantics,
            notes=enrichment.notes,
        )
        return ir_patch

    def load_and_apply(self, ir_patch: IRPatch,
                       validate: bool = True) -> IRPatch:
        """
        Load enrichment from cache and apply to IR patch.

        Args:
            ir_patch: The IR patch to enrich
            validate: Whether to validate enrichment against IR hash

        Returns:
            The IR patch with enrichment applied (if available)
        """
        patch_path = ir_patch.patch.path if ir_patch.patch else None
        if not patch_path:
            return ir_patch

        ir_sha = ir_patch.patch.graph_hash if ir_patch.patch else None

        # Check cache validity
        if validate and ir_sha:
            if not self.cache.is_valid(patch_path, ir_sha):
                # Enrichment is stale
                return ir_patch

        enrichment = self.cache.get(patch_path)
        if enrichment:
            return self.apply_enrichment(ir_patch, enrichment)

        return ir_patch

    def save_enrichment(self, ir_patch: IRPatch, enrichment: EnrichmentData):
        """
        Save enrichment data to cache.

        Args:
            ir_patch: The IR patch the enrichment is for
            enrichment: The enrichment data to save
        """
        patch_path = ir_patch.patch.path if ir_patch.patch else None
        if patch_path:
            self.cache.save(patch_path, enrichment)

    def generate_prompt_for_llm(self, ir_patch: IRPatch) -> str:
        """
        Generate a prompt for LLM-based enrichment.

        Args:
            ir_patch: The IR patch to generate a prompt for

        Returns:
            A prompt string suitable for an LLM
        """
        from .dsl import ir_to_dsl, DSLMode

        dsl = ir_to_dsl(ir_patch, DSLMode.COMPACT)

        prompt = f"""Analyze this Pure Data patch and provide semantic enrichment.

## Patch DSL Representation

```
{dsl}
```

## Instructions

Please provide:

1. **Summary**: A 1-2 sentence description of what this patch does.

2. **Roles**: List of functional roles this patch fulfills (e.g., "synthesizer", "effects_processor", "sequencer", "mixer", "utility").

3. **Inlet Semantics**: For each inlet, describe what data it expects.

4. **Outlet Semantics**: For each outlet, describe what data it produces.

## Response Format

Respond with JSON in this format:
```json
{{
  "summary": "Brief description of the patch",
  "roles": ["role1", "role2"],
  "inlet_semantics": {{
    "inlet#0": "Description of inlet 0",
    "inlet#1": "Description of inlet 1"
  }},
  "outlet_semantics": {{
    "outlet#0": "Description of outlet 0"
  }},
  "notes": ["Any additional observations"]
}}
```
"""
        return prompt

    def parse_llm_response(self, response: str,
                           ir_patch: IRPatch) -> EnrichmentData:
        """
        Parse an LLM response into EnrichmentData.

        Args:
            response: The LLM's response text
            ir_patch: The IR patch being enriched

        Returns:
            EnrichmentData parsed from the response
        """
        # Try to extract JSON from the response
        import re

        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("Could not find JSON in LLM response")

        data = json.loads(json_str)

        enrichment = self.create_enrichment(ir_patch, "llm")
        enrichment.summary = data.get('summary')
        enrichment.roles = data.get('roles', [])
        enrichment.inlet_semantics = data.get('inlet_semantics', {})
        enrichment.outlet_semantics = data.get('outlet_semantics', {})
        enrichment.notes = data.get('notes', [])

        return enrichment


def enrich_ir(ir_patch: IRPatch, enrichment_path: Optional[str] = None) -> IRPatch:
    """
    Load and apply enrichment to an IR patch.

    Convenience function for simple enrichment loading.

    Args:
        ir_patch: The IR patch to enrich
        enrichment_path: Optional explicit path to enrichment file

    Returns:
        The IR patch with enrichment applied (if available)
    """
    manager = EnrichmentManager()

    if enrichment_path and os.path.exists(enrichment_path):
        with open(enrichment_path, 'r') as f:
            enrichment = EnrichmentData.from_json(f.read())
        return manager.apply_enrichment(ir_patch, enrichment)

    return manager.load_and_apply(ir_patch)
