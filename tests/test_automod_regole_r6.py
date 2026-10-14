"""
tests/test_automod_regole_r6.py
===============================
Filtri AutoMod in più (#116): messaggi ripetuti (AMD-001), troppo corti
(AMD-004), link e menzioni nel tempo (AMD-006/007), testo di embed e inoltri
(AMD-019/020), tipi di file vietati (AMD-022), canali solo media o senza
allegati (AMD-023/024), azione kick (AMD-041).
"""

from types import SimpleNamespace

import discord
import pytest

from cogs.automod import automod as automod_module
from cogs.automod.automod import AutomodCog
from core.automod_advanced_logic import (
    AntiLinkConfig,
    AutomodAdvancedConfig,
    MessageSignals,
    RateFilterConfig,
    VIOLATION_CORTO,
    VIOLATION_ESTENSIONI,
    VIOLATION_RIPETUTI,
    VIOLATION_SENZA_ALLEGATI,
    VIOLATION_SOLO_MEDIA,
    estensione,
    evaluate_message_violations,
    pulisci_estensioni,
)
from core.automod_rate_tracker import AutomodRateTracker
from core.repositories.automod_advanced_repo import _default_settings, _from_json, _to_json
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
def _memoria_pulita(monkeypatch):
    monkeypatch.setattr(automod_module, "rate_tracker", AutomodRateTracker())
    automod_module._ultimi_testi.clear()
    yield
    automod_module._ultimi_testi.clear()


def _v(content="", **config):
    return evaluate_message_violations(MessageSignals(content=content), AutomodAdvancedConfig(**config))


def test_regole_pure():
    assert _v("ok", min_caratteri=3) == (VIOLATION_CORTO,)
    assert _v("ciao", min_caratteri=3) == ()
    assert evaluate_message_violations(
        MessageSignals(content="", attachment_count=1), AutomodAdvancedConfig(min_caratteri=3)
    ) == ()
    assert evaluate_message_violations(
        MessageSignals(content="x", ripetuti=4), AutomodAdvancedConfig(max_ripetuti=3)
    ) == (VIOLATION_RIPETUTI,)
    assert estensione("virus.EXE") == "exe" and estensione("senza") == ""
    assert pulisci_estensioni("exe, .BAT scr exe ../x") == ("exe", "bat", "scr")
    cfg = AutomodAdvancedConfig(estensioni_vietate=("exe",), canali_solo_media=(5,), canali_senza_allegati=(6,))
    assert evaluate_message_violations(MessageSignals(content="", attachment_count=1, nomi_allegati=("a.exe",)), cfg) == (
        VIOLATION_ESTENSIONI,
    )
    assert evaluate_message_violations(MessageSignals(content="ciao", channel_id=5), cfg) == (VIOLATION_SOLO_MEDIA,)
    assert evaluate_message_violations(MessageSignals(content="https://x.it", channel_id=5), cfg) == ()
    assert evaluate_message_violations(
        MessageSignals(content="", attachment_count=1, nomi_allegati=("a.png",), channel_id=6), cfg
    ) == (VIOLATION_SENZA_ALLEGATI,)


def test_le_scelte_sopravvivono_al_salvataggio():
    base = _default_settings(1)
    cfg = AutomodAdvancedConfig(
        max_ripetuti=3, min_caratteri=2, link_nel_tempo=RateFilterConfig(True, 4, 20),
        menzioni_nel_tempo=RateFilterConfig(True, 9, 60), controlla_embed=True, controlla_inoltrati=True,
        estensioni_vietate=("exe",), canali_solo_media=(5,), canali_senza_allegati=(6,),
    )
    letto = _from_json(1, _to_json(base.__class__(**{**base.__dict__, "config": cfg}))).config
    assert letto == cfg


_NERA = AntiLinkConfig(mode="blacklist", blacklist=("vietato.example",))


def _scena():
    guild = _FakeGuild(GUILD_ID)
    return guild, _FakeMember(1, guild), _FakeTextChannel(1)


@pytest.mark.asyncio
async def test_lo_stesso_testo_ripetuto_viene_cancellato_dopo_la_soglia(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(max_ripetuti=2))
    guild, autore, canale = _scena()
    cog = AutomodCog(bot=None)
    messaggi = [_FakeMessage(guild, autore, canale, content="COMPRA ORA") for _ in range(3)]
    messaggi.append(_FakeMessage(guild, autore, canale, content="altro"))
    for m in messaggi:
        await cog.on_message(m)
    assert [m.deleted for m in messaggi] == [False, False, True, False]


@pytest.mark.asyncio
async def test_link_contati_su_piu_messaggi(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(link_nel_tempo=RateFilterConfig(True, 2, 60)))
    guild, autore, canale = _scena()
    cog = AutomodCog(bot=None)
    primo = _FakeMessage(guild, autore, canale, content="https://a.it https://b.it")
    secondo = _FakeMessage(guild, autore, canale, content="https://c.it")
    await cog.on_message(primo)
    await cog.on_message(secondo)
    assert (primo.deleted, secondo.deleted) == (False, True)


