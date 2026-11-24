"""
core/piani_comandi.py
=====================
Il lavoro di `/owner premium piano` e di `/admin-bot premium chiave`, senza Discord: legge gli argomenti già
controllati dal comando, chiama `core/piani.py` e `core/ai_chiavi_proprie.py` e restituisce il testo da mostrare.
Funzioni coperte: CFG-040, CFG-041, AI-003
Dipende da: core/piani.py, core/ai_chiavi_proprie.py
"""

from __future__ import annotations

from core import ai_chiavi_proprie as chiavi
from core import piani

AZIONI_OWNER = ("mostra", "limite", "prezzo", "sconto", "concedi", "revoca", "patreon")
AZIONI_CHIAVE = ("imposta", "togli", "elenco")


async def testo_piani() -> str:
    """Limiti e prezzi in uso, per `mostra`."""
    righe = ["**Limiti** (" + " / ".join(piani.ETICHETTE[l] for l in piani.LIVELLI) + ")"]
    for chiave, descrizione, valori in await piani.tabella_limiti():
        righe.append(f"`{chiave}` {descrizione}: " + " / ".join(str(v) for v in valori))
    righe += ["", "**Prezzi**", await piani.testo_listino()]
    return "\n".join(righe)[:1900]


async def esegui_owner(azione: str, *, livello: str | None, periodo: str | None, chiave: str | None,
                       valore: int | None, utente_id: int | None, server_id: int | None, owner_id: int) -> str:
    """Una azione dell'owner sui piani. Gli errori di valore tornano come frase, mai come eccezione."""
    try:
        if azione == "mostra":
            return await testo_piani()
        if azione == "limite":
            if not chiave or livello is None:
                return "Servono `chiave` (es. backup_copie) e `livello`. Senza `valore` torna il predefinito."
            await piani.imposta_limite(chiave, livello, valore)
            return f"Limite `{chiave}` per {piani.ETICHETTE[livello]}: " + (f"{valore}." if valore is not None else "predefinito.")
        if azione == "prezzo":
            if livello is None or periodo is None:
                return "Servono `livello` e `periodo`. `valore` è in centesimi; senza `valore` il prezzo si toglie."
            await piani.imposta_prezzo(livello, periodo, valore)
            return "Prezzo tolto." if valore is None else f"Prezzo {piani.ETICHETTE[livello]} {periodo}: {piani.euro(valore)}."
        if azione == "sconto":
            if not chiave:
                return "Serve `chiave`: il nome dello sconto. `valore` è la percentuale (1-100); senza `valore` lo sconto si toglie."
            await piani.imposta_sconto(chiave, valore, livello if livello in piani.LIVELLI_A_PAGAMENTO else None, periodo)
            return "Sconto tolto." if valore is None else f"Sconto `{chiave}`: {valore}%."
        if azione == "patreon":
            from core import patreon_service

            if not chiave:
                return "Serve `chiave`: l'ID del livello Patreon. `livello` è il livello del bot; senza `livello` l'associazione si toglie."
            await patreon_service.imposta_livello_tier(chiave, livello)
            return "Associazione tolta." if livello is None else f"Livello Patreon `{chiave}` = {piani.ETICHETTE[livello]}."
        if azione in ("concedi", "revoca"):
            soggetto, sid = ("server", server_id) if server_id else ("utente", utente_id)
            if not sid:
                return "Serve `utente` oppure `server`."
            if azione == "revoca":
                return f"Concessioni tolte: {await piani.revoca(soggetto, sid, 'manuale')}."
            if livello is None or periodo is None:
                return "Servono `livello` e `periodo`."
            scade = await piani.concedi(soggetto, sid, livello, "manuale" if periodo != "a_vita" else "a_vita",
                                        giorni=piani.GIORNI_PERIODO[periodo], concesso_da=owner_id)
            fine = f"fino al {scade.date().isoformat()}" if scade else "senza scadenza"
            return f"{piani.ETICHETTE[livello]} a `{sid}` ({soggetto}), {fine}."
    except piani.PianoNonValido as errore:
        return f"Valore non valido: {errore}."
    return "Azione sconosciuta."


async def esegui_chiave(azione: str, *, ambito: str, ambito_id: int, servizio: str | None, chiave: str | None, utente_id: int, t) -> str:
    """
    Imposta, toglie o elenca le chiavi proprie. Mai la chiave nel testo restituito.
    `t(chiave_testo, **parametri)` è la traduzione nella lingua di chi scrive (`testo_per` dell'interazione).
    """
    from core.premium_cache import invalida_cache_premium

    try:
        if azione == "elenco":
            servizi = await chiavi.servizi_con_chiave(ambito, ambito_id)
            if not servizi:
                return await t("piani_chiave_nessuna")
            return await t("piani_chiave_elenco", servizi=", ".join(f"`{s}`" for s in servizi))
        if azione == "togli":
            tolte = await chiavi.togli(ambito, ambito_id, servizio)
            invalida_cache_premium(ambito_id if ambito == "server" else None)
            return await t("piani_chiave_tolte", n=tolte)
        if azione == "imposta":
            await chiavi.verifica_e_salva(ambito, ambito_id, servizio or "", chiave or "", utente_id)
            invalida_cache_premium(ambito_id if ambito == "server" else None)
            return await t("piani_chiave_salvata", servizio=servizio)
    except chiavi.CifraturaNonConfigurata:
        return await t("piani_chiave_senza_cifratura")
    except chiavi.ServizioSconosciuto:
        return await t("piani_chiave_servizio_ignoto")
    except chiavi.ChiaveRifiutata:
        return await t("piani_chiave_rifiutata")
    except chiavi.ChiaveNonValida:
        return await t("piani_chiave_non_valida")
    return await t("piani_chiave_non_valida")
