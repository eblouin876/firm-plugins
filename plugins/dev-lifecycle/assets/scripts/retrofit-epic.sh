#!/usr/bin/env bash
#
# retrofit-epic.sh — one-shot migration for an epic created before the
# epic-checkoff workflow existed. It backfills the three things that workflow
# (and GitHub's native sub-issue rollup) rely on:
#
#   1. an `Epic: #<epic>` marker line on each child (stage/feature) issue,
#   2. the child's number on the epic's matching checklist line — `... (#42)`,
#   3. the child registered as a native GitHub sub-issue of the epic.
#
# It also ticks the epic's box for any child that is ALREADY closed, so the
# roadmap is immediately consistent. After this runs once, future closes are
# handled automatically by .github/workflows/epic-checkoff.yml.
#
# SAFE BY DEFAULT: prints the plan and the proposed epic-body diff, mutating
# NOTHING. Re-run with --apply to actually write. Idempotent — running it again
# is a no-op once everything is linked.
#
# Requires: gh (authenticated), awk, standard coreutils.
#
# Usage:
#   retrofit-epic.sh <owner/repo> <epic-number> [child-number ...]
#   retrofit-epic.sh <owner/repo> <epic-number> [child-number ...] --apply
#
# If no child numbers are given, the epic's existing native sub-issues are
# discovered automatically. Give them explicitly for an epic that only has a
# markdown checklist (no sub-issues yet) — the common pre-migration case:
#   retrofit-epic.sh me/app 7 12 15 18 --apply
#
# Placement of a child's number onto a checklist line is by case-insensitive
# title match. If a line can't be matched unambiguously (zero or several
# candidates), the script SAYS SO and skips it rather than guessing — put the
# `(#n)` on by hand for those, then re-run.

set -euo pipefail

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "$0"; }

apply=0
positional=()
for a in "$@"; do
  case "$a" in
    --apply)   apply=1 ;;
    -h|--help) usage; exit 0 ;;
    -*)        echo "unknown flag: $a" >&2; exit 2 ;;
    *)         positional+=("$a") ;;
  esac
done

repo="${positional[0]:-}"
epic="${positional[1]:-}"
if [ -z "$repo" ] || [ -z "$epic" ]; then usage; exit 2; fi
children=("${positional[@]:2}")

