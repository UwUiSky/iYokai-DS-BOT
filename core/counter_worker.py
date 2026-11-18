"""
core/counter_worker.py
======================
Aggiorna i nomi dei canali contatore (NF-16). Un giro ogni 10 minuti (LIM-3: Discord
permette 2 rinomine ogni 10 minuti per canale): un canale si rinomina solo se il numero
è cambiato, e se Discord dice di aspettare si riprova al giro dopo. Un errore su un
server non ferma gli altri.
Funzioni coperte: SPEC §23 (NF-16); STA-033..052
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import discord

from core.channel_rename import RenameRateLimited, rename_channel
from core.counter_logic import (
    SEGNAPOSTO_NOMINATI,
    TIPI_DI_TESTO,
    TIPI_SOCIAL,
    Istantanea,
    nome_del_contatore,
    valore_del_contatore,
)
from core.counter_social import leggi_social
from core.guild_iteration import for_each_guild_safely

logger = logging.getLogger("iyokai.counters")


def _segnaposti(contatore) -> set[str]:
    """I segnaposto con nome dell'etichetta («{online}», «{bot}»...): servono altri numeri oltre al principale."""
    return set(re.findall(r"\{(\w+)\}", contatore.label)) & set(SEGNAPOSTO_NOMINATI)


def _nominati(contatore, snap=None) -> bool:
    """True se il nome può cambiare anche se il numero principale non è cambiato."""
    return bool(_segnaposti(contatore))


def _intero(valore) -> int:
    return valore if isinstance(valore, int) else 0


class _Gruppo:
    """Un server con i suoi contatori: serve a for_each_guild_safely (nome nei log)."""

    def __init__(self, guild_id: int, contatori: list) -> None:
        self.id = guild_id
        self.contatori = contatori


class CounterWorker:
    def __init__(self, repo, rename=rename_channel, db=None, conta_ticket=None, social=leggi_social) -> None:
        self._repo = repo
        self._rename = rename
        self._social_fn = social
        self._social: dict = {}
        if conta_ticket is None:
            from core.repositories.ticket_repo import ticket_repo

            conta_ticket = lambda guild_id: ticket_repo.count_open_tickets(guild_id)  # noqa: E731
        self._conta_ticket = conta_ticket
        if db is None:
            from core.database import db as db_globale

            db = db_globale
        self._db = db

    async def tick(self, bot) -> None:
        tutti = await self._repo.list_all()
        gruppi: dict[int, list] = {}
        for contatore in tutti:
            gruppi.setdefault(contatore.guild_id, []).append(contatore)
        elementi = [_Gruppo(g, c) for g, c in gruppi.items()]
        await self._leggi_social(bot, tutti)

        async def per_server(gruppo: _Gruppo) -> None:
            await self._aggiorna_server(bot, gruppo)

        await for_each_guild_safely(elementi, per_server, nome_worker="counter_worker")

    async def _leggi_social(self, bot, tutti: list) -> None:
        """STA-045, 046: i numeri esterni di tutti i contatori, letti una volta sola per giro."""
        richieste = {
            (c.kind, c.param) for c in tutti
            if c.kind in TIPI_SOCIAL and getattr(c, "param", None) and bot.get_guild(c.guild_id) is not None
        }
        self._social = {}
        if richieste:
            try:
                self._social = await self._social_fn(richieste)
            except Exception:
                logger.exception("Contatori: numeri esterni non letti")

    @staticmethod
    def _ultimo_membro(guild) -> str | None:
        """STA-052: chi è entrato per ultimo (dalla memoria del bot; i bot non contano)."""
        recenti = [m for m in guild.members if not m.bot and m.joined_at is not None]
        if not recenti:
            return None
        ultimo = max(recenti, key=lambda m: m.joined_at)
        return " ".join(ultimo.display_name.split())[:30] or None

    async def _aggiorna_server(self, bot, gruppo: _Gruppo) -> None:
        guild = bot.get_guild(gruppo.id)
        if guild is None or not await self._db.is_module_active_for_guild(gruppo.id, "counters"):
            return
        online = None
        if any(c.kind in ("online", "offline") or {"online", "offline"} & _segnaposti(c) for c in gruppo.contatori):
            # Una sola richiesta per server, qualunque sia il numero di contatori "online".
            try:
                con_conteggi = await bot.fetch_guild(gruppo.id, with_counts=True)
                online = con_conteggi.approximate_presence_count
            except discord.HTTPException:
                logger.warning("Contatori: conteggio online non letto nel server %s", gruppo.id)
        ticket = None
        if any(c.kind == "tickets" or "ticket" in _segnaposti(c) for c in gruppo.contatori):
            ticket = await self._conta_ticket(gruppo.id)
        tipi = {c.kind for c in gruppo.contatori}
        con_ruolo = {}
        for c in gruppo.contatori:
            param = getattr(c, "param", None)
            if c.kind in ("role_with", "role_without") and param and param.isdigit():
                ruolo = guild.get_role(int(param))
                if ruolo is not None:
                    con_ruolo[int(param)] = len(ruolo.members)
        nominati = set().union(*(_segnaposti(c) for c in gruppo.contatori)) if gruppo.contatori else set()
        snap = Istantanea(
            member_count=guild.member_count or 0,
            online_count=online,
            boost_count=guild.premium_subscription_count or 0,
            ticket_aperti=ticket,
            ruoli=len(guild.roles),
            canali=len(guild.channels),
            emoji=len(guild.emojis),
            bot=sum(1 for m in guild.members if m.bot) if ({"users", "bots"} & tipi or {"utenti", "bot"} & nominati) else 0,
            livello_boost=_intero(guild.premium_tier),
            ultimo_membro=self._ultimo_membro(guild) if "last_member" in tipi or "ultimo" in nominati else None,
            per_ruolo=con_ruolo,
            social=self._social,
        )
        for contatore in gruppo.contatori:
            await self._aggiorna_contatore(guild, contatore, snap)

    async def _aggiorna_contatore(self, guild, contatore, snap: Istantanea) -> None:
        canale = guild.get_channel(contatore.channel_id)
        if canale is None:
            await self._repo.delete_by_channel(contatore.channel_id)  # cancellato: il contatore non serve più
            return
        param = getattr(contatore, "param", None)
        numerico = contatore.kind not in TIPI_DI_TESTO
        valore = valore_del_contatore(contatore.kind, snap, param) if numerico else None
        if numerico and (valore is None or (valore == contatore.last_value and not _nominati(contatore, snap))):
            return
        nome = nome_del_contatore(contatore, snap, datetime.now(timezone.utc))
        if nome is None:
            return
        try:
            if canale.name != nome:
                await self._rename(canale, nome, reason="Contatore")
        except RenameRateLimited:
            return  # al prossimo giro
        except discord.NotFound:
            await self._repo.delete_by_channel(contatore.channel_id)
            return
        except discord.HTTPException as errore:
            logger.warning("Contatore %s: rinomina non riuscita nel server %s: %s", contatore.id, guild.id, errore)
            return
        if numerico:
            await self._repo.set_last_value(contatore.id, valore)
