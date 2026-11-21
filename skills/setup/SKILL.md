---
name: setup
description: >-
  First-time setup of this repository on a computer running macOS, Windows or Linux: asks the user's
  language, installs uv, Google Chrome, the Shopify CLI and the project's own dependencies with the command
  for that system, and checks the result. Use when asked to install or set up the repository, before
  anything else on a new machine, or when `meli-orders doctor` reports a missing tool.
---

# Setup

Nothing else works until this passes. It changes nothing in any store.

Work from the repository's root folder. Know the system first: macOS, Windows or Linux.

## 1. uv

`uv --version`. If it is missing, install it; it needs no administrator rights and brings its own Python.

| System | Command |
|---|---|
| macOS, Linux | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (macOS with Homebrew: `brew install uv`) |
| Windows | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |

Open a new terminal afterwards so `uv` is found. If the user refuses uv: with Python 3.11 to 3.13,
`python -m venv .venv`, activate it, `pip install -e .`, and from then on run `meli-orders ...` wherever a
skill says `uv run meli-orders ...`.

## 2. The tool

`uv sync` installs the project's libraries. Nothing else is downloaded: the browser is the user's Chrome.

## 3. Language

`uv run meli-orders settings`. If it shows no `language`, ask the user (Español first, English second) and
save it: `uv run meli-orders settings es` or `en`.

## 4. Check and install what is missing

`uv run meli-orders doctor --json`. Each item is `{check, ok, warning, detail, fix}`. For every item with
`ok: false` and `warning: false`, `fix` is the install command **for this system**: use it.

| Check | What it needs |
|---|---|
| `google-chrome` | Google Chrome itself; Chromium does not work |
| `shopify` | The Shopify CLI. Outside Homebrew it is installed with npm, so Node.js LTS goes first |

If the user asked you to install the repository, run these installers yourself after telling them what you
are about to install; a system installer may ask for their password. Otherwise give them the command and
wait. After installing, open a new terminal and run the check again until no item fails.

A `system validated` item with `warning: true` is not a failure: a whole purchase has only been run on
macOS. Tell the user that on Windows or Linux they are the first to try, and go on.

`stores` failing is expected here: continue with [store-connect](../store-connect/SKILL.md).

## What you cannot install

Tell the user now, so they have it ready:

- A **Mercado Libre account with Mercado Pago balance**. Purchases are paid only with that balance.
- A **Shopify store** where they can approve access for an app.
