"""Symbolic rule engine for Rails monoliths.

Reads the per-app input layout produced by the existing ROR-MSI pipeline
(`results/<app>/input/{classes,data}/...`) and emits typed facts that the
neural analysis layer (Paper 2) and the graph-RL decomposer (Paper 3) consume:

  must_link        — pairs that MUST end up in the same microservice
  cannot_link      — pairs that MUST end up in different microservices
  soft_affinity    — graded co-locality preferences (weight in [0,1])
  framework_noise  — classes to down-weight (boilerplate / cross-cutting)
  role_groups      — Rails-role buckets for diagnostics and weak supervision

Design rationale: hard constraints come only from rules whose linguistic
ground truth is unambiguous in the Rails universe (ActiveRecord associations,
explicit `include`/`extend` of named modules). Anything inferred from naming
heuristics is emitted as a soft affinity, never as a hard fact, so the neural
layer can override it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


CamelCase = re.compile(r"(?:^|_)([a-z0-9])")
ASSOCIATION_RE = re.compile(
    r"^\s*(belongs_to|has_many|has_one|has_and_belongs_to_many)\s+:([a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?:\s*,\s*(.*))?$"
)
CLASS_NAME_OPT = re.compile(r"class_name:\s*['\"]([A-Z][A-Za-z0-9:]*)['\"]")
THROUGH_OPT = re.compile(r"through:\s*:([a-zA-Z_][a-zA-Z0-9_]*)")
INCLUDE_RE = re.compile(r"^\s*(include|extend)\s+([A-Z][A-Za-z0-9:]*)\s*$")
CLASS_DEF_RE = re.compile(r"^\s*class\s+([A-Z][A-Za-z0-9:]*)(?:\s*<\s*([A-Z][A-Za-z0-9:]*))?")
MODULE_DEF_RE = re.compile(r"^\s*module\s+([A-Z][A-Za-z0-9:]*)")

# Rails-aware coupling patterns (mirrors tools/RailsCouplingExtractor.rb).
MODEL_LOOKUP_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:::[A-Z][A-Za-z0-9]*)*)\."
    r"(?:where|find|find_by|find_or_create_by|find_or_initialize_by|"
    r"create|create!|all|first|last|new|includes|joins|left_joins|"
    r"eager_load|preload|references|group|order|having|limit|offset|"
    r"pluck|count|exists\?|any\?|none\?|update|update_all|destroy|"
    r"destroy_all|delete|delete_all|distinct|unscoped|readonly|lock)\b"
)
MAILER_OR_JOB_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:Mailer|Job|Worker))(?:\.[a-z_][a-zA-Z0-9_]*)?"
    r"\.(?:deliver_now|deliver_later|deliver|perform_now|perform_later|set)\b"
)
SERVICE_CALL_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9]+(?:Service|Workflow|Operation|Action|Builder|"
    r"Finder|Presenter|Validator|Uploader|Dispatcher|Listener|Drop|"
    r"Channel|Policy))(?:\.new\b|\.call\b)"
)
BEFORE_ACTION_RE = re.compile(
    r"^\s*(?:before_action|after_action|around_action|before_filter|"
    r"after_filter|around_filter|skip_before_action)\s+:([a-zA-Z_][a-zA-Z0-9_!?]*)"
)

# Rails app/ subdirectory roles. Mirrors RAILS_CLASS_DIRS in
# tools/RailsAwareGraph.rb. Used by extract_facts_from_rails_app.
RAILS_APP_DIRS = (
    "models", "controllers", "helpers", "mailers", "jobs", "policies",
    "workflows", "services", "builders", "presenters", "validators",
    "uploaders", "finders", "actions", "channels", "listeners",
    "dispatchers", "drops", "fields", "mailboxes", "dashboards",
    "lib", "classes", "data",
)

# Framework base classes that should never anchor a microservice — every Rails
# app has them and they form spurious super-clusters in raw clustering.
FRAMEWORK_BASES = frozenset({
    "ApplicationRecord",
    "ApplicationController",
    "ApplicationJob",
    "ApplicationMailer",
    "ApplicationHelper",
    "ActiveRecord::Base",
    "ActionController::Base",
    "ActionController::API",
    "ActiveJob::Base",
    "ActionMailer::Base",
})

# App-internal base-class naming conventions. Rails projects routinely define
# their own abstract bases (BaseController, BasePolicy, BaseService, ...) that
# every concrete subclass extends. Treating them as ordinary classes pollutes
# every clustering signal — they end up pseudo-coupled to half the codebase.
_APP_BASE_PREFIXES = ("Base",)
_APP_BASE_SUFFIXES = ("Base",)


def _looks_like_app_base(name: str) -> bool:
    """True if `name` matches the app-internal abstract-base naming convention.

    Examples that match: BaseController, BaseService, AbstractBase.
    Examples that don't: Basecamp (no role suffix), DatabaseConfig (Database is
    a domain word), BaseballGame (heuristic accepts the false positive — the
    cost is one extra noise tag, not a hard misclassification).
    """
    if name in FRAMEWORK_BASES:
        return True
    # Prefix match: "Base" + a role-like suffix (Controller/Service/Policy/...).
    role_suffixes = (
        "Controller", "Service", "Policy", "Helper", "Mailer", "Job",
        "Builder", "Dispatcher", "Drop", "Listener", "Renderer", "Presenter",
        "Strategy", "Client",
    )
    if name.startswith("Base") and any(name.endswith(s) for s in role_suffixes):
        return True
    if name.endswith("Base") and len(name) > 4:
        # `*Base` only when capitalized prefix exists (so "Database" doesn't trip).
        return True
    return False


def _singular_to_class(name: str) -> str:
    """`comment` → `Comment`, `post_status` → `PostStatus`. Rails-style.

    Pluralization is intentionally NOT undone here — `belongs_to :user` already
    references the singular form by Rails convention. For `has_many :comments`,
    callers pass the singularized stem.
    """
    return CamelCase.sub(lambda m: m.group(1).upper(), name)


def _depluralize(name: str) -> str:
    """Cheap Rails-style depluralizer. Good enough for the four benchmark apps;
    edge cases (people→person) handled explicitly when they appear."""
    irregular = {"people": "person", "children": "child", "men": "man", "women": "woman"}
    if name in irregular:
        return irregular[name]
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses") or name.endswith("xes") or name.endswith("zes"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


@dataclass
class SymbolicFacts:
    """Container for all symbolic facts extracted from one Rails app."""

    app: str
    classes: list[str] = field(default_factory=list)
    must_link: list[tuple[str, str, str]] = field(default_factory=list)  # (a, b, reason)
    cannot_link: list[tuple[str, str, str]] = field(default_factory=list)
    soft_affinity: list[tuple[str, str, float, str]] = field(default_factory=list)
    framework_noise: list[str] = field(default_factory=list)
    role_groups: dict[str, list[str]] = field(default_factory=dict)
    namespaces: dict[str, str] = field(default_factory=dict)  # class -> top-level namespace

    def iter_cannot_link(self) -> Iterable[tuple[str, str]]:
        """Expand namespace cannot-link facts to the full pairwise cross-product
        on demand. Direct (non-namespace) cannot-link facts pass through."""
        by_ns: dict[str, list[str]] = {}
        for c, ns in self.namespaces.items():
            if ns:
                by_ns.setdefault(ns, []).append(c)
        ns_keys = sorted(by_ns)
        for i, ns_a in enumerate(ns_keys):
            for ns_b in ns_keys[i + 1:]:
                for a in by_ns[ns_a]:
                    for b in by_ns[ns_b]:
                        yield tuple(sorted([a, b]))
        for a, b, reason in self.cannot_link:
            if not reason.startswith("ns_pair:"):
                yield (a, b)

    def to_json(self) -> dict:
        d = asdict(self)
        # tuples → lists for JSON
        d["must_link"] = [list(t) for t in self.must_link]
        d["cannot_link"] = [list(t) for t in self.cannot_link]
        d["soft_affinity"] = [list(t) for t in self.soft_affinity]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "SymbolicFacts":
        """Reconstruct a SymbolicFacts from a saved facts JSON (the inverse of
        to_json/save). Lets downstream stages reuse pre-extracted facts instead
        of re-parsing the Rails source tree — which may be absent on a runner
        (e.g. Colab stages only classes/+data/, not the full app/ tree)."""
        return cls(
            app=d.get("app", ""),
            classes=list(d.get("classes", [])),
            must_link=[tuple(t) for t in d.get("must_link", [])],
            cannot_link=[tuple(t) for t in d.get("cannot_link", [])],
            soft_affinity=[tuple(t) for t in d.get("soft_affinity", [])],
            framework_noise=list(d.get("framework_noise", [])),
            role_groups={k: list(v) for k, v in d.get("role_groups", {}).items()},
            namespaces=dict(d.get("namespaces", {})),
        )

    @classmethod
    def load(cls, path: str | Path) -> "SymbolicFacts":
        return cls.from_json(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        # Atomic write: serialize to a temp file in the same dir, then os.replace
        # (atomic on POSIX). Prevents truncated/corrupt facts files if the run is
        # interrupted or two extractors race on the same app (the cause of an
        # astuto 79->21 corruption observed with parallel per-app extraction).
        import os, tempfile
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_json(), indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # atomic
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def _walk_ruby_files(root: Path) -> Iterable[tuple[Path, str]]:
    for p in root.rglob("*.rb"):
        try:
            yield p, p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def _role_from_rails_app_path(rel_path: Path) -> str:
    """Map a path relative to <app>/app/ (or <app>/) to a Rails role bucket.

    Examples:
      controllers/api/v1/posts_controller.rb -> "controllers"
      models/concerns/searchable.rb          -> "models"
      services/notifications/sender.rb       -> "services"
    """
    parts = rel_path.parts
    if not parts:
        return "unknown"
    top = parts[0]
    return top if top in RAILS_APP_DIRS else "unknown"


def _parse_rails_aware_couplings(
    text: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Extract Rails-framework-aware couplings beyond AR associations.

    Returns: (model_lookups, mailer_or_job_targets, service_targets,
              before_action_method_names). All are *unresolved* names — the
              caller resolves them against the actual class index.
    """
    model_lookups: list[str] = []
    mailer_or_jobs: list[str] = []
    services: list[str] = []
    before_actions: list[str] = []
    for line in text.splitlines():
        for m in MODEL_LOOKUP_RE.finditer(line):
            model_lookups.append(m.group(1).split("::")[-1])
        for m in MAILER_OR_JOB_RE.finditer(line):
            mailer_or_jobs.append(m.group(1).split("::")[-1])
        for m in SERVICE_CALL_RE.finditer(line):
            services.append(m.group(1).split("::")[-1])
        m = BEFORE_ACTION_RE.match(line)
        if m:
            before_actions.append(m.group(1))
    return model_lookups, mailer_or_jobs, services, before_actions


