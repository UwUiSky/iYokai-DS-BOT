"""
tests/test_lingue_struttura.py
==============================
D58 (#77): struttura delle lingue (cartelle, ripiego lingua -> en-US -> it), controllo e creazione di una lingua,
nomi tradotti validi, peso dei comandi con tutte le lingue, richiesta di una lingua all'owner.
"""

import datetime as dt
import json
import re
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import command_translator as tr
from core import i18n, lingua_richieste as rich, lingue_controllo as ctl

NUOVE = ("de", "es-ES", "fr", "ja", "ko", "ru", "uk", "zh-CN")


def test_ogni_lingua_ha_la_sua_cartella_con_i_due_file():
    assert i18n.LINGUE == ("it", "en-US") + NUOVE
    for lingua in i18n.LINGUE:
        assert isinstance(json.loads(i18n.percorso_testi(lingua).read_text(encoding="utf-8")), dict), lingua
        assert isinstance(json.loads(i18n.percorso_comandi(lingua).read_text(encoding="utf-8")), dict), lingua
    for lingua in NUOVE:
        assert json.loads(i18n.percorso_testi(lingua).read_text(encoding="utf-8")) == {}


def test_ripiego_lingua_en_it(monkeypatch):
    catalogo = {"it": {"a": "uno", "b": "due", "c": "tre"}, "en-US": {"a": "one", "b": "two"}, "fr": {"a": "un"}}
    monkeypatch.setattr(i18n, "carica_catalogo", lambda forza=False: catalogo)
    assert i18n.t("a", "fr") == "un"
    assert i18n.t("b", "fr") == "two"       # manca in fr: en-US
    assert i18n.t("c", "fr") == "tre"       # manca anche in en-US: it
    assert i18n.t("c", "ja") == "tre"
    assert i18n.t("b", "en") == "two" and i18n.t("b", "en-GB") == "two"
    assert i18n.t("zzz", "fr") == "zzz"


def test_le_lingue_vuote_non_sono_disponibili_e_en_si_salva_come_en():
    assert i18n.lingue_disponibili() == ("it", "en")
    assert i18n.lingua_valida("en") and not i18n.lingua_valida("fr")


def test_un_testo_vuoto_vale_da_tradurre(tmp_path, monkeypatch):
    cartella = tmp_path / "fr"
    cartella.mkdir()
    (cartella / "testi.json").write_text('{"x": ""}', encoding="utf-8")
    monkeypatch.setattr(i18n, "CARTELLA_LOCALES", tmp_path)
    assert i18n.carica_catalogo(forza=True)["fr"] == {}
    monkeypatch.undo()
    i18n.carica_catalogo(forza=True)


def test_nessuna_lingua_ha_chiavi_che_l_italiano_non_ha():
    it = ctl._testi("it")
    for lingua in i18n.LINGUE:
        assert sorted(set(ctl._testi(lingua)) - set(it)) == [], lingua


