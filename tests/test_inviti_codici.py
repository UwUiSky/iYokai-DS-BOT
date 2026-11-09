"""
tests/test_inviti_codici.py
===========================
D69 B12 (UTL-166, 167, 174, 180, 181): elenco dei codici, etichetta con ruolo, invito nuovo, cancellazione a gruppi.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

import cogs.utility.invites as invites
import cogs.utility.inviti_codici as modulo
from core.inviti_codici_logic import (
    InvitoVisto, da_cancellare, da_invito, pagine, riga_codice,
)
from core.repositories.inviti_extra_repo import InvitiExtraRepository, TroppeEtichette
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo

G = 900000000000000003


def _inv(code, usi=0, canale=1, creatore=5, max_usi=0, scade=None):
    return SimpleNamespace(
        code=code, uses=usi, max_uses=max_usi, channel=SimpleNamespace(id=canale), expires_at=scade,
        inviter=SimpleNamespace(id=creatore) if creatore else None, delete=AsyncMock(),
    )


# ------------------------------------------------------------------ logica
def test_da_cancellare_un_solo_criterio_e_protetti():
    v = [InvitoVisto("a", 0, 0, 1, None, 5), InvitoVisto("b", 3, 0, 2, None, 5), InvitoVisto("c", 9, 0, 2, None, 5)]
    assert [i.codice for i in da_cancellare(v, codice="b")] == ["b"]
    assert [i.codice for i in da_cancellare(v, usi_sotto=4)] == ["a", "b"]
    assert [i.codice for i in da_cancellare(v, canale_id=2)] == ["b", "c"]
    assert [i.codice for i in da_cancellare(v, usi_sotto=4, protetti={"a"})] == ["b"]
    assert da_cancellare(v) == [] and da_cancellare(v, codice="a", usi_sotto=1) == []


def test_righe_e_pagine():
    assert [pagine(n) for n in (0, 10, 11)] == [1, 1, 2]
    i = da_invito(_inv("xyz", 2, 7, max_usi=5, scade=datetime(2030, 1, 1, tzinfo=timezone.utc)))
    riga = riga_codice(i, "Twitch")
    assert "`xyz`" in riga and "**Twitch**" in riga and "2/5" in riga and "<#7>" in riga and "<t:" in riga


# ------------------------------------------------------------------ archivio
@pytest.fixture
def extra(clean_db):
    return InvitiExtraRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_etichette_salvate_aggiornate_e_tolte(extra):
    await extra.imposta_etichetta(G, "abc", "Twitch", 9)
    await extra.imposta_etichetta(G, "abc", "YouTube", None)
    assert await extra.etichette_di(G, ["abc", "zzz"]) == {"abc": ("YouTube", None)}
    assert await extra.etichette_di(G, []) == {}
    assert await extra.togli_etichetta(G, "abc") is True and await extra.togli_etichetta(G, "abc") is False


@pytest.mark.asyncio
async def test_tetto_etichette(extra, monkeypatch):
    import core.repositories.inviti_extra_repo as m

    monkeypatch.setattr(m, "MAX_ETICHETTE_SERVER", 2)
    await extra.imposta_etichetta(G, "aa", "1", None)
    await extra.imposta_etichetta(G, "bb", "2", None)
    with pytest.raises(TroppeEtichette):
        await extra.imposta_etichetta(G, "cc", "3", None)
    await extra.imposta_etichetta(G, "aa", "uno", None)  # aggiornare non è nuovo


# ------------------------------------------------------------------ cog
class _Scena:
    def __init__(self, monkeypatch, utente_alto=100):
        self.cog = modulo.InvitiCodiciCog(MagicMock())
        self.guild = fake_guild()
        self.guild.owner_id = 1
        self.guild.me.guild_permissions = discord.Permissions(manage_roles=True)
        self.guild.me.top_role = SimpleNamespace(position=10)
        self.repo = MagicMock()
        self.repo.imposta_etichetta = AsyncMock()
        self.repo.etichette_di = AsyncMock(return_value={})
        self.repo.togli_etichetta = AsyncMock()
        monkeypatch.setattr(modulo, "inviti_extra_repo", self.repo)
        db = MagicMock()
        db.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db)
        self.utente = fake_member(user_id=50)
        self.utente.top_role = SimpleNamespace(position=utente_alto)
        self.interazione = fake_interaction(guild=self.guild, user=self.utente)


def _ruolo(posizione, gestito=False, default=False):
    r = MagicMock(spec=discord.Role)
    r.position, r.managed, r.id = posizione, gestito, 77
    r.is_default = MagicMock(return_value=default)
    return r


@pytest.mark.asyncio
async def test_ruolo_non_dato_se_piu_alto_del_bot_o_di_chi_configura(monkeypatch):
    s = _Scena(monkeypatch, utente_alto=5)
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(3)) is None
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(5)) == "invites_ruolo_troppo_alto_per_te"
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(10)) == "invites_ruolo_troppo_alto_per_il_bot"
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(1, gestito=True)) == "invites_ruolo_non_valido"
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(1, default=True)) == "invites_ruolo_non_valido"
    s.guild.me.guild_permissions = discord.Permissions()
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(1)) == "invites_ruolo_troppo_alto_per_il_bot"


@pytest.mark.asyncio
async def test_proprietario_puo_dare_ruoli_alti_ma_non_piu_del_bot(monkeypatch):
    s = _Scena(monkeypatch, utente_alto=1)
    s.guild.owner_id = s.utente.id
    assert await modulo.motivo_ruolo_non_dato(s.interazione, _ruolo(9)) is None


@pytest.mark.asyncio
async def test_elenco_codici_di_un_membro(monkeypatch):
    s = _Scena(monkeypatch)
    inviti = [_inv("a", creatore=5), _inv("b", creatore=6), *[_inv(f"c{n}", creatore=5) for n in range(11)]]
    s.guild.invites = AsyncMock(return_value=inviti)
    s.repo.etichette_di = AsyncMock(return_value={"a": ("Twitch", None)})
    membro = fake_member(user_id=5)
    await s.cog.codici.callback(s.cog, s.interazione, membro, 1)
    testo = s.interazione.followup.send.await_args.args[0]
    assert "12" in testo and "pagina 1 di 2" in testo and "**Twitch**" in testo and "`b`" not in testo
    assert testo.count("`") // 2 == 10  # dieci righe per pagina


@pytest.mark.asyncio
async def test_elenco_senza_permesso_o_vuoto(monkeypatch):
    s = _Scena(monkeypatch)
    s.guild.invites = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no"))
    await s.cog.codici.callback(s.cog, s.interazione, fake_member(user_id=5), 1)
    s.guild.invites = AsyncMock(return_value=[])
    i2 = fake_interaction(guild=s.guild, user=s.utente)
    await s.cog.codici.callback(s.cog, i2, fake_member(user_id=5), 1)
    assert i2.followup.send.await_count == 1


@pytest.mark.asyncio
async def test_etichetta_rifiuta_codice_sconosciuto_e_ruolo_alto(monkeypatch):
    s = _Scena(monkeypatch, utente_alto=5)
    s.guild.invites = AsyncMock(return_value=[_inv("abc")])
    with patch.object(modulo.invite_tracker, "codici", return_value=set()):
        await s.cog.etichetta.callback(s.cog, s.interazione, "nope", "Nome", None)
        s.repo.imposta_etichetta.assert_not_awaited()
        await s.cog.etichetta.callback(s.cog, s.interazione, "abc", "Nome", _ruolo(8))
        s.repo.imposta_etichetta.assert_not_awaited()
        await s.cog.etichetta.callback(s.cog, s.interazione, "https://discord.gg/abc", "Nome", _ruolo(3))
    s.repo.imposta_etichetta.assert_awaited_once_with(s.guild.id, "abc", "Nome", 77)


@pytest.mark.asyncio
async def test_crea_invito_senza_scadenza_e_registra_nel_tracker(monkeypatch):
    s = _Scena(monkeypatch)
    canale = fake_text_channel(40)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=True))
    canale.create_invite = AsyncMock(return_value=SimpleNamespace(code="nuovo"))
    s.guild.invites = AsyncMock(return_value=[])
    with patch.object(modulo.invite_tracker, "registra_invito") as reg:
        await s.cog.crea.callback(s.cog, s.interazione, canale, 3, "Twitch", None)
    kw = canale.create_invite.await_args.kwargs
    assert kw["max_age"] == 0 and kw["max_uses"] == 3 and kw["unique"] is True
    reg.assert_called_once()
    s.repo.imposta_etichetta.assert_awaited_once_with(s.guild.id, "nuovo", "Twitch", None)
    assert "discord.gg/nuovo" in s.interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_crea_si_ferma_al_tetto_di_1000_e_senza_permessi(monkeypatch):
    s = _Scena(monkeypatch)
    canale = fake_text_channel(40)
    canale.permissions_for = MagicMock(return_value=discord.Permissions(create_instant_invite=True))
    canale.create_invite = AsyncMock()
    s.guild.invites = AsyncMock(return_value=[_inv(f"c{n}") for n in range(1000)])
    await s.cog.crea.callback(s.cog, s.interazione, canale, 0, None, None)
    canale.create_invite.assert_not_awaited()
    canale.permissions_for = MagicMock(return_value=discord.Permissions())
    await s.cog.crea.callback(s.cog, fake_interaction(guild=s.guild, user=s.utente), canale, 0, None, None)
    canale.create_invite.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancella_chiede_un_solo_criterio_poi_conferma(monkeypatch):
    s = _Scena(monkeypatch)
    s.guild.invites = AsyncMock(return_value=[_inv("a", 0), _inv("b", 9)])
    with patch.object(modulo.invite_links_repo, "codici_personali", AsyncMock(return_value=set())):
        await s.cog.cancella.callback(s.cog, s.interazione, None, None, None)
        s.interazione.response.defer.assert_not_awaited()
        await s.cog.cancella.callback(s.cog, s.interazione, "a", 3, None)
        s.interazione.response.defer.assert_not_awaited()
        await s.cog.cancella.callback(s.cog, s.interazione, None, 3, None)
    vista = s.interazione.followup.send.await_args.kwargs["view"]
    assert vista.codici == ["a"]


@pytest.mark.asyncio
async def test_cancella_a_uno_al_secondo_si_ferma_al_primo_rifiuto(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "PAUSA_CANCELLAZIONE", 0)
    a, b, c = _inv("a"), _inv("b"), _inv("c")
    b.delete = AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no"))
    s.guild.invites = AsyncMock(return_value=[a, b, c])
    fatti, fermato = await s.cog.cancella_a_uno_al_secondo(s.guild, ["a", "b", "c", "gia-sparito"], 50)
    assert (fatti, fermato) == (1, True)
    c.delete.assert_not_awaited()
    s.repo.togli_etichetta.assert_awaited_once_with(s.guild.id, "a")


@pytest.mark.asyncio
async def test_la_conferma_la_usa_solo_chi_ha_dato_il_comando(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    s = _Scena(monkeypatch)
    vista = modulo.ConfermaCancellazione(s.cog, 50, s.guild, ["a"])
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=51))) is False
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=50))) is True


@pytest.mark.asyncio
async def test_albero_dei_comandi():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await invites.setup(bot)
    await modulo.setup(bot)
    for nome in ("codici", "etichetta", "crea", "cancella"):
        assert comando_nel_gruppo("admin-inviti", nome)
    assert comando_nel_gruppo("level", "inviti codici")


# ------------------------------------------------------------------ ruolo dal codice all'ingresso
@pytest.mark.asyncio
async def test_ruolo_dal_codice_solo_se_riconosciuto_e_dopo_la_verifica():
    cog = invites.InvitesCog(MagicMock())
    guild = fake_guild()
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)
    guild.me.top_role = SimpleNamespace(position=10)
    ruolo = _ruolo(3)
    guild.get_role = MagicMock(return_value=ruolo)
    m = fake_member(user_id=9)
    m.guild, m.pending, m.roles = guild, False, []
    m.add_roles = AsyncMock()
    with patch.object(invites.inviti_extra_repo, "etichette_di", AsyncMock(return_value={"abc": ("T", 77)})):
        await cog._ruolo_dal_codice(m, None)  # codice non riconosciuto
        m.add_roles.assert_not_awaited()
        m.pending = True
        await cog._ruolo_dal_codice(m, "abc")  # verifica non ancora passata
        m.add_roles.assert_not_awaited()
        m.pending = False
        await cog._ruolo_dal_codice(m, "abc")
        m.add_roles.assert_awaited_once()
        ruolo.position = 10  # più in alto del bot: niente
        m.add_roles.reset_mock()
        await cog._ruolo_dal_codice(m, "abc")
        m.add_roles.assert_not_awaited()
