#!/usr/bin/env python3
"""
Validate the dev-lifecycle plugin before it ships.

Deterministic, no-auth structural checks that mirror what Claude Code rejects on
install — the JSON manifests, and (the one that bit us) the YAML frontmatter of
every SKILL.md. Run locally with `python scripts/validate_plugin.py`; runs in CI
on every push and PR. Exits non-zero on any error.
"""
import json
import os
import sys
import glob

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required (pip install pyyaml)")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "dev-lifecycle")
ALLOWED_PLUGIN_FIELDS = {
    "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords",
}

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        err(f"missing file: {os.path.relpath(path, ROOT)}")
    except json.JSONDecodeError as e:
        err(f"invalid JSON in {os.path.relpath(path, ROOT)}: {e}")
    return None


# 1. marketplace.json
mkt = load_json(os.path.join(ROOT, ".claude-plugin", "marketplace.json"))
if isinstance(mkt, dict):
    if not mkt.get("name"):
        err("marketplace.json: missing 'name'")
    if not isinstance(mkt.get("owner"), dict):
        err("marketplace.json: 'owner' must be an object")
    plugins = mkt.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        err("marketplace.json: 'plugins' must be a non-empty array")
    else:
        has_root = bool(mkt.get("metadata", {}).get("pluginRoot"))
        for i, p in enumerate(plugins):
            if not p.get("name"):
                err(f"marketplace.json: plugins[{i}] missing 'name'")
            if not p.get("source") and not has_root:
                err(f"marketplace.json: plugins[{i}] missing 'source' "
                    "(and no metadata.pluginRoot set)")

