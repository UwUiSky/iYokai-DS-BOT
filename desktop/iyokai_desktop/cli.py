"""
desktop/iyokai_desktop/cli.py
=============================
Il programma a righe di comando di iYokai Desktop: collegamento, rich presence (stato, profili, rotazione), avvisi
e storico delle menzioni, storico dei comandi, traduzione rapida, testi pronti, i miei server, pannello rapido dello
staff, funzioni che aspettano l'approvazione di Discord.
Funzioni coperte: SPEC D.1-D.11
"""

from __future__ import annotations

import argparse
import getpass
import sys
from threading import Event

from . import appunti, notifiche, presenza, rpc_avanzato
from .impostazioni import ErroreImpostazioni, Impostazioni, cartella_config
from .ipc import ClienteIPC, ErroreIPC
from .servizio import ErroreServizio, Servizio

MESSAGGI = {
    "it": {
        "token_non_valido": "Codice non valido o revocato: ricrealo con il comando dell'app iYokai.",
        "rete_non_raggiungibile": "Il servizio iYokai non risponde.", "troppe_richieste": "Troppe richieste: aspetta un minuto.",
        "nessun_servizio": "Manca l'indirizzo del servizio: usa `configura --servizio`.",
        "nessun_codice": "Non sei collegato: usa `collega`.", "nessun_app_id": "Manca l'ID dell'applicazione: usa `configura --app-id`.",
        "nessun_permesso": "Non hai il permesso per questa azione in quel server.", "ok": "Fatto.",
        "dati_non_validi": "Dati non validi.", "server_sconosciuto": "Server sconosciuto (iYokai deve esserci).",
        "canale_sconosciuto": "Canale sconosciuto.", "membro_sconosciuto": "Membro non trovato.",
        "gerarchia": "Non puoi agire su quella persona.", "bot_senza_permessi": "Al bot mancano i permessi.",
        "azione_sconosciuta": "Azione sconosciuta.", "discord_non_trovato": "Discord non è aperto sul PC.",
        "da_attivare": "Da attivare: serve l'approvazione di Discord.", "nessun_testo": "Niente da fare.",
    },
    "en": {
        "token_non_valido": "Code invalid or revoked: create it again with the iYokai app command.",
        "rete_non_raggiungibile": "The iYokai service is not answering.", "troppe_richieste": "Too many requests: wait a minute.",
        "nessun_servizio": "Service address missing: use `configura --servizio`.",
        "nessun_codice": "You are not connected: use `collega`.", "nessun_app_id": "Application ID missing: use `configura --app-id`.",
        "nessun_permesso": "You lack the permission for this action in that server.", "ok": "Done.",
        "dati_non_validi": "Invalid data.", "server_sconosciuto": "Unknown server (iYokai must be there).",
        "canale_sconosciuto": "Unknown channel.", "membro_sconosciuto": "Member not found.",
        "gerarchia": "You cannot act on that person.", "bot_senza_permessi": "The bot lacks permissions.",
        "azione_sconosciuta": "Unknown action.", "discord_non_trovato": "Discord is not open on this PC.",
        "da_attivare": "To be enabled: needs Discord approval.", "nessun_testo": "Nothing to do.",
    },
}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="iyokai_desktop", description="iYokai Desktop")
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("configura")
    c.add_argument("--servizio")
    c.add_argument("--app-id")
    c.add_argument("--lingua")
    sub.add_parser("collega")
    sub.add_parser("scollega")
    pr = sub.add_parser("presenza")
    pr.add_argument("--details")
    pr.add_argument("--state")
    pr.add_argument("--large-image")
    pr.add_argument("--large-text")
    pr.add_argument("--small-image")
    pr.add_argument("--small-text")
    pr.add_argument("--bottone", action="append", default=[], help="«Testo|https://indirizzo» (al massimo 2)")
    pr.add_argument("--timer", help="«avvio» o i secondi alla fine")
    pr.add_argument("--profilo", help="usa un profilo salvato")
    pr.add_argument("--ferma", action="store_true")
    pf = sub.add_parser("profilo")
    pf.add_argument("azione", choices=["salva", "elenco", "elimina"])
    pf.add_argument("nome", nargs="?")
    pf.add_argument("--details")
    pf.add_argument("--state")
    pf.add_argument("--large-image")
    pf.add_argument("--large-text")
    pf.add_argument("--small-image")
    pf.add_argument("--small-text")
    pf.add_argument("--bottone", action="append", default=[])
    pf.add_argument("--timer")
    ro = sub.add_parser("rotazione")
    ro.add_argument("profili", nargs="+")
    ro.add_argument("--ogni", type=int, default=30)
    sub.add_parser("avvisi")
    me = sub.add_parser("menzioni")
    me.add_argument("--tipo")
    me.add_argument("--apri", type=int, help="numero della riga da aprire")
    sub.add_parser("storico")
    tr = sub.add_parser("traduci")
    tr.add_argument("testo", nargs="?")
    tr.add_argument("--lingua", default="en")
    sub.add_parser("traduci-appunti").add_argument("--lingua", default="en")
    sub.add_parser("risposte")
    sub.add_parser("incolla").add_argument("nome")
    sub.add_parser("server")
    sub.add_parser("radio")
    st = sub.add_parser("staff")
    st.add_argument("azione", choices=["azioni", "blocca", "sblocca", "timeout", "annuncio"])
    st.add_argument("server", type=int)
    st.add_argument("a", nargs="?", help="canale o utente")
    st.add_argument("b", nargs="?", help="minuti o testo")
    st.add_argument("--motivo", default="")
    sub.add_parser("avanzate")
    return p


