(function () {
  var container = document.getElementById("toastContainer");
  if (!container) return;

  var toasts = container.querySelectorAll(".toast");
  toasts.forEach(function (toast) {
    setTimeout(function () {
      toast.classList.add("hiding");
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 3000);
  });
})();