# 2. plugin.json
pj = load_json(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"))
if isinstance(pj, dict):
    for req in ("name", "version", "description"):
        if not pj.get(req):
            err(f"plugin.json: missing required field '{req}'")
    extra = set(pj) - ALLOWED_PLUGIN_FIELDS
    if extra:
        err(f"plugin.json: unsupported field(s) {sorted(extra)} "
            f"(allowed: {sorted(ALLOWED_PLUGIN_FIELDS)})")
    author = pj.get("author")
    if author is not None and not (isinstance(author, dict) and author.get("name")):
        err("plugin.json: 'author' must be an object with a 'name'")

# 3. every SKILL.md frontmatter must be valid YAML with name + description
skills = sorted(glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md")))
if not skills:
    err("no skills found under plugins/dev-lifecycle/skills/")
for path in skills:
    rel = os.path.relpath(path, ROOT)
    skill_dir = os.path.basename(os.path.dirname(path))
    text = open(path).read()
    if not text.startswith("---"):
        err(f"{rel}: missing YAML frontmatter")
        continue
    parts = text.split("---", 2)
    if len(parts) < 3:
        err(f"{rel}: malformed frontmatter (no closing '---')")
        continue
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        err(f"{rel}: invalid YAML frontmatter -> {e}")
        continue
    if not isinstance(data, dict):
        err(f"{rel}: frontmatter is not a mapping")
        continue
    name = data.get("name")
    if not name:
        err(f"{rel}: frontmatter missing 'name'")
    elif name != skill_dir:
        err(f"{rel}: name '{name}' does not match directory '{skill_dir}'")
    if not data.get("description"):
        err(f"{rel}: frontmatter missing 'description'")

# 4. (warning) references should carry a metadata header for the freshness audit
for path in glob.glob(os.path.join(PLUGIN, "references", "**", "*.md"), recursive=True):
    if os.path.basename(path).startswith("_"):
        continue
    head = open(path).read(1000)
    if "last-verified:" not in head:
        warn(f"{os.path.relpath(path, ROOT)}: no 'last-verified' metadata header")

# 4a. (warning) same freshness/header check for real template blocks, once they
#     exist. `_`-prefixed files are schema exemplars (e.g. _TEMPLATE-README.md)
#     and are skipped, matching the references check above. The glob is
#     empty-dir safe: as of Stage 0 no real block has landed yet, so this is a
#     no-op until Stage 1+ adds one.
for path in glob.glob(os.path.join(PLUGIN, "templates", "**", "*.md"), recursive=True):
    if os.path.basename(path).startswith("_"):
        continue
    head = open(path).read(1000)
    if "last-verified:" not in head:
        warn(f"{os.path.relpath(path, ROOT)}: no 'last-verified' metadata header")

# 5. firm Action wiring. The implement/review logic lives in REUSABLE workflows
#    (.github/workflows/*.reusable.yml), called by the thin caller stubs that
#    projects copy from assets/workflows/. A locally-installed plugin does not
#    reach the Action runner, so every claude-code-action step must set
#    plugin_marketplaces (a full git URL, NOT owner/repo shorthand) + plugins;
#    the firm is OAuth-only (no anthropic_api_key); and it must allow bot actors.
def _entries(val):
    """A with-input that may be a scalar or a newline block -> list of lines."""
    if val is None:
        return []
    return [ln.strip() for ln in str(val).splitlines() if ln.strip()]


def check_action_step(rel, w, expect_pr_create):
    """Validate a single claude-code-action `with:` block, wherever it lives."""
    markets = _entries(w.get("plugin_marketplaces"))
    if not markets:
        err(f"{rel}: a claude-code-action step does not set "
            "'plugin_marketplaces' (the plugin won't reach the runner)")
    for m in markets:
        if "://" not in m and not m.startswith("git@"):
            err(f"{rel}: plugin_marketplaces entry '{m}' is not a git URL "
                "(owner/repo shorthand is rejected by the action; use "
                "https://github.com/<owner>/<repo>.git)")
    if not _entries(w.get("plugins")):
        err(f"{rel}: a claude-code-action step does not set 'plugins' "
            "(the plugin won't reach the runner)")
    if not w.get("claude_code_oauth_token"):
        err(f"{rel}: a claude-code-action step does not authenticate with "
            "'claude_code_oauth_token' (the firm is OAuth-only)")
    if w.get("anthropic_api_key"):
        err(f"{rel}: uses 'anthropic_api_key' — the firm authenticates "
            "with CLAUDE_CODE_OAUTH_TOKEN only")
    # The action ignores bot-actor events by default, but the firm's autonomous
    # pipeline drives itself as a bot (Claude opens PRs, and the review posts an
    # @claude routing comment). Without allowed_bots those events are dropped and
    # the pipeline stalls, so require it on every step.
    if not str(w.get("allowed_bots", "")).strip():
        err(f"{rel}: a claude-code-action step does not set 'allowed_bots' — "
            "the action ignores bot-actor events by default, so events posted "
            "by Claude (an autonomously opened PR, an @claude follow-up, or the "
            "review's routing comment) won't trigger it")
    # The action documents --system-prompt for standing instructions;
    # --append-system-prompt is undocumented for it and its bundled CLI rejects
    # it, which silently breaks tag mode. Forbid it.
    args = str(w.get("claude_args", ""))
    if "--append-system-prompt" in args:
        err(f"{rel}: claude_args uses '--append-system-prompt' — the action's "
            "CLI rejects it; use '--system-prompt' instead")
    # Headless runs approve nothing interactively: without --allowedTools the
    # firm skills' Bash commands (tests, linters, git, gh) are rejected as
    # "requires approval" and verification silently no-ops.
    if "--allowedTools" not in args:
        err(f"{rel}: a claude-code-action step does not set '--allowedTools' in "
            "claude_args — headless Bash commands (tests/linters/git/gh) will be "
            "rejected as 'requires approval' and verification won't run")
    # The implement workflow must open the PR itself: the action only posts a
    # compare link in tag mode, and the review can't fire until a PR exists, so
    # an implicit link leaves the pipeline stalled.
    if expect_pr_create and "gh pr create" not in args:
        err(f"{rel}: the implement workflow must instruct the agent to open the "
            "PR ('gh pr create' in the system prompt) — the action does not "
            "open one in tag mode")


def action_steps(doc):
    for job in (doc.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            if "claude-code-action" in str(step.get("uses", "")):
                yield step


# 5a. The reusable workflows hold the claude-code-action steps.
GH_WF = os.path.join(ROOT, ".github", "workflows")
for req in ("claude-implement.reusable.yml", "claude-review.reusable.yml"):
    if not os.path.exists(os.path.join(GH_WF, req)):
        err(f".github/workflows/{req} is missing — the firm's reusable Action "
            "the caller stubs delegate to")
saw_action = False
for path in sorted(glob.glob(os.path.join(GH_WF, "*.reusable.yml"))
                   + glob.glob(os.path.join(GH_WF, "*.reusable.yaml"))):
    rel = os.path.relpath(path, ROOT)
    try:
        doc = yaml.safe_load(open(path)) or {}
    except yaml.YAMLError as e:
        err(f"{rel}: invalid workflow YAML -> {e}")
        continue
    expect_pr = os.path.basename(path) == "claude-implement.reusable.yml"
    for step in action_steps(doc):
        saw_action = True
        check_action_step(rel, step.get("with") or {}, expect_pr)
if not saw_action:
    err("no claude-code-action step found in any .github/workflows/*.reusable.yml")

# 5b. Caller stubs projects copy: claude.yml + claude-review.yml must delegate
#     to a reusable workflow (uses:), forward secrets, and pass the owner input.
#     epic-checkoff.yml is self-contained (no plugin/secret) and is exempt.
STUBS = {"claude.yml", "claude-review.yml"}
for path in sorted(glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yml"))
                   + glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yaml"))):
    rel = os.path.relpath(path, ROOT)
    base = os.path.basename(path)
    try:
        doc = yaml.safe_load(open(path)) or {}
    except yaml.YAMLError as e:
        err(f"{rel}: invalid workflow YAML -> {e}")
        continue
    # If a stub still carries an inlined action step, validate it in place too.
    for step in action_steps(doc):
        check_action_step(rel, step.get("with") or {}, base == "claude.yml")
    if base not in STUBS:
        continue
    caller = next((j for j in (doc.get("jobs") or {}).values()
                   if ".reusable.yml" in str(j.get("uses", ""))
                   or ".reusable.yaml" in str(j.get("uses", ""))), None)
    if caller is None:
        err(f"{rel}: expected a job that `uses:` a *.reusable.yml workflow — the "
            "stub delegates to the firm's reusable Action")
        continue
    sec = caller.get("secrets")
    if sec != "inherit" and not isinstance(sec, dict):
        err(f"{rel}: the reusable-workflow call must forward secrets "
            "('secrets: inherit') so CLAUDE_CODE_OAUTH_TOKEN reaches it")
    if "owner" not in (caller.get("with") or {}):
        err(f"{rel}: the reusable-workflow call must pass the 'owner' input")

# report
for w in warnings:
    print(f"::warning:: {w}" if os.getenv("GITHUB_ACTIONS") else f"WARN  {w}")
if errors:
    print()
    for e in errors:
        print(f"::error:: {e}" if os.getenv("GITHUB_ACTIONS") else f"ERROR {e}")
    print(f"\nValidation FAILED: {len(errors)} error(s), {len(warnings)} warning(s).")
    sys.exit(1)

print(f"Validation passed: {len(skills)} skills, {len(warnings)} warning(s).")
