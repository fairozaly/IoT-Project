(function () {
    'use strict';
    const indicator = document.getElementById('resultText');
    const barcodeInput = document.getElementById('barcode');
    let scanQueue = Promise.resolve();

    async function cartRequest(path = '/api/cart', method = 'GET', data) {
        const response = await fetch(path, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: data === undefined ? undefined : JSON.stringify(data)
        });
        const cart = await response.json();
        if (!response.ok) throw new Error(cart.error || 'Unable to update cart.');
        renderCart(cart);
    }

    async function scanItem(code) {
        try {
            await cartRequest('/api/cart/items', 'POST', {barcode: code});
            indicator.textContent = 'Item added.';
        } catch (error) {
            indicator.textContent = error.message;
        }
    }

    function renderCart(cart) {
        const container = document.getElementById('cart');
        container.replaceChildren();
        cart.items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'example-item';
            const label = document.createElement('span');
            label.textContent = `${item.name} — ${item.quantity} — $${item.subtotal.toFixed(2)}`;
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = '−';
            remove.setAttribute('aria-label', `Remove one ${item.name}`);
            remove.addEventListener('click', async () => {
                remove.disabled = true;
                try {
                    await cartRequest(`/api/cart/items/${item.product_id}`, 'PATCH', {quantity: item.quantity - 1});
                    indicator.textContent = 'Item removed.';
                } catch (error) {
                    indicator.textContent = error.message;
                } finally {
                    remove.disabled = false;
                }
            });
            row.append(label, remove);
            container.append(row);
        });
        document.getElementById('cart-total').textContent = `Total: $${cart.total.toFixed(2)}`;
        if (!cart.stock_available) indicator.textContent = 'Stock has changed. Remove unavailable quantities before checkout.';
    }

    document.getElementById('clear-cart').addEventListener('click', async () => {
        try {
            await cartRequest('/api/cart', 'DELETE');
            indicator.textContent = 'Cart cleared.';
        } catch (error) {
            indicator.textContent = error.message;
        }
    });
    cartRequest().catch(error => { indicator.textContent = error.message; });
    document.getElementById('barcode-form').addEventListener('submit', event => {
        event.preventDefault();
        const code = barcodeInput.value.trim();
        if (!code) return;
        barcodeInput.value = '';
        barcodeInput.focus();
        scanQueue = scanQueue.then(() => scanItem(code));
    });
})();
