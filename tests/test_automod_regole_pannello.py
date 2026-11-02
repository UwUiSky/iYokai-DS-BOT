"""
tests/test_automod_regole_pannello.py
=====================================
Pannello delle regole AutoMod: forma entro i limiti di Discord (5 righe, menu da 25, etichette, custom_id, embed
≤ 6000 nel caso peggiore), finestre con al massimo 5 campi, e il giro modifica -> salva sul database vero.
Funzioni coperte: SPEC §6 (AMD-029..056, AMD-067), D63
"""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import core.automod_regole_pannello as P
from core import automod_pannello_logic as L
from core import automod_regole_service as servizio
from core.automod_regole_logic import Condizioni, Contatore, Regola, Soglia, azioni_da_json
from core.repositories.automod_regole_repo import automod_regole_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

ETICHETTE = {k: f"Filtro {k}" for ks in L.FILTRI_PER_CATEGORIA.values() for k in ks}
GID = 666


def _vista():
    inter = fake_interaction(guild=fake_guild(guild_id=GID))
    inter.user = fake_member(user_id=5)
    inter.guild.me.guild_permissions = discord.Permissions.none()
    return P.PannelloRegole(inter, "it", ETICHETTE), inter


def _controlla_forma(vista, embed):
    righe = vista.to_components()
    assert 1 <= len(righe) <= 5
    for riga in righe:
        assert 1 <= len(riga["components"]) <= 5
        for c in riga["components"]:
            assert len(c.get("custom_id", "x")) <= 100
            assert len(c.get("label", "")) <= 45, c
            assert len(c.get("placeholder", "")) <= 150
            opzioni = c.get("options", [])
            assert len(opzioni) <= 25
            for o in opzioni:
                assert len(o["label"]) <= 100 and len(o["value"]) <= 100
                assert len(o.get("description", "")) <= 100
    assert len(embed) <= 6000
    assert all(len(f.value) <= 1024 and len(f.name) <= 256 for f in embed.fields)


def _peggiore() -> Regola:
    ids = tuple(range(10**17, 10**17 + 25))
    az = azioni_da_json([{"t": "avviso_canale", "testo": "x" * 300}, {"t": "dm", "testo": "y" * 1000},
                         {"t": "nickname", "testo": "z" * 32}, {"t": "timeout", "secondi": 60},
                         {"t": "thread_apri", "nome": "w" * 100}, {"t": "log", "ping_ruolo": 10**17},
                         {"t": "dm_staff", "utenti": list(ids[:5])}, {"t": "ban_tempo", "giorni": 3}])
    return Regola(chiave="p:99", tipo="personale", nome="n" * 32, gruppo="g" * 32, calore=100,
                  condizioni=Condizioni(canali_inclusi=ids, canali_esclusi=ids, ruoli_inclusi=ids, ruoli_esclusi=ids, utenti_esclusi=ids),
                  azioni=az, contatore=Contatore("c" * 32, 365, tuple(Soglia(3, 10, az[:3]) for _ in range(3))),
                  innesco={"tipo": "regex", "regex": ["a" * 260] * 10})


@pytest.mark.parametrize("categoria", L.CATEGORIE)
async def test_elenco_di_ogni_categoria_entro_i_limiti(categoria):
    vista, _ = _vista()
    vista.categoria = categoria
    vista.regole = tuple(Regola(chiave=f"p:{i}", tipo="personale", nome="n" * 32, evento=ev, id=i)
                         for i, ev in enumerate(["messaggio"] * 60 + ["nome", "thread", "ingresso"] * 10))
    embed = vista.schermata_elenco()
    _controlla_forma(vista, embed)
    assert len(embed.description.split("\n")) <= 25


@pytest.mark.parametrize("sezione", [None, *P.COSA_MODIFICARE])
async def test_modifica_nel_caso_peggiore_entro_i_limiti(sezione):
    vista, _ = _vista()
    vista.bozza, vista.sezione = _peggiore(), sezione
    _controlla_forma(vista, vista.schermata_regola())
    vista.elimina_armato = True
    _controlla_forma(vista, vista.schermata_regola())


@pytest.mark.parametrize("sezione", ["chi", "sanzioni", "messaggi", "canale", "contatore", "gruppo", "innesco"])
async def test_ogni_finestra_ha_al_massimo_5_campi_con_limite_di_lunghezza(sezione):
    vista, _ = _vista()
    vista.bozza = _peggiore()
    modale = vista._modale(sezione)
    assert 1 <= len(modale.children) <= 5
    assert len(modale.title) <= 45
    for c in modale.children:
        assert c.max_length and len(c.label) <= 45
        assert c.default is None or len(c.default) <= c.max_length  # il valore di partenza non supera il tetto


