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
crearne un altro quando servirà.
"""

from __future__ import annotations

import discord

from core.backup_clone_logic import (
    clone_categories_and_channels,
    clone_emoji,
    clone_roles,
    clone_soundboard,
    clone_stickers,
    clone_webhooks,
)
from core.repositories.backup_repo import STATUS_RUNNING, BackupRepository


async def start_backup_job(
    creator_client: discord.Client,
    main_guild: discord.Guild,
    main_client_id: int,
    main_permissions: discord.Permissions,
) -> tuple[discord.Guild, str]:
    """
    Crea il nuovo server e clona tutto quello che è possibile
    clonare in questa fase. Restituisce (nuovo_server, url_invito) —
    il chiamante deve poi: salvare backup_guild_id sul job (tramite
    BackupRepository.set_backup_guild_id) e consegnare l'URL a chi
    deve autorizzare Main a entrare.
    """
    nuovo_server = await creator_client.create_guild(name=f"Backup di {main_guild.name}")

    mappa_ruoli = await clone_roles(main_guild, nuovo_server)
    mappa_canali = await clone_categories_and_channels(main_guild, nuovo_server, mappa_ruoli)
    await clone_emoji(main_guild, nuovo_server)
    await clone_stickers(main_guild, nuovo_server)
    await clone_soundboard(main_guild, nuovo_server)
    await clone_webhooks(main_guild, nuovo_server, mappa_canali)

    url_invito = discord.utils.oauth_url(
        main_client_id,
        permissions=main_permissions,
        guild=nuovo_server,
        disable_guild_select=True,
        scopes=["bot"],
    )

    return nuovo_server, url_invito


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

    await backup_repo.mark_completed(job.id, backup_guild_id=joined_guild.id)
    return True
