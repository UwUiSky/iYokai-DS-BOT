"""
desktop/iyokai_desktop/notifiche.py
===================================
Notifiche a schermo per gli avvisi del servizio (menzioni, risposte, parole chiave, promemoria, assistenza) e
storico con salto al messaggio. Le notifiche usano gli strumenti del sistema, chiamati con argomenti separati
(mai una riga di comando composta con il testo). Il salto al messaggio apre solo link di Discord.
Funzioni coperte: SPEC D.5, D.6
"""

from __future__ import annotations

import re
import subprocess
import sys
import webbrowser

from .servizio import ErroreServizio, Servizio

MAX_TITOLO = 80
MAX_TESTO = 200
_LINK_DISCORD = re.compile(r"^https://discord\.com/channels/(\d{1,20}|@me)/\d{1,20}/\d{1,20}$")

TESTI = {
    "it": {
        "menzione": "{autore} ti ha menzionato in #{canale}", "risposta": "{autore} ti ha risposto in #{canale}",
        "parola": "{autore} ha scritto una tua parola chiave in #{canale}", "promemoria": "Promemoria",
        "assistenza": "Assistenza iYokai", "staff": "Avviso per lo staff",
    },
    "en": {
        "menzione": "{autore} mentioned you in #{canale}", "risposta": "{autore} replied to you in #{canale}",
        "parola": "{autore} wrote one of your keywords in #{canale}", "promemoria": "Reminder",
        "assistenza": "iYokai support", "staff": "Staff alert",
    },
}


def titolo_evento(evento: dict, lingua: str = "it") -> str:
    modello = TESTI.get(lingua, TESTI["it"]).get(evento.get("tipo"), evento.get("tipo") or "iYokai")
    return modello.format(autore=evento.get("autore") or "?", canale=evento.get("canale") or "?")[:MAX_TITOLO]


def link_valido(link: str | None) -> str | None:
    """Il link solo se è un messaggio di Discord: il programma non apre altro."""
    return link if link and _LINK_DISCORD.match(link) else None


def comando_notifica(titolo: str, testo: str, piattaforma: str | None = None) -> tuple[list[str], dict[str, str]]:
    """(argomenti, variabili d'ambiente in più). Il testo non entra mai in una riga di comando composta."""
    piattaforma = piattaforma or sys.platform
    titolo, testo = titolo[:MAX_TITOLO], testo[:MAX_TESTO]
    if piattaforma.startswith("win"):
        copione = (
            "$t=[System.Security.SecurityElement]::Escape($env:IYOKAI_TITOLO);"
            "$x=[System.Security.SecurityElement]::Escape($env:IYOKAI_TESTO);"
            "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
            "$d=New-Object Windows.Data.Xml.Dom.XmlDocument;"
            "$d.LoadXml('<toast><visual><binding template=\"ToastText02\"><text id=\"1\">'+$t+'</text><text id=\"2\">'+$x+'</text></binding></visual></toast>');"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('iYokai Desktop').Show("
            "[Windows.UI.Notifications.ToastNotification]::new($d))"
        )
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", copione], {"IYOKAI_TITOLO": titolo, "IYOKAI_TESTO": testo}
    if piattaforma == "darwin":
        copione = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run'
        return ["osascript", "-e", copione, titolo, testo], {}
    return ["notify-send", "--app-name=iYokai", "--", titolo, testo], {}


def invia_notifica(titolo: str, testo: str, esegui=subprocess.run) -> bool:
    """True se il sistema ha accettato la notifica. Strumento mancante o in errore = False (non ferma il programma)."""
    argomenti, extra = comando_notifica(titolo, testo)
    import os

    try:
        return esegui(argomenti, env={**os.environ, **extra}, timeout=15, capture_output=True, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ciclo_avvisi(servizio: Servizio, ultimo: int, lingua: str = "it", invia=invia_notifica, attesa: int = 20) -> int:
    """Una giro di ascolto: chiede gli avvisi nuovi (attende fino a `attesa` secondi), li mostra e ritorna l'ultimo id visto."""
    for evento in servizio.eventi(dopo=ultimo, attesa=attesa):
        invia(titolo_evento(evento, lingua), evento.get("testo") or "")
        ultimo = max(ultimo, int(evento["id"]))
    return ultimo


def riga_storico(evento: dict, numero: int, lingua: str = "it") -> str:
    """Una riga dell'elenco delle menzioni: numero, quando, titolo e testo breve."""
    quando = str(evento.get("quando", ""))[:16].replace("T", " ")
    testo = (evento.get("testo") or "").strip()
    return f"{numero:>3}. {quando}  {titolo_evento(evento, lingua)}" + (f": {testo}" if testo else "")


def salta_al_messaggio(evento: dict, apri=webbrowser.open) -> bool:
    """Apre il messaggio nel client Discord (il sistema passa il link a Discord). False se non c'è un link valido."""
    link = link_valido(evento.get("link"))
    return bool(link) and bool(apri(link))


def avvisi_in_ascolto(servizio: Servizio, impostazioni, fermati, invia=invia_notifica, passo_errore: float = 30.0) -> None:
    """Il ciclo del programma: ascolta finché `fermati` non scatta. Se la rete cade riprova senza uscire."""
    lingua = impostazioni.leggi("lingua", "it")
    while not fermati.is_set():
        try:
            nuovo = ciclo_avvisi(servizio, impostazioni.ultimo_evento(), lingua, invia)
            impostazioni.imposta_ultimo_evento(nuovo)
        except ErroreServizio as errore:
            if errore.codice == "token_non_valido":
                raise
            fermati.wait(passo_errore)
