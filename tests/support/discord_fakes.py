"""
tests/support/discord_fakes.py
==================================
Oggetti finti FEDELI alle classi reali di discord.py, costruiti con
unittest.mock.create_autospec(..., instance=True): un autospec rifiuta
una chiamata con una firma sbagliata (argomento inesistente, tipo
diverso), a differenza di un finto scritto a mano che accetta
qualunque cosa.

Esempio concreto del problema che risolvono: un finto scritto a mano
con `async def delete(self, delay=None): ...` non avrebbe mai fatto
fallire `channel.delete(delay=10)`, che invece è un errore reale
(discord.py non ha quel parametro su TextChannel.delete). Con
`fake_text_channel()` la stessa chiamata solleva TypeError, esattamente
come col bot vero — è così che si sarebbe trovato BUG-1 prima che
arrivasse in produzione.

Uso: chiamare la funzione fake_*(), poi impostare gli attributi che
servono al test (es. `canale.id = 123`). I metodi async sono già
AsyncMock con la firma vera — basta leggere `.call_args` o impostare
`.return_value` / `.side_effect` come su un Mock normale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord


def _autospec_instance(cls: type) -> MagicMock:
    """
    Wrapper comune: autospec di un'istanza della classe, con gli
    attributi di base (id, name, mention) preimpostati a valori finti
    ma coerenti in modo che i test non li debbano sempre reimpostare.
    """
    return create_autospec(cls, instance=True, spec_set=False)


def fake_text_channel(channel_id: int = 111, name: str = "generale") -> MagicMock:
    canale = _autospec_instance(discord.TextChannel)
    canale.id = channel_id
    canale.name = name
    canale.mention = f"<#{channel_id}>"
    canale.type = discord.ChannelType.text
    return canale


def fake_voice_channel(channel_id: int = 222, name: str = "vocale") -> MagicMock:
    canale = _autospec_instance(discord.VoiceChannel)
    canale.id = channel_id
    canale.name = name
    canale.mention = f"<#{channel_id}>"
    canale.type = discord.ChannelType.voice
    canale.members = []
    return canale


def fake_forum_channel(channel_id: int = 333, name: str = "forum") -> MagicMock:
    canale = _autospec_instance(discord.ForumChannel)
    canale.id = channel_id
    canale.name = name
    canale.mention = f"<#{channel_id}>"
    canale.type = discord.ChannelType.forum
    return canale


def _confronto_per_posizione(a, b) -> int:
    """
    Replica il confronto reale di discord.Role (Role.__lt__): posizione
    più bassa prima, a parità di posizione l'id più alto è "più basso"
    in gerarchia. Restituisce -1/0/1 come una comparazione classica.
    Non replica il controllo "stessa guild" di discord.py perché nei
    test un ruolo finto non appartiene mai a più guild finte diverse.
    """
    if a.position != b.position:
        return -1 if a.position < b.position else 1
    if a.id == b.id:
        return 0
    return -1 if a.id > b.id else 1


def fake_role(
    role_id: int = 444,
    name: str = "Ruolo",
    *,
    position: int = 1,
    managed: bool = False,
    permissions: discord.Permissions | None = None,
) -> MagicMock:
    ruolo = _autospec_instance(discord.Role)
    ruolo.id = role_id
    ruolo.name = name
    ruolo.mention = f"<@&{role_id}>"
    ruolo.position = position
    ruolo.managed = managed
    ruolo.is_default = MagicMock(return_value=(role_id == 0))
    ruolo.permissions = permissions if permissions is not None else discord.Permissions.none()

    # discord.Role definisce __lt__/__le__/__gt__/__ge__ in base alla
    # posizione in gerarchia (vedi _confronto_per_posizione sopra):
    # core/role_safety.py li usa per capire se un ruolo è "sopra" un
    # altro, quindi il finto deve confrontarsi allo stesso modo.
    ruolo.__lt__ = lambda self, other: _confronto_per_posizione(self, other) < 0
    ruolo.__le__ = lambda self, other: _confronto_per_posizione(self, other) <= 0
    ruolo.__gt__ = lambda self, other: _confronto_per_posizione(self, other) > 0
    ruolo.__ge__ = lambda self, other: _confronto_per_posizione(self, other) >= 0
    return ruolo


def fake_member(
    user_id: int = 555,
    name: str = "utente",
    *,
    roles: list | None = None,
    guild_permissions: discord.Permissions | None = None,
    bot: bool = False,
) -> MagicMock:
    membro = _autospec_instance(discord.Member)
    membro.id = user_id
    membro.name = name
    membro.mention = f"<@{user_id}>"
    membro.bot = bot
    membro.roles = roles if roles is not None else []
    membro.guild_permissions = (
        guild_permissions if guild_permissions is not None else discord.Permissions.none()
    )
    membro.top_role = membro.roles[-1] if membro.roles else fake_role(role_id=0, name="@everyone", position=0)
    return membro


def fake_guild(
    guild_id: int = 666,
    name: str = "Server di test",
    *,
    owner_id: int = 555,
    me: MagicMock | None = None,
) -> MagicMock:
    server = _autospec_instance(discord.Guild)
    server.id = guild_id
    server.name = name
    server.owner_id = owner_id
    server.me = me if me is not None else fake_member(user_id=999, name="Yokai Bot", bot=True)
    # Guild.delete è decorato con @utils.deprecated: l'autospec non lo vede
    # come coroutine, quindi lo dichiariamo a mano.
    server.delete = AsyncMock()
    server.roles = []
    server.members = []
    server.get_role = MagicMock(return_value=None)
    server.get_member = MagicMock(return_value=None)
    server.get_channel = MagicMock(return_value=None)
    return server


def fake_message(
    message_id: int = 777,
    *,
    author: MagicMock | None = None,
    channel: MagicMock | None = None,
    guild: MagicMock | None = None,
    content: str = "",
) -> MagicMock:
    messaggio = _autospec_instance(discord.Message)
    messaggio.id = message_id
    messaggio.author = author if author is not None else fake_member()
    messaggio.channel = channel if channel is not None else fake_text_channel()
    messaggio.guild = guild if guild is not None else fake_guild()
    messaggio.content = content
    return messaggio


def fake_interaction(
    *,
    guild: MagicMock | None = None,
    user: MagicMock | None = None,
    channel: MagicMock | None = None,
    permissions: discord.Permissions | None = None,
) -> MagicMock:
    """
    Interaction finta con response/followup già pronti come AsyncMock.
    `response.is_done()` parte False (comportamento di default prima
    che il comando risponda), impostabile dal test dopo un
    `response.send_message`/`defer` se serve simulare la sequenza.
    """
    interazione = _autospec_instance(discord.Interaction)
    interazione.guild = guild if guild is not None else fake_guild()
    interazione.user = user if user is not None else fake_member()
    interazione.channel = channel if channel is not None else fake_text_channel()
    interazione.permissions = (
        permissions if permissions is not None else discord.Permissions.none()
    )

    interazione.response = create_autospec(discord.InteractionResponse, instance=True)
    interazione.response.is_done.return_value = False

    interazione.followup = create_autospec(discord.Webhook, instance=True)

    return interazione
