"""
tests/test_global_ban_117.py
============================
Ban globale, catalogo #117 e difetti trovati leggendo:
- SIC-046  due interruttori separati: "invia" e "ricevi";
- un appello accolto toglie anche i ban propagati agli altri server
  (prima l'utente restava bannato altrove);
- il registro delle propagazioni non conserva gli ID per sempre.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.global_ban as modulo
from core.repositories.global_ban_repo import global_ban_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

USER = 900000900


class _Ban:
    def __init__(self, reason):
        self.reason = reason


def _server(guild_id: int, ban_reason: str | None = "Ban globale — x") -> MagicMock:
    s = fake_guild(guild_id=guild_id, name=f"S{guild_id}")
    s.ban = AsyncMock()
    s.unban = AsyncMock()
    s.fetch_ban = AsyncMock(return_value=_Ban(ban_reason))
    return s


@pytest.fixture
def ambiente(clean_db, monkeypatch):
    monkeypatch.setattr(global_ban_repo, "_pool_provider", lambda: clean_db)
    attivi: set[int] = set()
    finto = MagicMock()
    finto.is_module_active_for_guild = AsyncMock(side_effect=lambda gid, _m: gid in attivi)
    finto.set_module_active_for_guild = AsyncMock(
        side_effect=lambda gid, _m, valore, changed_by=None: attivi.add(gid) if valore else attivi.discard(gid)
    )
    monkeypatch.setattr(modulo, "db", finto)
    monkeypatch.setattr(modulo, "premium_sbloccato", AsyncMock(return_value=True))
    monkeypatch.setattr(modulo, "PAUSA_TRA_I_BAN", 0)
    return attivi


def _bot(*server):
    bot = MagicMock()
    bot.guilds = list(server)
    bot.get_guild = lambda gid: next((s for s in server if s.id == gid), None)
    return bot


async def test_chi_non_riceve_non_viene_bannato_e_chi_non_invia_non_propaga(ambiente):
    sorgente, riceve, non_riceve = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    await global_ban_repo.set_direction(3, send=True, receive=False)
    propagati = await modulo.propagate_ban(_bot(sorgente, riceve, non_riceve), sorgente, USER, "x")
    assert propagati == [2]
    non_riceve.ban.assert_not_awaited()

    await global_ban_repo.set_direction(1, send=False, receive=True)
    riceve.ban.reset_mock()
    assert await modulo.propagate_ban(_bot(sorgente, riceve, non_riceve), sorgente, USER, "x") == []
    riceve.ban.assert_not_awaited()


async def test_solo_ricevere_e_permesso(ambiente):
    sorgente, riceve = _server(1), _server(2)
    ambiente.update({1, 2})
    await global_ban_repo.set_direction(2, send=False, receive=True)
    assert await modulo.propagate_ban(_bot(sorgente, riceve), sorgente, USER, "x") == [2]
    # ...e il server che riceve soltanto non propaga i propri ban.
    riceve.ban.reset_mock()
    sorgente.ban.reset_mock()
    assert await modulo.propagate_ban(_bot(sorgente, riceve), riceve, USER, "x") == []
    sorgente.ban.assert_not_awaited()


async def test_enable_salva_le_direzioni_e_rifiuta_di_spegnerle_tutte(ambiente):
    cog = modulo.GlobalBanCog(bot=MagicMock())
    guild = fake_guild(guild_id=7)
    nessuna = fake_interaction(guild=guild)
    await cog.enable.callback(cog, nessuna, False, False)
    assert "almeno una" in nessuna.response.send_message.call_args.args[0]
    assert 7 not in ambiente

    solo_ricevo = fake_interaction(guild=guild)
    await cog.enable.callback(cog, solo_ricevo, False, True)
    assert await global_ban_repo.get_direction(7) == (False, True)
    assert 7 in ambiente


async def test_senza_riga_le_direzioni_sono_entrambe_attive(ambiente):
    assert await global_ban_repo.get_direction(12345) == (True, True)


async def test_revoca_toglie_il_ban_solo_dove_era_nostro(ambiente):
    sorgente = _server(1)
    nostro = _server(2, "Ban globale — Spam trap")
    ripreso = _server(3, "Bannato a mano dallo staff")
    ambiente.update({1, 2, 3})
    bot = _bot(sorgente, nostro, ripreso)
    assert await modulo.propagate_ban(bot, sorgente, USER, "x") == [2, 3]

    assert await modulo.revoca_ban_propagati(bot, 1, USER) == 1
    nostro.unban.assert_awaited_once()
    ripreso.unban.assert_not_awaited()
    # Una seconda volta non fa niente.
    assert await modulo.revoca_ban_propagati(bot, 1, USER) == 0
    nostro.unban.assert_awaited_once()


async def test_revoca_con_server_sparito_o_errore_non_si_ferma(ambiente):
    sorgente, rotto, buono = _server(1), _server(2, "Ban globale — x"), _server(3, "Ban globale — x")
    ambiente.update({1, 2, 3})
    bot = _bot(sorgente, rotto, buono)
    await modulo.propagate_ban(bot, sorgente, USER, "x")
    rotto.unban.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    assert await modulo.revoca_ban_propagati(bot, 1, USER) == 1
    buono.unban.assert_awaited_once()


async def test_il_registro_toglie_le_voci_vecchie(ambiente, clean_db):
    await clean_db.execute(
        "INSERT INTO global_ban_log (source_guild_id, target_guild_id, user_id, created_at) "
        "VALUES (1, 2, 3, now() - interval '400 days')"
    )
    await global_ban_repo.log_propagation(1, 2, 4, "x")
    righe = await clean_db.fetch("SELECT user_id FROM global_ban_log")
    assert [r["user_id"] for r in righe] == [4]


# ---------------------------------------------------------------- SIC-044
async def test_controlla_utente_conta_i_server_senza_dirne_i_nomi(ambiente):
    sorgente_a, sorgente_b, riceve = _server(1), _server(2), _server(3)
    ambiente.update({1, 2, 3})
    bot = _bot(sorgente_a, sorgente_b, riceve)
    await modulo.propagate_ban(bot, sorgente_a, USER, "x")
    await modulo.propagate_ban(bot, sorgente_b, USER, "x")

    cog = modulo.GlobalBanCog(bot)
    interazione = fake_interaction(guild=fake_guild(guild_id=3))
    utente = MagicMock(id=USER, mention=f"<@{USER}>")
    await cog.controlla.callback(cog, interazione, utente)

    testo = interazione.response.send_message.call_args.args[0]
    assert "2 server" in testo
    assert "S1" not in testo and "S2" not in testo  # niente nomi di altri server


async def test_controlla_utente_solo_per_chi_partecipa_alla_rete(ambiente):
    cog = modulo.GlobalBanCog(MagicMock())
    interazione = fake_interaction(guild=fake_guild(guild_id=3))
    await cog.controlla.callback(cog, interazione, MagicMock(id=555, mention="<@555>"))
    assert "partecipano" in interazione.response.send_message.call_args.args[0]


async def test_controlla_utente_mai_bannato(ambiente):
    ambiente.add(3)
    cog = modulo.GlobalBanCog(MagicMock())
    interazione = fake_interaction(guild=fake_guild(guild_id=3))
    await cog.controlla.callback(cog, interazione, MagicMock(id=555, mention="<@555>"))
    assert "nessun" in interazione.response.send_message.call_args.args[0].lower()
