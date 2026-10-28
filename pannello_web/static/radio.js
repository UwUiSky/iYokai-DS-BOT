// Pagina «radio iYokai» dentro Discord (Activity). Nessun segreto qui:
// l'identificativo dell'applicazione arriva dall'attributo data-client della pagina.
(function () {
  var radice = document.getElementById("radio");
  var titolo = document.getElementById("brano");
  var barra = document.getElementById("avanzamento");
  var audio = document.getElementById("audio");
  var stato = null;
  var ricevuto = 0;

  function mmss(ms) {
    var s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
  }
  function disegna() {
    if (!stato || !stato.attiva) {
      titolo.textContent = radice.dataset.spenta;
      barra.value = 0;
      return;
    }
    var trascorso = Math.min(stato.durata_ms, stato.trascorso_ms + (Date.now() - ricevuto));
    titolo.textContent = stato.titolo + " (" + mmss(trascorso) + " / " + mmss(stato.durata_ms) + ")";
    barra.max = stato.durata_ms;
    barra.value = trascorso;
  }
  function aggiorna() {
    fetch(radice.dataset.base + "stato", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (dati) { stato = dati; ricevuto = Date.now(); disegna(); })
      .catch(function () {});
  }
  if (window.DiscordSDK && radice.dataset.client) {
    try {
      var sdk = new window.DiscordSDK(radice.dataset.client);
      sdk.ready().catch(function () {});
    } catch (e) {}
  }
  if (audio && radice.dataset.flusso) {
    audio.src = radice.dataset.flusso;
    audio.hidden = false;
  }
  aggiorna();
  setInterval(aggiorna, 10000);
  setInterval(disegna, 1000);
})();
