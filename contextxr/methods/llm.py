"""Zero-shot and few-shot LLM facet suggestion (paper §4.2.2, Appendix A).

The LLM receives the current task and environment, a catalog of all facets (with
descriptions, capabilities and facet-graph links) and, for few-shot prompting,
historical scenarios selected under a transfer condition:

    user         same user, other task and other environment
    task         other users, same task, other environment
    environment  other users, same environment, other task
    user+task    same user and task, other environment
    user+env     same user and environment, other task
    task+env     other users, same task and environment

Task/environment labels are matched exactly. If no historical scenario matches,
`suggest` raises `SuggestionUnavailable("no_matching_examples")`. For next facet
suggestion the facets already placed (with their relevance tier) are added to the
prompt.

All calls go through `LLMCache`. By default (`mode="replay"`) responses are replayed
from `cache/llm/` and a cache miss raises `CacheMiss`; `mode="live"` calls Gemini
(model `gemini-3-flash-preview`, temperature 0.2) for misses and records the
responses. Live mode requires the [llm] extra and an API key in GOOGLE_API_KEY or
GEMINI_API_KEY.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from contextxr.data.schema import RELEVANCE_RANK, Context, Dataset, FacetCatalog, FacetId, Scenario, normalize_tier
from contextxr.methods.base import SuggestionUnavailable, Suggester
from contextxr.methods.llm_cache import LLMCache, LLMRequest

DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_TEMPERATURE = 0.2


@dataclass(frozen=True)
class TransferCondition:
    key: str
    label: str
    description: str
    same_user: Optional[bool]
    same_task: Optional[bool]
    same_environment: Optional[bool]
    diversify_users: bool = False


ZERO_SHOT = TransferCondition("zero_shot", "Cold-start", "General inference from current task and environment only.", None, None, None)
CONDITIONS: Dict[str, TransferCondition] = {
    c.key: c
    for c in [
        TransferCondition("user", "U-transfer", "Same user from other tasks and environments.", True, False, False),
        TransferCondition("task", "T-transfer", "Task prior from other users across environments.", False, True, False, True),
        TransferCondition("environment", "E-transfer", "Environment prior from other users.", False, False, True, True),
        TransferCondition("user+task", "UT-transfer", "Same user and task across environments.", True, True, False),
        TransferCondition("user+env", "UE-transfer", "Same user and environment across tasks.", True, False, True),
        TransferCondition("task+env", "TE-transfer", "Same task and environment from other users.", False, True, True, True),
    ]
}
CONDITION_ALIASES = {
    "u": "user", "t": "task", "e": "environment", "env": "environment",
    "ut": "user+task", "ue": "user+env", "user+environment": "user+env",
    "te": "task+env", "task+environment": "task+env",
}
# Keys used by the paper's research code (cache provenance).
LEGACY_CONDITION_KEYS = {
    "zero_shot": "static_cold_start", "user": "static_u_transfer", "task": "static_t_transfer",
    "environment": "static_e_transfer", "user+task": "static_ut_transfer", "user+env": "static_ue_transfer",
    "task+env": "static_te_transfer",
}
_PROMPT_LABEL = {"primary": "primary", "peripheral": "secondary", "ambient": "ambient"}


def _template(name: str) -> str:
    return resources.files("contextxr.methods").joinpath(f"prompts/{name}").read_text(encoding="utf-8")


def resolve_condition(condition: Optional[str]) -> TransferCondition:
    if condition in (None, "", "zero_shot", "zero-shot", "cold_start"):
        return ZERO_SHOT
    key = CONDITION_ALIASES.get(condition.lower(), condition.lower())
    if key not in CONDITIONS:
        raise ValueError(f"Unknown transfer condition '{condition}'. Choose from {sorted(CONDITIONS)}")
    return CONDITIONS[key]


# ---------------------------------------------------------------------------
# Catalog text
# ---------------------------------------------------------------------------


def catalog_rows(catalog: FacetCatalog) -> List[Dict]:
    by_source_cap: Dict[Tuple[str, str], str] = {(e.source, e.capability): e.target for e in catalog.edges}
    rows = []
    for app in catalog.apps.values():
        for fid in app.facet_ids:
            facet = catalog.facets[fid]
            links: List[str] = []
            for cap in facet.capabilities:
                target = by_source_cap.get((fid, cap))
                if target and target != fid and target not in links:
                    links.append(target)
            caps = [c for c in facet.capabilities if not c.startswith("open_")]
            caps += [c for c in facet.capabilities if c.startswith("open_") and c not in caps]
            rows.append(
                {
                    "facet_id": fid,
                    "app": app.app_id,
                    "name": facet.name or fid,
                    "description": " ".join(facet.description.split()),
                    "is_entry_facet": facet.is_entry,
                    "linked_facets": links,
                    "capabilities": list(dict.fromkeys(caps)),
                }
            )
    return rows


def catalog_text(catalog: FacetCatalog) -> str:
    return "\n".join(f"{i}. {json.dumps(row, ensure_ascii=True)}" for i, row in enumerate(catalog_rows(catalog), start=1))


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------


def _matches(cond: TransferCondition, target: Context, other: Context) -> bool:
    return (
        (other.user == target.user) == cond.same_user
        and (other.task == target.task) == cond.same_task
        and (other.environment == target.environment) == cond.same_environment
    )


def support_pool(cond: TransferCondition, context: Context, dataset: Dataset, exclude: Optional[str]) -> List[Scenario]:
    pool = [s for sid, s in dataset.scenarios.items() if sid != exclude and _matches(cond, context, s.context)]
    pool.sort(key=lambda s: (s.context.user, s.context.environment, s.context.task, s.scenario_id))
    return pool


def select_examples(pool: Sequence[Scenario], cond: TransferCondition, max_examples: Optional[int]) -> List[Scenario]:
    """All examples, or the first `max_examples` (one per user first for task/environment conditions)."""
    if max_examples is None:
        return list(pool)
    if max_examples <= 0:
        return []
    if len(pool) <= max_examples:
        return list(pool)
    if not cond.diversify_users:
        return list(pool[:max_examples])
    picked: List[Scenario] = []
    users = set()
    for s in pool:
        if s.context.user in users:
            continue
        picked.append(s)
        users.add(s.context.user)
        if len(picked) >= max_examples:
            return picked
    for s in pool:
        if s not in picked:
            picked.append(s)
            if len(picked) >= max_examples:
                break
    return picked


def _facet_display(catalog: FacetCatalog, facet_id: str) -> Tuple[str, str]:
    if facet_id in catalog:
        facet = catalog.facet(facet_id)
        return catalog.apps[facet.app_id].name, facet.name or facet_id
    prefix = facet_id.split(".", 1)[0]
    return prefix, facet_id


def support_block(examples: Sequence[Scenario], catalog: FacetCatalog, max_facets_per_tier: int = 0) -> str:
    if not examples:
        return "None"
    template = _template("support_example.txt")
    blocks = []
    for index, s in enumerate(examples, start=1):
        groups: Dict[str, List[str]] = {"primary": [], "secondary": [], "ambient": []}
        for fid, tier in sorted(s.targets, key=lambda kv: (-RELEVANCE_RANK.get(normalize_tier(kv[1]), 0), kv[0])):
            label = _PROMPT_LABEL.get(normalize_tier(tier))
            if label is None:
                continue
            app_name, facet_name = _facet_display(catalog, fid)
            groups[label].append(f"{app_name} / {facet_name} [{fid}]")
        lines = []
        for label in ("primary", "secondary", "ambient"):
            items = groups[label][:max_facets_per_tier] if max_facets_per_tier > 0 else groups[label]
            if items:
                lines.append(f"  - {label}: " + "; ".join(items))
        if not lines:
            lines.append("  - (no facet annotations)")
        blocks.append(
            template.format(
                index=index, scenario_key=s.scenario_id, participant_id=s.context.user,
                task_id=s.context.task, environment_id=s.context.environment, facet_lines="\n".join(lines),
            )
        )
    return "\n\n".join(blocks)


def history_block(history: Sequence[str], catalog: FacetCatalog) -> str:
    if not history:
        return ""
    line = _template("placed_facet_line.txt")
    lines = []
    for idx, fid in enumerate(history, start=1):
        app_name, facet_name = _facet_display(catalog, str(fid))
        lines.append(line.format(index=idx, facet_id=str(fid), app_name=app_name, facet_name=facet_name,
                                 relevance=getattr(fid, "tier", "") or "unknown"))
    return _template("next_facet_history.txt").format(placed_facet_lines="\n".join(lines))


def build_prompts(
    cond: TransferCondition,
    context: Context,
    catalog_txt: str,
    *,
    examples_block: str = "",
    details: str = "",
    top_k: int = 10,
) -> Tuple[str, str]:
    details_block = f"\n{details.strip()}\n" if details.strip() else ""
    if cond is ZERO_SHOT:
        system = _template("system_zero_shot.txt")
        user = _template("user_zero_shot.txt").format(
            task_id=context.task, environment_id=context.environment, details_block=details_block,
            catalog_text=catalog_txt, top_k=top_k,
        )
    else:
        system = _template("system_few_shot.txt")
        user = _template("user_few_shot.txt").format(
            task_id=context.task, environment_id=context.environment, details_block=details_block,
            condition_label=cond.label, condition_description=cond.description, support_block=examples_block,
            catalog_text=catalog_txt, top_k=top_k,
        )
    return system, user


# ---------------------------------------------------------------------------
# Response parsing and facet-id resolution (as in the paper's pipeline)
# ---------------------------------------------------------------------------


def parse_response(text: str) -> Dict:
    cleaned = re.sub(r"```json|```", "", str(text or "")).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


class FacetResolver:
    """Maps facet references in LLM output to catalog ids (exact, case-folded, contained, alias)."""

    def __init__(self, catalog: FacetCatalog):
        self.ids = [r["facet_id"] for r in catalog_rows(catalog)]
        self.aliases: Dict[str, Tuple[str, str]] = {}
        for fid in self.ids:
            facet = catalog.facet(fid)
            app_name = catalog.apps[facet.app_id].name
            name = facet.name or fid
            candidates = {
                fid: "facet_id",
                fid.replace(".", " "): "facet_id_text",
                name: "facet_name",
                f"{app_name} {name}": "app_plus_facet_name",
                f"{facet.app_id} {name}": "app_id_plus_facet_name",
                f"{facet.app_id}.{name}": "app_id_dot_facet_name",
            }
            if "." in fid:
                tail = fid.split(".", 1)[1]
                candidates[tail] = "facet_tail"
                candidates[tail.replace(".", " ")] = "facet_tail_text"
            for alias, source in candidates.items():
                slug = _slug(alias)
                if slug and slug not in self.aliases:
                    self.aliases[slug] = (fid, source)
        self._set = set(self.ids)

    def resolve(self, raw: object) -> Tuple[str, str]:
        text = str(raw or "").strip()
        if not text:
            return "", ""
        if text in self._set:
            return text, "exact"
        lowered = text.lower()
        for fid in self.ids:
            if fid.lower() == lowered:
                return fid, "casefold"
            if fid.lower() in lowered:
                return fid, "contains_facet_id"
        slug = _slug(text)
        if slug in self.aliases:
            return self.aliases[slug]
        for alias_slug, resolved in self.aliases.items():
            if alias_slug and alias_slug in slug:
                return resolved
        return "", ""

    def normalize(self, payload: Mapping, top_k: int) -> List[str]:
        rows = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
        out: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fid, _ = self.resolve(row.get("facet_id") or row.get("facet") or row.get("facet_name") or "")
            if not fid or fid in out:
                continue
            out.append(fid)
            if len(out) >= top_k:
                break
        return out


# ---------------------------------------------------------------------------
# Suggester
# ---------------------------------------------------------------------------


class LLMSuggester(Suggester):
    """Zero-shot (`condition=None`) or few-shot LLM suggestion.

    Args:
        dataset: scenarios available as few-shot examples. The scenario being evaluated is
            excluded from its own example pool (identified by its context).
        condition: None for zero-shot, or a transfer condition (see module docstring).
        max_examples: number of examples per prompt; None uses every matching scenario
            (paper, initial facet suggestion), 3 reproduces the paper's next facet runs.
        max_facets_per_tier: cap on facets listed per tier in an example (0 = no cap).
        cache: response cache; defaults to replaying `cache/llm/`.
    """

    def __init__(
        self,
        dataset: Dataset,
        condition: Optional[str] = None,
        *,
        max_examples: Optional[int] = None,
        max_facets_per_tier: int = 0,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        cache: Optional[LLMCache] = None,
    ):
        self.dataset = dataset
        self.condition = resolve_condition(condition)
        self.max_examples = max_examples
        self.max_facets_per_tier = max_facets_per_tier
        self.model = model
        self.temperature = temperature
        self.cache = cache or LLMCache()
        self.name = "zero_shot_llm" if self.condition is ZERO_SHOT else f"few_shot_llm[{self.condition.key}]"
        self._by_context: Dict[Context, List[str]] = {}
        for sid, s in dataset.scenarios.items():
            self._by_context.setdefault(s.context, []).append(sid)
        self._catalog_cache: Dict[int, Tuple[str, FacetResolver]] = {}

    def _catalog(self, catalog: FacetCatalog) -> Tuple[str, FacetResolver]:
        key = id(catalog)
        if key not in self._catalog_cache:
            self._catalog_cache[key] = (catalog_text(catalog), FacetResolver(catalog))
        return self._catalog_cache[key]

    def _scenario_id(self, context: Context) -> Optional[str]:
        ids = self._by_context.get(context, [])
        return ids[0] if len(ids) == 1 else None

    def prompts(self, context: Context, catalog: FacetCatalog, history: Optional[List[FacetId]] = None,
                k: int = 10) -> Tuple[str, str]:
        """System and user prompt for a query (raises SuggestionUnavailable without examples)."""
        catalog_txt, _ = self._catalog(catalog)
        scenario_id = self._scenario_id(context)
        examples = ""
        if self.condition is not ZERO_SHOT:
            pool = support_pool(self.condition, context, self.dataset, scenario_id)
            if not pool:
                raise SuggestionUnavailable("no_matching_examples", detail=self.condition.key)
            chosen = select_examples(pool, self.condition, self.max_examples)
            examples = support_block(chosen, catalog, self.max_facets_per_tier)
        details = history_block(history or [], catalog)
        return build_prompts(self.condition, context, catalog_txt, examples_block=examples, details=details, top_k=k)

    def suggest(self, context: Context, catalog: FacetCatalog, history: Optional[List[FacetId]] = None,
                k: int = 10) -> List[FacetId]:
        system, user = self.prompts(context, catalog, history, k)
        request = LLMRequest(
            model=self.model,
            temperature=self.temperature,
            task="initial" if history is None else "next",
            condition=self.condition.key,
            scenario_id=self._scenario_id(context) or "",
            step=None if history is None else len(history),
            system_prompt=system,
            user_prompt=user,
        )
        response = self.cache.complete(request)
        if response.error:
            raise SuggestionUnavailable("llm_error", detail=response.error)
        try:
            payload = parse_response(response.text)
        except json.JSONDecodeError as exc:
            raise SuggestionUnavailable("llm_parse_error", detail=str(exc)) from exc
        _, resolver = self._catalog(catalog)
        return resolver.normalize(payload, k)
