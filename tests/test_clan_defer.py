"""
tests/test_clan_defer.py
========================
LIM-25, M 9.11: i comandi delle gilde che parlano più volte con Discord
(crea, sciogli, invita, espelli, promuovi, compra-canale) fanno defer()
come prima cosa e rispondono poi con followup. Database vero.
Funzioni coperte: SPEC §15.14
"""

import pytest

from tests.test_guild_clan_cog_behavior import (  # noqa: F401  (cog_e_repos è una fixture)
    _crea_clan_con_categoria,
    _FakeGuild,
    _FakeInteraction,
    _FakeMember,
    cog_e_repos,
)

GUILD_ID = 100
CAPO = 1


async def _chiama(cog, nome_comando: str, interazione, **argomenti) -> None:
    comando = getattr(cog, nome_comando)
    await comando.callback(cog, interazione, **argomenti)


# (comando, argomenti) per chi NON è in nessuna gilda: il comando si
# ferma al primo controllo, ma il defer deve essere già partito.
COMANDI_SENZA_GILDA = [
    ("clan_sciogli", {}),
    ("clan_invita", {"membro": _FakeMember(2)}),
    ("clan_espelli", {"membro": _FakeMember(2)}),
    ("clan_promuovi", {"membro": _FakeMember(2), "ruolo": "admin"}),
    ("clan_compra_canale", {"tipo": "testuale", "nome": None}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("nome_comando, argomenti", COMANDI_SENZA_GILDA)
async def test_defer_per_primo_anche_quando_il_comando_viene_rifiutato(
    cog_e_repos, nome_comando, argomenti
):
    cog, _, _ = cog_e_repos
    interazione = _FakeInteraction(_FakeGuild(GUILD_ID), user=_FakeMember(CAPO))

    await _chiama(cog, nome_comando, interazione, **argomenti)

    assert interazione.response.chiamate == ["defer", "followup"]
    assert "Non fai parte di nessuna gilda" in interazione.response.sent_messages[0]


@pytest.mark.asyncio
async def test_crea_fa_defer_prima_di_creare_la_categoria(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    interazione = _FakeInteraction(guild, user=_FakeMember(CAPO))
    momento_del_defer = []
    defer_vero = interazione.response.defer

    async def defer_che_guarda(**kwargs):
        momento_del_defer.append(len(guild.created_categories))
        await defer_vero(**kwargs)

    interazione.response.defer = defer_che_guarda

    await cog.clan_crea.callback(cog, interazione, tag="ABC", name="I Cavalieri")

    assert momento_del_defer == [0]  # al momento del defer la categoria non c'era ancora
    assert interazione.response.chiamate == ["defer", "followup"]
    assert len(guild.created_categories) == 1
    assert await clan_repo.get_clan_by_tag(GUILD_ID, "ABC") is not None


@pytest.mark.asyncio
async def test_sciogli_con_molti_canali_risponde_dopo_il_defer(cog_e_repos):
    cog, clan_repo, _ = cog_e_repos
    guild = _FakeGuild(GUILD_ID)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    for numero in range(8):
        await guild.create_text_channel(f"canale-{numero}", category=categoria)
    interazione = _FakeInteraction(guild, user=_FakeMember(CAPO))

    await cog.clan_sciogli.callback(cog, interazione)

    assert interazione.response.chiamate == ["defer", "followup"]
    assert all(canale.deleted for canale in categoria.channels)
    assert await clan_repo.get_clan(clan_id) is None


@pytest.mark.asyncio
async def test_crea_se_il_database_rifiuta_la_gilda_la_categoria_viene_tolta(cog_e_repos):
    """Due creazioni insieme con lo stesso tag: una sola gilda, nessuna categoria orfana."""
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    cog, clan_repo, _ = cog_e_repos
    await apri_connessioni(clan_repo._pool)
    guild = _FakeGuild(GUILD_ID)
    prima = _FakeInteraction(guild, user=_FakeMember(1))
    seconda = _FakeInteraction(guild, user=_FakeMember(2))

    await asyncio.gather(
        cog.clan_crea.callback(cog, prima, tag="ABC", name="Prima"),
        cog.clan_crea.callback(cog, seconda, tag="ABC", name="Seconda"),
    )

    assert len(await clan_repo.list_clans(GUILD_ID)) == 1
    rimaste = [c for c in guild.created_categories if not c.deleted]
    assert len(rimaste) == 1
    risposte = prima.response.sent_messages + seconda.response.sent_messages
    assert sum("creata" in testo for testo in risposte) == 1
    assert sum("già usato" in testo for testo in risposte) == 1