def _role_from_path(rel_path: Path, classes_root: Path, data_root: Path) -> str:
    """Map a file path (relative to input_dir) to a Rails role bucket.

    `rel_path` is e.g. `classes/controllers/api/v1/posts_controller.rb` or
    `data/post.rb`. We inspect its parts directly rather than re-relativizing.
    """
    parts = rel_path.parts
    if not parts:
        return "unknown"
    if parts[0] == "data":
        return "models"
    if parts[0] == "classes" and len(parts) >= 2:
        return parts[1]  # controllers, jobs, helpers, ...
    return "unknown"


def _class_name_from_file(text: str, file_stem: str) -> str | None:
    """Best-effort: prefer the first `class Foo` declaration; fall back to the
    file stem (Rails convention enforces a 1:1 file-to-class mapping for models
    and controllers, so the stem is reliable when the regex misses)."""
    for line in text.splitlines():
        m = CLASS_DEF_RE.match(line)
        if m:
            return m.group(1).split("::")[-1]
    return _singular_to_class(file_stem)


def _module_name_from_file(text: str, file_stem: str) -> str | None:
    for line in text.splitlines():
        m = MODULE_DEF_RE.match(line)
        if m:
            return m.group(1).split("::")[-1]
    return _singular_to_class(file_stem)


