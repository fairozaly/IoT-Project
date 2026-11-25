(() => {
    'use strict';
    const form = document.getElementById('rfid-receive-form');
    if (!form) return;
    const productSelect = document.getElementById('receive-product');
    const supplierInput = document.getElementById('receive-supplier');
    const status = document.getElementById('receive-reader-status');
    const count = document.getElementById('receive-count');
    const message = document.getElementById('receive-message');
    const list = document.getElementById('receive-tags');
    const processed = new Set();
    let running = true;
    let busy = false;
    let timer;
    let received = 0;

    function say(text, error = false) {
        message.textContent = text;
        message.style.color = error ? '#ce6060' : '';
    }

    function setConnected(connected) {
        status.textContent = connected ? 'Reader connected' : 'Not connected';
        status.classList.toggle('online', connected);
    }

    function addRow(epc, productName) {
        const row = document.createElement('li');
        row.textContent = `${epc} — received into ${productName}`;
        list.prepend(row);
    }

    async function receive(epcs, productId, productName) {
        const response = await fetch('/api/inventory/receive/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                product_id: productId,
                epcs,
                supplier: supplierInput.value.trim() || null
            })
        });
        const data = await response.json();
        if (!response.ok) {
            say(data.error || 'Could not receive scanned tags.', true);
            return;
        }
        if (data.count) {
            received += data.count;
            count.textContent = `${received} tag${received === 1 ? '' : 's'} received`;
            data.received.forEach(epc => addRow(epc, productName));
            say(`Received ${data.count} tag${data.count === 1 ? '' : 's'}. Stock is now ${data.quantity}.`);
        } else if (data.already_registered.length) {
            say('Scanned tags are already registered to this product.');
        }
        if (data.conflicts.length) {
            say(`Some tags belong to another product: ${data.conflicts.join(', ')}`, true);
        }
    }

    async function poll() {
        if (!running || busy) return;
        busy = true;
        try {
            const response = await fetch('/api/rfid/tags');
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Reader unavailable.');
            setConnected(data.connected);
            if (!data.connected) {
                say(data.error || 'Waiting for the RFID reader…', true);
            } else if (!productSelect.value) {
                say('Select a product to receive scanned tags.');
            } else {
                const productId = Number(productSelect.value);
                const productName = productSelect.selectedOptions[0].textContent;
                const epcs = data.tags.filter(epc => !processed.has(epc));
                if (!epcs.length) return;
                epcs.forEach(epc => processed.add(epc));
                try {
                    await receive(epcs, productId, productName);
                } catch (error) {
                    epcs.forEach(epc => processed.delete(epc));
                    say(error.message, true);
                }
            }
        } catch (error) {
            setConnected(false);
            say(error.message, true);
        } finally {
            busy = false;
            if (running) timer = setTimeout(poll, 700);
        }
    }

    form.addEventListener('submit', event => event.preventDefault());

    productSelect.addEventListener('change', () => {
        processed.clear();
        say(productSelect.value
            ? 'Scanning automatically for the selected product.'
            : 'Select a product to receive scanned tags.');
    });

    window.addEventListener('pagehide', () => {
        running = false;
        clearTimeout(timer);
    });

    poll();
})();
