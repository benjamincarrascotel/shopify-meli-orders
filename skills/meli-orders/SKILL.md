---
name: meli-orders
description: >-
  Entry point for buying Shopify orders on Mercado Libre with this repository. Use for any request about
  it: setting it up, connecting a store, choosing what to buy for a product, running the day's purchases,
  or finding out why an order was not bought. It checks what is configured, asks what it cannot know, and
  hands over to the right skill.
---

# meli-orders

Run every command as `uv run meli-orders ...` from the repository root. Follow [AGENTS.md](../../AGENTS.md).
If `uv` or the command is missing, the repository is not installed yet: start with [setup](../setup/SKILL.md).

## 1. Language first

Run `uv run meli-orders settings`. If it has no `language`, ask the user before anything else, offering
**Español** first and **English** second, and save it with `uv run meli-orders settings es` (or `en`).
From then on speak to the user in that language. Never guess it from the conversation.

## 2. See where things stand

Run `uv run meli-orders doctor --json`. Each item is `{check, ok, warning, detail, fix}`; an item fails
when `ok` is false and `warning` is false.

| What fails | Go to |
|---|---|
| `google-chrome`, `shopify`, `language`, `local-folder-ignored-by-git` | [setup](../setup/SKILL.md) |
| `stores`, or a store's `shopify access` or `mercado libre account` | [store-connect](../store-connect/SKILL.md) |
| a store's `products` | [product-config](../product-config/SKILL.md) |
| nothing | what the user asked for, below |

`system validated` and `site validated` only warn: tell the user that this system, or that Mercado Libre
site, has never been run end to end, and go on.

## 3. Do what was asked

| The user wants | Skill |
|---|---|
| First-time setup, "is everything installed" | [setup](../setup/SKILL.md), then store-connect, then product-config |
| Another store, a new Mercado Libre login, a daily cap | [store-connect](../store-connect/SKILL.md) |
| A new product, other listings, other caps, automatic or ask-every-time | [product-config](../product-config/SKILL.md) |
| Today's purchases, a specific order, why an order was not bought | [purchase-run](../purchase-run/SKILL.md) |

## Ask, do not assume

- More than one store in `uv run meli-orders store list` and the user did not name one: ask which.
- The request could mean two things (configure a product or buy now): ask.
- Anything that spends money needs figures the user has seen. Never approve a purchase on their behalf.
- Never invent a setting. A limit, an amount or a choice the user did not give is asked, and a "no" means
  none: the only spending limit that exists is the store's optional daily cap.
