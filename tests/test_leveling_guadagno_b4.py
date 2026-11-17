"""
tests/test_leveling_guadagno_b4.py
==================================
#124 B4 (LIV-010, 011, 012, 014, 015, 016) e voci del catalogo già in codice che qui trovano il loro
codice con una prova: LIV-022, 023, 024, 025, 028, 029, 030, 040, 049, 050, 052, 073.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.leveling.leveling as modulo
from cogs.leveling.guadagno import GuadagnoCog
from core.leveling_logic import (
    ConfigLivelli,
    LevelingSettings,
    contesto_con_xp,
    deve_annunciare,
    is_eligible_for_voice_xp,
    scegli_premi,
)
from core.rank_card_image import ALTEZZA, COLORE_DI_BASE, LARGHEZZA, DatiRankCard, render_rank_card
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_member, fake_message, fake_text_channel
from tests.test_leveling_guadagno_b3 import _comando, _inter, _scelta, _testo, ambiente  # noqa: F401
from tests.test_leveling_settings import cog_xp  # noqa: F401

GUILD = 100


# ---------------------------------------------------------------- LIV-011 e 012
def test_liv011_la_soglia_di_persone_nel_canale():
    assert is_eligible_for_voice_xp(False, False, 1)  # di base: serve un'altra persona
    assert not is_eligible_for_voice_xp(False, False, 0)
    assert not is_eligible_for_voice_xp(False, False, 2, min_persone=4)
    assert is_eligible_for_voice_xp(False, False, 3, min_persone=4)
    assert is_eligible_for_voice_xp(False, False, 0, min_persone=1)  # soglia 1: anche da solo


def test_liv012_anti_farm_spento_non_guarda_l_assordato_ma_l_afk_resta_escluso():
    assert not is_eligible_for_voice_xp(True, False, 1)
    assert is_eligible_for_voice_xp(True, False, 1, anti_farm=False)
    assert not is_eligible_for_voice_xp(False, True, 5, anti_farm=False)


@pytest.mark.asyncio
async def test_liv011_012_il_comando_salva_e_rifiuta_chi_non_gestisce(ambiente):  # noqa: F811
    cog = ambiente
    cmd = _comando(cog, "admin-livelli guadagno vocale")
    senza = _inter(permessi=discord.Permissions.none())
    await cmd.callback(cog, senza, 5, False)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.voce_min_persone == 2
    inter = _inter()
    await cmd.callback(cog, inter, 5, False)
    i = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.voce_min_persone, i.anti_farm) == (5, False)
    assert "5" in _testo(inter)


@pytest.mark.asyncio
async def test_liv011_soglia_fuori_dai_limiti_e_rifiutata_dall_archivio(ambiente):  # noqa: F811
    with pytest.raises(ValueError):
        await leveling_settings_repo.set_options(GUILD, voce_min_persone=11)
    with pytest.raises(ValueError):
        await leveling_settings_repo.set_options(GUILD, voce_min_persone=0)


# ---------------------------------------------------------------- LIV-014, 015, 016
def test_liv014_015_016_tipo_di_canale():
    thread = MagicMock(spec=discord.Thread)
    thread.parent = MagicMock(spec=discord.TextChannel)
    post = MagicMock(spec=discord.Thread)
    post.parent = MagicMock(spec=discord.ForumChannel)
    assert modulo.tipo_di_canale(thread) == "thread"
    assert modulo.tipo_di_canale(post) == "forum"
    assert modulo.tipo_di_canale(MagicMock(spec=discord.VoiceChannel)) == "chat_vocale"
    assert modulo.tipo_di_canale(MagicMock(spec=discord.StageChannel)) == "chat_vocale"
    assert modulo.tipo_di_canale(fake_text_channel()) == "testo"


def test_liv014_di_base_tutti_i_contesti_danno_xp():
    i = LevelingSettings()
    assert all(contesto_con_xp(i, t) for t in ("thread", "forum", "chat_vocale", "testo"))
    assert not contesto_con_xp(LevelingSettings(xp_forum=False), "forum")


def _msg_in(canale):
    m = fake_message(author=fake_member(), channel=canale, content="ciao")
    m.type = discord.MessageType.default
    m.attachments = []
    canale.send = AsyncMock()
    m.author.send = AsyncMock()
    return m


@pytest.mark.asyncio
@pytest.mark.parametrize("campo,classe,parent", [
    ("xp_thread", discord.Thread, discord.TextChannel),
    ("xp_forum", discord.Thread, discord.ForumChannel),
    ("xp_chat_vocale", discord.VoiceChannel, None),
])
async def test_liv014_015_016_con_l_interruttore_spento_non_da_xp(cog_xp, campo, classe, parent):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    canale = MagicMock(spec=classe)
    canale.id, canale.category_id = 4242, None
    if parent:
        canale.parent = MagicMock(spec=parent)
        canale.parent.id = 4243
        canale.parent_id = 4243
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(**{campo: False}))
    await cog.on_message(_msg_in(canale))
    repo_xp.add_text_xp.assert_not_awaited()
    config["valore"] = ConfigLivelli()
    await cog.on_message(_msg_in(canale))
    repo_xp.add_text_xp.assert_awaited_once()


@pytest.mark.asyncio
async def test_liv014_015_016_il_comando_salva(ambiente):  # noqa: F811
    cog = ambiente
    await _comando(cog, "admin-livelli guadagno contesti").callback(cog, _inter(), False, None, False)
    i = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.xp_thread, i.xp_forum, i.xp_chat_vocale) == (False, True, False)


# ---------------------------------------------------------------- voci già in codice
def test_liv022_023_ruolo_escluso_e_tolto_dall_elenco():
    c = ConfigLivelli(ruoli_esclusi=frozenset({3}))
    assert c.e_escluso([1], [3])
    assert not ConfigLivelli().e_escluso([1], [3])  # tolto dall'elenco: torna a dare XP


def test_liv024_025_moltiplicatori_per_ruolo_e_per_canale():
    c = ConfigLivelli(mult_canali={1: 2.0}, mult_ruoli={5: 1.5})
    assert c.moltiplicatore([1], [5]) == 2.5
    assert c.moltiplicatore([2], [5]) == 1.5


def test_liv028_029_030_modi_dell_annuncio():
    assert not deve_annunciare(5, LevelingSettings(levelup_mode="spento"), False)
    for modo in ("dm", "canale_scelto", "canale_corrente"):
        assert deve_annunciare(5, LevelingSettings(levelup_mode=modo), False)


def test_liv040_premi_solo_il_ruolo_piu_alto():
    class P:
        def __init__(self, livello, ruolo):
            self.level_threshold, self.role_id = livello, ruolo

    assert scegli_premi([P(5, 1), P(10, 2)], "sostituisci") == ([2], [1])


def test_liv049_050_052_la_card_e_un_immagine_con_il_colore_scelto_e_lo_sfondo_dell_utente():
    sfondo = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 10, 10)).save(sfondo, "PNG")
    dati = DatiRankCard("Yokai", 3, 10, 100, 130, 1, 5, colore="#FF8800")
    png = render_rank_card(dati, None, sfondo.getvalue())
    assert Image.open(io.BytesIO(png)).size == (LARGHEZZA, ALTEZZA)
    assert render_rank_card(DatiRankCard("Yokai", 3, 10, 100, 130, 1, 5, colore=COLORE_DI_BASE), None) != png


def test_liv073_il_riepilogo_mostra_anche_come_si_guadagna_xp():
    config = ConfigLivelli(impostazioni=LevelingSettings(
        formula="lineare", xp_modo="parola", prefissi_ignorati=("!", "a`b")))
    embed = modulo._embed_impostazioni(config)
    campo = next(f for f in embed.fields if f.name == "Come si guadagna XP")
    assert "lineare" in campo.value and "a parola" in campo.value
    assert "`!`" in campo.value and "`ab`" in campo.value
    assert len(embed) <= 6000
