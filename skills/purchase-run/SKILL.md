---
name: purchase-run
description: >-
  Runs the purchases of a store: buys each paid Shopify order of a configured product on Mercado Libre,
  asks the user to approve when a purchase needs it, and reports what was bought, what was left for manual
  review and why. Use for "run today's purchases", "buy order #1234", "why was this order not bought", or
  after an approval was pending.
---

# Purchase run

## Before

`uv run meli-orders status <store>` shows, without opening a browser, each pending order and what a run
would do with it, the products and their approval mode, the daily cap and what was spent today. If there
is more than one store and the user named none, ask which.

## Run

```bash
uv run meli-orders run <store> --json
```

`--order '#1234'` limits it to one order. `--dry-run` stops on the payment screen of the first order, pays
nothing and writes nothing. The output is `{store, results, exit_code}`; act on the exit code.

| Exit | What happened | What you do |
|---|---|---|
| 0 | Everything eligible was bought and fulfilled, or there was nothing | Report the results |
| 20 | A result has `"result": "needs_approval"` | Show its figures and ask; see below |
| 10 | Some results are `"manual"` | Report each order with its `text`; the order is tagged `mercadolibre-manual` and untouched otherwise |
| 30 | A result is `"stopped"` (daily cap or balance) | Report its `text`; nothing more is bought until the user acts |
| 1 | An error, or `"unconfirmed"` | See "Unconfirmed payment" |

### Approval

A purchase waits when it is the first of its product or the product is set to ask every time. Show the user,
in their language: order, product and units, seller, recipient and address, delivery, price (`items`),
shipping, total, balance now and balance after. Ask for a yes or no. Only on a yes:

```bash
uv run meli-orders run <store> --approve '<order>' --json
```

The approval covers the total they saw. If the total went up, the command asks again instead of paying.

When a bought result has `"ask_approval_mode": true`, it was the product's first purchase. Ask the user
whether that product should now be bought automatically or ask before every purchase, and record it:
`uv run meli-orders product approval <store> <product> auto` or `each`.

### Unconfirmed payment

The pay button was pressed and Mercado Libre's confirmation was not seen. The order keeps the tag
`mercadolibre-check` and no run will buy it again. Do not retry and do not fulfil it. Tell the user to open
«Mis compras» in Mercado Libre and check whether the purchase exists; they then fix the order by hand
(remove `mercadolibre-check` to let it be bought, or mark it purchased and fulfil it).

## Report

Tell the user, in their language: orders bought with total and purchase number, orders left for manual
review with the reason, anything that stopped the run and what they need to do. Do not paste customer
addresses or phones into files.

## Manual-review orders

They are skipped by later runs. After the user fixed the cause (for example the address in Shopify), run
`uv run meli-orders run <store> --retry-manual --json`.
