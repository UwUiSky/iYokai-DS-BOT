"""
core/backup_orchestrator.py
===========================
Copia del server principale nel server di backup (SPEC.md §11.1, D8). Un
admin crea il server di backup e vi invita iYokai Creator; dopo il
collegamento con il codice (core/backup_link_logic.py) il Creator porta il
server di backup allo stato corrente: ruoli, canali, emoji, sticker, suoni e
webhook. Il lavoro gira sul client del Creator, non su quello principale.
Funzioni coperte: SPEC §11.1, §11.12, M 12.1, M 12.2
"""

from __future__ import annotations

import logging

import discord

from core.backup_clone_logic import (
    RiepilogoCopia,
    clone_categories_and_channels,
    clone_emoji,
    clone_roles,
    clone_soundboard,
    clone_stickers,
    clone_webhooks,
    conta_canali_non_visibili,
    create_mirror_webhooks,
)
from core.repositories.backup_repo import STATUS_PENDING, STATUS_RUNNING, BackupRepository

logger = logging.getLogger("iyokai.backup_orchestrator")


async def popola_server_backup(
    main_guild: discord.Guild, backup_guild: discord.Guild
) -> tuple[dict[int, str], RiepilogoCopia]:
    """
    Copia struttura e risorse del server principale in ``backup_guild``,
    che deve essere un oggetto del client del Creator. Una chiamata alla
    volta, mai in parallelo. Restituisce (mappa canale principale ->
    URL del webhook di mirror, riepilogo di ciò che è stato adattato o saltato).
    """
    riepilogo = RiepilogoCopia()
    riepilogo.canali_non_visibili = conta_canali_non_visibili(main_guild)

    mappa_ruoli = await clone_roles(main_guild, backup_guild, riepilogo)
    mappa_canali = await clone_categories_and_channels(
        main_guild, backup_guild, mappa_ruoli, riepilogo
    )
    riepilogo.emoji_saltate = await clone_emoji(main_guild, backup_guild)
    riepilogo.sticker_saltati = await clone_stickers(main_guild, backup_guild)
    riepilogo.suoni_saltati = await clone_soundboard(main_guild, backup_guild)
    await clone_webhooks(main_guild, backup_guild, mappa_canali, riepilogo)
    mappa_webhook_mirror = await create_mirror_webhooks(backup_guild, mappa_canali, riepilogo)

    if riepilogo.emoji_saltate or riepilogo.sticker_saltati or riepilogo.suoni_saltati:
        logger.warning(
            "Backup di %s: saltati %d emoji, %d sticker, %d suoni (oltre i limiti o rifiutati da Discord).",
            main_guild.id,
            riepilogo.emoji_saltate,
            riepilogo.sticker_saltati,
            riepilogo.suoni_saltati,
        )
    return mappa_webhook_mirror, riepilogo


def riassunto_copia(riepilogo: RiepilogoCopia) -> str:
    """Righe da mostrare all'admin: solo ciò che non è andato come l'originale."""
    righe = []
    if riepilogo.canali_offuscati:
        righe.append(f"Canali offuscati saltati: {riepilogo.canali_offuscati}.")
    if riepilogo.canali_non_visibili:
        righe.append(
            f"{riepilogo.canali_non_visibili} canali non visibili al bot: "
            "dagli il permesso di vedere tutti i canali e rilancia la copia."
        )
    if riepilogo.webhook_saltati:
        righe.append(f"Webhook oltre il limite di 14 per canale: {riepilogo.webhook_saltati}.")
    if riepilogo.mirror_non_creati:
        righe.append(f"Canali senza mirror (webhook al massimo): {riepilogo.mirror_non_creati}.")
    if riepilogo.posizioni_ruoli_fallite:
        righe.append("Ordine dei ruoli non impostato: metti il ruolo del Creator in alto.")
    if riepilogo.ruoli_non_aggiornati:
        righe.append(f"Ruoli sopra quello del Creator, non aggiornati: {riepilogo.ruoli_non_aggiornati}.")
    if riepilogo.permessi_ridotti:
        righe.append(
            f"Ruoli con permessi che il Creator non ha: {riepilogo.permessi_ridotti}. "
            "Per una copia fedele dai al Creator il permesso Amministratore."
        )
    saltati = riepilogo.emoji_saltate + riepilogo.sticker_saltati + riepilogo.suoni_saltati
    if saltati:
        righe.append(f"Emoji, sticker e suoni oltre i limiti del server: {saltati}.")
    return "\n".join(righe)


async def finalize_backup_job(
    joined_guild: discord.Guild,
    creator_client: discord.Client | None,
    backup_repo: BackupRepository,
) -> bool:
    """
    Chiamata da ``main.py`` quando iYokai entra in un server: True se quel
    server è un backup collegato o con una copia in corso (non va trattato
    come server nuovo). Nel flusso D8 niente cessione di proprietà e niente
    uscita del Creator: il Creator resta per tenere il server aggiornato.
    """
    job = await backup_repo.get_job_by_backup_guild_id(joined_guild.id)
    if job is not None and job.status in (STATUS_PENDING, STATUS_RUNNING):
        return True
    return await backup_repo.get_pair_by_backup_guild_id(joined_guild.id) is not None
