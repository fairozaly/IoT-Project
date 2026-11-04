# Smart Store

```sh
pip install -r requirements.txt
python app.py
```
Shopping cart API (sign-in required):

- `GET /api/cart`: current user's saved cart, current prices, totals and stock availability.
- `POST /api/cart/items`: add `{"barcode":"123","quantity":1}` or `{"product_id":1,"quantity":1}`. Quantity defaults to one and increments the existing quantity.
- `PATCH /api/cart/items/1`: set `{"quantity":2}`; zero removes the item.
- `DELETE /api/cart/items/1`: remove an item.
- `DELETE /api/cart`: empty the cart.

Cart contents persist in SQLite per user. Prices and stock come from the server;
adding to a cart does not reserve stock or complete a purchase. Payment must
revalidate stock and deduct inventory in its own transaction. Restart the app
to create the new CartItems table on an existing database.

Run backend checks: `python3 -m unittest discover -s tests -v`.

Products and RFID tags:

- Each product has one unique UPC; individual EPCs are stored in `ProductTags`
  with a many-to-one relationship to the product.
- In Inventory, click a product name or **Register EPC** to view and register
  tags. EPCs must contain 2–24 hexadecimal characters in pairs. They are
  normalized to uppercase and are unique across all products.
- Registering a tag does not change stock. Record deliveries with **Receive stock**.
- Startup migrates the former `Products.epc` values into `ProductTags`, keeping
  product IDs and related stock, purchase, and cart records.

The Scan Testing page polls the existing `tag_reader.py` reader automatically
and looks up detected EPCs, showing registered products without a page refresh.
Repeated EPCs update the same row. Use Pause scanning to stop polling.
The reader must be attached to the computer running Flask; defaults are
`RFID_PORT=/dev/ttyUSB0` and `RFID_BAUD=115200`. Close standalone reader scripts
before using the page. An unavailable reader is reported on the page and retried.
The existing reader command/parser is retained; hardware protocol verification
is still needed if the reader connects but produces no EPCs.
