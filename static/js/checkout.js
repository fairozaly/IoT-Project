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
    const signedInMember = root.dataset.member === 'true';
    const membershipForm = $('scMembershipForm');
    const membershipInput = $('scMembershipNumber');
    const membershipMessage = $('scMembershipMessage');
    const membershipContinue = $('scMembershipContinue');
    let membershipApplied = false;
    let membershipPending = false;
    let running = true;
    let readerRequest;
    let transitioning = false;
    let completing = false;
    let step = 1;
    let readerTimer;
    let lastTagAt = 0;
    const seenEpcs = new Set();

    function isMacOSBrowser() {
        const userAgent = navigator.userAgent || '';
        const platform = navigator.userAgentData?.platform || navigator.platform || '';
        const isTouchMac = navigator.maxTouchPoints > 1 && /Macintosh|Mac OS X/i.test(userAgent);
        return !isTouchMac && (/Macintosh|Mac OS X/i.test(userAgent) || /^Mac/i.test(platform));
    }

    function initMockControls() {
        const container = $('scMockControls');
        if (!container || !isMacOSBrowser()) return;

        let products;
        try {
            products = JSON.parse(container.dataset.products || '[]');
        } catch (error) {
            return;
        }
        if (!Array.isArray(products) || !products.length) return;

        const title = document.createElement('h3');
        title.textContent = 'Simulate RFID scans';
        const description = document.createElement('p');
        description.textContent = 'macOS test control. Each click scans one registered sample tag.';
        const sampleBasket = document.createElement('button');
        sampleBasket.type = 'button';
        sampleBasket.className = 'sc-btn sc-btn-primary';
        sampleBasket.textContent = 'Load sample basket';
        sampleBasket.title = 'Scan three available sample products';
        const list = document.createElement('div');
        list.className = 'sc-mock-product-list';
        const mockButtons = new Map();

        function availableEpc(product) {
            const epcs = Array.isArray(product.epcs) ? product.epcs : [];
            return epcs.find(value => !seenEpcs.has(value));
        }

        products.forEach(product => {
            const epcs = Array.isArray(product.epcs) ? product.epcs : [];
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'sc-btn sc-btn-soft';
            button.textContent = `Scan ${product.name}`;
            button.dataset.productId = String(product.product_id);
            button.disabled = !product.in_stock || epcs.length === 0;
            if (!product.in_stock) button.title = 'Out of stock';
            if (epcs.length === 0) button.title = 'No sample RFID tags are registered';
            button.addEventListener('click', async () => {
                if (button.disabled) return;
                const epc = epcs.find(value => !seenEpcs.has(value));
                if (!epc) {
                    button.disabled = true;
                    button.title = 'All sample RFID tags have been scanned';
                    return;
                }
                button.disabled = true;
                try {
                    await addTagProduct({
                        epc,
                        product: {product_id: product.product_id, name: product.name}
                    });
                    recordScan(epc, product.name);
                } catch (error) {
                    notice(error.message, true);
                } finally {
                    button.disabled = !product.in_stock || !epcs.some(value => !seenEpcs.has(value));
                    if (button.disabled && epcs.length) {
                        button.title = 'All sample RFID tags have been scanned';
                    }
                }
            });
            mockButtons.set(product.product_id, button);
            list.append(button);
        });

        sampleBasket.addEventListener('click', async () => {
            const sampleProducts = products
                .filter(product => product.in_stock && availableEpc(product))
                .slice(0, 3);
            if (!sampleProducts.length) {
                notice('No unused sample stock is available. Clear the basket or add more stock.', true);
                return;
            }
            sampleBasket.disabled = true;
            try {
                for (const product of sampleProducts) {
                    const epc = availableEpc(product);
                    await addTagProduct({
                        epc,
                        product: {product_id: product.product_id, name: product.name}
                    });
                    recordScan(epc, product.name);
                    const button = mockButtons.get(product.product_id);
                    if (button) button.disabled = !availableEpc(product);
                }
                notice('Sample basket loaded. Continue to membership and payment.');
            } catch (error) {
                notice(error.message, true);
            } finally {
                sampleBasket.disabled = false;
            }
        });

        const basketActions = document.createElement('div');
        basketActions.className = 'sc-mock-actions';
        basketActions.append(sampleBasket);
        container.append(title, description, basketActions, list);
        container.hidden = false;
    }

    function notice(text, error = false) {
        const el = $('scNotice');
        el.hidden = false;
        el.textContent = text;
        el.setAttribute('role', error ? 'alert' : 'status');
        el.setAttribute('aria-live', error ? 'assertive' : 'polite');
        el.style.borderColor = error ? '#ce7070' : '';
    }

    function recordScan(epc, productName) {
        seenEpcs.add(epc);
        lastTagAt = Date.now();
        $('scScanCount').textContent = `${seenEpcs.size} unique tag${seenEpcs.size === 1 ? '' : 's'}`;
        $('scLastScan').textContent = `Last tag read at ${new Date(lastTagAt).toLocaleTimeString()}`;
        notice(`Scanned ${productName} (${epc}).`);
    }

    function updatePayment() {
        const enabled = step === 3 && !membershipPending && cart.items.length > 0 && cart.stock_available;
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
            if (value === step) el.setAttribute('aria-current', 'step');
            else el.removeAttribute('aria-current');
        });
        $('scMemberSection').hidden = !signedInMember && step < 2;
        $('scPaymentSection').hidden = step < 3;
        if (membershipContinue) membershipContinue.hidden = step !== 2;
        $('scMemberSection').classList.toggle('is-current', step === 2);
        $('scPaymentSection').classList.toggle('is-current', step === 3);
        $('scNext').textContent = step === 1
            ? (signedInMember ? 'Review and pay' : 'Continue to membership')
            : 'Scan more items';
        $('scNext').disabled = transitioning || (step === 1 && (!cart.items.length || !cart.stock_available));
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
            icon.setAttribute('aria-hidden', 'true');
            icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 4h2l2.4 11h10.2L20 7H6"/><circle cx="9" cy="19" r="1.5"/><circle cx="17" cy="19" r="1.5"/></svg>';
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
        $('scNext').disabled = transitioning || (step === 1 && (!cart.items.length || !cart.stock_available));
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
        badge.textContent = connected ? 'Reader ready' : 'Reader not connected';
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

    function pollTags() {
        if (!running) return;
        readerRequest = readTags().finally(() => {
            if (running) readerTimer = setTimeout(pollTags, 700);
        });
    }

    async function readTags() {
        try {
            const response = await fetch('/api/checkout/tags', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
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
        }
    }

    function setMembership(applied) {
        membershipApplied = applied;
        $('scMemberStatus').hidden = !applied;
        membershipForm.hidden = applied;
        membershipContinue.textContent = applied ? 'Continue to payment' : 'Continue without membership';
    }

    function membershipFeedback(text, invalid = false) {
        membershipMessage.textContent = text;
        membershipMessage.classList.toggle('is-error', invalid);
        membershipMessage.setAttribute('role', invalid ? 'alert' : 'status');
        membershipMessage.setAttribute('aria-live', invalid ? 'assertive' : 'polite');
        membershipInput.setAttribute('aria-invalid', String(invalid));
    }

    function continueToPayment() {
        setStep(3);
        $('scPay').focus({preventScroll: true});
    }

    async function changeMembership(method, identifier) {
        if (membershipPending) return;
        const apply = $('scApplyMembership');
        const remove = $('scRemoveMembership');
        const removing = method === 'DELETE';
        membershipPending = true;
        membershipForm.setAttribute('aria-busy', 'true');
        apply.disabled = true;
        membershipInput.readOnly = true;
        remove.disabled = true;
        membershipContinue.disabled = true;
        $('scNext').disabled = true;
        apply.textContent = 'Checking membership…';
        membershipFeedback(removing ? 'Removing membership…' : '');
        updatePayment();
        try {
            const response = await fetch('/api/checkout/membership', {
                method,
                headers: {'Content-Type': 'application/json'},
                signal: AbortSignal.timeout(8000),
                body: identifier === undefined ? undefined : JSON.stringify({membership: identifier})
            });
            const data = await response.json();
            if (response.status === 404) {
                throw new Error('No membership found. Check the number or continue without membership.');
            }
            if (!response.ok) throw new Error(data.error || 'Unable to update membership.');
            setMembership(data.applied);
            membershipInput.value = '';
            membershipFeedback(data.applied ? '' : 'Membership removed.');
        } catch (error) {
            membershipFeedback(error.message, !removing);
        } finally {
            membershipPending = false;
            membershipForm.removeAttribute('aria-busy');
            apply.textContent = 'Apply membership';
            apply.disabled = false;
            membershipInput.readOnly = false;
            remove.disabled = false;
            membershipContinue.disabled = false;
            $('scNext').disabled = step === 1 && (!cart.items.length || !cart.stock_available);
            updatePayment();
            if (membershipApplied) {
                const target = membershipContinue.hidden ? (removing ? remove : $('scPay')) : membershipContinue;
                target.focus({preventScroll: true});
            } else {
                membershipInput.focus({preventScroll: true});
                if (membershipInput.value) membershipInput.select();
            }
        }
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

    $('scNext').addEventListener('click', async () => {
        if (step !== 1) {
            setStep(1);
            running = true;
            pollTags();
            return;
        }
        transitioning = true;
        $('scNext').disabled = true;
        running = false;
        clearTimeout(readerTimer);
        await readerRequest;
        transitioning = false;
        if (!cart.items.length || !cart.stock_available) {
            setStep(1);
            running = true;
            pollTags();
            return;
        }
        $('scScanHeadline').textContent = 'Scanning paused';
        $('scScanCaption').textContent = 'Choose Scan more items to resume.';
        if (signedInMember) {
            continueToPayment();
            return;
        }
        setStep(2);
        (membershipApplied ? membershipContinue : membershipInput).focus({preventScroll: true});
    });

    if (membershipForm) {
        setMembership(membershipForm.dataset.applied === 'true');
        membershipContinue.addEventListener('click', continueToPayment);
        $('scRemoveMembership').addEventListener('click', () => changeMembership('DELETE'));
        membershipInput.addEventListener('input', () => membershipFeedback(''));
        membershipForm.addEventListener('submit', event => {
            event.preventDefault();
            const identifier = membershipInput.value.trim();
            if (!identifier) {
                membershipFeedback('Scan or enter a membership number.', true);
                membershipInput.focus();
                return;
            }
            changeMembership('POST', identifier);
        });
    }

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

    initMockControls();
    setStep(1);
    cartRequest().catch(error => notice(error.message, true)).finally(pollTags);
})();
