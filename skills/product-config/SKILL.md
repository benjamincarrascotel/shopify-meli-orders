---
name: product-config
description: >-
  Configures which Mercado Libre listing is bought for a Shopify product: lets the user pick the product,
  researches listings, shows the best candidates with evidence that they are the same product, records the
  chosen main listing and fallbacks with their price caps, and measures the real total without paying. Use
  to add a product, replace its listings, change its caps, set pack sizes, or switch it between automatic
  and ask-every-time.
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
3. Decide whether each is **the same product**: look at the listing's images next to the store's images and
   compare shape, parts, measures and materials. Discard anything you cannot match and say why.
4. Rank what is left by, in this order: lowest total cost (price plus shipping), FULL, seller reputation
   (official store, sales, rating).

## 3. Propose and let the user choose

Show three to five candidates in a table: seller, price, FULL, rating and sales, link, and one line of
evidence that it is identical. Ask the user which is the main listing and which, if any, are fallbacks in
order. A fallback is used only when the main one fails a check (other seller, no stock, over the cap).

Propose the caps and let the user change them: `max_unit_price` about 20 % above the main listing's price,
`max_shipping` above the highest shipping you expect. A purchase may cost at most
`units × max_unit_price + max_shipping`.

## 4. Record

```bash
uv run meli-orders product init <store> <key> --shopify-product <id> \
    --listing <main url> --listing <fallback url> \
    --max-unit-price <n> --max-shipping <n> --notes "<what the research found>"
```

The command reads seller and selected variation from each listing page. Then:

- **Packs.** If a Shopify variant is a pack, set its `units_per_item` in
  `local/stores/<store>/products/<key>.json` and run `uv run meli-orders validate`.
- **Measure.** `uv run meli-orders product check <store> <key> --save --evidence "<why it is identical>"`
  takes every listing to the payment screen, pays nothing, and records unit price, shipping and total. It
  delivers to the account's default address, so shipping to a customer elsewhere can differ.
  Add `--units 2` to see that the listing sells more than one.

## 5. What the user should know

- The **first purchase** of this product always stops: the tool shows the real figures and waits for a yes.
- After it they choose: `uv run meli-orders product approval <store> <key> auto` (buy without asking) or
  `each` (ask before every purchase). Until they choose, every purchase asks.
- To stop buying a product, set `"status": "paused"` in its file.
