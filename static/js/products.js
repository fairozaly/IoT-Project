(() => {
  const cards = [...document.querySelectorAll('[data-product-card]')];
  const search = document.getElementById('productSearch');
  const category = document.getElementById('productCategory');
  const results = document.getElementById('productsResults');
  const empty = document.getElementById('noProductsMatch');
  const report = document.getElementById('productsReport');
  const text = id => document.getElementById(id);
  const unique = field => [...new Set(cards.map(card => card.dataset[field].trim()).filter(Boolean))];
  text('productsStock').textContent = cards.reduce((sum, c) => sum + (Number(c.dataset.quantity) || 0), 0).toLocaleString();
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
