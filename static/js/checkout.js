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

    function notice(text, error = false) {
        const el = $('scNotice');
        el.hidden = false;
        el.textContent = text;
        el.style.borderColor = error ? '#ce7070' : '';
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
        membershipInput.setAttribute('aria-invalid', String(invalid));
    }

    function continueToPayment() {
        setStep(3);
        $('scPaymentSection').scrollIntoView({behavior: 'smooth', block: 'center'});
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
                throw new Error('No membership found. Check the number or email, or continue without membership.');
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
        $('scMemberSection').scrollIntoView({behavior: 'smooth', block: 'center'});
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
                membershipFeedback('Scan or enter a membership number or email.', true);
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

    setStep(1);
    cartRequest().catch(error => notice(error.message, true)).finally(pollTags);
})();
