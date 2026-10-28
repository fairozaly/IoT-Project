(function () {
    'use strict';
    let html5QrcodeScanner;
    const scanCooldown = 3000;
    let shoppingCart = JSON.parse(localStorage.getItem('checkoutCart')) || [];
    // const lastScannedItem = JSON.parse(document.getElementById("last-item-data").textContent);
    let lastScannedCode = "";
    let lastScanTime = 0;
    const successIndicator = document.getElementById('resultText'); // Not sure if temp or not, for displaying success or error, maybe replaced by beep?
    html5QrcodeScanner = new Html5QrcodeScanner("reader", {fps:10, qrbox: 250}, false);
    html5QrcodeScanner.render(scanItem);
    renderCart();
    console.log("WE ARE IN CHECKOUT JS SCRIPT");

    async function scanItem(Text, Result) {
        if (Text === lastScannedCode && Date.now() - lastScanTime < scanCooldown) return;
        lastScannedCode = Text;
        lastScanTime = Date.now();
        const response = await fetch('/submit-barcode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ barcode: Text }) 
        });

        if (!response.ok) {
            successIndicator.innerHTML = "Unknown barcode: " + Text;
            return;
        }

        const item = await response.json();
        if (addItemToCart(item)) {
            successIndicator.innerHTML = 'Added ' + item.name;
        }
    }

    function addItemToCart(item) {
        const existingItem = shoppingCart.find(cartItem => cartItem.product_id === item.product_id);

        const amountInCart = existingItem ? existingItem.quantity : 0;

         if (amountInCart >= item.stock) {
            successIndicator.innerHTML = 'Not enough ' + item.name + ' in stock';
            return false;
        }

        if (existingItem) {
            existingItem.quantity += 1;
            existingItem.stock = item.stock;
        } else {
            shoppingCart.push({ ...item, quantity: 1 });
        }  

    localStorage.setItem('checkoutCart', JSON.stringify(shoppingCart));
    renderCart();
    return true;
    }

    function decrementItem(product_id) {
        const item = shoppingCart.find(cartItem => cartItem.product_id === product_id);

        item.quantity -= 1;
        if (item.quantity <= 0) {
            shoppingCart = shoppingCart.filter(cartItem => cartItem.product_id !== product_id);
        }

        localStorage.setItem('checkoutCart', JSON.stringify(shoppingCart));
        renderCart();
    }

    window.decrementItem = decrementItem; // Allows on click to access the function by attaching it to window

    function renderCart() {
    const cartContainer = document.getElementById('cart');

    cartContainer.innerHTML = ''; // Clear out old items
    let grandTotal = 0;

    shoppingCart.forEach(item => {
        const itemTotal = item.price * item.quantity;
        grandTotal += itemTotal;

        // Follows example layout in checkout
        const itemRow = document.createElement('div');
        itemRow.className = 'example-item';

        itemRow.innerHTML = `
            <div class="item-name-container">
                <span class="item-name">${item.name}</span>
            </div>
            <div class="item-quantity-container">
                <span class="item-quantity">${item.quantity}</span>
                <button class="remove-item" onclick="decrementItem(${item.product_id})">-</button>
            </div>
            <div class="item-price-container">
                <span class="item-price">${itemTotal.toFixed(2)}$</span>
            </div>
        `;
        
        cartContainer.appendChild(itemRow);
        });

          document.getElementById('cart-total').innerHTML = 'Total: ' + grandTotal.toFixed(2) + '$';
    }
})();