def test_il_controllo_conta_mancanti_uguali_e_segnaposto(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "CARTELLA_LOCALES", tmp_path)
    for lingua, dati in {
        "it": {"a": "Ciao {n}", "b": "Addio {n}", "c": "Boh {n}", "d": "{n}"},
        "fr": {"a": "Salut {m}", "b": "Addio {n}", "d": "{n}"},
    }.items():
        (tmp_path / lingua).mkdir()
        (tmp_path / lingua / "testi.json").write_text(json.dumps(dati), encoding="utf-8")
        (tmp_path / lingua / "comandi.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ctl, "cartella_lingua", i18n.cartella_lingua)
    stato = ctl.stato_lingua("fr")
    assert stato.mancanti == ["c"] and stato.uguali == ["b"] and stato.segnaposto_diversi == ["a"]
    assert "| fr | 4 | 1 | 1 | 1 |" in ctl.riepilogo([stato])


def test_nuova_lingua_crea_tutte_le_chiavi_vuote(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "CARTELLA_LOCALES", tmp_path)
    for lingua, dati in {"it": {"a": "uno", "b": "due"}, "en-US": {"a": "one", "b": "two"}}.items():
        (tmp_path / lingua).mkdir()
        (tmp_path / lingua / "testi.json").write_text(json.dumps(dati), encoding="utf-8")
        (tmp_path / lingua / "comandi.json").write_text(json.dumps({"nomi": {"x": "y"}, "descrizioni": {"x": "z"}}), encoding="utf-8")
    assert ctl.crea_lingua("pt-BR") == ["locales/pt-BR/testi.json", "locales/pt-BR/comandi.json"]
    assert json.loads((tmp_path / "pt-BR" / "testi.json").read_text(encoding="utf-8")) == {"a": "", "b": ""}
    comandi = json.loads((tmp_path / "pt-BR" / "comandi.json").read_text(encoding="utf-8"))
    assert comandi["nomi"] == {"x": ""} and comandi["descrizioni"] == {"x": ""}
    with pytest.raises(ValueError):
        ctl.crea_lingua("pt-BR")
    with pytest.raises(ValueError):
        ctl.crea_lingua("../x")


def test_nomi_validi_secondo_la_regola_di_discord():
    for ok in ("ban", "admin-voce", "ban_user", "голос", "禁止", "вимкнути", "금지", "बैन", "บัน", "ʼx", "café"):
        assert tr.nome_valido(ok), ok
    for no in ("", "Ban", "con spazio", "a" * 33, "ban!", "x.y", "a/b"):
        assert not tr.nome_valido(no), no


def test_il_prefisso_dello_staff_non_si_traduce(monkeypatch):
    dati = tr.carica_tutte()
    monkeypatch.setitem(dati, "fr", {s: {} for s in tr.SEZIONI})
    dati["fr"]["nomi"].update({"admin-vocali": "admin-vocal", "mod-ban": "bannir", "founder": "fondateur", "ban": "bannir"})
    assert tr.nome_tradotto("admin-vocali", "fr") == "admin-vocal"
    assert tr.nome_tradotto("mod-ban", "fr") is None          # toglie il prefisso mod-
    assert tr.nome_tradotto("founder", "fr") is None
    assert tr.nome_tradotto("ban", "fr") == "bannir"


def test_il_traduttore_manda_solo_le_chiavi_tradotte(monkeypatch):
    dati = tr.carica_tutte()
    monkeypatch.setitem(dati, "fr", {s: {} for s in tr.SEZIONI})
    dati["fr"]["descrizioni"]["mod-ban"] = "Bannit un membre."
    L = discord.app_commands.TranslationContextLocation
    comando = MagicMock(qualified_name="mod-ban")
    ctx = MagicMock(location=L.command_description, data=comando)
    assert tr.tradotto_per(ctx, "fr") == "Bannit un membre."
    assert tr.tradotto_per(ctx, "de") is None   # vuota
    assert tr.tradotto_per(ctx, "it") is None   # la base
    assert tr.tradotto_per(ctx, "en-US") == tr.descrizione_tradotta("mod-ban", "en-US")


def test_l_aiuto_lungo_ricade_su_en_poi_it(monkeypatch):
    dati = tr.carica_tutte()
    for l in ("it", "en-US", "fr"):
        monkeypatch.setitem(dati, l, {s: {} for s in tr.SEZIONI})
    dati["it"]["aiuto"]["x y"] = "testo it"
    assert tr.aiuto_comando("x y", "fr") == "testo it"
    dati["en-US"]["aiuto"]["x y"] = "text en"
    assert tr.aiuto_comando("x y", "fr") == "text en"
    dati["fr"]["aiuto"]["x y"] = "texte fr"
    assert tr.aiuto_comando("x y", "fr") == "texte fr"
    assert tr.aiuto_comando("senza", "fr") is None


async def test_il_peso_conta_la_versione_piu_lunga_tra_le_lingue(monkeypatch):
    from discord import app_commands

    comando = app_commands.Command(name="ban", description="x" * 10, callback=_cb)
    base = tr.caratteri_con_traduzioni(comando)
    dati = tr.carica_tutte()
    monkeypatch.setitem(dati, "de", {s: {} for s in tr.SEZIONI})
    dati["de"]["descrizioni"]["ban"] = "y" * 60
    dati["de"]["nomi"]["ban"] = "verbannen"
    assert base == 13 and tr.caratteri_con_traduzioni(comando) == len("verbannen") + 60


async def _cb(interaction):  # pragma: no cover
    pass


def _utente(uid=5):
    u = MagicMock(id=uid)
    u.__str__ = lambda self: "Mario"
    return u


async def test_la_richiesta_arriva_all_owner_e_c_e_un_tetto_al_giorno():
    rich._ultimo_giorno.clear()
    owner = MagicMock(send=AsyncMock())
    bot = MagicMock(get_user=MagicMock(return_value=owner))
    adesso = dt.datetime(2026, 11, 1, 10, tzinfo=dt.timezone.utc)
    esito = await rich.invia_richiesta(bot, _utente(), MagicMock(id=9), "  Portoghese @everyone ", "nota\ncon a capo", adesso)
    assert esito is rich.Esito.INVIATA
    testo = owner.send.call_args.args[0]
    assert "Portoghese" in testo and "@everyone" not in testo.replace("@​everyone", "") and len(testo) <= 2000
    assert owner.send.call_args.kwargs["allowed_mentions"].everyone is False
    assert await rich.invia_richiesta(bot, _utente(), None, "Olandese", "", adesso) is rich.Esito.LIMITE
    assert owner.send.await_count == 1
    domani = adesso + dt.timedelta(days=1)
    assert await rich.invia_richiesta(bot, _utente(), None, "Olandese", "", domani) is rich.Esito.INVIATA
    assert await rich.invia_richiesta(bot, _utente(6), None, "Polacco", "", adesso) is rich.Esito.INVIATA


async def test_nome_vuoto_dm_chiusi_e_tagli():
    rich._ultimo_giorno.clear()
    assert await rich.invia_richiesta(MagicMock(), _utente(), None, "   ", "x") is rich.Esito.NOME_VUOTO
    owner = MagicMock(send=AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "dm chiusi")))
    bot = MagicMock(get_user=MagicMock(return_value=owner))
    assert await rich.invia_richiesta(bot, _utente(), None, "Polacco", "") is rich.Esito.NON_INVIATA
    assert not rich.ha_gia_richiesto(5)   # il tetto non si consuma se il DM non parte
    assert len(rich.pulisci("a" * 500, rich.MAX_NOME_LINGUA)) == 50


