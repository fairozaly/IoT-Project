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

})();
