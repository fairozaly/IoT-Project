(() => {
  const cards = [...document.querySelectorAll('[data-product-card]')];
  const search = document.getElementById('productSearch');
  const category = document.getElementById('productCategory');
  const results = document.getElementById('productsResults');
  const empty = document.getElementById('noProductsMatch');
  const report = document.getElementById('productsReport');
  const text = id => document.getElementById(id);
  const unique = field => [...new Set(cards.map(card => card.dataset[field].trim()).filter(Boolean))];
  function renderStockTotal() {
    text('productsStock').textContent = cards.reduce((sum, card) => sum + Number(card.dataset.quantity), 0).toLocaleString();
  }
  function renderStockStatus(card, item) {
    let status = card.querySelector('[data-stock-status]');
    if (!status) {
      status = document.createElement('span');
      status.dataset.stockStatus = '';
      status.className = 'products-live-stock-status';
      const body = card.querySelector('.product-tile-body') || card;
      body.appendChild(status);
    }
    const labels = {
      in_stock: 'In stock',
      low_stock: 'Low stock',
      out_of_stock: 'Out of stock',
    };
    status.textContent = labels[item.status] || 'Stock status unavailable';
    status.dataset.status = item.status || 'unknown';
    card.setAttribute('aria-label', `${item.name}: ${status.textContent}, ${item.quantity} units`);
  }
  function applyInventory(items) {
    if (!Array.isArray(items)) return;
    items.forEach(item => {
      const card = cards.find(candidate => Number(candidate.dataset.productId) === Number(item.product_id));
      if (!card || !Number.isFinite(Number(item.quantity))) return;
      card.dataset.quantity = String(item.quantity);
      const units = card.querySelector('[data-stock-units]');
      const tags = card.querySelector('[data-stock-tags]');
      if (units) units.textContent = `${item.quantity} units`;
      if (tags && Number.isFinite(Number(item.tag_count))) tags.textContent = `${item.tag_count} registered`;
      renderStockStatus(card, item);
    });
    renderStockTotal();
  }
  async function pollInventory() {
    try {
      const response = await fetch('/api/inventory', {
        headers: {Accept: 'application/json'},
        cache: 'no-store',
      });
      if (!response.ok) return;
      const payload = await response.json();
      applyInventory(payload.items);
    } catch (error) {
      // Inventory remains usable with the last rendered values if polling fails.
    }
  }
  renderStockTotal();
  cards.forEach(card => renderStockStatus(card, {
    name: card.dataset.name,
    quantity: Number(card.dataset.quantity),
    status: Number(card.dataset.quantity) === 0 ? 'out_of_stock' : 'in_stock',
  }));
  pollInventory();
  window.setInterval(pollInventory, 3000);

  document.addEventListener('inventory:received', event => {
    const {productId, quantity, tag_count: tagCount} = event.detail;
    const card = cards.find(item => Number(item.dataset.productId) === productId);
    if (!card) return;
    card.dataset.quantity = quantity;
    card.querySelector('[data-stock-units]').textContent = `${quantity} units`;
    card.querySelector('[data-stock-tags]').textContent = `${tagCount} registered`;
    renderStockStatus(card, {
      name: card.dataset.name,
      quantity,
      status: quantity === 0 ? 'out_of_stock' : 'in_stock',
    });
    renderStockTotal();
  });
  text('productsCount').textContent = cards.length.toLocaleString();
  text('productsCategories').textContent = unique('category').length;
  text('productsManufacturers').textContent = unique('company').length;
  unique('category').sort((a,b)=>a.localeCompare(b)).forEach(value => {
    const option=document.createElement('option'); option.value=value; option.textContent=value; category.appendChild(option);
  });
  function filter() {
    const q=(search.value||'').trim().toLocaleLowerCase();
    const selected=category.value;
    let shown=0;
    cards.forEach(card => {
      const matchesCategory=!selected || card.dataset.category===selected;
      const matchesText=[card.dataset.name,card.dataset.category,card.dataset.company,card.dataset.upc].some(v=>(v||'').toLocaleLowerCase().includes(q));
      const visible=matchesCategory && matchesText;
      card.hidden=!visible;
      if(visible) shown++;
    });
    if(results) results.textContent=`Showing ${shown} of ${cards.length} products`;
    if(empty) empty.hidden=shown!==0;
  }
  if(search) search.addEventListener('input',filter);
  if(category) category.addEventListener('change',filter);
  function csvCell(value) {return '"'+String(value??'').replace(/"/g,'""')+'"';}
  report?.addEventListener('click',() => {
    const visible=cards.filter(card=>!card.hidden);
    const fields=['name','category','company','upc','price','quantity'];
    const rows=[['Product','Category','Manufacturer','UPC','Price','Quantity'],...visible.map(c=>fields.map(f=>c.dataset[f]||''))];
    const csv='\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download='products-report.csv';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  filter();
})();
