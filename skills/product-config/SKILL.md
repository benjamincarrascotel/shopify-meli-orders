---
name: product-config
description: >-
  Configures which Mercado Libre listing is bought for a Shopify product: lets the user pick the product,
  researches listings, proposes every candidate from best to worst match with its link, records the main
  listing and fallbacks the user chose, and measures the real price, shipping and total without paying. Use
  to add a product, replace its listings, set pack sizes, or switch it between automatic and
  ask-every-time.
---

# Configure a product

## 1. Which product

`uv run meli-orders product list <store>` lists the store's active products with their images and variants,
and `configured_as` for those already set up. Show the list and let the user choose. Products they do not
choose are ignored for good: their orders are never touched.

## 2. Research

1. Search with several queries built from the product's title and key attributes (material, shape, size):
   `uv run meli-orders product search <store> "<query>"`. Results come organic first; `ad` marks sponsored
   ones.
2. Read the promising ones: `uv run meli-orders product inspect <store> <url>` returns price, seller,
   official store, FULL (stored and shipped by Mercado Libre), stock, rating, sales, the selected variation
   and the image URLs.
3. Compare each one with the store's product. Open **every** image of the listing's gallery (`images`),
   not only the first, next to the store's images, and read the measures and materials in its text. One
   photo from another angle is not a difference: a single image that looks different while the rest of
   the gallery and the measures agree is the same product.
4. Order all of them from best to worst match; between equal matches, by lowest price, then FULL, then
   seller reputation (official store, sales, rating).

## 3. Propose; the user decides

You recommend, the user chooses. Never drop a candidate or pick the listings on your own.

Show **every** candidate you read, best match first, in a table: the full link so they can open it,
seller, price, FULL, rating and sales, how sure you are that it is the same product, and any doubt you
have in one line ("first photo shows the ball on one post; the other photos and the measures agree").
A doubt lowers a candidate in the list; it does not remove it. Only a product that is plainly another one
(other shape, other parts, other size) goes below the table, in one line with its link and the reason, so
the user can still overrule you.

Then give your recommendation (which one as main, which as fallbacks and in what order) and ask which ones
they keep. A fallback is used only when the main one fails a check (other seller, no stock, another
variation). End with one short line: if they already have a listing in mind, they can paste its link and
you add it. Read that one with `product inspect` and treat it like the others.

Do not propose, ask for or set any price or shipping limit: the tool has none. The cost of a purchase is
the listing's price plus the delivery to that customer, whatever it is that day.

## 4. Record

```bash
uv run meli-orders product init <store> <key> --shopify-product <id> \
    --listing <main url> --listing <fallback url> \
    --notes "<what the research found>"
```

The command reads seller and selected variation from each listing page. Then:

- **Packs.** If a Shopify variant is a pack, set its `units_per_item` in
  `local/stores/<store>/products/<key>.json` and run `uv run meli-orders validate`.
- **Measure.** `uv run meli-orders product check <store> <key> --save --evidence "<why it is identical>"`
  takes every listing to the payment screen, pays nothing, and records unit price, shipping and total. It
  delivers to the account's default address, so shipping to a customer elsewhere can differ.
  Add `--units 2` to see that the listing sells more than one.
- **Report.** Show the user, per listing: price, shipping and total. That is what a purchase costs. Say that
  shipping changes with each customer's address and that nothing blocks a purchase because of it.

## 5. What the user should know

- The **first purchase** of this product always stops: the tool shows the real price, shipping and total
  for that customer and waits for a yes.
- After it they choose: `uv run meli-orders product approval <store> <key> auto` (buy without asking) or
  `each` (ask before every purchase). Until they choose, every purchase asks.
- To stop buying a product, set `"status": "paused"` in its file.
