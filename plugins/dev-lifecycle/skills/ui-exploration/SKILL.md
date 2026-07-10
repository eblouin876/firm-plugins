---
name: ui-exploration
description: Explore net-new UI — a new screen, feature look, or a product's visual direction — and turn the chosen direction into an implementable spec. Use this skill WHENEVER the work is figuring out what something should look like before building it: "design a screen for X", "explore some directions for this UI", "what should this page look like", "mock up the dashboard", "help me figure out the layout". It leans on Claude Design for visual exploration where available, then captures the decisions as a spec that the frontend skill implements and the design-system skill codifies. It explores and specs; it does not implement.

---

# UI exploration

Figure out what new UI should look like, then hand the build a clear spec — not just a picture. This skill bridges "what should it look like" and "here's the buildable thing": it explores directions (in **Claude Design** where available — its canvas is the right place to iterate visually), converges with you on one, and turns that into a spec `frontend` can implement against `design-system`'s tokens.

## Core rules

- **Explore before committing.** Consider a few directions rather than building out the first idea. Use Claude Design's canvas for visual exploration when it's available; otherwise lay out the options clearly enough to choose between. Get the user's pick before spec'ing.
- **Output a spec, not just visuals.** A picture isn't buildable on its own. The deliverable is layout structure, component breakdown, the tokens it uses, every state, responsive behavior, interactions, and accessibility.
- **Feed the system, don't fork it.** Reuse the existing `design-system` tokens wherever possible. Genuinely new tokens get *proposed to* `design-system` to codify — never hardcoded into the eventual components.
- **Explore and spec; don't implement.** `frontend` builds it; `design-system` codifies the tokens. This skill stops at the spec.
- **Ground in what exists.** For a brownfield app, the exploration lives within the current design system and patterns. For greenfield, the chosen direction becomes the seed `design-system` then formalizes.

## Workflow

### 1. Understand the UI need
What screen/feature/flow, for whom, with what content and constraints (brand, existing patterns, device targets). Pull the real content where possible — designing around realistic data beats lorem ipsum.

### 2. Explore directions
Generate a few distinct directions. In **Claude Design**, iterate on the canvas and refine via chat; otherwise present the options with enough structure (layout, hierarchy, mood) to choose. Converge with the user on one direction — don't spec three.

### 3. Turn the chosen direction into a spec
Capture it as something buildable:
- **Layout & hierarchy** — structure, regions, responsive behavior across breakpoints.
- **Component breakdown** — the components involved, new vs reused.
- **Tokens** — which `design-system` tokens it uses; any new ones it implies.
- **States** — default, hover, active, disabled, loading, empty, error.
- **Interactions** — what responds to what, transitions, feedback.
- **Accessibility** — semantics, focus order, contrast, keyboard paths.

### 4. Reconcile with the design system
Map the spec onto existing tokens; list any net-new tokens for `design-system` to add. Flag anything that would break existing patterns so it's a deliberate choice, not drift.

### 5. Hand off
Deliver the spec to `frontend` (to implement) and the new-token list to `design-system` (to codify). Note anything still open for the user to decide.

## What this skill does NOT do
- Implement the UI (that's `frontend`).
- Invent one-off tokens hardcoded into components (propose them to `design-system`).
- Hand over an image with no spec behind it.
- Explore endlessly — converge on a direction, then spec it.
