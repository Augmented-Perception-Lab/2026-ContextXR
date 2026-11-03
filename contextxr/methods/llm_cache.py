"""Cache of LLM prompt/response pairs (cache/llm/).

Entries are keyed by (model, task, condition, scenario_id, step, prompt hash), where the
prompt hash is the SHA-256 of the system prompt, a blank line, and the user prompt.
Including the scenario and step keeps independent calls with identical prompts
(e.g. zero-shot prompts for two users in the same task and environment) separate.

Layout:
    cache/llm/<model>/<task>/<condition>.jsonl   one JSON object per call
    cache/llm/catalogs/<sha256>.txt              facet catalogs referenced by prompts

To keep the cache small, the facet catalog inside a user prompt is replaced by
`{{catalog:<sha256>}}` and stored once under catalogs/.

Modes:
    replay (default)  serve cached responses; a miss raises CacheMiss
    live              serve cached responses; call the model on a miss and record it
    refresh           always call the model and overwrite the entry
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

PathLike = Union[str, Path]
MODES = ("replay", "live", "refresh")
_CATALOG_RE = re.compile(r"\{\{catalog:([0-9a-f]{64})\}\}")
_CATALOG_MARKER = "Available facet catalog:\n"
_CATALOG_END = "\n\nInstructions:\n"


class CacheMiss(RuntimeError):
    """Raised in replay mode when a request has no cached response."""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    return sha256(system_prompt + "\n\n" + user_prompt)


def default_cache_dir() -> Path:
    """Directory where live-mode responses are recorded (see contextxr.paths)."""
    from contextxr.paths import llm_cache_write_dir

    return llm_cache_write_dir()


@dataclass(frozen=True)
class LLMRequest:
    model: str
    temperature: float
    task: str  # "initial" | "next"
    condition: str  # "zero_shot" | transfer condition key
    scenario_id: str
    step: Optional[int]
    system_prompt: str
    user_prompt: str

    @property
    def prompt_sha256(self) -> str:
        return prompt_hash(self.system_prompt, self.user_prompt)

    @property
    def key(self) -> Tuple:
        return (self.model, self.task, self.condition, self.scenario_id, self.step, self.prompt_sha256)


@dataclass
class LLMResponse:
    text: str = ""
    error: Optional[str] = None
    provenance: str = "live"
    meta: Dict = field(default_factory=dict)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", value)


class LLMCache:
    def __init__(self, root: Optional[PathLike] = None, *, mode: str = "replay", client=None):
        """`root`: a single cache directory (read and write). By default, responses are read from
        the layered locations in `contextxr.paths` and recorded to `default_cache_dir()`."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if root is not None:
            self.root = Path(root)
            self.read_roots = [self.root]
        else:
            from contextxr.paths import llm_cache_read_dirs

            self.root = default_cache_dir()
            self.read_roots = llm_cache_read_dirs()
        self.mode = mode
        self._client = client
        self._index: Dict[Tuple, Dict] = {}
        self._loaded_files: set = set()

    # -- storage ------------------------------------------------------------------

    def _file(self, model: str, task: str, condition: str, root: Optional[Path] = None) -> Path:
        return (root or self.root) / _slug(model) / task / f"{_slug(condition)}.jsonl"

    def _load(self, path: Path) -> None:
        if path in self._loaded_files:
            return
        self._loaded_files.add(path)
        if not path.exists():
            return
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    entry = json.loads(line)
                    k = entry["key"]
                    key = (k["model"], k["task"], k["condition"], k["scenario_id"], k["step"], k["prompt_sha256"])
                    self._index.setdefault(key, entry)  # earlier (more specific) roots win

    def compress_prompt(self, user_prompt: str) -> str:
        """Replace the catalog in a user prompt by a reference, storing the catalog once."""
        start = user_prompt.find(_CATALOG_MARKER)
        end = user_prompt.find(_CATALOG_END, start)
        if start < 0 or end < 0:
            return user_prompt
        start += len(_CATALOG_MARKER)
        catalog = user_prompt[start:end]
        digest = sha256(catalog)
        path = self.root / "catalogs" / f"{digest}.txt"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(catalog, encoding="utf-8")
        return user_prompt[:start] + "{{catalog:" + digest + "}}" + user_prompt[end:]

    def expand_prompt(self, stored: str) -> str:
        def repl(match):
            for root in self.read_roots:
                path = root / "catalogs" / f"{match.group(1)}.txt"
                if path.exists():
                    return path.read_text(encoding="utf-8")
            raise FileNotFoundError(f"catalog {match.group(1)} not found in {self.read_roots}")

        return _CATALOG_RE.sub(repl, stored)

    def lookup(self, request: LLMRequest) -> Optional[Dict]:
        for root in self.read_roots:
            self._load(self._file(request.model, request.task, request.condition, root))
        return self._index.get(request.key)

    def put(self, request: LLMRequest, response: LLMResponse) -> Dict:
        entry = {
            "key": {
                "model": request.model,
                "task": request.task,
                "condition": request.condition,
                "scenario_id": request.scenario_id,
                "step": request.step,
                "prompt_sha256": request.prompt_sha256,
            },
            "temperature": request.temperature,
            "system_prompt_sha256": sha256(request.system_prompt),
            "user_prompt": self.compress_prompt(request.user_prompt),
            "response": {"text": response.text, "error": response.error, "provenance": response.provenance, **response.meta},
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = self._file(request.model, request.task, request.condition)
        path.parent.mkdir(parents=True, exist_ok=True)
        own = []
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                own = [json.loads(line) for line in handle if line.strip()]
        if any(e["key"] == entry["key"] for e in own):
            own = [entry if e["key"] == entry["key"] else e for e in own]
            with path.open("w", encoding="utf-8") as handle:
                for e in own:
                    handle.write(json.dumps(e, ensure_ascii=False) + "\n")
        else:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._index[request.key] = entry
        return entry

    # -- serving ------------------------------------------------------------------

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.mode != "refresh":
            entry = self.lookup(request)
            if entry is not None:
                r = entry["response"]
                return LLMResponse(text=r.get("text") or "", error=r.get("error"), provenance=r.get("provenance", ""))
            if self.mode == "replay":
                raise CacheMiss(
                    f"No cached LLM response for model={request.model} task={request.task} "
                    f"condition={request.condition} scenario={request.scenario_id} step={request.step} "
                    f"prompt={request.prompt_sha256[:12]} in {[str(r) for r in self.read_roots]}. Run with live mode "
                    "(contextxr run ... --live, needs the [llm] extra and GOOGLE_API_KEY) to call the model."
                )
        response = self._call(request)
        self.put(request, response)
        return response

    def _call(self, request: LLMRequest) -> LLMResponse:
        if self._client is None:
            self._client = GeminiClient()
        return self._client.generate(request)


class GeminiClient:
    """Minimal Gemini client (google-genai). Reads GOOGLE_API_KEY / GEMINI_API_KEY from the environment."""

    TRANSIENT = ("429", "500", "502", "503", "504", "deadline", "timeout", "temporarily", "unavailable",
                 "resource_exhausted", "quota", "rate limit", "overloaded", "connection")

    def __init__(self, *, max_attempts: int = 8, backoff_seconds: float = 2.0):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError("Live LLM calls need the [llm] extra: pip install 'contextxr[llm]'") from exc
        if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
            raise RuntimeError("Set GOOGLE_API_KEY (or GEMINI_API_KEY) to call Gemini in live mode.")
        self._client = genai.Client()
        self._types = types
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def generate(self, request: LLMRequest) -> LLMResponse:
        attempt = 0
        while True:
            attempt += 1
            try:
                result = self._client.models.generate_content(
                    model=request.model,
                    contents=[request.user_prompt],
                    config=self._types.GenerateContentConfig(
                        system_instruction=request.system_prompt, temperature=request.temperature
                    ),
                )
                return LLMResponse(text=result.text or "", provenance="live")
            except Exception as exc:  # noqa: BLE001 - surface non-transient errors
                message = str(exc)
                transient = any(token in message.lower() for token in self.TRANSIENT)
                if not transient or attempt >= self.max_attempts:
                    return LLMResponse(error=message, provenance="live")
                time.sleep(self.backoff_seconds)
