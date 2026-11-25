const inventory = document.getElementById('inventory-report');
const refreshStatus = document.getElementById('inventory-refresh');

async function refreshInventory() {
  try {
    const response = await fetch(window.location.href, {
      headers: {'X-Report-Fragment': 'inventory'},
      cache: 'no-store',
      signal: AbortSignal.timeout(8000)
    });
    if (response.redirected) {
      window.location.assign(response.url);
      return;
    }
    if (!response.ok) throw new Error('Inventory request failed');
    const content = await response.text();
    if (content !== inventory.lastReport) {
      inventory.innerHTML = content;
      inventory.lastReport = content;
    }
    refreshStatus.textContent = 'Updates every 3 seconds';
  } catch {
    refreshStatus.textContent = 'Refresh unavailable. Showing the last inventory update.';
  } finally {
    setTimeout(refreshInventory, 3000);
  }
}

setTimeout(refreshInventory, 3000);
