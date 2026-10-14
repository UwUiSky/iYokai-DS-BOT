"""
tests/test_phishing_sic042.py
=============================
SIC-042: accorciatori di link e inviti a server per adulti, ognuno con un
interruttore proprio dentro il filtro phishing.
"""

from types import SimpleNamespace

import discord
import pytest

from cogs.automod import automod as automod_mod
from cogs.automod.automod import AutomodCog
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    MessageSignals,
    VIOLATION_ACCORCIATORI,
    evaluate_message_violations,
)
from core.phishing_logic import codici_invito, e_accorciatore, server_per_adulti
from core.repositories.automod_advanced_repo import _from_json, _to_json
from tests.test_automod_advanced_behavior import (  # noqa: F401
    GUILD_ID,
    _FakeGuild,
    _FakeMember,
    _FakeMessage,
    _FakeTextChannel,
    _salva_config,
    contesto,
)


@pytest.fixture(autouse=True)
def _cache_vuota():
    automod_mod._inviti_adulti.clear()
    yield
    automod_mod._inviti_adulti.clear()


def test_accorciatori_riconosciuti_anche_nei_sottodomini_e_whitelist_sblocca():
    assert e_accorciatore(["bit.ly"]) and e_accorciatore(["www.tinyurl.com"])
    assert not e_accorciatore(["example.com", "notbit.ly.example.org"])
    assert not e_accorciatore(["bit.ly"], consentiti=["bit.ly"])


def test_accorciatori_solo_se_l_interruttore_e_acceso():
    segnali = MessageSignals(content="guarda https://bit.ly/abc")
    assert evaluate_message_violations(segnali, AutomodAdvancedConfig()) == ()
    acceso = AutomodAdvancedConfig(phishing_accorciatori=True)
    assert evaluate_message_violations(segnali, acceso) == (VIOLATION_ACCORCIATORI,)
    in_whitelist = AutomodAdvancedConfig(
        phishing_accorciatori=True, anti_link=AntiLinkConfig(whitelist=("bit.ly",))
    )
    assert evaluate_message_violations(segnali, in_whitelist) == ()


def test_codici_invito_senza_doppioni_e_con_tetto():
    testo = "discord.gg/abc discord.gg/abc https://discord.com/invite/Xy-1 discordapp.com/invite/q2 discord.gg/zz9"
    assert codici_invito(testo) == ("abc", "Xy-1", "q2")


@pytest.mark.parametrize("livello,nome,atteso", [
    ("explicit", "Server qualsiasi", True),
    ("age_restricted", "", True),
    ("default", "NSFW Lounge", True),
    ("safe", "Amici del calcio", False),
    ("default", "Gaming Italia", False),
])
def test_server_per_adulti(livello, nome, atteso):
    assert server_per_adulti(livello, nome) is atteso


def test_le_due_scelte_sopravvivono_al_salvataggio():
    from core.repositories.automod_advanced_repo import _default_settings

    base = _default_settings(1)
    cfg = AutomodAdvancedConfig(phishing_accorciatori=True, phishing_inviti_adulti=True)
    letto = _from_json(1, _to_json(base.__class__(**{**base.__dict__, "config": cfg})))
    assert letto.config.phishing_accorciatori and letto.config.phishing_inviti_adulti


class _Bot:
    def __init__(self, inviti):
        self.inviti = inviti
        self.chiamate = []

    async def fetch_invite(self, codice, *, with_counts=True):
        self.chiamate.append(codice)
        esito = self.inviti[codice]
        if isinstance(esito, Exception):
            raise esito
        return esito


def _invito(guild_id, livello, nome="Server"):
    return SimpleNamespace(guild=SimpleNamespace(id=guild_id, nsfw_level=discord.NSFWLevel[livello], name=nome))


@pytest.mark.asyncio
async def test_invito_a_server_per_adulti_cancellato_una_sola_chiamata_per_codice(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(phishing_inviti_adulti=True))
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    bot = _Bot({"adulti": _invito(77, "explicit"), "pulito": _invito(78, "safe", "Calcio")})
    cog = AutomodCog(bot=bot)

    primo = _FakeMessage(guild, autore, canale, content="entra: discord.gg/adulti")
    await cog.on_message(primo)
    assert primo.deleted is True

    secondo = _FakeMessage(guild, autore, canale, content="di nuovo discord.gg/adulti")
    await cog.on_message(secondo)
    assert secondo.deleted is True
    assert bot.chiamate == ["adulti"]  # il secondo esito viene dalla memoria

    pulito = _FakeMessage(guild, autore, canale, content="discord.gg/pulito")
    await cog.on_message(pulito)
    assert pulito.deleted is False


@pytest.mark.asyncio
async def test_invito_del_proprio_server_o_scaduto_o_interruttore_spento_passa(contesto):
    guild = _FakeGuild(GUILD_ID)
    autore = _FakeMember(1, guild)
    canale = _FakeTextChannel(1)
    risposta = SimpleNamespace(status=404, reason="x")
    bot = _Bot({"mio": _invito(GUILD_ID, "explicit"), "morto": discord.NotFound(risposta, "nope")})
    cog = AutomodCog(bot=bot)

    await _salva_config(contesto, config=AutomodAdvancedConfig(phishing_inviti_adulti=True))
    for testo in ("discord.gg/mio", "discord.gg/morto"):
        m = _FakeMessage(guild, autore, canale, content=testo)
        await cog.on_message(m)
        assert m.deleted is False

    await _salva_config(contesto, config=AutomodAdvancedConfig())
    bot.inviti["altro"] = _invito(99, "explicit")
    m = _FakeMessage(guild, autore, canale, content="discord.gg/altro")
    await cog.on_message(m)
    assert m.deleted is False and "altro" not in bot.chiamate
