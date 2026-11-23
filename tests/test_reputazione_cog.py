"""
tests/test_reputazione_cog.py
=============================
Comandi /rep e «grazie @utente» (LIV-076…088): controlli sui ruoli, bot, se stessi, spenta di base.
Funzioni coperte: catalogo #124
"""

from unittest.mock import AsyncMock

import pytest

import cogs.leveling.reputazione as modulo
from cogs.leveling.reputazione import ReputazioneCog
from core.repositories.reputazione_repo import ReputazioneRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_role, fake_text_channel

G = 600


@pytest.fixture
def cog(clean_db, monkeypatch):
    repo = ReputazioneRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "reputazione_repo", repo)
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    monkeypatch.setattr(modulo, "sincronizza_ruoli", AsyncMock())

    async def testo(interaction, chiave, **kw):
        return chiave

    monkeypatch.setattr(modulo, "testo_per", testo)
    c = ReputazioneCog(bot=None)
    c.repo = repo
    return c


def _i(utente):
    return fake_interaction(guild=fake_guild(G), user=utente)


def _chiave(i):
    return i.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_dai_spenta_bot_se_stessi_e_poi_ok(cog):
    a, b = fake_member(1), fake_member(2)
    for bersaglio, atteso in ((fake_member(3, bot=True), "rep_bersaglio"), (a, "rep_bersaglio"), (b, "rep_spenta")):
        i = _i(a)
        await cog.dai.callback(cog, i, bersaglio, 1, None)
        assert _chiave(i) == atteso
    await cog.repo.imposta(G, attiva=True)
    i = _i(a)
    await cog.dai.callback(cog, i, b, 1, "grazie")
    assert _chiave(i) == "rep_dato" and await cog.repo.punti_e_posizione(G, 2) == (1, 1)
    i = _i(a)
    await cog.dai.callback(cog, i, b, 1, None)
    assert _chiave(i) == "rep_pausa"


@pytest.mark.asyncio
async def test_ruoli_dare_ricevere_e_togliere(cog):
    r_dare, r_togli = fake_role(role_id=11), fake_role(role_id=12)
    await cog.repo.imposta(G, attiva=True, ruolo_dare_richiesto=11, ruolo_togliere=12)
    senza, con = fake_member(1), fake_member(2, roles=[r_dare])
    i = _i(senza)
    await cog.dai.callback(cog, i, fake_member(9), 1, None)
    assert _chiave(i) == "rep_non_puoi_dare"
    i = _i(con)
    await cog.togli.callback(cog, i, fake_member(9), 1, None)
    assert _chiave(i) == "rep_non_puoi_togliere"
    togli = fake_member(3, roles=[r_dare, r_togli])
    i = _i(togli)
    await cog.togli.callback(cog, i, fake_member(9), 1, None)
    assert _chiave(i) == "rep_tolto"


@pytest.mark.asyncio
async def test_grazie_solo_nei_canali_scelti_e_una_persona(cog):
    canale = fake_text_channel(channel_id=77)
    await cog.repo.imposta(G, attiva=True, grazie_attivo=True, grazie_canali=[77])
    autore, aiutante = fake_member(1), fake_member(2)

    def msg(testo, menzioni, canale=canale):
        m = fake_message(author=autore, channel=canale, guild=fake_guild(G), content=testo)
        m.mentions = menzioni
        m.add_reaction = AsyncMock()
        return m

    fuori = msg("grazie <@2>", [aiutante], fake_text_channel(channel_id=78))
    await cog.on_message(fuori)
    assert await cog.repo.punti_e_posizione(G, 2) == (0, None)
    due = msg("grazie <@2> <@3>", [aiutante, fake_member(3)])
    await cog.on_message(due)
    assert await cog.repo.punti_e_posizione(G, 2) == (0, None)
    bot = msg("grazie <@4>", [fake_member(4, bot=True)])
    await cog.on_message(bot)
    ok = msg("grazie <@2>", [aiutante])
    await cog.on_message(ok)
    assert await cog.repo.punti_e_posizione(G, 2) == (1, 1) and ok.add_reaction.await_count == 1
    ancora = msg("grazie <@2>", [aiutante])
    await cog.on_message(ancora)  # pausa: nessun secondo punto
    assert await cog.repo.punti_e_posizione(G, 2) == (1, 1)


@pytest.mark.asyncio
async def test_registro_degli_altri_solo_staff(cog):
    i = _i(fake_member(1))
    await cog.registro.callback(cog, i, fake_member(2))
    assert _chiave(i) == "rep_registro_staff"
