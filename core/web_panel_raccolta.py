"""
core/web_panel_raccolta.py
==========================
Raccolta pubblica dei modelli di server nel pannello (BKP-022/023, D127): elenco pubblico dei modelli APPROVATI in sola
lettura (pagina «modelli», con voti e conteggi, mai la struttura intera) e revisione del proprietario del bot (`/proprietario/modelli`:
approva, rifiuta, modifica nome, descrizione e struttura, sempre ricontrollata come una proposta). Un modello in revisione o
rifiutato non si vede mai fuori dalle pagine del proprietario. Sessione, CSRF e limiti sono quelli del pannello.
Funzioni coperte: BKP-022, BKP-023 (D127, D130)
Dipende da: core/backup_raccolta_logic.py, core/repositories/backup_raccolta_repo.py
"""

from __future__ import annotations

import json

from aiohttp import web

from core import backup_raccolta_logic as raccolta
from core.repositories.backup_raccolta_repo import backup_raccolta_repo

ID_MASSIMO = 2**63 - 1
STRUTTURA_MAX_BYTE = 200_000


def registra_rotte(app: web.Application, *, pagina, errore, scrittura, chiave_utente, ip, e_proprietario) -> None:
    from core import web_panel_logic as regole

    limite = regole.LimiteFrequenza(30, 60)  # l'elenco pubblico interroga il database

    def vai(url: str) -> web.Response:
        return web.Response(status=302, headers={"Location": url})

    def id_modello(request: web.Request) -> int | None:
        valore = int(request.match_info["modello"])
        return valore if 0 < valore <= ID_MASSIMO else None

    def solo_proprietario(request: web.Request):
        utente = request.get(chiave_utente)
        if utente is None:
            return vai("/accedi")
        if not e_proprietario(utente):
            return errore(request, 403, "Accesso negato", "Questa pagina è solo del proprietario del bot.")
        return None

    async def elenco_pubblico(request: web.Request) -> web.StreamResponse:
        if not limite.consenti(ip(request)):
            return errore(request, 429, "Troppe richieste", "Aspetta un minuto e riprova.")
        cerca = raccolta.ricerca_pulita(request.query.get("cerca", ""))
        lingua = raccolta.lingua_valida(request.query.get("lingua", ""))
        voci = await backup_raccolta_repo.elenco_pubblico(lingua=lingua, ricerca=cerca, limite=50)
        return pagina(request, "modelli.html", voci=voci, cerca=cerca, lingua=lingua or "", lingue=raccolta.LINGUE)

    async def revisione(request: web.Request) -> web.StreamResponse:
        rifiuto = solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        return pagina(
            request, "modelli_revisione.html",
            attesa=await backup_raccolta_repo.da_rivedere("revisione"),
            approvati=await backup_raccolta_repo.da_rivedere("approvato"),
        )

    async def scheda(request: web.Request, messaggio: str = "", status: int = 200) -> web.StreamResponse:
        rifiuto = solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        mid = id_modello(request)
        trovato = await backup_raccolta_repo.leggi_per_owner(mid) if mid else None
        if trovato is None:
            return errore(request, 404, "Modello non trovato", "Questo modello non esiste (più).")
        m, dati = trovato
        return pagina(
            request, "modelli_scheda.html", status, m=m, pericolosi=raccolta.ruoli_pericolosi(dati),
            struttura=json.dumps(dati, ensure_ascii=False, indent=1), messaggio=messaggio,
        )

    async def decidi(request: web.Request) -> web.StreamResponse:
        rifiuto = solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        mid = id_modello(request)
        scelta = form.get("scelta")
        if not mid or scelta not in ("approva", "rifiuta"):
            return errore(request, 400, "Richiesta non valida", "Scelta non valida.")
        if not await backup_raccolta_repo.decidi(mid, scelta == "approva", request[chiave_utente]):
            return errore(request, 404, "Modello non trovato", "Il modello non esiste o è già in quello stato.")
        return vai("/proprietario/modelli")

    async def modifica(request: web.Request) -> web.StreamResponse:
        rifiuto = solo_proprietario(request)
        if rifiuto is not None:
            return rifiuto
        form, rifiuto = await scrittura(request)
        if rifiuto is not None:
            return rifiuto
        mid = id_modello(request)
        testo = str(form.get("struttura", ""))
        nome = raccolta.nome_modello(str(form.get("nome", ""))[:200])
        errori = []
        pulita = None
        if len(testo.encode()) > STRUTTURA_MAX_BYTE:
            errori.append("struttura troppo grande")
        else:
            try:
                pulita, errori = raccolta.prepara_struttura(json.loads(testo))
            except ValueError:
                errori = ["la struttura non è un JSON valido"]
        if nome is None:
            errori = [*errori, "nome da 3 a 60 caratteri"]
        if errori or pulita is None or not mid:
            return await scheda(request, "; ".join(errori[:5]) or "modello non valido", 400)
        if not await backup_raccolta_repo.modifica(mid, nome, raccolta.descrizione_modello(str(form.get("descrizione", ""))[:600]), pulita):
            return errore(request, 404, "Modello non trovato", "Questo modello non esiste (più).")
        return vai(f"/proprietario/modelli/{mid}")

    app.router.add_get("/" + "modelli", elenco_pubblico)
    app.router.add_get("/proprietario/modelli", revisione)
    app.router.add_get(r"/proprietario/modelli/{modello:\d{1,19}}", scheda)
    app.router.add_post(r"/proprietario/modelli/{modello:\d{1,19}}/decidi", decidi)
    app.router.add_post(r"/proprietario/modelli/{modello:\d{1,19}}/modifica", modifica)
