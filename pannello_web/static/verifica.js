// Pagina di verifica (D64): manda al server il fuso orario del browser (es. «Europe/Rome»).
// Da solo non blocca nessuno: è un indizio in più contro le VPN. Nient'altro viene letto o inviato.
(function () {
  try {
    var campo = document.getElementById("fuso");
    if (campo) campo.value = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (e) {}
})();
