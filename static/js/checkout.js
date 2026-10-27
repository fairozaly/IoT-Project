(function () {
    'use strict';
    let html5QrcodeScanner;
    const successIndicator = document.getElementById('resultText'); // Not sure if temp or not, for displaying success or error, maybe replaced by beep?
    html5QrcodeScanner = new Html5QrcodeScanner("reader", {fps:10, qrbox: 250}, false);
    html5QrcodeScanner.render(scanItem);
    console.log("WE ARE IN QR JS SCRIPT");
    function scanItem(Text, Result) {
        successIndicator.innerHTML = '' + Text + Result;
    }
    fetch('/submit-barcode', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ barcode: decodedText }) 
    });

})();
