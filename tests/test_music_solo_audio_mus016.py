"""
tests/test_music_solo_audio_mus016.py
=====================================
MUS-016 (D121): `/admin-musica impostazioni solo-audio:sì` fa preferire, nelle ricerche per titolo, le versioni
senza «video ufficiale» nel titolo. Un link o una playlist non cambiano. Se i risultati sono tutti video, restano.
"""

from types import SimpleNamespace

from core import music_settings_logic as ms


def _t(titolo):
    return SimpleNamespace(title=titolo)


def test_i_video_vanno_in_fondo_senza_cambiare_l_ordine_del_resto():
    r = [_t("Canzone (Official Video)"), _t("Canzone [Official Audio]"), _t("Canzone live"), _t("Canzone - Video Ufficiale")]
    out = ms.preferisci_solo_audio(r)
    assert [t.title for t in out] == ["Canzone [Official Audio]", "Canzone live", "Canzone (Official Video)", "Canzone - Video Ufficiale"]


def test_se_sono_tutti_video_restano_come_sono():
    r = [_t("A (Official Music Video)"), _t("B (videoclip)")]
    assert ms.preferisci_solo_audio(r) == r


def test_non_tocca_parole_simili_dentro_altre():
    r = [_t("Videogame soundtrack"), _t("Altro")]
    assert ms.preferisci_solo_audio(r) == r  # «videogame» non è un video musicale


def test_audio_dichiarato_vince_su_video_nello_stesso_titolo():
    r = [_t("X (Official Video)"), _t("X (Audio Only)")]
    assert ms.preferisci_solo_audio(r)[0].title == "X (Audio Only)"


def test_lista_vuota_e_non_lista():
    assert ms.preferisci_solo_audio([]) == []
    marker = object()
    assert ms.preferisci_solo_audio(marker) is marker


async def test_l_impostazione_si_salva_e_si_legge(clean_db, monkeypatch):
    import core.database as dbm

    monkeypatch.setattr(dbm.db, "_pool", clean_db)
    await dbm.db.ensure_guild_exists(777001)
    assert (await ms.load_music_settings(dbm.db, 777001)).audio_only is False
    await ms.save_music_setting(dbm.db, 777001, ms.SETTING_AUDIO_ONLY, True, 1)
    assert (await ms.load_music_settings(dbm.db, 777001)).audio_only is True