def _parse_associations(text: str) -> list[tuple[str, str]]:
    """Return list of (kind, target_class_name) for every association line."""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = ASSOCIATION_RE.match(line)
        if not m:
            continue
        kind, target_sym, opts = m.group(1), m.group(2), m.group(3) or ""
        # Resolve target class: explicit class_name beats convention.
        cn = CLASS_NAME_OPT.search(opts)
        if cn:
            target = cn.group(1).split("::")[-1]
        else:
            stem = _depluralize(target_sym) if kind != "belongs_to" else target_sym
            target = _singular_to_class(stem)
        out.append((kind, target))
    return out


def _parse_includes(text: str) -> list[tuple[str, str]]:
    """Return (kind, module_name) for every top-level include/extend."""
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = INCLUDE_RE.match(line)
        if m:
            mod = m.group(2).split("::")[-1]
            out.append((m.group(1), mod))
    return out


def _namespace_of(rel_path: Path, classes_root: Path) -> str:
    """Top-level namespace inferred from path. For `classes/controllers/api/v1/
    posts_controller.rb` → `api`. Skips the role directory (`controllers/`,
    `jobs/`, ...). Empty string for non-namespaced classes."""
    parts = rel_path.parts
    # Need at least: <top>/<role>/<namespace>/<file>.rb
    if len(parts) < 4 or parts[0] != "classes":
        return ""
    candidate = parts[2]
    if candidate.endswith(".rb"):
        return ""
    # Filter out generic subdirs that are NOT bounded contexts.
    if candidate in {"concerns"}:
        return ""
    return candidate


