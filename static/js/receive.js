(() => {
    'use strict';
    const form = document.getElementById('rfid-receive-form');
    if (!form) return;

    const product = document.getElementById('receive-product');
    const supplier = document.getElementById('receive-supplier');
    const status = document.getElementById('receive-reader-status');
    const count = document.getElementById('receive-count');
    const message = document.getElementById('receive-message');
    const list = document.getElementById('receive-tags');
    const stop = document.getElementById('receive-stop');
    const history = document.getElementById('receive-history');
    let version = 0;
    let cursor = null;
    let received = 0;
    let timer;
    let pendingPoll;
    let undoing = false;

    function say(text, error = false) {
        message.textContent = text;
        message.classList.toggle('receive-error', error);
    }

    function addReception(reception) {
        const table = history.querySelector('tbody');
        if ([...table.rows].some(row => row.dataset.receptionId === String(reception.reception_id))) return;
        const row = table.insertRow(0);
        row.dataset.receptionId = reception.reception_id;
        for (const value of [reception.product_name, reception.quantity_received,
            reception.supplier || '—', reception.received_at]) {
            row.insertCell().textContent = value;
        }
        if (table.rows.length > 20) table.deleteRow(-1);
        history.hidden = false;
        document.getElementById('receive-history-empty').hidden = true;
    }

    function updateCount() {
        count.textContent = `${received} ${received === 1 ? 'unit' : 'units'} received`;
    }

    async function undoTag(epc, receptionId, row) {
        if (undoing) return;
        undoing = true;
        clearTimeout(timer);
        product.disabled = true;
        stop.disabled = true;
        list.querySelectorAll('button').forEach(button => { button.disabled = true; });
        try {
            await pendingPoll;
            const response = await fetch(form.dataset.undoUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                signal: AbortSignal.timeout(8000),
                body: JSON.stringify({reception_id: receptionId, epc})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not undo the scan.');

            row.remove();
            received--;
            updateCount();
            const reception = history.querySelector(`[data-reception-id="${receptionId}"]`);
            if (reception && data.quantity_received) {
                reception.cells[1].textContent = data.quantity_received;
            } else if (reception) {
                reception.remove();
                history.hidden = !history.querySelector('tbody tr');
                document.getElementById('receive-history-empty').hidden = !history.hidden;
            }
            document.dispatchEvent(new CustomEvent('inventory:received', {
                detail: {productId: data.product_id, quantity: data.quantity, tag_count: data.tag_count}
            }));
            say(`Undid ${epc}. Stock is now ${data.quantity}. Move the tag away from the reader before scanning it again.`);
        } catch (error) {
            say(error.message, true);
        } finally {
            undoing = false;
            product.disabled = false;
            stop.disabled = !product.value;
            list.querySelectorAll('button').forEach(button => { button.disabled = false; });
            message.focus({preventScroll: true});
            if (product.value && !document.hidden) queuePoll(version);
        }
    }

    function queuePoll(currentVersion) {
        pendingPoll = poll(currentVersion);
    }

    function showResult(productId, data, currentBatch) {
        if (data.reception) {
            addReception(data.reception);
            document.dispatchEvent(new CustomEvent('inventory:received', {
                detail: {productId, quantity: data.quantity, tag_count: data.tag_count}
            }));
        }
        if (!currentBatch) return;

        if (data.reception) {
            received += data.count;
            updateCount();
            for (const epc of data.received) {
                const tag = document.createElement('li');
                const code = document.createElement('code');
                code.textContent = epc;
                const undo = document.createElement('button');
                undo.type = 'button';
                undo.className = 'receive-undo';
                undo.textContent = 'Undo';
                undo.disabled = undoing;
                undo.setAttribute('aria-label', `Undo tag ${epc}`);
                undo.addEventListener('click', () => undoTag(epc, data.reception.reception_id, tag));
                tag.append(code, undo);
                list.prepend(tag);
            }
            while (list.children.length > 20) list.lastElementChild.remove();
        }

        const feedback = [];
        if (data.count) feedback.push(`Stock is now ${data.quantity}.`);
        if (data.already_registered?.length) feedback.push(`Already in stock: ${data.already_registered.join(', ')}.`);
        if (data.conflicts?.length) feedback.push(`Assigned to another product: ${data.conflicts.join(', ')}.`);
        if (feedback.length) say(feedback.join(' '), Boolean(data.conflicts?.length));
    }

    async function poll(currentVersion) {
        if (currentVersion !== version || !product.value || document.hidden || undoing) return;
        const productId = Number(product.value);
        const wasArming = cursor === null;
        try {
            const response = await fetch(form.dataset.receiveUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                signal: AbortSignal.timeout(8000),
                body: JSON.stringify({
                    product_id: productId, after: cursor, supplier: supplier.value.trim() || null
                })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not receive tags.');
            showResult(productId, data, currentVersion === version);
            if (currentVersion !== version) return;
            cursor = data.cursor;
            const wasConnected = status.classList.contains('online');
            status.textContent = data.connected ? 'Reader connected' : 'Reader unavailable';
            status.classList.toggle('online', data.connected);
            if (!data.connected) say(data.error || 'Waiting for the RFID reader.', true);

            if (data.connected && (wasArming || !wasConnected) && !data.reception) {
                say('Ready. Scan tags for the selected product.');
            }
        } catch (error) {
            if (currentVersion === version) {
                status.textContent = 'Reader unavailable';
                status.classList.remove('online');
                say(error.message, true);
            }
        } finally {
            if (currentVersion === version && product.value && !document.hidden && !undoing) {
                timer = setTimeout(() => queuePoll(currentVersion), 650);
            }
        }
    }

    function start() {
        clearTimeout(timer);
        cursor = null;
        if (product.value) {
            received = 0;
            updateCount();
            list.replaceChildren();
        }
        version++;
        stop.disabled = !product.value;
        status.classList.remove('online');
        status.textContent = product.value ? 'Checking reader…' : 'Select a product';
        say(product.value ? 'Preparing the reader…' : '');
        if (product.value) {
            message.focus({preventScroll: true});
            queuePoll(version);
        }
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        message.focus({preventScroll: true});
    });
    product.addEventListener('change', start);
    stop.addEventListener('click', () => {
        product.value = '';
        start();
        say('Receiving stopped.');
        product.focus();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && product.value) {
            product.value = '';
            start();
        }
    });
    window.addEventListener('pagehide', () => {
        version++;
        clearTimeout(timer);
    });
    start();
})();
