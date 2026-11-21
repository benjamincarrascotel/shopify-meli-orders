# Agent instructions

This repository buys paid Shopify orders on Mercado Libre and fulfils them. It moves real money and emails
real customers, so the rules below are not style preferences.

## Asked to install or set this up

The user will not read documentation: they hand you this repository and expect it working. Do it in this
order and do not skip ahead.

1. Find out the system (macOS, Windows or Linux) and follow [`skills/setup/SKILL.md`](skills/setup/SKILL.md):
   it has the install command of each requirement per system.
2. When `uv run meli-orders doctor` shows no ✗, continue with
   [`skills/meli-orders/SKILL.md`](skills/meli-orders/SKILL.md), which connects the store and configures
   the products by interviewing the user.

Tell the user up front what cannot be installed for them: a Mercado Libre account with Mercado Pago balance
(the only payment method) and a Shopify store they can approve access to.

## Using it for a user

Start from [`skills/meli-orders/SKILL.md`](skills/meli-orders/SKILL.md). It decides which of the other skills
applies and what to ask first. Run commands as `uv run meli-orders ...` from the repository root.

- Address the user in the language stored in settings (`uv run meli-orders settings`). If none is stored,
  ask for it before anything else.
- Never assume which store: with more than one, ask.
- Never pay around the tool: do not click in its browser, do not pass `--approve` without the user's yes to
  the figures of that purchase, do not edit order tags to force a retry unless the user says so.
- Never fulfil an order by hand to "fix" a run. An order is fulfilled only by a confirmed purchase.
- `local/` holds store configuration, the purchase ledger and logged-in browser sessions. Never commit,
  copy, print or upload anything from it. Do not paste customer names, addresses or phones into files in git.

## Changing the code

- Everything in the repository is English: code, comments, documentation, skills, commit messages. Texts shown
  to the user live in `src/meli_orders/locales/` in every supported language, with the same keys.
- The integrity rules are stated at the top of [`src/meli_orders/run.py`](src/meli_orders/run.py) and in the
  README. A change must keep them, and `tests/test_run.py` checks the order of writes to Shopify.
- Screens are located by their visible labels. When Mercado Libre changes one, fix the locator in
  `src/meli_orders/meli/` and say in the docstring when it was last observed. Mark anything not exercised
  against the real site as "not exercised".
- A new field in a configuration file goes into its JSON Schema with a description, in the same change.
- Run `uv run pytest` before committing.
