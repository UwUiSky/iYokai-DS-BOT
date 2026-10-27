"""
tests/test_greetings_extra.py
=============================
Benvenuto: DM con testo suo, varianti a caso, reazioni sul messaggio (RUO-013, 017, 023, 025; #123).
"""

import random
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.greetings_logic import (
    MAX_REAZIONI,
    MAX_VARIANTI,
    analizza_reazioni,
    analizza_varianti,
    scegli_testo,
)
from core.repositories.greetings_repo import GreetingsRepository


def test_varianti_una_per_riga_senza_righe_vuote():
    varianti, errore = analizza_varianti("Ciao {user}\n\n  Benvenuto!  \n")
    assert errore is None
    assert varianti == ["Ciao {user}", "Benvenuto!"]


def test_varianti_oltre_il_tetto_rifiutate():
    righe = "\n".join(f"v{n}" for n in range(MAX_VARIANTI + 1))
    varianti, errore = analizza_varianti(righe)
    assert varianti == []
    assert errore is not None and str(MAX_VARIANTI) in errore


def test_variante_oltre_2000_caratteri_rifiutata():
    _, errore = analizza_varianti("x" * 2001)
    assert errore is not None


def test_reazioni_valide_e_senza_doppioni():
    reazioni, errore = analizza_reazioni("🎉 👋 🎉 <:ok:123456789012345678>")
    assert errore is None
    assert reazioni == ["🎉", "👋", "<:ok:123456789012345678>"]


def test_reazione_che_non_e_emoji_rifiutata():
    reazioni, errore = analizza_reazioni("🎉 ciao")
    assert reazioni == []
    assert errore is not None and "ciao" in errore


def test_reazioni_oltre_il_tetto_rifiutate():
    _, errore = analizza_reazioni(" ".join(["🎉", "👋", "😀", "😎", "🔥", "💜"][: MAX_REAZIONI + 1]))
    assert errore is not None


def test_scegli_testo_senza_varianti_da_il_principale():
    assert scegli_testo("principale", []) == "principale"


def test_scegli_testo_prende_tra_principale_e_varianti():
    visti = {scegli_testo("a", ["b", "c"], random.Random(n)) for n in range(40)}
    assert visti == {"a", "b", "c"}


@pytest.fixture
def repo(clean_db):
    return GreetingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_extra_default_e_salvataggio(repo):
    config = await repo.get_config(7)
    assert config.welcome_dm_message == ""
    assert config.welcome_variants == []
    assert config.welcome_reactions == []

    await repo.set_welcome_extra(7, "Ciao in DM", ["uno", "due"], ["🎉"], "Ban di {username}")
    config = await repo.get_config(7)
    assert config.welcome_dm_message == "Ciao in DM"
    assert config.welcome_variants == ["uno", "due"]
    assert config.welcome_reactions == ["🎉"]
    assert config.ban_message == "Ban di {username}"
    # Il resto della riga non si perde.
    await repo.set_welcome(7, enabled=True, channel_id=5, message="m", dm=False)
    assert (await repo.get_config(7)).welcome_variants == ["uno", "due"]


# ---- cog -----------------------------------------------------------------
from unittest.mock import create_autospec  # noqa: E402

import cogs.utility.greetings as modulo  # noqa: E402
from core.database import Database  # noqa: E402
from core.repositories.greetings_repo import GreetingsConfig  # noqa: E402
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel  # noqa: E402


def _prepara(monkeypatch, **extra):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)
    repo = create_autospec(GreetingsRepository, instance=True)
    repo.get_config.return_value = GreetingsConfig(
        guild_id=666, welcome_enabled=True, welcome_channel_id=5151,
        welcome_message="Principale {user}", welcome_dm=True,
        goodbye_enabled=False, goodbye_channel_id=None, goodbye_message="",
        boost_enabled=False, boost_channel_id=None, boost_message="", **extra,
    )
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    canale = fake_text_channel(channel_id=5151)
    messaggio = MagicMock(spec=discord.Message)
    messaggio.add_reaction = AsyncMock()
    canale.send.return_value = messaggio
    server = fake_guild()
    server.member_count = 10
    server.get_channel.return_value = canale
    membro = fake_member(user_id=42, bot=False)
    membro.guild = server
    return canale, membro, messaggio


async def test_dm_con_testo_suo_e_reazioni_sul_messaggio(monkeypatch):
    canale, membro, messaggio = _prepara(
        monkeypatch, welcome_dm_message="Solo per te {username}", welcome_reactions=["🎉", "👋"]
    )
    await modulo.GreetingsCog(bot=None).on_member_join(membro)
    assert membro.send.await_args.args[0].startswith("Solo per te")
    assert canale.send.await_args.args[0].startswith("Principale")
    assert [c.args[0] for c in messaggio.add_reaction.await_args_list] == ["🎉", "👋"]


