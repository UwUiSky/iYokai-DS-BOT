"""
tests/test_music_fonte_impostazione.py
======================================
Fonte preferita per server (B2, #126, D16): una chiave, un controllo nello schema, una voce
nella scheda del pannello, l'opzione di /admin-musica impostazioni e la riga del riepilogo.
"""

from types import SimpleNamespace

import pytest

from cogs.music.settings import MusicSettingsCog
from cogs.utility import config_history as storia
from core import config_impostazioni as ci
from core.music_settings_logic import (
    SETTING_DEFAULT_SEARCH,
    MusicSettings,
    load_music_settings,
    summary_lines,
)
from core.music_sources import FONTI_DI_RICERCA


class _Db:
    def __init__(self, valori=None):
        self.valori = dict(valori or {})

    async def get_guild_setting(self, guild_id, chiave, default=None):
        return self.valori.get(chiave, default)

    async def set_guild_setting(self, guild_id, chiave, valore, changed_by=None):
        if valore is None:
            self.valori.pop(chiave, None)
        else:
            self.valori[chiave] = valore


def test_la_chiave_e_nello_schema_e_nella_scheda_del_pannello():
    assert SETTING_DEFAULT_SEARCH == "music_default_search"
    tipo = storia.SETTINGS_SCHEMA[SETTING_DEFAULT_SEARCH]
    controllo, _ = storia.CONTROLLI_PER_TIPO[tipo]
    assert all(controllo(f) for f in FONTI_DI_RICERCA)
    assert not controllo("napster") and not controllo("") and not controllo(5)
    campo = next(c for c in ci.SCHEDE["music"] if c.chiave == SETTING_DEFAULT_SEARCH)
    assert campo.tipo == ci.SCELTA
    assert ci._scelte(tipo) == FONTI_DI_RICERCA


@pytest.mark.asyncio
async def test_lettura_con_default_valore_buono_e_valore_storto():
    assert (await load_music_settings(_Db(), 1)).default_search == ""
    assert (await load_music_settings(_Db({SETTING_DEFAULT_SEARCH: "soundcloud"}), 1)).default_search == "soundcloud"
    assert (await load_music_settings(_Db({SETTING_DEFAULT_SEARCH: "napster"}), 1)).default_search == ""


def test_il_riepilogo_dice_dove_si_cerca():
    testo = "\n".join(summary_lines(MusicSettings(default_search="soundcloud")))
    assert "SoundCloud" in testo
    assert "automatica" in "\n".join(summary_lines(MusicSettings())).lower()


class _Risposta:
    def __init__(self):
        self.inviati = []

    async def send_message(self, testo=None, **kw):
        self.inviati.append(testo)

    async def defer(self, **kw):
        pass


@pytest.mark.asyncio
async def test_il_comando_salva_e_toglie_la_fonte_preferita(monkeypatch):
    import cogs.music.settings as modulo

    db = _Db()
    monkeypatch.setattr(modulo, "db", db)
    cog = MusicSettingsCog(bot=None)

    def interazione():
        i = SimpleNamespace(guild=SimpleNamespace(id=900), user=SimpleNamespace(id=5), locale=None,
                            guild_id=900, response=_Risposta(), followup=_Risposta())
        i.followup.send = i.followup.send_message
        return i

    await cog.impostazioni.callback(cog, interazione(), ricerca_predefinita="deezer")
    assert db.valori[SETTING_DEFAULT_SEARCH] == "deezer"
    await cog.impostazioni.callback(cog, interazione(), ricerca_predefinita="automatica")
    assert SETTING_DEFAULT_SEARCH not in db.valori


def test_l_opzione_ha_le_scelte_e_il_comando_resta_sotto_25_opzioni():
    import inspect

    cb = MusicSettingsCog.impostazioni.callback
    scelte = cb.__discord_app_commands_param_choices__["ricerca_predefinita"]
    assert [c.value for c in scelte] == ["automatica", *FONTI_DI_RICERCA]
    assert len(cb.__discord_app_commands_param_description__["ricerca_predefinita"]) <= 100
    assert cb.__discord_app_commands_param_rename__["ricerca_predefinita"] == "ricerca-predefinita"
    assert len(inspect.signature(cb).parameters) - 2 <= 25