async def test_il_modulo_ha_i_limiti_e_risponde_all_utente():
    from cogs.utility.lingua import ChiediLinguaView, RichiestaLinguaModal

    modulo = RichiestaLinguaModal(MagicMock(), "it")
    assert modulo.nome.max_length == 50 and modulo.nota.max_length == 300 and not modulo.nota.required
    assert len(modulo.title) <= 45 and len(modulo.nome.label) <= 45 and len(modulo.nota.label) <= 45
    vista = ChiediLinguaView(MagicMock(), "en")
    assert [b.label for b in vista.children] == [i18n.t("lingua_richiesta_bottone", "en")]
    rich._ultimo_giorno.clear()
    owner = MagicMock(send=AsyncMock())
    modulo.bot = MagicMock(get_user=MagicMock(return_value=owner))
    modulo.nome._value = "Svedese"
    modulo.nota._value = ""
    interazione = MagicMock(user=_utente(77), guild=None)
    interazione.response.defer = AsyncMock()
    interazione.followup.send = AsyncMock()
    await modulo.on_submit(interazione)
    assert interazione.followup.send.call_args.args[0] == i18n.t("lingua_richiesta_ok", "it")
    assert interazione.followup.send.call_args.kwargs["ephemeral"] is True


async def test_due_moduli_inviati_insieme_mandano_un_solo_dm():
    """Doppio invio (due moduli aperti): il tetto si prende prima del DM, non dopo."""
    import asyncio

    rich._ultimo_giorno.clear()

    async def lento(*_a, **_k):
        await asyncio.sleep(0.05)

    owner = MagicMock(send=AsyncMock(side_effect=lento))
    bot = MagicMock(get_user=MagicMock(return_value=owner))
    esiti = await asyncio.gather(*(rich.invia_richiesta(bot, _utente(), None, "Olandese", "") for _ in range(3)))
    assert sorted(e.value for e in esiti) == ["inviata", "limite", "limite"]
    assert owner.send.await_count == 1


def test_una_lingua_sconosciuta_non_allarga_la_cache_dei_comandi():
    prima = set(tr.carica_tutte())
    for codice in ("xx", "pt-BR", "../it", "en"):
        assert tr.nome_tradotto("ban", codice) is None or codice == "en"
        tr.carica_traduzioni(lingua=codice)
    assert set(tr.carica_tutte()) == prima == set(i18n.LINGUE)
