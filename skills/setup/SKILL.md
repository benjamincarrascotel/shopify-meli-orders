---
name: setup
description: >-
  First-time setup of this repository on a computer: asks the user's language, checks that Google Chrome,
  uv, git and the Shopify CLI are installed, tells the user how to install what is missing, and installs
  the project's own dependencies. Use before anything else on a new machine, or when `meli-orders doctor`
  reports a missing tool.
---

# Setup

Nothing else works until this passes. It changes nothing in any store.

1. **Language.** If `uv run meli-orders settings` shows no `language`, ask the user (Español first, English
   second) and save it: `uv run meli-orders settings es`. If `uv` itself is missing, ask in the
   conversation and save it after step 3.
2. **Check.** `uv run meli-orders doctor --json`.
3. **Install what is missing.** For each failed tool give the user the `fix` text from the check and wait
   for them to install it; do not install system software yourself unless they ask you to.
   - Google Chrome: https://www.google.com/chrome/
   - uv: `brew install uv`
   - git: `xcode-select --install`
   - Shopify CLI: `brew tap shopify/shopify && brew install shopify-cli`
4. **Project dependencies.** `uv sync` in the repository root.
5. **Check again.** Repeat step 2 until the tool checks pass. Then continue with
   [store-connect](../store-connect/SKILL.md).

Only macOS has been run. On another system say so before going on: connecting a store opens the browser
through macOS's `open`.
