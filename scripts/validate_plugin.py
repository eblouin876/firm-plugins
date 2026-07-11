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
    head = open(path).read(200)
    if "last-verified:" not in head:
        warn(f"{os.path.relpath(path, ROOT)}: no 'last-verified' metadata header")

# 5. firm workflow templates must load the plugin and authenticate with OAuth.
#    A locally-installed plugin does not reach the Action runner, so every
#    claude-code-action step must set plugin_marketplaces (as a full git URL,
#    NOT owner/repo shorthand, which the action rejects) + plugins; and the
#    firm is OAuth-only, so anthropic_api_key is forbidden.
def _entries(val):
    """A with-input that may be a scalar or a newline block -> list of lines."""
    if val is None:
        return []
    return [ln.strip() for ln in str(val).splitlines() if ln.strip()]


wf_templates = sorted(
    glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yml"))
    + glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yaml"))
)
for path in wf_templates:
    rel = os.path.relpath(path, ROOT)
    try:
        doc = yaml.safe_load(open(path)) or {}
    except yaml.YAMLError as e:
        err(f"{rel}: invalid workflow YAML -> {e}")
        continue
    for job in (doc.get("jobs") or {}).values():
        for step in (job.get("steps") or []):
            if "claude-code-action" not in str(step.get("uses", "")):
                continue
            w = step.get("with") or {}
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
            # The action ignores bot-actor events by default, but the firm's
            # autonomous pipeline drives itself as a bot (Claude opens PRs and
            # posts @claude follow-ups). Without allowed_bots those events are
            # dropped and the pipeline stalls, so require it on every step.
            if not str(w.get("allowed_bots", "")).strip():
                err(f"{rel}: a claude-code-action step does not set "
                    "'allowed_bots' — the action ignores bot-actor events by "
                    "default, so events posted by Claude (e.g. an autonomously "
                    "opened PR or an @claude follow-up) won't trigger it")
            # The action documents --system-prompt for standing instructions;
            # --append-system-prompt is undocumented for it and its bundled CLI
            # rejects it, which silently breaks tag mode. Forbid it.
            args = str(w.get("claude_args", ""))
            if "--append-system-prompt" in args:
                err(f"{rel}: claude_args uses '--append-system-prompt' — the "
                    "action's CLI rejects it; use '--system-prompt' instead")
            # Headless runs approve nothing interactively: without --allowedTools
            # the firm skills' Bash commands (tests, linters, git, gh) are
            # rejected as "requires approval" and verification silently no-ops.
            if "--allowedTools" not in args:
                err(f"{rel}: a claude-code-action step does not set "
                    "'--allowedTools' in claude_args — headless Bash commands "
                    "(tests/linters/git/gh) will be rejected as 'requires "
                    "approval' and verification won't run")
            # The implement template must open the PR itself: the action only
            # posts a compare link in tag mode, and claude-review.yml can't fire
            # until a PR exists, so an implicit link leaves the pipeline stalled.
            if os.path.basename(path) == "claude.yml" and "gh pr create" not in args:
                err(f"{rel}: the implement template must instruct the agent to "
                    "open the PR ('gh pr create' in the system prompt) — the "
                    "action does not open one in tag mode")

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
