/* Scheda del ticket, tempo reale (TKT-085): ogni pochi secondi chiede lo stato al sito (JSON con ETag, 304 se non cambia).
   Non legge mai il testo dei messaggi. Si ferma da solo se il ticket non c'è più o se non hai più il permesso. */
(function () {
  var radice = document.getElementById("ticket-live");
  if (!radice || !window.fetch) return;
  var indirizzo = radice.getAttribute("data-url");
  var etag = null, attesa = 5000, prima = null;
  function scrivi(id, valore) {
    var e = document.getElementById(id);
    if (e) e.textContent = valore;
  }
  function mostra(d) {
    scrivi("live-stato", d.stato === "open" ? "aperto" : "chiuso");
    scrivi("live-presa", d.presa_da || "nessuno");
    scrivi("live-utente", d.utente_scritto ? d.utente_scritto.replace("T", " ").replace("Z", " UTC") : "mai");
    scrivi("live-attivita", d.attivita ? d.attivita.replace("T", " ").replace("Z", " UTC") : "—");
    if (prima === null) prima = d.utente_scritto || "";
    var nuovo = document.getElementById("live-nuovo");
    if (nuovo) nuovo.hidden = (d.utente_scritto || "") === prima;
    if (d.stato !== "open") {
      var modulo = document.querySelector("form.carta");
      if (modulo) {
        var campi = modulo.querySelectorAll("textarea, button, input");
        for (var i = 0; i < campi.length; i++) campi[i].disabled = true;
      }
    }
  }
  function ferma(testo) {
    scrivi("live-avviso", testo);
  }
  function giro() {
    if (document.hidden) { setTimeout(giro, attesa); return; }
    var intestazioni = { "Accept": "application/json" };
    if (etag) intestazioni["If-None-Match"] = etag;
    fetch(indirizzo, { headers: intestazioni, credentials: "same-origin", cache: "no-store" }).then(function (r) {
      if (r.status === 304) { attesa = Math.min(attesa * 1.5, 30000); return null; }
      if (r.status === 200) { etag = r.headers.get("ETag"); attesa = 5000; return r.json(); }
      if (r.status === 429) { attesa = 30000; return null; }
      ferma("Il ticket non è più disponibile o non puoi più rispondere: ricarica la pagina.");
      attesa = 0;
      return null;
    }).then(function (d) {
      if (d) mostra(d);
    }).catch(function () {
      attesa = Math.min(attesa * 2, 30000);
    }).then(function () {
      if (attesa > 0) setTimeout(giro, attesa);
    });
  }
  giro();
})();
