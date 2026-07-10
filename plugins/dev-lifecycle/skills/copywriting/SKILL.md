---
name: copywriting
description: Write user-facing product and interface copy — microcopy (buttons, labels, empty states, error and success messages, tooltips), onboarding, notifications, and marketing/landing copy — in a consistent voice. Use this skill WHENEVER the work is words the end user reads in the product: "write the copy for X", "what should this button/error say", "write the empty state", "onboarding copy", "landing page headline", "make this message clearer". It detects and matches the product's voice, and runs a humanizer + ruthless-edit pass so the copy sounds human and tight. This is product copy — for technical docs use the documentation skill.
---

# Copywriting

Write the words the user reads, and make them clear, human, and consistent. Copy is UX: a good error message or empty state does real work. This skill writes product/UI copy and runs it through the quality pass (`humanizer`, `ruthless-edit`) so nothing ships bloated or AI-sounding.

## Core rules

- **Match the copy to the moment.** A button is a terse action; an error is calm and actionable (what happened + what to do); an empty state guides the next step; onboarding is warm; a landing headline earns attention. Don't write one register for all of them.
- **Voice is consistent across the project.** Detect the product's existing voice and terms and match them; use the same pattern for the same situation everywhere. Inconsistent copy reads as a buggy product.
- **Clear beats clever.** Plain language, short where short works, the user's words not the system's. Clever only when it doesn't cost clarity.
- **Human and tight.** Run every piece through `humanizer` (kill AI-isms and hedging) and `ruthless-edit` (cut filler). If a word isn't working, remove it.
- **Accessible.** Meaningful link and button text (never "click here"), plain language, no meaning carried by idiom or color alone.
- **Never fabricate.** No invented metrics, features, or claims in marketing copy — write what's true.

## Workflow

### 1. Identify the surface & voice
What copy, on what surface, for whom, at what moment. Detect the product's existing voice and terminology (read a few existing strings) and conform. If there's no established voice and it matters, propose one briefly and confirm.

### 2. Write to the moment
Use the right pattern for the surface:
- **Buttons/actions** — a verb, the specific action (`Save changes`, not `Submit`).
- **Errors** — what happened and what to do next, without blame or jargon; never a raw code alone.
- **Empty states** — orient and point to the first action.
- **Onboarding/tooltips** — one idea at a time, in the user's language.
- **Marketing/landing** — lead with the value to the user; concrete over superlative.

### 3. Quality pass
Apply `humanizer` and `ruthless-edit`: remove hedging, throat-clearing, AI tells, and filler; tighten to what earns its place. Read it aloud in your head — if it sounds like a bot, rewrite it.

### 4. Consistency check
Same situations use the same patterns and terms across the project. Note any terms worth adding to a shared voice/glossary so future copy stays aligned.

### 5. Hand off
Deliver the copy in context (which string goes where). Flag any voice or terminology decisions worth codifying for reuse, and anything you need a real value for rather than a placeholder.

## What this skill does NOT do
- Fabricate product claims, metrics, or features.
- Write technical documentation (that's `documentation`).
- Ship AI-sounding or padded copy — the quality pass is mandatory.
- Impose a new voice on a product that already has one.