command -v gh >/dev/null || { echo "gh is required and not on PATH." >&2; exit 3; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
epicbody="$work/epic.md"

# Discover children from native sub-issues if none were passed.
if [ "${#children[@]}" -eq 0 ]; then
  mapfile -t children < <(gh api "repos/$repo/issues/$epic/sub_issues" --jq '.[].number' 2>/dev/null || true)
  if [ "${#children[@]}" -eq 0 ]; then
    echo "No child numbers given and epic #$epic has no native sub-issues to discover." >&2
    echo "Pass the stage/feature issue numbers explicitly, e.g.:" >&2
    echo "  $0 $repo $epic 12 15 18" >&2
    exit 2
  fi
  echo "Discovered ${#children[@]} sub-issue(s) of epic #$epic: ${children[*]}"
fi

gh api "repos/$repo/issues/$epic" --jq '.body // ""' > "$epicbody"

echo
echo "Epic: $repo#$epic"
echo "Children: ${children[*]}"
echo "Mode: $([ "$apply" -eq 1 ] && echo APPLY || echo 'dry-run (no writes)')"
echo "----------------------------------------------------------------------"

# Per-child body/marker/sub-issue actions are collected as closures to run only
# under --apply; the epic body is transformed in place in $epicbody either way,
# then pushed once at the end.
declare -a marker_children=() subissue_children=()

for c in "${children[@]}"; do
  if [ "$c" = "$epic" ]; then echo "  skip #$c (that's the epic itself)"; continue; fi

  title="$(gh api "repos/$repo/issues/$c" --jq '.title')"
  state="$(gh api "repos/$repo/issues/$c" --jq '.state')"
  cbody="$(gh api "repos/$repo/issues/$c" --jq '.body // ""')"

  echo "  #$c  \"$title\"  [$state]"

  # (1) Marker on the child body.
  if printf '%s' "$cbody" | grep -qiE "epic:[[:space:]]*#$epic([^0-9]|\$)"; then
    echo "      marker: present"
  else
    echo "      marker: will add 'Epic: #$epic' to #$c body"
    marker_children+=("$c")
  fi

  # (2) Number on the epic's checklist line.
  if grep -qE "#$c([^0-9]|\$)" "$epicbody"; then
    echo "      number: already on a line"
  else
    title_lc="$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]')"
    mapfile -t cand < <(awk -v tl="$title_lc" '
      /^[[:space:]]*[-*] \[[ xX]\]/ {
        if (index(tolower($0), tl) > 0 && $0 !~ /\(#[0-9]+\)/) print NR
      }' "$epicbody")
    if [ "${#cand[@]}" -eq 1 ]; then
      ln="${cand[0]}"
      awk -v ln="$ln" -v c="$c" 'NR==ln { sub(/[[:space:]]+$/,""); $0=$0" (#"c")" } {print}' \
        "$epicbody" > "$epicbody.tmp" && mv "$epicbody.tmp" "$epicbody"
      echo "      number: will add (#$c) to epic line $ln"
    else
      echo "      number: SKIPPED — ${#cand[@]} candidate checklist lines match \"$title\"; add (#$c) by hand, then re-run"
    fi
  fi

  # (3) Native sub-issue registration.
  subissue_children+=("$c")

  # (4) Tick the box now if the child is already closed.
  if [ "$state" = "closed" ]; then
    before="$(cat "$epicbody")"
    awk -v c="$c" '
      function has(s,t){ return index(s,t) > 0 }
      {
        line=$0
        if (line ~ /^[[:space:]]*[-*] \[[ xX]\]/ && line ~ ("#" c "([^0-9]|$)") && has(line,"[ ]")) {
          sub(/\[ \]/, "[x]", line)
        }
        print line
      }' "$epicbody" > "$epicbody.tmp" && mv "$epicbody.tmp" "$epicbody"
    if [ "$before" != "$(cat "$epicbody")" ]; then
      echo "      tick:   will check the box (#$c is closed)"
    fi
  fi
done

echo "----------------------------------------------------------------------"

# Show the proposed epic-body change.
orig="$work/epic.orig"; gh api "repos/$repo/issues/$epic" --jq '.body // ""' > "$orig"
if cmp -s "$orig" "$epicbody"; then
  echo "Epic body: no change."
  epic_changed=0
else
  echo "Epic body diff:"
  diff -u "$orig" "$epicbody" | sed 's/^/    /' || true
  epic_changed=1
fi

if [ "$apply" -eq 0 ]; then
  echo
  echo "Dry run complete. Re-run with --apply to write these changes."
  exit 0
fi

echo
echo "Applying..."

# Markers on child bodies.
for c in "${marker_children[@]}"; do
  cb="$(gh api "repos/$repo/issues/$c" --jq '.body // ""')"
  printf '%s\n\nEpic: #%s\n' "$cb" "$epic" | gh issue edit "$c" --repo "$repo" --body-file -
  echo "  marker added to #$c"
done

# Native sub-issue registration (idempotent — a 422 just means already linked).
for c in "${subissue_children[@]}"; do
  cid="$(gh api "repos/$repo/issues/$c" --jq '.id')"
  if gh api -X POST "repos/$repo/issues/$epic/sub_issues" -F "sub_issue_id=$cid" >/dev/null 2>&1; then
    echo "  #$c registered as sub-issue of #$epic"
  else
    echo "  #$c sub-issue link already present (or unsupported) — skipped"
  fi
done

# Epic body, pushed once.
if [ "$epic_changed" -eq 1 ]; then
  gh issue edit "$epic" --repo "$repo" --body-file "$epicbody"
  echo "  epic #$epic body updated"
fi

echo "Done."
