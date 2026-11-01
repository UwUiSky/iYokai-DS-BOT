"""
tests/test_lore_nomi.py
=======================
Nomi a tema (§25.69) e passo del tema nel primo avvio (§25.47): logica pura e punto unico `imposta_lore` su database vero.
"""

import pytest

from core import ai_impostazioni
from core import lore_nomi_logic as logica
from core.ai_testi_logic import TEMI
from core.config_schema import ImpostazioneNonValida
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo

G = 8501


def test_ogni_tema_ha_i_nomi_e_rispetta_il_tetto():
    assert set(logica.NOMI) == set(TEMI)
    for n in logica.NOMI.values():
        assert all(len(x) <= logica.MAX_NOME for x in (n.moneta, n.punti, n.prefisso))
        assert len(n.titoli) == 5


def test_titolo_livello_per_fascia_e_senza_tema():
    assert logica.titolo_livello(None, None, 12) == "Livello 12"
    assert logica.titolo_livello("pirati", "Grado", 3) == "Grado 3: Mozzo"
    assert logica.titolo_livello("pirati", "Grado", 25) == "Grado 25: Nostromo"
    assert logica.titolo_livello("pirati", None, 999) == "Livello 999: Re dei pirati"


def test_nome_pulito_toglie_menzioni_e_formattazione():
    assert logica.nome_pulito("  @everyone **Oro** ") == "everyone Oro"
    assert logica.nome_pulito("@@") is None and logica.nome_pulito(None) is None
    assert len(logica.nome_pulito("x" * 50)) == 20


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_repo, leveling_settings_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    return clean_db


async def test_imposta_lore_con_nomi_cambia_moneta_punti_titoli(repo):
    nomi = await ai_impostazioni.imposta_lore(G, "cyberpunk", "pioggia", nomi_a_tema=True)
    assert nomi["moneta"] == "Crediti"
    cfg = await ai_repo.get_config(G)
    assert (cfg.lore_tema, cfg.nome_punti, cfg.prefisso_titolo) == ("cyberpunk", "Bit", "Livello neon")
    assert (await leveling_settings_repo.get_config(G)).impostazioni.currency_name == "Crediti"


async def test_imposta_lore_senza_nomi_non_tocca_la_moneta_e_nessuno_toglie(repo):
    assert await ai_impostazioni.imposta_lore(G + 1, "horror") == {}
    assert (await leveling_settings_repo.get_config(G + 1)).impostazioni.currency_name == "coin"
    await ai_impostazioni.imposta_lore(G + 1, "horror", nomi_a_tema=True)
    await ai_impostazioni.imposta_lore(G + 1, None)
    cfg = await ai_repo.get_config(G + 1)
    assert (cfg.lore_tema, cfg.nome_punti, cfg.prefisso_titolo) == (None, None, None)
    with pytest.raises(ImpostazioneNonValida):
        await ai_impostazioni.imposta_lore(G + 1, "boh")


async def test_passo_del_tema_si_propone_solo_senza_tema_e_salva_la_scelta(repo):
    from cogs.ai import _lore_setup
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

    g = G + 2
    i = fake_interaction(guild=fake_guild(g), user=fake_member(1))
    i.guild_id = g
    assert await _lore_setup.proponi_tema(i) is True
    vista = i.followup.send.call_args.kwargs["view"]
    menu = next(c for c in vista.children if isinstance(c, _lore_setup._ScegliTema))
    scelta = fake_interaction(guild=fake_guild(g), user=fake_member(1))
    scelta.guild_id = g
    from unittest.mock import patch

    with patch.object(type(menu), "values", ["horror"]):
        await menu.callback(scelta)
    assert (await ai_repo.get_config(g)).lore_tema == "horror"
    again = fake_interaction(guild=fake_guild(g), user=fake_member(1))
    again.guild_id = g
    assert await _lore_setup.proponi_tema(again) is False
