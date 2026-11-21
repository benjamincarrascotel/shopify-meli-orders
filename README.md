# shopify-meli-orders

Buy each paid Shopify order on Mercado Libre with the customer as the recipient, then mark it fulfilled in
Shopify so the customer gets the shipping email. One command per day, or none once it is scheduled.

Mercado Libre has no API to buy as a buyer, so the purchase runs in a real Chrome window that the tool
drives. That browser is isolated: each store has its own profile folder with its own Mercado Libre and
Shopify sessions, and your everyday Chrome profiles are never touched. Orders are read and updated through
the Shopify CLI, never in the browser.

> You are responsible for how you use this with your Mercado Libre account and for complying with its terms.

**Using an AI agent?** Give it this repository and say "install this and set it up". It reads
[`AGENTS.md`](AGENTS.md), installs what is missing for your system, and interviews you. You do not need to
read the rest of this page.

## What you need

These are strict. Nothing works without them, and `meli-orders doctor` checks them.

| | Requirement | Why |
|---|---|---|
| 1 | macOS, Windows or Linux with a desktop | The purchase happens in a visible Chrome window |
| 2 | [Google Chrome](https://www.google.com/chrome/) (Chromium is not enough) | It is the browser the tool drives |
| 3 | [Shopify CLI](https://shopify.dev/docs/api/shopify-cli) with the `shopify store auth` and `shopify store execute` commands (run with 4.9.4) | Orders are read, tagged and fulfilled through it |
| 4 | A Shopify store where you can approve app access (owner or staff with that permission) | One approval, the first time |
| 5 | A Mercado Libre account you can log in to, with **Mercado Pago balance** | Purchases are paid only with that balance. No card, no other method |
| 6 | Python 3.11 to 3.13, which [uv](https://docs.astral.sh/uv/) installs for you | The tool is a Python program |

What the tool assumes:

- **The balance covers the purchases.** A run compares it with everything pending and stops if it is short.
- **One product per order.** An order may have several units of one configured product; an order that mixes
  products is left for you.
- **The listing sells the same product you sell.** You choose the listings; the tool checks seller and
  variation on every purchase, not the product itself.
- **You approve the first purchase of each product** with its real price, shipping and total. After it you
  choose: automatic, or ask every time. There is no price or shipping cap; the only spending limit is an
  optional daily cap per store.
- **Orders ship without a tracking number.** The order is fulfilled when Mercado Libre confirms the purchase.
- git is not needed: a downloaded zip works the same.

## Install

1. **Get the code.** `git clone https://github.com/benjamincarrascotel/shopify-meli-orders`, or download
   [the zip](https://github.com/benjamincarrascotel/shopify-meli-orders/archive/refs/heads/dev.zip) and unpack it.
2. **Install uv, Google Chrome and the Shopify CLI** for your system:

   | | macOS | Windows (PowerShell) | Linux |
   |---|---|---|---|
   | uv | `brew install uv` | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
   | Google Chrome | `brew install --cask google-chrome` | `winget install -e --id Google.Chrome` | the `.deb` or `.rpm` from [google.com/chrome](https://www.google.com/chrome/) |
   | Shopify CLI | `brew tap shopify/shopify && brew install shopify-cli` | `winget install -e --id OpenJS.NodeJS.LTS`, then `npm install -g @shopify/cli@latest` | Node.js LTS, then `npm install -g @shopify/cli@latest` |

   On macOS without Homebrew, the Linux commands for uv and the Shopify CLI work too.
3. **Install the tool and check.** In the repository folder:

   ```bash
   uv sync
   uv run meli-orders doctor
   ```

   `doctor` lists what is missing with the install command for your system. Run it until nothing is marked ✗.

Without uv: with Python 3.11 to 3.13, `python -m venv .venv`, activate it, `pip install -e .` (the `-e`
matters: the configuration lives next to the code), and use `meli-orders ...` wherever this page says
`uv run meli-orders ...`.

## Set up and run

```bash
uv run meli-orders settings es                                   # or en: the language you are addressed in
uv run meli-orders store add mystore mystore.com                 # approve the access to the store, once
uv run meli-orders store login mystore                           # log in to Mercado Libre in the store's browser
uv run meli-orders product list mystore                          # pick what is bought on Mercado Libre
uv run meli-orders product search mystore "cat scratcher arch"   # candidates
uv run meli-orders product init mystore scratcher --shopify-product 123 \
    --listing https://www.mercadolibre.cl/...
uv run meli-orders product check mystore scratcher --save        # payment screen, nothing paid
uv run meli-orders run mystore                                   # the purchase run
```

With an AI agent, ask it to "set up meli-orders" or "run today's purchases": the skills in [`skills/`](skills/)
walk through the same steps, interview you and research the listings. They are plain Markdown, usable by any
agent that reads [`AGENTS.md`](AGENTS.md); Claude Code can also install them as a plugin from this repository.

The Shopify approval opens in the store's isolated browser on macOS and in your default browser on Windows
and Linux. The Shopify CLI keeps the authorization, so it makes no difference afterwards.

## What a run does

For every open, paid, unfulfilled order whose product is configured:

1. Checks the order (one configured product, known variant, complete address) and the optional daily cap.
2. Opens the listing, checks seller and variation, sets the quantity, uses «Comprar ahora» and enters the
   customer's address. If the main listing fails a check, the next approved listing is tried.
   The address is cleaned first: what follows the house number (floor, office, apartment) goes to the
   delivery notes, and only street and number are typed. Mercado Libre's suggestion must be in the order's
   commune, with the same number and a close street name (a spelling slip or «Ohiggins» for «O'Higgins»
   passes). Symbols its own forms refuse are removed. Anything that does not match sends the order to
   manual review with the reason.
   Shopify's checkout has no RUT field, so a store may relabel «Empresa» (Company) as «RUT»: the order then
   shows the customer's RUT as company. A RUT there is not sent and does not make the address a workplace;
   any other company does.
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
- There is no price or shipping cap: a purchase costs what the listing and the delivery cost that day, and
  the first purchase of a product shows you price, shipping and total before paying. A run never spends
  past the store's optional daily cap or the balance. The balance is checked against everything pending
  before the first purchase of a run.

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
    ├── products/<product>.json   Shopify product and variants, listings in order, approval mode
    ├── ledger.jsonl              one line per outcome: bought, manual, needs approval, unconfirmed
    ├── browser-profile/          the isolated Chrome profile with the logged-in sessions
    └── runs/<date>/              screenshots of the payment and confirmation screens
```

Each file has a JSON Schema in [`src/meli_orders/schemas/`](src/meli_orders/schemas/) that documents every
field and is enforced on load and save; `meli-orders validate` checks the whole folder. Edit a product file
by hand to set `units_per_item` for packs, reorder listings or pause a product.

`browser-profile/` holds live sessions of your Mercado Libre and Shopify accounts. Treat the `local/` folder
like a password: do not copy, zip or share it.

## What has been tested

Done for real, on macOS with Mercado Libre Chile:

- Setup from an empty folder by an AI agent following the skills: store, Mercado Libre login, product.
- A real order of one unit: bought with the Mercado Pago balance, delivered to the customer's address,
  tagged, noted and fulfilled in Shopify, with the customer's shipping email sent.
- Two units of one listing: taken to the payment screen and the total read, without paying.

Checked only by the automated tests, which run on macOS, Windows and Linux at every change: the order
logic, addresses, the review screen's figures, configuration, and the whole run against fakes including the
order of every write to Shopify. They never open a browser or reach a store.

Not tested yet:

- **Windows and Linux.** The code is written for them and the automated tests pass there, but nobody has run
  a purchase on them. `doctor` marks the system with `!` as a reminder.
- **Mercado Libre sites other than Chile.** The domains are configured; the address form was never exercised.
- Fallback listings and the free-delivery choice: implemented and unit-tested, not yet met in a real purchase.
- Three to six units in one purchase. More than six is not automated: the order is left for manual review.
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
