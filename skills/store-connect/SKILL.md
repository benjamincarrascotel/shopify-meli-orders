---
name: store-connect
description: >-
  Connects one Shopify store and the Mercado Libre account that will buy for it: authorizes the store,
  opens the store's isolated browser for the Mercado Libre login, and records the daily spending cap. Use
  for the first store, for an additional store, when a session expired, or to change the daily cap.
---

# Connect a store

Each store gets its own isolated Chrome profile under `local/stores/<store>/browser-profile/`. Both
approvals below happen in that window, never in the user's everyday browser.

## Ask first

1. The store's `<name>.myshopify.com` domain.
2. A short name for it (lowercase, digits and hyphens), used in every command.
3. The Mercado Libre country. Only Chile (`MLC`) has been run; say so if they pick another.
4. Whether they want a daily spending cap for this store, and how much. It is optional: it protects
   against a mistake that would trigger many purchases.

## Steps

1. **Shopify.** `uv run meli-orders store add <store> <domain> --site MLC`. If the store is not yet
   authorized a window opens: the user logs in to Shopify there and approves the access. The approval asks
   for everything the tool will ever need, so it happens once.
2. **Mercado Libre.** `uv run meli-orders store login <store>`. The user logs in to the account that will
   buy. The command saves the account name; every later run refuses to continue under another account.
3. **Payment.** Tell the user: purchases are paid only with the Mercado Pago balance of that account, so it
   must have funds before a run. A run checks the balance against everything pending and stops if it is short.
4. **Daily cap.** `uv run meli-orders store limits <store> --daily-cap <amount>` or `--daily-cap none`.
5. **Verify.** `uv run meli-orders doctor`: the store's `shopify access` and `mercado libre account` pass.

Then continue with [product-config](../product-config/SKILL.md).

## Later

- "The session expired" or `wrong_account` in a run: repeat step 2.
- A store's `shopify access` check fails: repeat step 1.