@pytest.mark.asyncio
async def test_link_contati_con_un_tetto_per_messaggio(contesto):
    # Un messaggio con centinaia di link non deve riempire la coda in memoria.
    await _salva_config(contesto, config=AutomodAdvancedConfig(link_nel_tempo=RateFilterConfig(True, 500, 60)))
    guild, autore, canale = _scena()
    testo = " ".join(f"https://a{i}.it" for i in range(300))
    await AutomodCog(bot=None).on_message(_FakeMessage(guild, autore, canale, content=testo))
    coda = automod_module.rate_tracker._data.get((guild.id, autore.id, "links"))
    assert len(coda) == automod_module.MAX_EVENTI_PER_MESSAGGIO


@pytest.mark.asyncio
async def test_menzioni_contate_su_piu_messaggi(contesto):
    await _salva_config(contesto, config=AutomodAdvancedConfig(menzioni_nel_tempo=RateFilterConfig(True, 3, 60)))
    guild, autore, canale = _scena()
    cog = AutomodCog(bot=None)
    altri = [_FakeMember(i, guild) for i in range(10, 14)]
    primo = _FakeMessage(guild, autore, canale, content="ciao", mentions=altri[:2])
    secondo = _FakeMessage(guild, autore, canale, content="ciao", mentions=altri[2:])
    await cog.on_message(primo)
    await cog.on_message(secondo)
    assert (primo.deleted, secondo.deleted) == (False, True)


@pytest.mark.asyncio
async def test_embed_e_inoltri_letti_solo_se_scelti(contesto):
    guild, autore, canale = _scena()
    cog = AutomodCog(bot=None)
    embed = discord.Embed(title="Offerta", description="https://vietato.example/x")

    def _msg():
        m = _FakeMessage(guild, autore, canale, content="guarda")
        m.embeds = [embed]
        m.message_snapshots = [SimpleNamespace(content="https://vietato.example/a", embeds=[])]
        return m

    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_link=_NERA))
    spento = _msg()
    await cog.on_message(spento)
    assert spento.deleted is False

    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_link=_NERA, controlla_inoltrati=True))
    inoltro = _msg()
    await cog.on_message(inoltro)
    assert inoltro.deleted is True

    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_link=_NERA, controlla_embed=True))
    nell_embed = _msg()
    nell_embed.message_snapshots = []
    await cog.on_message(nell_embed)
    assert nell_embed.deleted is True


@pytest.mark.asyncio
async def test_azione_kick_con_dm_prima(contesto):
    ordine = []

    class _Espellibile(_FakeMember):
        async def kick(self, reason=None):
            ordine.append("kick")

        async def send(self, embed=None):
            ordine.append("dm")

    guild = _FakeGuild(GUILD_ID)
    guild.name = "Server"
    autore = _Espellibile(1, guild)
    await _salva_config(
        contesto, config=AutomodAdvancedConfig(min_caratteri=5), actions={VIOLATION_CORTO: ("delete", "kick")}
    )
    messaggio = _FakeMessage(guild, autore, _FakeTextChannel(1), content="ok")
    await AutomodCog(bot=None).on_message(messaggio)
    assert messaggio.deleted and ordine == ["dm", "kick"]


@pytest.mark.asyncio
async def test_anteprima_arrivata_con_modifica_controllata_solo_per_i_link(contesto):
    # L'anteprima di un link arriva con una modifica a testo invariato (AMD-019).
    guild, autore, canale = _scena()
    cog = AutomodCog(bot=None)

    def _coppia(embed):
        prima = _FakeMessage(guild, autore, canale, content="guarda")
        dopo = _FakeMessage(guild, autore, canale, content="guarda")
        prima.embeds, dopo.embeds = [], [embed]
        return prima, dopo

    await _salva_config(contesto, config=AutomodAdvancedConfig(anti_link=_NERA, controlla_embed=True))
    prima, dopo = _coppia(discord.Embed(title="x", description="https://vietato.example/a"))
    await cog.on_message_edit(prima, dopo)
    assert dopo.deleted is True

    # Il titolo dell'anteprima in maiuscolo o lungo non è dell'utente: niente caps né lunghezza.
    await _salva_config(contesto, config=AutomodAdvancedConfig(
        controlla_embed=True, max_lunghezza=10,
        anti_caps=automod_module.CapsFilterConfig(enabled=True, threshold_percent=50, min_length=3),
    ))
    titolo = discord.Embed(title="OFFERTA INCREDIBILE SOLO OGGI", description="testo lunghissimo " * 5)
    prima, dopo = _coppia(titolo)
    await cog.on_message_edit(prima, dopo)
    assert dopo.deleted is False
    nuovo = _FakeMessage(guild, autore, canale, content="guarda")
    nuovo.embeds, nuovo.message_snapshots = [titolo], []
    await cog.on_message(nuovo)
    assert nuovo.deleted is False


def test_solo_media_accetta_sticker_e_inoltri_con_immagine():
    cfg = AutomodAdvancedConfig(canali_solo_media=(5,))
    assert evaluate_message_violations(MessageSignals(content="", sticker_count=1, channel_id=5), cfg) == ()
    assert evaluate_message_violations(MessageSignals(content="", media_inoltrati=1, channel_id=5), cfg) == ()
    m = SimpleNamespace(message_snapshots=[SimpleNamespace(attachments=[object()], embeds=[])])
    assert automod_module._media_inoltrati(m) == 1
