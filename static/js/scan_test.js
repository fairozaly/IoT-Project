(function () {
    'use strict';
    const status = document.getElementById('reader-status');
    const body = document.getElementById('live-tags');
    const rows = new Map();
    let running = true;
    let busy = false;
    let timer;
    let controller;

    function showTag(result) {
        let row = rows.get(result.epc);
        if (!row) {
            if (rows.size >= 100) {
                const oldest = rows.keys().next().value;
                rows.get(oldest).remove();
                rows.delete(oldest);
            }
            row = document.createElement('tr');
            rows.set(result.epc, row);
            body.prepend(row);
        }
        row.replaceChildren();
        const product = result.product;
        const values = [result.epc, result.status, product ? product.name : '—',
            product ? product.upc : '—', product ? `$${product.price.toFixed(2)}` : '—',
            product ? product.quantity : '—'];
        values.forEach((value, index) => {
            const cell = document.createElement('td');
            if (index === 2 && product) {
                const link = document.createElement('a');
                link.href = `/products/${product.product_id}`;
                link.textContent = value;
                cell.append(link);
            } else {
                cell.textContent = value;
            }
            row.append(cell);
        });
        document.getElementById('live-results').hidden = false;
    }

    async function poll() {
        if (!running || busy) return;
        busy = true;
        controller = new AbortController();
        try {
            const response = await fetch('/api/scan-test/read', {
                method: 'POST', signal: controller.signal
            });
            const data = await response.json();
            if (!running) return;
            if (response.status === 401) {
                running = false;
                status.textContent = 'Sign in to continue reading tags.';
                return;
            }
            if (!response.ok) throw new Error(data.error || 'Unable to read tags.');
            if (data.connected === false) {
                status.textContent = 'Connecting to reader…';
                return;
            }
            data.results.forEach(showTag);
            status.textContent = rows.size
                ? `Reader scanning — ${rows.size} unique tag(s) detected.`
                : 'Reader connected. Waiting for tags…';
        } catch (error) {
            if (error.name !== 'AbortError') status.textContent = error.message;
        } finally {
            busy = false;
            if (running) timer = setTimeout(poll, 500);
        }
    }

    window.addEventListener('pagehide', () => {
        running = false;
        clearTimeout(timer);
        if (controller) controller.abort();
    });
    poll();
})();
