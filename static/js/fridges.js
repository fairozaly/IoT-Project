(function () {
  var grid = document.getElementById("cardGrid");
  if (!grid) return;

  function render(readings) {
    grid.textContent = "";
    if (!readings.length) {
      var empty = document.createElement("p");
      empty.className = "subhead";
      empty.textContent = "No fridge readings yet.";
      grid.appendChild(empty);
      return;
    }
    readings.forEach(function (reading) {
      var card = document.createElement("div");
      card.className = "card";

      var details = document.createElement("div");
      details.className = "card-details";

      var name = document.createElement("h3");
      name.textContent = reading.name;

      var temperature = document.createElement("p");
      temperature.textContent =
        "Temperature: " + reading.temperature.toFixed(1) + " \u00b0C";

      var humidity = document.createElement("p");
      humidity.textContent =
        "Humidity: " + reading.humidity.toFixed(1) + " %";

      details.appendChild(name);
      details.appendChild(temperature);
      details.appendChild(humidity);
      card.appendChild(details);
      grid.appendChild(card);
    });
  }

  function refresh() {
    fetch("/api/readings")
      .then(function (response) { return response.json(); })
      .then(render)
      .catch(function () {});
  }

  refresh();
  setInterval(refresh, 3000);
})();
