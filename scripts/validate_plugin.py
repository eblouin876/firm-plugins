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
#    template that invokes claude-code-action must set plugin_marketplaces +
#    plugins; and the firm is OAuth-only, so anthropic_api_key is forbidden.
wf_templates = sorted(
    glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yml"))
    + glob.glob(os.path.join(PLUGIN, "assets", "workflows", "*.yaml"))
)
for path in wf_templates:
    rel = os.path.relpath(path, ROOT)
    # ignore comment lines so notes like "never an anthropic_api_key" don't trip checks
    body = "\n".join(
        ln for ln in open(path).read().splitlines() if not ln.lstrip().startswith("#")
    )
    if "claude-code-action" not in body:
        continue
    if "plugin_marketplaces:" not in body:
        err(f"{rel}: invokes claude-code-action but does not set "
            "'plugin_marketplaces:' (the plugin won't reach the runner)")
    if "plugins:" not in body:
        err(f"{rel}: invokes claude-code-action but does not set 'plugins:' "
            "(the plugin won't reach the runner)")
    if "claude_code_oauth_token" not in body:
        err(f"{rel}: invokes claude-code-action but does not authenticate with "
            "'claude_code_oauth_token' (the firm is OAuth-only)")
    if "anthropic_api_key" in body:
        err(f"{rel}: uses 'anthropic_api_key' — the firm authenticates with "
            "CLAUDE_CODE_OAUTH_TOKEN only")

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
