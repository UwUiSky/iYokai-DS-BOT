"""
core/automod_contatori.py
=========================
Contatori delle regole AutoMod: «X violazioni in Y minuti» con scadenza in giorni. Conta le righe del registro
(`automod_action_log.contatore`) solo quando una regola scatta, mai a ogni messaggio.
Funzioni coperte: SPEC §6 (AMD-058, 059, 060, 061)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.automod_regole_logic import Contatore, Soglia
from core.repositories.automod_advanced_repo import automod_advanced_repo


def inizio_finestra(contatore: Contatore, soglia: Soglia, adesso: datetime) -> datetime:
    """Dove comincia il conteggio di una soglia: i suoi minuti, ma mai oltre la scadenza in giorni del contatore."""
    inizio = adesso - timedelta(minutes=soglia.minuti)
    if contatore.scadenza_giorni is not None:
        inizio = max(inizio, adesso - timedelta(days=contatore.scadenza_giorni))
    return inizio


async def soglia_scattata(guild_id: int, user_id: int, contatore: Contatore, adesso: datetime | None = None) -> Soglia | None:
    """La soglia più alta raggiunta da questo utente, o None. Una query per soglia (al massimo tre)."""
    adesso = adesso or datetime.now(timezone.utc)
    for soglia in sorted(contatore.soglie, key=lambda s: s.violazioni, reverse=True):
        conta = await automod_advanced_repo.conta_contatore(
            guild_id, user_id, contatore.nome, inizio_finestra(contatore, soglia, adesso))
        if conta >= soglia.violazioni:
            return soglia
    return None


async def consuma(guild_id: int, user_id: int, contatore: Contatore) -> int:
    """Dopo una soglia scattata (o con l'azione `azzera`) il contatore dell'utente riparte da zero."""
    return await automod_advanced_repo.svuota_contatore_utente(guild_id, user_id, contatore.nome)