def _campi(a) -> dict:
    campi = {k: getattr(a, k, None) for k in ("details", "state", "large_image", "large_text", "small_image", "small_text", "timer")}
    campi["bottoni"] = [tuple(b.split("|", 1)) for b in getattr(a, "bottone", [])]
    return {k: v for k, v in campi.items() if v}


def main(argv=None, *, uscita=print, impostazioni: Impostazioni | None = None, servizio_di=Servizio, cliente_di=ClienteIPC,
         chiedi_codice=getpass.getpass, fermati: Event | None = None) -> int:
    a = _parser().parse_args(argv)
    imp = impostazioni or Impostazioni(cartella_config())
    lingua = imp.leggi("lingua", "it")
    testi = MESSAGGI.get(lingua, MESSAGGI["it"])

    def dire(codice: str) -> None:
        uscita(testi.get(codice, codice))

    def servizio() -> Servizio:
        base, codice = imp.leggi("servizio"), imp.codice()
        if not base:
            raise ErroreServizio("nessun_servizio")
        if not codice:
            raise ErroreServizio("nessun_codice")
        return servizio_di(base, codice)

    try:
        return _esegui(a, imp, servizio, servizio_di, cliente_di, uscita, dire, lingua, chiedi_codice, fermati or Event())
    except ErroreServizio as e:
        dire(e.codice)
    except (ErroreIPC, presenza.ErrorePresenza, ErroreImpostazioni, appunti.ErroreAppunti) as e:
        dire(getattr(e, "codice", None) or str(e).split(":")[0])
    return 1


def _cliente(imp, cliente_di) -> ClienteIPC:
    app_id = imp.leggi("app_id")
    if not app_id:
        raise ErroreServizio("nessun_app_id")
    cliente = cliente_di(app_id)
    cliente.connetti()
    return cliente


