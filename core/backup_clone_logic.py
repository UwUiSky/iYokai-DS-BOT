"""
core/backup_clone_logic.py
==============================
Clonazione server per server (SPEC.md §11.3 ruoli, §11.4 canali —
il resto della sezione, in ordine, negli stessi file man mano che si
costruisce). Funzioni di orchestrazione reali contro l'API discord.py
(verificata prima di scrivere, non a memoria — vedi le firme usate),
testabili con oggetti finti che replicano l'interfaccia vera dato
che non è possibile una connessione Discord reale in questo ambiente.

Chiamate sequenziali (mai `asyncio.gather` per creare più ruoli/
canali insieme) — discord.py gestisce da solo i rate limit di
Discord sulle richieste in sequenza, ma spararle tutte insieme
peggiorerebbe le cose, non le velocizzerebbe.
"""

from __future__ import annotations

import discord


async def clone_roles(source_guild: discord.Guild, target_guild: discord.Guild) -> dict[int, int]:
    """
    Clona i ruoli del server sorgente nel server di destinazione.

    @everyone non viene CREATO (esiste già di default in ogni
    server, Discord non permette di crearne un secondo) — ma i suoi
    PERMESSI vengono comunque applicati esplicitamente al server di
    destinazione: l'amministratore del server originale potrebbe
    averli personalizzati rispetto al default di Discord (es. tolto
    "Invia messaggi" di default a tutti), e quella scelta va
    preservata nel backup, non persa silenziosamente.

    I ruoli "managed" (creati da un'integrazione o da un bot, es. il
    ruolo automatico di un bot musicale) vengono saltati — Discord
    non permette di crearli manualmente, si ricreano da soli quando
    l'integrazione/il bot viene reinvitato.

    Restituisce la mappa ID_ruolo_originale -> ID_ruolo_clonato
    (include anche @everyone, mappato al default_role già esistente
    nel server di destinazione), necessaria per rimappare gli
    overwrite di permessi sui canali (clone_categories_and_channels).

    I ruoli normali vengono creati dal più basso al più alto in
    posizione: ogni nuovo ruolo creato finisce sopra i precedenti
    per comportamento di default di Discord, quindi partire dal più
    basso mantiene l'ordine finale corretto.
    """
    mappa_id: dict[int, int] = {}

    await target_guild.default_role.edit(
        permissions=source_guild.default_role.permissions,
        reason="Clonazione backup iYokai — permessi di @everyone",
    )
    mappa_id[source_guild.default_role.id] = target_guild.default_role.id

    ruoli_da_clonare = sorted(
        (ruolo for ruolo in source_guild.roles if not ruolo.is_default() and not ruolo.managed),
        key=lambda r: r.position,
    )

    for ruolo in ruoli_da_clonare:
        nuovo_ruolo = await target_guild.create_role(
            name=ruolo.name,
            permissions=ruolo.permissions,
            colour=ruolo.colour,
            hoist=ruolo.hoist,
            mentionable=ruolo.mentionable,
            reason="Clonazione backup iYokai",
        )
        mappa_id[ruolo.id] = nuovo_ruolo.id

    return mappa_id


def remap_permission_overwrites(
    source_overwrites: dict,
    role_id_map: dict[int, int],
    target_guild: discord.Guild,
) -> dict:
    """
    Converte gli overwrite di permessi (canale/categoria) dal server
    originale al server clonato. Solo quelli per RUOLO vengono
    riportati (i ruoli clonati hanno ID diversi da quelli originali,
    serve la mappa per trovare il ruolo giusto nel server nuovo) —
    gli overwrite per singolo UTENTE vengono saltati: un server
    appena clonato non ha ancora nessun membro (il restore utenti è
    un passo separato, §11.11), non esiste nessun Member a cui
    applicarli.
    """
    nuovi_overwrites = {}
    for destinatario, overwrite in source_overwrites.items():
        if not isinstance(destinatario, discord.Role):
            continue  # overwrite per singolo utente, saltato

        if destinatario.is_default():
            # @everyone esiste già nel server di destinazione, non
            # passa dalla mappa dei ruoli clonati.
            nuovi_overwrites[target_guild.default_role] = overwrite
            continue

        nuovo_id = role_id_map.get(destinatario.id)
        if nuovo_id is None:
            continue  # ruolo non clonato (managed, o rimosso nel frattempo)

        nuovo_ruolo = target_guild.get_role(nuovo_id)
        if nuovo_ruolo is not None:
            nuovi_overwrites[nuovo_ruolo] = overwrite

    return nuovi_overwrites


async def clone_categories_and_channels(
    source_guild: discord.Guild,
    target_guild: discord.Guild,
    role_id_map: dict[int, int],
) -> dict[int, int]:
    """
    Clona categorie e canali (testuali e vocali) del server sorgente
    nel server di destinazione, preservando l'ordine e gli overwrite
    di permessi per ruolo (rimappati tramite remap_permission_
    overwrites — serve la mappa già prodotta da clone_roles).

    Le CATEGORIE vanno create per prime: un canale dentro una
    categoria ha bisogno dell'oggetto categoria già esistente sul
    lato destinazione per essere assegnato correttamente.

    Restituisce la mappa ID_canale_originale -> ID_canale_clonato
    (categorie incluse) — utile a chi chiama per ulteriori passaggi
    (es. §11.9 mirror messaggi, che deve sapere in quale canale
    clonato inoltrare ogni messaggio del canale originale).
    """
    mappa_id: dict[int, int] = {}
    mappa_categorie: dict[int, discord.CategoryChannel] = {}

    categorie_ordinate = sorted(source_guild.categories, key=lambda c: c.position)
    for categoria in categorie_ordinate:
        overwrites = remap_permission_overwrites(categoria.overwrites, role_id_map, target_guild)
        nuova_categoria = await target_guild.create_category(
            name=categoria.name,
            overwrites=overwrites,
            reason="Clonazione backup iYokai",
        )
        mappa_id[categoria.id] = nuova_categoria.id
        mappa_categorie[categoria.id] = nuova_categoria

    canali_ordinati = sorted(source_guild.channels, key=lambda c: c.position)
    for canale in canali_ordinati:
        if isinstance(canale, discord.CategoryChannel):
            continue  # già clonate sopra

        categoria_destinazione = None
        if canale.category is not None:
            categoria_destinazione = mappa_categorie.get(canale.category.id)

        overwrites = remap_permission_overwrites(canale.overwrites, role_id_map, target_guild)

        if isinstance(canale, discord.VoiceChannel):
            nuovo_canale = await target_guild.create_voice_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                bitrate=canale.bitrate,
                user_limit=canale.user_limit,
                reason="Clonazione backup iYokai",
            )
        elif isinstance(canale, discord.TextChannel):
            nuovo_canale = await target_guild.create_text_channel(
                name=canale.name,
                category=categoria_destinazione,
                overwrites=overwrites,
                topic=canale.topic or "",
                nsfw=canale.nsfw,
                slowmode_delay=canale.slowmode_delay,
                reason="Clonazione backup iYokai",
            )
        else:
            continue  # tipi di canale non gestiti (forum, stage, ecc.) — fuori scope qui

        mappa_id[canale.id] = nuovo_canale.id

    return mappa_id
