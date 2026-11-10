(function () {
  var container = document.getElementById("toastContainer");
  if (!container) return;

  function dismiss(toast) {
    setTimeout(function () {
      toast.classList.add("hiding");
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 3000);
  }

  window.showToast = function (message, category) {
    var toast = document.createElement("div");
    toast.className = "toast " + (category || "error");
    toast.textContent = message;
    container.appendChild(toast);
    dismiss(toast);
  };

  var toasts = container.querySelectorAll(".toast");
  toasts.forEach(dismiss);

  var seen = {};
  function pollAlerts() {
    fetch("/alerts")
      .then(function (response) { return response.json(); })
      .then(function (items) {
        items.forEach(function (item) {
          if (seen[item.id]) return;
          seen[item.id] = true;
          window.showToast(item.message, "error");
        });
      })
      .catch(function () {});
  }
  pollAlerts();
  setInterval(pollAlerts, 5000);
})();