def _esegui(a, imp, servizio, servizio_di, cliente_di, uscita, dire, lingua, chiedi_codice, fermati) -> int:
    c = a.comando
    archivio = presenza.ArchivioProfili(imp.cartella / "profili.json")
    if c == "configura":
        if a.servizio:
            imp.imposta_servizio(a.servizio)
        if a.app_id:
            imp.imposta_app_id(a.app_id)
        if a.lingua:
            imp.imposta_lingua(a.lingua)
        dire("ok")
    elif c == "collega":
        base = imp.leggi("servizio")
        if not base:
            raise ErroreServizio("nessun_servizio")
        codice = chiedi_codice("Codice (dal comando dell'app iYokai): ").strip()
        servizio_di(base, codice).io()  # il codice si prova prima di salvarlo
        imp.salva_codice(codice)
        dire("ok")
    elif c == "scollega":
        imp.dimentica_codice()
        dire("ok")
    elif c == "presenza":
        cliente = _cliente(imp, cliente_di)
        if a.ferma:
            cliente.imposta_attivita(None)
        else:
            campi = archivio.carica(a.profilo) if a.profilo else _campi(a)
            if campi is None:
                raise presenza.ErrorePresenza("profilo_inesistente")
            cliente.imposta_attivita(presenza.costruisci(campi))
        dire("ok")
    elif c == "profilo":
        if a.azione == "elenco":
            uscita("\n".join(archivio.nomi()) or "-")
        elif a.azione == "salva":
            archivio.salva(a.nome or "", _campi(a))
            dire("ok")
        else:
            uscita("ok" if archivio.elimina(a.nome or "") else "-")
    elif c == "rotazione":
        elenco = [archivio.carica(n) for n in a.profili]
        if any(e is None for e in elenco):
            raise presenza.ErrorePresenza("profilo_inesistente")
        presenza.ruota(_cliente(imp, cliente_di), elenco, a.ogni, fermati)
    elif c == "avvisi":
        notifiche.avvisi_in_ascolto(servizio(), imp, fermati)
    elif c == "menzioni":
        eventi = servizio().eventi(tipo=a.tipo, limite=50)
        if a.apri:
            if not 1 <= a.apri <= len(eventi) or not notifiche.salta_al_messaggio(eventi[a.apri - 1]):
                dire("nessun_testo")
        else:
            uscita("\n".join(notifiche.riga_storico(e, n, lingua) for n, e in enumerate(eventi, 1)) or "-")
    elif c == "storico":
        dati = servizio().storico()
        uscita("\n".join(f"{x['quando'][:16]}  {x['comando']}" for x in dati.get("comandi", [])) or "-")
        uscita("\n".join(f"{x['quando'][:16]}  {x['azione']} {x['dettaglio']} -> {x['esito']}" for x in dati.get("azioni", [])) or "-")
    elif c == "traduci":
        testo = a.testo or sys.stdin.read().strip()
        if not testo:
            dire("nessun_testo")
            return 1
        uscita(servizio().traduci(testo, a.lingua))
    elif c == "traduci-appunti":
        uscita(appunti.traduci_appunti(servizio(), a.lingua))
    elif c == "risposte":
        uscita("\n".join(f"{r['nome']}: {r['testo'][:60]}" for r in servizio().risposte()) or "-")
    elif c == "incolla":
        appunti.copia_risposta(servizio(), a.nome)
        dire("ok")
    elif c == "server":
        for s in servizio().server():
            uscita(f"{s['nome']}  iYokai" + ("  staff" if s["staff"] else "") + (f"  {s['pannello']}" if s.get("pannello") else ""))
    elif c == "radio":
        r = servizio().radio()
        uscita(f"{r['titolo']} ({r['numero']}/{r['totale']})" if r.get("attiva") else "-")
    elif c == "staff":
        return _staff(a, servizio(), uscita, dire)
    elif c == "avanzate":
        for nome, scope, descrizione in rpc_avanzato.elenco():
            uscita(f"{nome}  [{scope}]  {descrizione}")
        dire("da_attivare")
    return 0


def _staff(a, servizio: Servizio, uscita, dire) -> int:
    if a.azione == "azioni":
        for x in servizio.staff_azioni(a.server):
            uscita(f"{x['quando'][:16]}  {x['azione']} {x['dettaglio']} -> {x['esito']}")
        return 0
    try:
        if a.azione in ("blocca", "sblocca"):
            esito = servizio.staff_azione(a.server, a.azione + "_canale", channel_id=int(a.a))
        elif a.azione == "timeout":
            esito = servizio.staff_azione(a.server, "timeout", target_id=int(a.a), minuti=int(a.b), motivo=a.motivo)
        else:
            esito = servizio.staff_azione(a.server, "annuncio", channel_id=int(a.a), testo=a.b or "")
    except (TypeError, ValueError):
        dire("dati_non_validi")
        return 1
    dire(esito)
    return 0 if esito == "ok" else 1
