"""
core/automod_modelli.py
=======================
Regole pronte da cui partire (Solo YouTube, parolacce, siti-vetrina degli inviti, account nuovi senza link).
Sono solo bozze: l'admin le guarda nel pannello e le salva.
Funzioni coperte: SPEC §6 (AMD-015, AMD-025, AMD-028, AMD-032), D63
"""

from __future__ import annotations

from core.automod_regole_logic import Condizioni, Regola, azioni_da_json

MODELLI = ("solo_youtube", "parolacce", "vetrine", "account_nuovi")
_CANCELLA = {"t": "cancella"}


def modello(chiave: str, nome: str) -> Regola:
    """La bozza di regola personale per il modello `chiave`, con il nome dato (già nella lingua giusta)."""
    nome = nome[:32]
    if chiave == "solo_youtube":
        return Regola(chiave="p:0", tipo="personale", nome=nome, azioni=azioni_da_json([_CANCELLA]),
                      innesco={"tipo": "domini", "modo": "permessi", "parole": ["youtube.com", "youtu.be", "music.youtube.com"]})
    if chiave == "parolacce":
        return Regola(chiave="p:0", tipo="personale", nome=nome, azioni=azioni_da_json([_CANCELLA]),
                      innesco={"tipo": "lista", "liste": ["@parolacce-it", "@parolacce-en"]})
    if chiave == "vetrine":
        return Regola(chiave="p:0", tipo="personale", nome=nome, azioni=azioni_da_json([_CANCELLA]),
                      innesco={"tipo": "domini", "modo": "vietati", "liste": ["@vetrine-inviti"]})
    if chiave == "account_nuovi":
        return Regola(chiave="p:0", tipo="personale", nome=nome, condizioni=Condizioni(eta_account_giorni=(None, 7)),
                      azioni=azioni_da_json([_CANCELLA, {"t": "avviso_canale", "testo": "{utente}, i link non sono permessi agli account nuovi."}]),
                      innesco={"tipo": "regex", "regex": [r"https?://"]})
    raise KeyError(chiave)