async def test_variante_scelta_a_caso(monkeypatch):
    canale, membro, _ = _prepara(monkeypatch, welcome_variants=["Variante unica"])
    monkeypatch.setattr(modulo, "scegli_testo", lambda principale, varianti, rng=None: varianti[0])
    await modulo.GreetingsCog(bot=None).on_member_join(membro)
    assert canale.send.await_args.args[0] == "Variante unica"


async def test_reazione_che_fallisce_non_ferma_il_benvenuto(monkeypatch):
    canale, membro, messaggio = _prepara(monkeypatch, welcome_reactions=["🎉"])
    messaggio.add_reaction.side_effect = discord.HTTPException(MagicMock(status=400), "no")
    await modulo.GreetingsCog(bot=None).on_member_join(membro)
    membro.send.assert_awaited_once()


async def test_ban_pubblico_nel_canale_dell_addio(monkeypatch):
    canale, membro, _ = _prepara(monkeypatch, ban_message="{username} è stato bannato da {server}")
    repo = modulo.greetings_repo
    base = repo.get_config.return_value
    repo.get_config.return_value = GreetingsConfig(
        **{**base.__dict__, "goodbye_enabled": True, "goodbye_channel_id": 5151}
    )
    utente = MagicMock(spec=discord.User)
    utente.id, utente.name, utente.bot = 42, "Mario", False
    utente.display_name, utente.mention = "Mario", "<@42>"
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    assert canale.send.await_args.args[0].startswith("Mario è stato bannato")


async def test_ban_spento_senza_testo(monkeypatch):
    canale, membro, _ = _prepara(monkeypatch)
    utente = MagicMock(spec=discord.User)
    utente.bot = False
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    canale.send.assert_not_awaited()


def _config_base(**extra) -> GreetingsConfig:
    return GreetingsConfig(
        guild_id=666, welcome_enabled=True, welcome_channel_id=5151,
        welcome_message="Principale", welcome_dm=True,
        goodbye_enabled=True, goodbye_channel_id=5151, goodbye_message="",
        boost_enabled=False, boost_channel_id=None, boost_message="", **extra,
    )


def test_finestra_extra_etichette_entro_45_caratteri():
    """Discord rifiuta la finestra intera se un'etichetta supera 45 caratteri."""
    finestra = modulo.ExtraBenvenutoModal(_config_base())
    assert len(finestra.title) <= 45
    for campo in finestra.children:
        assert len(campo.label) <= 45, campo.label


async def test_durante_un_raid_niente_reazioni_sul_benvenuto(monkeypatch):
    canale, membro, messaggio = _prepara(monkeypatch, welcome_reactions=["🎉", "👋"])
    monkeypatch.setattr(modulo, "raid_in_corso", lambda _g: True)
    await modulo.GreetingsCog(bot=None).on_member_join(membro)
    canale.send.assert_awaited_once()
    messaggio.add_reaction.assert_not_awaited()


async def test_durante_un_raid_niente_messaggio_di_ban(monkeypatch):
    canale, membro, _ = _prepara(monkeypatch)
    modulo.greetings_repo.get_config.return_value = _config_base(ban_message="{username} bannato")
    monkeypatch.setattr(modulo, "raid_in_corso", lambda _g: True)
    utente = MagicMock(spec=discord.User)
    utente.id, utente.name, utente.bot = 42, "Mario", False
    utente.display_name, utente.mention = "Mario", "<@42>"
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    canale.send.assert_not_awaited()


async def _invia_finestra(monkeypatch, utente, **valori):
    repo = create_autospec(GreetingsRepository, instance=True)
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    finestra = modulo.ExtraBenvenutoModal(_config_base())
    for nome in ("dm", "varianti", "reazioni", "ban"):
        getattr(finestra, nome)._value = valori.get(nome, "")
    interazione = MagicMock()
    interazione.guild = fake_guild()
    interazione.guild.member_count = 10
    interazione.user = utente
    interazione.response.send_message = AsyncMock()
    await finestra.on_submit(interazione)
    return repo, interazione.response.send_message.await_args


async def test_finestra_rifiuta_ruolo_citato_senza_menziona_tutti(monkeypatch):
    repo, risposta = await _invia_finestra(
        monkeypatch, fake_member(user_id=1), varianti="Ciao <@&123>", ban="ok"
    )
    repo.set_welcome_extra.assert_not_awaited()
    assert "Menziona tutti" in risposta.args[0]


async def test_finestra_salva_i_quattro_campi(monkeypatch):
    repo, _ = await _invia_finestra(
        monkeypatch, fake_member(user_id=1), dm=" DM ", varianti="a\nb", reazioni="🎉", ban="Ban {username}"
    )
    repo.set_welcome_extra.assert_awaited_once()
    assert repo.set_welcome_extra.await_args.args[1:] == ("DM", ["a", "b"], ["🎉"], "Ban {username}")