def test_i_testi_usati_dal_pannello_ci_sono_in_tutte_e_due_le_lingue():
    codice = (Path(P.__file__).read_text() + (Path(P.__file__).parent.parent / "cogs/automod/regole.py").read_text())
    chiavi = set(re.findall(r'tx\("([a-z_]+)"', codice)) | set(re.findall(r'"amregole_([a-z_]+)"', codice))
    chiavi |= {f"cat_{c}" for c in L.CATEGORIE} | {f"cosa_{c}" for c in P.COSA_MODIFICARE}
    chiavi |= {f"az_{a}" for a in (*L.AZIONI_UTENTE_MENU, *L.AZIONI_CANALE_STAFF_MENU)}
    chiavi |= {f"mod_{m}" for m in P.MODELLI} | {"ph_modello"}
    chiavi |= {"ph_categoria", "ph_regola", "ph_cosa", "ph_azioni_utente", "ph_azioni_canale", "ph_canali", "ph_ruoli", "ph_utenti",
               "btn_nuova", "btn_indietro", "btn_salva", "btn_elimina", "btn_elimina_si", "btn_prova", "btn_acceso", "btn_spento"}
    for lingua in ("it", "en-US"):
        catalogo = json.loads((Path(P.__file__).parent.parent / f"locales/{lingua}/testi.json").read_text())
        mancano = [k for k in chiavi if f"amregole_{k}" not in catalogo]
        assert not mancano, (lingua, mancano)
        for k in chiavi:
            testo = catalogo[f"amregole_{k}"]
            if k.startswith(("cat_", "cosa_", "az_", "btn_", "f_", "mod_")):
                assert len(testo) <= 36, (k, testo)  # le lingue lunghe hanno spazio fino a 45


@pytest.fixture
def db_regole(clean_db, monkeypatch):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    monkeypatch.setattr(automod_regole_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    servizio.svuota_cache()
    return clean_db


def _risposta(inter, valori=None):
    inter.data = {"values": valori or []}
    inter.response.edit_message = AsyncMock()
    return inter


async def test_nuova_regola_azioni_dal_menu_e_salvataggio(db_regole):
    vista, inter = _vista()
    inter = _risposta(inter)
    vista.bozza = __import__("dataclasses").replace(
        __import__("core.automod_regole_logic", fromlist=["x"]).Regola(chiave="p:0", tipo="personale", nome="Prova"), evento="messaggio")
    vista.nuova = True
    # menu delle azioni sulla persona: cancella + timeout (parametri di base)
    await vista._scelta_azioni(L.AZIONI_UTENTE_MENU)(_risposta(inter, ["cancella", "timeout"]))
    assert {a.t for a in vista.bozza.azioni} == {"cancella", "timeout"}
    # il canale escluso arriva dal menu nativo
    vista._condizioni(canali_esclusi=(111,))
    await vista._salva(_risposta(inter))
    salvata = (await servizio.regole_del_server(GID))[0]
    assert salvata.chiave.startswith("p:") and salvata.condizioni.canali_esclusi == (111,)
    assert vista.nuova is False and "Salvato" in vista.messaggio
    # al bot mancano i permessi: lo dice, ma salva
    assert "moderate_members" in vista.messaggio and "manage_messages" in vista.messaggio


async def test_filtro_di_oggi_si_apre_si_modifica_e_si_salva(db_regole):
    vista, inter = _vista()
    await vista._carica()
    inter = _risposta(inter, ["anti_caps"])
    await vista._scelta_regola(inter)
    assert vista.bozza.chiave == "anti_caps" and [a.t for a in vista.bozza.azioni] == ["cancella"]  # azioni di partenza
    vista._condizioni(senza_ruoli=True)
    await vista._onoff(_risposta(inter))
    await vista._salva(_risposta(inter))
    r = await servizio.regola_effettiva(GID, "anti_caps")
    assert r.id is not None and r.condizioni.senza_ruoli and r.attiva is False


async def test_errore_di_validazione_resta_nella_bozza(db_regole):
    vista, inter = _vista()
    vista.bozza = Regola(chiave="anti_caps", tipo="filtro", nome="x", calore=500)
    await vista._salva(_risposta(inter))
    assert "⚠️" in vista.messaggio
    assert await servizio.regole_del_server(GID) == ()


async def test_elimina_chiede_due_volte(db_regole):
    vista, inter = _vista()
    r = await servizio.crea_personale(GID, Regola(chiave="x", tipo="personale", nome="Da togliere"), 1)
    vista.bozza = r
    await vista._elimina(_risposta(inter))
    assert len(await servizio.regole_del_server(GID)) == 1 and vista.elimina_armato
    await vista._elimina(_risposta(inter))
    assert await servizio.regole_del_server(GID) == ()


async def test_solo_chi_ha_aperto_il_pannello_lo_usa():
    vista, inter = _vista()
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=5)))
    assert not await vista.interaction_check(fake_interaction(user=fake_member(user_id=6)))


async def test_finestra_innesco_accetta_regex_lunghe_fino_a_260_con_virgole():
    vista, inter = _vista()
    vista.bozza = Regola(chiave="p:0", tipo="personale", nome="Prova")
    lunga = r"(compra|vendi)\s+\w{2,8}\s+" + "x" * 150  # oltre i 60 caratteri di una voce di lista, sotto i 260
    modale = vista._modale("innesco")
    await modale._su_invio(_risposta(inter), {"tipo": "regex", "contenuto": lunga, "liste": "", "modo": ""})
    assert vista.bozza.innesco == {"tipo": "regex", "regex": [lunga]}, vista.messaggio
