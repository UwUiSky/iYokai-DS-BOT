"""
tests/test_admin_mentions_logic.py
=====================================
D12 / M 10.6: ping di ruolo nei testi dell'admin solo con "Menziona tutti";
@everyone e @here mai. Più gli elenchi entro i limiti (M 10.5, 10.12).
"""

import discord

from core.admin_mentions_logic import (
    menzioni_ammesse,
    puo_pingare_ruoli,
    taglia_messaggio,
    utente_puo_pingare_ruoli,
)
from core.lista_limiti_logic import dividi_in_blocchi, righe_entro_limite


def test_chi_ha_menziona_tutti_puo_pingare_i_ruoli():
    assert puo_pingare_ruoli(discord.Permissions(mention_everyone=True))
    assert puo_pingare_ruoli(discord.Permissions(administrator=True))
    assert not puo_pingare_ruoli(discord.Permissions(manage_guild=True))
    assert not puo_pingare_ruoli(None)


def test_ruoli_attivi_ma_everyone_sempre_muto():
    m = menzioni_ammesse(True)
    assert m.roles is True
    assert m.everyone is False
    assert menzioni_ammesse(False).roles is False


def test_gli_utenti_scritti_dall_admin_pingano():
    assert menzioni_ammesse(False).users is True
    assert menzioni_ammesse(True).users is True


def test_regola_d12_in_un_punto_solo():
    from tests.support.discord_fakes import fake_member

    con = fake_member(guild_permissions=discord.Permissions(mention_everyone=True))
    senza = fake_member(guild_permissions=discord.Permissions(manage_guild=True))
    assert utente_puo_pingare_ruoli(con) is True
    assert utente_puo_pingare_ruoli(senza) is False
    assert utente_puo_pingare_ruoli(discord.Object(id=1)) is False  # non è un Member


def test_taglia_messaggio_a_2000():
    assert taglia_messaggio("a" * 2000) == "a" * 2000
    tagliato = taglia_messaggio("a" * 2500)
    assert len(tagliato) == 2000 and tagliato.endswith("…")


def test_righe_entro_limite_non_supera_mai_il_limite():
    righe = [f"riga {i} " + "x" * 60 for i in range(200)]
    testo, omesse = righe_entro_limite(righe, 4000)
    assert len(testo) <= 4000
    assert omesse > 0 and f"altre {omesse}" in testo
    assert righe_entro_limite(["a", "b"], 100) == ("a\nb", 0)


def test_pagine_ognuna_entro_il_limite_e_nessuna_riga_persa():
    righe = [f"riga {i} " + "x" * 80 for i in range(120)]
    pagine = dividi_in_blocchi(righe, 1900)
    assert all(len(p) <= 1900 for p in pagine)
    assert "\n".join(pagine).split("\n") == righe
    assert dividi_in_blocchi([], 1900) == [""]
    assert len(dividi_in_blocchi(["z" * 5000], 1900)[0]) == 1900
