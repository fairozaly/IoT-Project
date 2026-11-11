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

() => {
  'use strict';
  const root = document.getElementById('selfCheckout');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const money = v => new Intl.NumberFormat('en-CA', {
    style: 'currency',
    currency: 'CAD'
  }).format(Number(v) || 0);
  const member = root.dataset.member === 'true';
  let cart = {
    items: [],
    quantity: 0,
    total: 0,
    stock_available: true
  };
  let scanning = false,
    busy = false,
    completing = false,
    step = 1;
  const seenEpcs = new Set(),
    removedEpcs = new Set(),
    epcToProduct = new Map();
  let readerTimer;

  function notice(message, error = false) {
    const el = $('scNotice');
    el.hidden = false;
    el.textContent = message;
    el.style.borderColor = error ? '#ce7070' : '';
  }

  function paymentMethod() {
    return document.querySelector('input[name="demo_payment_method"]:checked')?.value || 'credit';
  }

  function validCash() {
    const input = $('scCashReceived');
    return input.value.trim() !== '' && Number.isFinite(Number(input.value)) && Number(input.value) >= Number(cart.total) && Number(input.value) >= 0;
  }

  function updatePayment() {
    const method = paymentMethod(),
      enabled = step === 4 && cart.items.length > 0 && cart.stock_available;
    $('scPaymentMethods').disabled = !enabled;
    for (const [name, id] of Object.entries({
        credit: 'scCardFields',
        debit: 'scDebitFields',
        cash: 'scCashFields',
        mobile: 'scMobileFields'
      })) $(id).hidden = method !== name;
    $('scCashReceived').disabled = !enabled || method !== 'cash';
    $('scPaymentAmount').textContent = money(cart.total);
    $('scPay').textContent = `Pay ${money(cart.total)} (simulation)`;
    const cashValid = method !== 'cash' || validCash();
    $('scChange').textContent = money(method === 'cash' && validCash() ? Math.max(0, Number($('scCashReceived').value) - Number(cart.total)) : 0);
    $('scCashError').textContent = enabled && method === 'cash' && !cashValid ? 'Enter a cash amount equal to or greater than the total.' : '';
    $('scPay').disabled = completing || !enabled || !$('scConfirm').checked || !cashValid;
  }
}