def extract_facts(input_dir: str | Path, app_name: str) -> SymbolicFacts:
    """Main entry point. Walks `input_dir/{classes,data}` and emits SymbolicFacts.

    The class-name graph is built first so association targets can be resolved
    against the actual class set (not every `belongs_to :user` resolves — some
    target classes live in gems and we silently drop those).
    """
    input_dir = Path(input_dir)
    classes_root = input_dir / "classes"
    data_root = input_dir / "data"

    facts = SymbolicFacts(app=app_name)
    # class_name → (path, role, raw_text) for second pass
    class_index: dict[str, tuple[Path, str, str]] = {}
    # module_name → list of class_names that include it
    concern_inclusions: dict[str, list[str]] = {}
    # module_name → set of class_names that *define* this module (for concern resolution)
    module_definitions: set[str] = set()

    # ----- Pass 1: enumerate classes and modules -----
    for path, text in _walk_ruby_files(input_dir):
        rel = path.relative_to(input_dir)
        role = _role_from_path(rel, classes_root, data_root)
        stem = path.stem

        # A concerns file defines a module, not a class.
        if "concerns" in rel.parts or path.parent.name == "concerns":
            mod = _module_name_from_file(text, stem)
            if mod:
                module_definitions.add(mod)
            continue

        cls = _class_name_from_file(text, stem)
        if cls is None:
            continue
        class_index[cls] = (path, role, text)
        ns = _namespace_of(rel, classes_root)
        if ns:
            facts.namespaces[cls] = ns
        facts.role_groups.setdefault(role, []).append(cls)

    facts.classes = sorted(class_index.keys())

    # ----- Pass 2: extract facts per class -----
    for cls, (path, role, text) in class_index.items():
        # Framework noise: literal Rails framework bases plus app-internal
        # abstract bases (BaseController, BasePolicy, ...). Both pollute
        # clustering signals when treated as ordinary classes.
        if _looks_like_app_base(cls):
            facts.framework_noise.append(cls)

        # Associations → must_link (when both ends exist in the class set).
        for kind, target in _parse_associations(text):
            if target in class_index and target != cls:
                pair = tuple(sorted([cls, target]))
                facts.must_link.append((pair[0], pair[1], f"assoc:{kind}"))

        # include/extend a *defined* concern → must_link with all other includers
        # (deferred: we collect now and pair up after the loop).
        for kind, mod in _parse_includes(text):
            if mod in module_definitions:
                concern_inclusions.setdefault(mod, []).append(cls)

    # Concern co-inclusion: every pair of classes including the same concern is
    # a soft affinity (NOT hard must-link — including TenantOwnable in 30 models
    # doesn't mean those 30 should all be one service).
    for mod, includers in concern_inclusions.items():
        n = len(includers)
        if n < 2:
            continue
        # Weight inversely proportional to the breadth of inclusion: a concern
        # included by 2 classes is a strong signal; included by 30 is weak.
        weight = max(0.1, min(1.0, 2.0 / n))
        for i in range(n):
            for j in range(i + 1, n):
                a, b = sorted([includers[i], includers[j]])
                facts.soft_affinity.append((a, b, weight, f"concern:{mod}"))

    # Role-based soft affinity: same role = mild same-microservice preference.
    # Keep weight low so it's only a tiebreaker, not a driver.
    for role, members in facts.role_groups.items():
        if role in {"unknown", "lib"} or len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = sorted([members[i], members[j]])
                facts.soft_affinity.append((a, b, 0.15, f"role:{role}"))

    # Namespace cannot-link: classes in distinct top-level namespaces are
    # bounded contexts. To avoid the |ns_a| × |ns_b| materialization (which
    # explodes on Chatwoot), we keep `facts.namespaces` as the canonical
    # representation and emit cannot-link facts only for representative pairs
    # (one per namespace pair) so downstream code knows the rule fired without
    # holding the full cross product. The neural layer expands on demand via
    # `iter_cannot_link()`.
    seen_pairs: set[tuple[str, str]] = set()
    by_ns: dict[str, list[str]] = {}
    for c, ns in facts.namespaces.items():
        if ns:
            by_ns.setdefault(ns, []).append(c)
    ns_keys = sorted(by_ns)
    for i, ns_a in enumerate(ns_keys):
        for ns_b in ns_keys[i + 1:]:
            # Only emit if the namespaces are semantically disjoint; reuse the
            # convention that distinct top-level controller namespaces in Rails
            # are independent bounded contexts.
            rep_a = sorted(by_ns[ns_a])[0]
            rep_b = sorted(by_ns[ns_b])[0]
            pair = tuple(sorted([rep_a, rep_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            facts.cannot_link.append((pair[0], pair[1], f"ns_pair:{ns_a}|{ns_b}"))

    # Deduplicate (same pair can appear via multiple rules).
    facts.must_link = sorted(set(facts.must_link))
    facts.cannot_link = sorted(set(facts.cannot_link))
    # For soft_affinity, sum weights when the same pair is attested by multiple
    # rules — that's the symbolic version of "more evidence = stronger prior."
    agg: dict[tuple[str, str], tuple[float, list[str]]] = {}
    for a, b, w, reason in facts.soft_affinity:
        key = (a, b)
        prev_w, prev_r = agg.get(key, (0.0, []))
        agg[key] = (min(1.0, prev_w + w), prev_r + [reason])
    facts.soft_affinity = sorted(
        (a, b, w, ";".join(reasons)) for (a, b), (w, reasons) in agg.items()
    )

    return facts


def extract_facts_from_rails_app(
    app_root: str | Path,
    app_name: str,
) -> SymbolicFacts:
    """Rails-aware fact extractor — walks the FULL Rails tree, not just
    `input/classes` + `input/data`.

    `app_root` should be the directory that contains the Rails `app/`
    subdir (e.g. `datasets/astuto-main` or `datasets/industrial-x` — industrial-x has the
    Rails tree under its own `app/`). We also accept an `app_root`
    pointing directly *at* the `app/` directory.

    The difference vs `extract_facts` is supervision breadth:
      - associations on every model (not just `input/data`),
      - Rails-aware coupling edges (User.where, Mailer.deliver_later,
        Service.call) -> must_link facts between caller and callee,
      - before_action hooks resolved within the same controller (no
        new must_link, but suppressed as framework noise via the
        existing role_groups['controllers'] bucket).

    The richer `must_link` set is the contrastive supervision signal the
    neural layer (UnixCoder fine-tune) needs to escape the trivial
    "same role" recall that the legacy extractor produced.
    """
    app_root = Path(app_root)
    app_dir = app_root / "app" if (app_root / "app").is_dir() else app_root

    facts = SymbolicFacts(app=app_name)
    class_index: dict[str, tuple[Path, str, str]] = {}
    concern_inclusions: dict[str, list[str]] = {}
    module_definitions: set[str] = set()

    # ----- Pass 1: enumerate classes -----
    for path in app_dir.rglob("*.rb"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(app_dir)
        role = _role_from_rails_app_path(rel)
        if role == "unknown":
            continue
        if "concerns" in rel.parts:
            mod = _module_name_from_file(text, path.stem)
            if mod:
                module_definitions.add(mod)
            continue
        cls = _class_name_from_file(text, path.stem)
        if cls is None:
            continue
        class_index[cls] = (path, role, text)
        # Top-level namespace: parts after the role directory.
        ns = ""
        if len(rel.parts) >= 3 and rel.parts[1] not in {"concerns"}:
            ns = rel.parts[1]
        if ns:
            facts.namespaces[cls] = ns
        facts.role_groups.setdefault(role, []).append(cls)

    facts.classes = sorted(class_index.keys())
    name_set = set(facts.classes)

    # ----- Pass 2: extract facts per class -----
    for cls, (path, role, text) in class_index.items():
        if _looks_like_app_base(cls):
            facts.framework_noise.append(cls)

        # 1) ActiveRecord associations -> must_link.
        for kind, target in _parse_associations(text):
            if target in name_set and target != cls:
                pair = tuple(sorted([cls, target]))
                facts.must_link.append((pair[0], pair[1], f"assoc:{kind}"))

        # 2) Rails-aware couplings -> must_link.
        model_lookups, mailer_or_jobs, services, _ = _parse_rails_aware_couplings(text)
        for target in model_lookups:
            if target in name_set and target != cls:
                pair = tuple(sorted([cls, target]))
                facts.must_link.append((pair[0], pair[1], "rails:model_lookup"))
        for target in mailer_or_jobs:
            if target in name_set and target != cls:
                pair = tuple(sorted([cls, target]))
                facts.must_link.append((pair[0], pair[1], "rails:mailer_or_job"))
        for target in services:
            if target in name_set and target != cls:
                pair = tuple(sorted([cls, target]))
                facts.must_link.append((pair[0], pair[1], "rails:service_call"))

        # 3) Concern co-inclusion -> soft affinity (collected, paired below).
        for kind, mod in _parse_includes(text):
            if mod in module_definitions:
                concern_inclusions.setdefault(mod, []).append(cls)

    # Concern co-inclusion -> soft_affinity (weight inversely proportional to
    # the breadth of inclusion).
    for mod, includers in concern_inclusions.items():
        n = len(includers)
        if n < 2:
            continue
        weight = max(0.1, min(1.0, 2.0 / n))
        for i in range(n):
            for j in range(i + 1, n):
                a, b = sorted([includers[i], includers[j]])
                facts.soft_affinity.append((a, b, weight, f"concern:{mod}"))

    # Role-based soft affinity (mild tiebreaker).
    for role, members in facts.role_groups.items():
        if role in {"unknown", "lib"} or len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = sorted([members[i], members[j]])
                facts.soft_affinity.append((a, b, 0.15, f"role:{role}"))

    # Namespace cannot-link (representative pair per namespace cross).
    seen_pairs: set[tuple[str, str]] = set()
    by_ns: dict[str, list[str]] = {}
    for c, ns in facts.namespaces.items():
        if ns:
            by_ns.setdefault(ns, []).append(c)
    ns_keys = sorted(by_ns)
    for i, ns_a in enumerate(ns_keys):
        for ns_b in ns_keys[i + 1:]:
            rep_a = sorted(by_ns[ns_a])[0]
            rep_b = sorted(by_ns[ns_b])[0]
            pair = tuple(sorted([rep_a, rep_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            facts.cannot_link.append((pair[0], pair[1], f"ns_pair:{ns_a}|{ns_b}"))

    # Dedup / aggregate (same logic as extract_facts).
    facts.must_link = sorted(set(facts.must_link))
    facts.cannot_link = sorted(set(facts.cannot_link))
    agg: dict[tuple[str, str], tuple[float, list[str]]] = {}
    for a, b, w, reason in facts.soft_affinity:
        key = (a, b)
        prev_w, prev_r = agg.get(key, (0.0, []))
        agg[key] = (min(1.0, prev_w + w), prev_r + [reason])
    facts.soft_affinity = sorted(
        (a, b, w, ";".join(reasons)) for (a, b), (w, reasons) in agg.items()
    )
    return facts


def main() -> None:
    """CLI: extract facts for every app under results/."""
    import argparse

    p = argparse.ArgumentParser(description="Extract symbolic facts from Rails apps")
    p.add_argument("--results-dir", default="results", help="root containing per-app dirs (legacy)")
    p.add_argument("--datasets-dir", default="datasets",
                   help="root of the Rails app sources (e.g. datasets/astuto-main/app)")
    p.add_argument("--mode", choices=["rails-aware", "legacy"], default="rails-aware",
                   help="rails-aware = walk full Rails tree (new); legacy = walk input/{classes,data}")
    p.add_argument("--out-dir", default="neurosymbolic/output/facts", help="where to write JSON")
    p.add_argument("--apps", nargs="*", help="restrict to these apps (default: all)")
    args = p.parse_args()

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.mode == "rails-aware":
        datasets_root = Path(args.datasets_dir)
        for app_dir in sorted(datasets_root.iterdir()):
            if not app_dir.is_dir():
                continue
            if args.apps and app_dir.name not in args.apps:
                continue
            if not (app_dir / "app").is_dir():
                continue
            facts = extract_facts_from_rails_app(app_dir, app_dir.name)
            out_path = out_root / f"{app_dir.name}.json"
            facts.save(out_path)
            ml_by_src: dict[str, int] = {}
            for _, _, r in facts.must_link:
                ml_by_src[r] = ml_by_src.get(r, 0) + 1
            print(
                f"{app_dir.name}: {len(facts.classes)} classes, "
                f"{len(facts.must_link)} must-link "
                f"({', '.join(f'{k}={v}' for k, v in sorted(ml_by_src.items()))}), "
                f"{len(facts.cannot_link)} cannot-link, "
                f"{len(facts.soft_affinity)} soft, "
                f"{len(facts.framework_noise)} noise → {out_path}"
            )
        return

    # legacy mode
    results_root = Path(args.results_dir)
    for app_dir in sorted(results_root.iterdir()):
        if not app_dir.is_dir() or not (app_dir / "input").is_dir():
            continue
        if args.apps and app_dir.name not in args.apps:
            continue
        facts = extract_facts(app_dir / "input", app_dir.name)
        out_path = out_root / f"{app_dir.name}.json"
        facts.save(out_path)
        print(
            f"{app_dir.name}: {len(facts.classes)} classes, "
            f"{len(facts.must_link)} must-link, "
            f"{len(facts.cannot_link)} cannot-link, "
            f"{len(facts.soft_affinity)} soft, "
            f"{len(facts.framework_noise)} noise → {out_path}"
        )


if __name__ == "__main__":
    main()
