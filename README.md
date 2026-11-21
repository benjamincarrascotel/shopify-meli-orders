# shopify-meli-orders

Buy each paid Shopify order on Mercado Libre with the customer as the recipient, then mark it fulfilled in
Shopify so the customer gets the shipping email. One command per day, or none once it is scheduled.

Mercado Libre has no API to buy as a buyer, so the purchase runs in a real Chrome window that the tool
drives. That browser is isolated: each store has its own profile folder with its own Mercado Libre and
Shopify sessions, and your everyday Chrome profiles are never touched. Orders are read and updated through
the Shopify CLI, never in the browser.

> You are responsible for how you use this with your Mercado Libre account and for complying with its terms.
> Only Mercado Libre Chile on macOS has been run end to end. See [What has not been validated](#what-has-not-been-validated).

## Requirements

- macOS, [Google Chrome](https://www.google.com/chrome/), [uv](https://docs.astral.sh/uv/), git
- [Shopify CLI](https://shopify.dev/docs/api/shopify-cli) and a Shopify store you own
- A Mercado Libre account with Mercado Pago balance: purchases are paid only with that balance

`meli-orders doctor` checks all of it and says how to fix what is missing.

## Quick start

```bash
git clone https://github.com/benjamincarrascotel/shopify-meli-orders && cd shopify-meli-orders
uv sync
uv run meli-orders settings es                                   # or en: the language you are addressed in
uv run meli-orders doctor
uv run meli-orders store add mystore mystore.com                 # approve the access in the store's browser
uv run meli-orders store login mystore                           # log in to Mercado Libre in that browser
uv run meli-orders product list mystore                          # pick what is bought on Mercado Libre
uv run meli-orders product search mystore "cat scratcher arch"   # candidates
uv run meli-orders product init mystore scratcher --shopify-product 123 \
    --listing https://www.mercadolibre.cl/... --max-unit-price 11000 --max-shipping 4000
uv run meli-orders product check mystore scratcher --save        # payment screen, nothing paid
uv run meli-orders run mystore                                   # the purchase run
```

With an AI agent, ask it to "set up meli-orders" or "run today's purchases": the skills in [`skills/`](skills/)
walk through the same steps, interview you and research the listings. They are plain Markdown, usable by any
agent that reads [`AGENTS.md`](AGENTS.md); Claude Code can install them as a plugin from this repository.

## What a run does

For every open, paid, unfulfilled order whose product is configured:

1. Checks the order (one configured product, known variant, complete address) and the limits.
2. Opens the listing, checks seller and variation, sets the quantity, uses «Comprar ahora» and enters the
   customer's address. If the main listing fails a check, the next approved listing is tried.
3. Reads the real total and the Mercado Pago balance from the payment screen.
4. The first purchase of a product stops here: the browser closes and you get the figures to approve. After
   it you choose whether that product is bought automatically or asks every time.
5. Pays with the Mercado Pago balance, waits for Mercado Libre's confirmation, then tags the order, writes
   the purchase in its note and in the local ledger, and fulfils it in Shopify.

### Rules it never breaks

- An order is fulfilled, and the customer emailed, only after Mercado Libre confirmed the purchase.
- The tag `mercadolibre-check` goes on the order before the pay click and becomes `mercadolibre-purchased`
  on confirmation. An order left with `mercadolibre-check` is never bought again until you look at it.
- An order that could not be bought gets `mercadolibre-manual` and the reason in its note. Nothing else
  about it changes. Remove the tag, or use `--retry-manual`, to try again.
- A purchase never exceeds `units × max_unit_price + max_shipping`, the optional daily cap, or the balance.
  The balance is checked against everything pending before the first purchase of a run.

### Exit codes of `run`

| Code | Meaning |
|---|---|
| 0 | Done, or nothing to buy |
| 10 | Some orders were left for manual review |
| 20 | A purchase waits for approval: `meli-orders run <store> --approve '<order>'` |
| 30 | Stopped by the daily cap or the balance |
| 1 | Error, or a payment whose confirmation was not seen |

## Configuration

Everything about your stores lives in `local/`, which git ignores: commit nothing from it.

```text
local/
├── settings.json                 language
└── stores/<store>/
    ├── store.json                Shopify domain, Mercado Libre site and account, daily cap
    ├── products/<product>.json   Shopify product and variants, listings in order, caps, approval mode
    ├── ledger.jsonl              one line per outcome: bought, manual, needs approval, unconfirmed
    ├── browser-profile/          the isolated Chrome profile with the logged-in sessions
    └── runs/<date>/              screenshots of the payment and confirmation screens
```

Each file has a JSON Schema in [`src/meli_orders/schemas/`](src/meli_orders/schemas/) that documents every
field and is enforced on load and save; `meli-orders validate` checks the whole folder. Edit a product file
by hand to set `units_per_item` for packs, reorder listings or pause a product.

`browser-profile/` holds live sessions of your Mercado Libre and Shopify accounts. Treat the `local/` folder
like a password: do not copy, zip or share it.

## What has not been validated

- Mercado Libre sites other than Chile: the domains are configured, the address form was never exercised.
- Systems other than macOS: connecting a store relies on macOS's `open`.
- Fallback listings and the free-delivery choice: implemented and unit-tested, not yet met in a real purchase.
- More than 6 units of one listing, and orders that mix products: left for manual review.
- Post-purchase tracking: none. The order is fulfilled without a tracking number.

## Development

```bash
uv sync
uv run pytest
```

The tests cover the pure logic and the whole run against fakes, including the order of every write to
Shopify. They never open a browser or reach a store.

## License

[MIT](LICENSE)
