(function () {
    'use strict';
    const root = document.getElementById('selfCheckout');
    if (!root) return;
    const $ = id => document.getElementById(id);
    const money = value => new Intl.NumberFormat('en-CA', {
        style: 'currency',
        currency: 'CAD'
    }).format(Number(value) || 0);
    let cart = {items: [], quantity: 0, total: 0, stock_available: true};
    let hasMembership = false;
    let running = true;
    let busy = false;
    let completing = false;
    let step = 1;
    let readerTimer;
    let lastTagAt = 0;
    const seenEpcs = new Set();

    function notice(text, error = false) {
        const el = $('scNotice');
        el.hidden = false;
        el.textContent = text;
        el.style.borderColor = error ? '#ce7070' : '';
    }

    function updatePayment() {
        const enabled = step === 3 && hasMembership && cart.items.length > 0 && cart.stock_available;
        $('scPaymentAmount').textContent = money(cart.total);
        $('scPay').textContent = 'Pay now';
        $('scPay').disabled = completing || !enabled;
    }

    function setStep(next) {
        step = next;
        document.querySelectorAll('.sc-step').forEach(el => {
            const value = Number(el.dataset.step);
            el.classList.toggle('is-active', value === step);
            el.classList.toggle('is-done', value < step);
        });
        $('scMemberSection').hidden = step < 2;
        $('scPaymentSection').hidden = step < 3;
        $('scMemberSection').classList.toggle('is-current', step === 2);
        $('scPaymentSection').classList.toggle('is-current', step === 3);
        updatePayment();
    }

    function renderCart() {
        const container = $('scCartItems');
        container.replaceChildren();
        if (!cart.items.length) {
            const empty = document.createElement('div');
            empty.className = 'sc-empty';
            const icon = document.createElement('div');
            icon.className = 'sc-empty-icon';
            icon.textContent = '🛒';
            const strong = document.createElement('strong');
            strong.textContent = 'Your basket is empty';
            const text = document.createElement('p');
            text.textContent = 'Scan products to see them here.';
            empty.append(icon, strong, text);
            container.append(empty);
        }
        cart.items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'sc-item';
            const symbol = document.createElement('div');
            symbol.className = 'sc-item-symbol';
            if (item.image_url) {
                const image = document.createElement('img');
                image.src = item.image_url;
                image.alt = '';
                symbol.append(image);
            } else {
                symbol.textContent = (item.name || '?').charAt(0).toUpperCase();
            }
            const main = document.createElement('div');
            main.className = 'sc-item-main';
            const name = document.createElement('strong');
            name.textContent = item.name;
            const meta = document.createElement('small');
            meta.textContent = `${item.barcode} · ${item.quantity} × ${money(item.price)}`;
            main.append(name, meta);
            const side = document.createElement('div');
            side.className = 'sc-item-side';
            const subtotal = document.createElement('strong');
            subtotal.textContent = money(item.subtotal);
            side.append(subtotal);
            row.append(symbol, main, side);
            container.append(row);
        });
        $('scItemsCount').textContent = cart.items.length;
        $('scQuantity').textContent = cart.quantity;
        $('scSubtotal').textContent = money(cart.total);
        $('scTotal').textContent = money(cart.total);
        $('scNext').disabled = !cart.items.length || !cart.stock_available;
        if (!cart.stock_available) notice('Some quantities are no longer available. Update the basket before checkout.', true);
        updatePayment();
    }

    async function cartRequest(path = '/api/cart', method = 'GET', data) {
        const response = await fetch(path, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: data === undefined ? undefined : JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Unable to update cart.');
        cart = result;
        renderCart();
    }

    function setReader(connected) {
        const badge = $('scReaderBadge');
        badge.textContent = connected ? 'Reader online' : 'Not connected';
        badge.classList.toggle('online', connected);
    }

    async function addTagProduct(result) {
        if (!result.product) {
            notice(`Tag ${result.epc} is not registered to a product.`, true);
            return false;
        }
        await cartRequest('/api/cart/items', 'POST', {
            product_id: result.product.product_id, epc: result.epc
        });
        return true;
    }

    async function pollTags() {
        if (!running || busy) return;
        busy = true;
        try {
            const response = await fetch('/api/checkout/tags');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Reader unavailable.');
            setReader(data.connected);
            if (!data.connected) {
                $('scScanHeadline').textContent = 'Reader unavailable';
                $('scScanCaption').textContent = data.error || 'Check the RFID reader connection.';
                return;
            }
            $('scScanHeadline').textContent = 'Scanning automatically';
            $('scScanCaption').textContent = 'Place your products in the reader detection area.';
            for (const result of data.results) {
                if (seenEpcs.has(result.epc)) continue;
                seenEpcs.add(result.epc);
                try {
                    if (await addTagProduct(result)) {
                        lastTagAt = Date.now();
                        notice(`Added ${result.product.name} (${result.epc}).`);
                    }
                } catch (error) {
                    seenEpcs.delete(result.epc);
                    notice(error.message, true);
                }
            }
            $('scScanCount').textContent = `${seenEpcs.size} unique tag${seenEpcs.size === 1 ? '' : 's'}`;
            $('scLastScan').textContent = lastTagAt
                ? `Last tag read at ${new Date(lastTagAt).toLocaleTimeString()}`
                : 'No tags detected yet';
        } catch (error) {
            setReader(false);
            notice(error.message, true);
        } finally {
            busy = false;
            if (running) readerTimer = setTimeout(pollTags, 700);
        }
    }

    function setMembership(customer) {
        const box = $('scMemberStatus');
        box.replaceChildren();
        const icon = document.createElement('span');
        icon.className = 'sc-member-icon';
        icon.textContent = customer ? '✓' : '★';
        const text = document.createElement('span');
        const strong = document.createElement('strong');
        const small = document.createElement('small');
        if (customer) {
            strong.textContent = `${customer.first_name} ${customer.last_name}`;
            small.textContent = `Membership ${customer.membership_number} · ${customer.total_points} points`;
        } else {
            strong.textContent = 'No membership applied';
            small.textContent = 'Enter a membership number or continue as a guest.';
        }
        text.append(strong, small);
        box.append(icon, text);
        hasMembership = Boolean(customer);
        $('scMembershipContinue').textContent = 'Continue to payment';
        $('scMembershipContinue').disabled = !hasMembership;
        updatePayment();
    }

    $('scClearCart').addEventListener('click', async () => {
        try {
            await cartRequest('/api/cart', 'DELETE');
            seenEpcs.clear();
            $('scScanCount').textContent = '0 unique tags';
            $('scLastScan').textContent = 'No tags detected yet';
            notice('Basket cleared.');
        } catch (error) {
            notice(error.message, true);
        }
    });

    $('scNext').addEventListener('click', () => {
        setStep(2);
        $('scMemberSection').scrollIntoView({behavior: 'smooth', block: 'center'});
        $('scMembershipNumber').focus();
    });

    $('scMembershipContinue').addEventListener('click', () => {
        if (!hasMembership) return;
        setStep(3);
        $('scPaymentSection').scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    $('scMembershipForm').addEventListener('submit', async event => {
        event.preventDefault();
        const input = $('scMembershipNumber');
        const number = input.value.trim();
        const message = $('scMembershipMessage');
        if (!number) {
            message.textContent = 'Scan or enter a membership number.';
            return;
        }
        try {
            const response = await fetch('/api/checkout/membership', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({membership_number: number})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Membership not found.');
            setMembership(data.customer);
            input.value = '';
            message.textContent = 'Membership applied. Continue to payment.';
            message.style.color = '';
        } catch (error) {
            message.textContent = error.message;
            message.style.color = '#ce6060';
        }
    });

    $('scPaymentForm').addEventListener('submit', event => {
        if ($('scPay').disabled) {
            event.preventDefault();
            return;
        }
        completing = true;
        $('scPay').disabled = true;
        $('scPay').textContent = 'Completing checkout…';
    });

    window.addEventListener('pagehide', () => {
        running = false;
        clearTimeout(readerTimer);
    });

    setMembership(null);
    setStep(1);
    cartRequest().catch(error => notice(error.message, true));
    pollTags();
})();
