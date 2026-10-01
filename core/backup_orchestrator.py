"""
core/backup_orchestrator.py
===============================
Orchestrazione completa del Backup System (SPEC.md §11.1). Due fasi,
separate perché nel mezzo c'è un passaggio che questo codice non può
automatizzare del tutto — LIMITE REALE della piattaforma Discord,
verificato prima di progettare: un bot non può autoinvitarsi in un
server, serve sempre che una persona clicchi il link di
autorizzazione OAuth generato qui.

Fase 1 (start_backup_job): iYokai Creator crea il nuovo server,
clona tutto quello che si può clonare mentre è ancora admin (ruoli,
canali, emoji, sticker, soundboard, webhook — core/backup_clone_
logic.py), genera l'URL di invito per iYokai Main. Il chiamante
consegna quell'URL a qualcuno (DM all'amministratore, messaggio nel
server principale) — non è questo file a deciderlo.

Fase 2 (finalize_backup_job): chiamata dal listener on_guild_join di
iYokai Main, quando Main entra in un server che risulta essere il
backup atteso di un job in corso — trasferisce la proprietà a Main
e fa uscire Creator, così resta sotto il limite di 10 server e può
crearne un altro quando servirà; registra anche la coppia main →
backup (backup_pairs, BUG-3).
Funzioni coperte: SPEC §11.1, §11.12, REVIEW.md BUG-3 (issue #26).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord

from core.backup_clone_logic import (
    clone_categories_and_channels,
    clone_emoji,
    clone_roles,
    clone_soundboard,
    clone_stickers,
    clone_webhooks,
    create_mirror_webhooks,
)
from core.repositories.backup_repo import STATUS_RUNNING, BackupRepository

logger = logging.getLogger("iyokai.backup_orchestrator")

# Un server del Creator senza job in corso più vecchio di così è un resto.
ETA_MINIMA_SERVER_ORFANO = timedelta(hours=1)


async def elimina_server_creato(creator_client: discord.Client, guild_id: int) -> None:
    """
    BUG-4: libera lo slot del Creator (max 10 server). Se ne è ancora
    proprietario lo cancella; se la proprietà è già passata a Main
    può solo uscire. Un errore di Discord non solleva: è una pulizia.
    """
    guild = creator_client.get_guild(guild_id)
    if guild is None:
        return
    try:
        if guild.owner_id == creator_client.user.id:
            await guild.delete()
        else:
            await guild.leave()
    except discord.HTTPException:
        logger.warning("Impossibile liberare il server %s del Creator.", guild_id)


async def pulisci_server_orfani(
    creator_client: discord.Client, backup_repo: BackupRepository
) -> None:
    """
    BUG-4, all'avvio: i server del Creator non legati a un job in corso
    né a una coppia attiva e più vecchi di un'ora (resti di un crash)
    vengono cancellati, altrimenti occuperebbero gli slot per sempre.
    """
    in_corso = {
        job.backup_guild_id
        for job in await backup_repo.get_running_jobs()
        if job.backup_guild_id is not None
    }
    limite = datetime.now(timezone.utc) - ETA_MINIMA_SERVER_ORFANO
    for guild in list(creator_client.guilds):
        if guild.id in in_corso or guild.created_at > limite:
            continue
        if await backup_repo.get_pair_by_backup_guild_id(guild.id) is not None:
            continue
        await elimina_server_creato(creator_client, guild.id)


async def start_backup_job(
    creator_client: discord.Client,
    main_guild: discord.Guild,
    main_client_id: int,
    main_permissions: discord.Permissions,
) -> tuple[discord.Guild, str, dict[int, str]]:
    """
    Crea il nuovo server e clona tutto quello che è possibile
    clonare in questa fase. Restituisce (nuovo_server, url_invito,
    mappa_webhook_mirror) — il chiamante deve poi: salvare
    backup_guild_id sul job (tramite BackupRepository.
    set_backup_guild_id), salvare mappa_webhook_mirror (tramite
    BackupMirrorRepository.save_mapping, SPEC.md §11.9) e consegnare
    l'URL a chi deve autorizzare Main a entrare.
    """
    nuovo_server = await creator_client.create_guild(name=f"Backup di {main_guild.name}")

    try:
        mappa_ruoli = await clone_roles(main_guild, nuovo_server)
        mappa_canali = await clone_categories_and_channels(main_guild, nuovo_server, mappa_ruoli)
        emoji_saltate = await clone_emoji(main_guild, nuovo_server)
        sticker_saltati = await clone_stickers(main_guild, nuovo_server)
        suoni_saltati = await clone_soundboard(main_guild, nuovo_server)
        if emoji_saltate or sticker_saltati or suoni_saltati:
            logger.warning(
                "Backup di %s: saltati %d emoji, %d sticker, %d suoni (oltre i limiti o rifiutati da Discord).",
                main_guild.id,
                emoji_saltate,
                sticker_saltati,
                suoni_saltati,
            )
        await clone_webhooks(main_guild, nuovo_server, mappa_canali)
        mappa_webhook_mirror = await create_mirror_webhooks(nuovo_server, mappa_canali)
    except Exception:
        # BUG-4: il server a metà non serve a nessuno e occuperebbe uno
        # slot del Creator per sempre. Il Creator ne è proprietario.
        try:
            await nuovo_server.delete()
        except discord.HTTPException:
            logger.warning("Impossibile cancellare il server %s a metà.", nuovo_server.id)
        raise

    url_invito = discord.utils.oauth_url(
        main_client_id,
        permissions=main_permissions,
        guild=nuovo_server,
        disable_guild_select=True,
        scopes=["bot"],
    )

    return nuovo_server, url_invito, mappa_webhook_mirror


async def finalize_backup_job(
    joined_guild: discord.Guild,
    creator_client: discord.Client,
    backup_repo: BackupRepository,
) -> bool:
    """
    Da chiamare dal listener on_guild_join del bot MAIN. Se
    joined_guild è il backup atteso di un job ancora in corso:
    trasferisce la proprietà da Creator a Main (Main deve già essere
    membro, requisito di Discord per il trasferimento — lo è per
    definizione, essendo appena entrato) e fa uscire Creator.

    Restituisce True se questo guild era davvero atteso da un job
    (quindi la finalizzazione è avvenuta), False se Main è stato
    invitato in un server qualsiasi per altri motivi — in quel caso
    non c'è nulla da fare qui, il chiamante procede normalmente.
    """
    job = await backup_repo.get_job_by_backup_guild_id(joined_guild.id)
    if job is None or job.status != STATUS_RUNNING:
        return False

    server_lato_creator = creator_client.get_guild(joined_guild.id)
    if server_lato_creator is not None:
        await server_lato_creator.edit(
            owner=joined_guild.me, reason="Trasferimento proprietà backup iYokai"
        )
        await server_lato_creator.leave()

    # BUG-3: registra la coppia main -> backup. Senza, /promuovi-backup
    # dice sempre "non registrato" e lo snapshot settimanale degli
    # utenti non parte mai (nessuna coppia da cui partire).
    await backup_repo.define_backup(job.main_guild_id, joined_guild.id)
    await backup_repo.mark_completed(job.id, backup_guild_id=joined_guild.id)
    return True
