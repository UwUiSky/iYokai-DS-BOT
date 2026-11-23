"""
tests/test_security_controllo_link.py
=====================================
Controllo dei link (AMD-030, D111): normalizzazione, liste pubbliche, servizi con chiave, cache, quote. Nessuna rete.
"""

import json
import logging

import pytest

from core import controllo_link as cl
from core import controllo_link_liste as li
from core import controllo_link_servizi as sv
from core import safe_http


@pytest.fixture(autouse=True)
def _pulito(tmp_path, monkeypatch):
    monkeypatch.setenv(li.VARIABILE_CARTELLA, str(tmp_path / "cache"))
    monkeypatch.delenv(li.VARIABILE_ATTIVE, raising=False)
    li.stato.svuota()
    li.stato._letto_da_disco = True  # i test non leggono il disco del progetto
    li.stato._ultimo_giro = 1e12  # niente giri in sottofondo
    cl.svuota_cache()
    for t in sv.TETTI.values():
        t._minuto.clear()
        t._giorno.clear()
    yield
    li.stato.svuota()


async def _mai(*a, **k):
    raise AssertionError("nessuna richiesta di rete attesa")


# AMD-030
def test_normalizza_punycode_maiuscole_e_utente():
    u = cl.normalizza("HTTPS://paypal.com@Evil.EXAMPLE./a?b=1#frag")
    assert u.raw_host == "evil.example" and u.fragment == "" and u.user is None
    assert cl.normalizza("https://bücher.example/").raw_host == "xn--bcher-kva.example"
    assert cl.normalizza("ftp://x.example") is None and cl.normalizza("") is None
    assert cl.normalizza("https://a.example/" + "x" * 3000) is None


# AMD-030
def test_rimando_noto_si_scarta_senza_rete():
    u = cl.scarta_rimando(cl.normalizza("https://www.google.com/url?q=https%3A%2F%2Fevil.example%2Fx"))
    assert u.raw_host == "evil.example"


# AMD-030
def test_le_liste_si_leggono_nei_tre_formati_e_scartano_il_resto():
    assert li.interpreta("# c\nA.Example\n1.2.3.4\nnon valido\nwww.b.example\n", "domini") == {"a.example", "b.example"}
    assert li.interpreta("http://x.example/a.exe\nhttps://Y.example:8080/z\n", "url") == {"x.example", "y.example"}
    assert li.interpreta("0.0.0.0 m.example\n127.0.0.1 localhost\n", "hosts") == {"m.example"}


# AMD-030
def test_la_ricerca_nelle_liste_vale_anche_per_i_sottodomini():
    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    assert li.stato.cerca("a.b.cattivo.example") == ("urlhaus", "malware")
    assert li.stato.cerca("buono.example") is None


# AMD-030
def test_la_lista_dei_malware_di_amd031_si_riempie_dalle_fonti():
    from core import phishing_logic as ph

    assert ph.lista_siti("malware") == frozenset()
    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    assert "cattivo.example" in ph.lista_siti("malware")
    li.stato.svuota()
    assert ph.lista_siti("malware") == frozenset()


# AMD-030
def test_fonti_attive_senza_indirizzo_o_spente(monkeypatch):
    assert {f.nome for f in li.fonti_attive()} == {"urlhaus", "phishing_army", "openphish", "phishing_database"}
    monkeypatch.setenv("LINK_LISTA_AGCOM_URL", "https://esempio.example/agcom.txt")
    assert "agcom" in {f.nome for f in li.fonti_attive()}
    monkeypatch.setenv("LINK_LISTA_ADM_URL", "http://non-https.example/x")  # solo https
    assert "adm" not in {f.nome for f in li.fonti_attive()}
    monkeypatch.setenv(li.VARIABILE_ATTIVE, "urlhaus")
    assert [f.nome for f in li.fonti_attive()] == ["urlhaus"]
    monkeypatch.setenv(li.VARIABILE_ATTIVE, "nessuna")
    assert li.fonti_attive() == ()


# AMD-030
@pytest.mark.asyncio
async def test_scarico_salva_su_disco_e_una_fonte_che_fallisce_non_ferma_le_altre(monkeypatch, tmp_path):
    righe = "\n".join(f"http://m{i}.example/a" for i in range(20))
    visti = []

    async def finto(url, *, max_bytes):
        visti.append((url, max_bytes))
        if "openphish" in url:
            raise RuntimeError("giu")
        return None if "phishing.army" in url else righe

    monkeypatch.setattr(safe_http, "safe_get", finto)
    riuscite = await li.stato.aggiorna()
    assert riuscite == 2  # urlhaus e phishing_database; army vuota, openphish in errore
    assert all(mb == li.MAX_BYTE_LISTA for _, mb in visti)
    assert li.stato.cerca("m3.example") is not None
    assert (tmp_path / "cache" / "urlhaus.txt").is_file()
    li.stato.svuota()
    li.stato.carica_da_disco()
    assert li.stato.cerca("m3.example") is not None  # dalla cache su disco, senza rete


# AMD-030
@pytest.mark.asyncio
async def test_una_lista_troppo_corta_non_sostituisce_quella_buona(monkeypatch):
    li.stato.imposta("urlhaus", frozenset({"vecchio.example"}))

    async def finto(url, *, max_bytes):
        return "http://uno.example/\n"

    monkeypatch.setattr(safe_http, "safe_get", finto)
    assert not await li.stato.scarica_fonte(li.FONTI[0])
    assert li.stato.cerca("vecchio.example") is not None


# AMD-030
@pytest.mark.asyncio
async def test_google_safe_browsing_verdetti_e_chiave_spenta():
    async def trovato(url, **k):
        assert k["metodo"] == "POST" and "threatInfo" in k["json_corpo"]
        return json.dumps({"matches": [{"threatType": "SOCIAL_ENGINEERING"}]})

    async def vuoto(url, **k):
        return "{}"

    assert await sv.google_safe_browsing("https://x.example", "K", trovato) == ("pericoloso", "phishing")
    assert await sv.google_safe_browsing("https://x.example", "K", vuoto) == ("sicuro", "")
    assert await sv.google_safe_browsing("https://x.example", "", _mai) is None  # senza chiave: nessuna richiesta


# AMD-030
@pytest.mark.asyncio
async def test_servizio_che_non_risponde_o_risponde_male_vale_nessun_parere():
    async def rotto(url, **k):
        return "non json"

    async def niente(url, **k):
        return None

    assert await sv.google_safe_browsing("https://x.example", "K", rotto) is None
    assert await sv.virustotal("x.example", "K", niente) is None


# AMD-030
@pytest.mark.asyncio
async def test_cloudflare_e_virustotal():
    async def cf(url, **k):
        assert "/accounts/" + "a" * 32 + "/intel/domain?domain=x.example" in url
        assert k["headers"]["Authorization"] == "Bearer T"
        return json.dumps({"success": True, "result": {"risk_types": [{"name": "Phishing"}]}})

    assert await sv.cloudflare_intel("x.example", "T", "a" * 32, cf) == ("pericoloso", "phishing")
    assert await sv.cloudflare_intel("x.example", "T", "../evil", _mai) is None  # l'id account non entra nel percorso
    assert await sv.cloudflare_intel("x.example", "", "a" * 32, _mai) is None

    def vt(n_male, n_dubbi=0):
        async def f(url, **k):
            assert k["headers"] == {"x-apikey": "V"}
            return json.dumps({"data": {"attributes": {"last_analysis_stats": {"malicious": n_male, "suspicious": n_dubbi}}}})
        return f

    assert (await sv.virustotal("x.example", "V", vt(5)))[0] == "pericoloso"
    assert (await sv.virustotal("x.example", "V", vt(1)))[0] == "sospetto"
    assert (await sv.virustotal("x.example", "V", vt(0)))[0] == "sicuro"


# AMD-030
def test_i_tetti_per_servizio_fermano_le_richieste():
    t = sv.Tetto(2, 3)
    assert t.consuma(0) and t.consuma(1) and not t.consuma(2)  # 2 al minuto
    assert t.consuma(61) and not t.consuma(62)  # 3 al giorno finite
    assert t.consuma(86500)  # il giorno dopo si riparte


# AMD-030
@pytest.mark.asyncio
async def test_valuta_usa_prima_le_liste_senza_chiamare_i_servizi():
    li.stato.imposta("openphish", frozenset({"truffa.example"}))
    e = await cl.valuta("https://login.truffa.example/x", chiavi=sv.Chiavi(google="K"), richiesta=_mai)
    assert (e.livello, e.fonte, e.categoria) == ("pericoloso", "openphish", "phishing")


# AMD-030
@pytest.mark.asyncio
async def test_valuta_domini_ufficiali_e_whitelist_non_spendono_quota():
    k = sv.Chiavi(google="K")
    assert (await cl.valuta("https://discord.com/channels/1", chiavi=k, richiesta=_mai)).livello == "sicuro"
    li.stato.imposta("urlhaus", frozenset({"amico.example"}))
    assert (await cl.valuta("https://amico.example/", consentiti=("amico.example",), chiavi=k, richiesta=_mai)).livello == "sicuro"


# AMD-030
@pytest.mark.asyncio
async def test_valuta_serve_i_servizi_in_ordine_e_ricorda_il_verdetto():
    chiamate = []

    async def rich(url, **k):
        chiamate.append(url.split("?")[0])
        if "safebrowsing" in url:
            return "{}"
        return json.dumps({"data": {"attributes": {"last_analysis_stats": {"malicious": 7}}}})

    k = sv.Chiavi(google="K", virustotal="V")
    e = await cl.valuta("https://nuovo.example/a", chiavi=k, richiesta=rich)
    assert (e.livello, e.fonte) == ("pericoloso", "virustotal")
    n = len(chiamate)
    assert (await cl.valuta("https://NUOVO.example/a#x", chiavi=k, richiesta=_mai)).livello == "pericoloso"  # cache
    assert len(chiamate) == n


# AMD-030
@pytest.mark.asyncio
async def test_valuta_senza_chiavi_o_con_servizi_giu_non_solleva_e_non_blocca():
    assert (await cl.valuta("https://tranquillo.example/", chiavi=sv.Chiavi(), richiesta=_mai)).livello == "sicuro"

    async def esplode(url, **k):
        raise RuntimeError("giu")

    e = await cl.valuta("https://altro.example/", chiavi=sv.Chiavi(google="K"), richiesta=esplode)
    assert e.livello == "sicuro"
    assert (await cl.valuta("non e un link", chiavi=sv.Chiavi())).livello == "sicuro"


# AMD-030
@pytest.mark.asyncio
async def test_accorciatore_si_segue_con_safe_http_e_si_giudica_la_meta():
    li.stato.imposta("urlhaus", frozenset({"meta.example"}))
    visti = []

    async def segui(url):
        visti.append(url)
        return "https://meta.example/payload"

    e = await cl.valuta("https://bit.ly/abc", chiavi=sv.Chiavi(), richiesta=_mai, segui=segui)
    assert e.e_pericoloso and e.dominio == "meta.example" and visti == ["https://bit.ly/abc"]


# AMD-030
@pytest.mark.asyncio
async def test_il_tetto_dei_redirect_e_un_accorciatore_che_non_risponde():
    async def giu(url):
        return None

    e = await cl.valuta("https://tinyurl.com/x", chiavi=sv.Chiavi(), richiesta=_mai, segui=giu)
    assert e.livello in ("sicuro", "sospetto")  # resta il link di partenza
    cl._salti_al_minuto[:] = [10**12] * cl.MAX_SALTI_AL_MINUTO

    async def mai_segui(url):
        raise AssertionError("tetto superato")

    await cl.valuta("https://t.ly/zz", chiavi=sv.Chiavi(), richiesta=_mai, segui=mai_segui)


# AMD-030
@pytest.mark.asyncio
async def test_la_chiave_non_finisce_nei_log(caplog):
    async def rotto(url, **k):
        return None

    caplog.set_level(logging.DEBUG)
    await cl.valuta("https://segreto.example/?t=1", chiavi=sv.Chiavi(google="CHIAVE-SEGRETA", virustotal="VT-SEGRETA"), richiesta=rotto)
    assert "SEGRETA" not in caplog.text


# AMD-030
def test_link_nel_testo_ha_un_tetto_e_toglie_la_punteggiatura():
    testo = " ".join(f"https://a{i}.example/x)." for i in range(10)) + " https://a0.example/x)."
    link = cl.link_nel_testo(testo)
    assert len(link) == cl.MAX_LINK_PER_MESSAGGIO and link[0] == "https://a0.example/x"


# AMD-030
@pytest.mark.asyncio
async def test_primo_pericoloso_e_sospetti_a_scelta(monkeypatch):
    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    assert (await cl.primo_pericoloso("ciao https://ok.example e http://cattivo.example/a")).categoria == "malware"
    assert await cl.primo_pericoloso("https://grabify.link/ABC") is None  # cattura l'IP: solo sospetto
    assert (await cl.primo_pericoloso("https://grabify.link/ABC", anche_sospetti=True)).e_sospetto
    assert (await cl.primo_pericoloso("https://free-discord-nitro.example/")).categoria == "phishing"  # euristica del phishing


# AMD-030
@pytest.mark.asyncio
async def test_url_pubblicabile_rifiuta_interni_e_pericolosi(monkeypatch):
    async def vero(u):
        return "interno" not in u

    monkeypatch.setattr(safe_http, "url_e_sicuro", vero)
    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    assert await cl.url_pubblicabile("https://bene.example/")
    assert not await cl.url_pubblicabile("https://cattivo.example/")
    assert not await cl.url_pubblicabile("http://interno.example/")


# AMD-030
def test_automod_link_pericolosi_azioni_di_partenza_e_nome():
    from core import automod_advanced_logic as a

    assert a.VIOLATION_LINK_PERICOLOSI in a.ALL_VIOLATIONS
    assert a.AZIONI_DI_PARTENZA[a.VIOLATION_LINK_PERICOLOSI] == ("delete", "warn")  # cancella e avvisa
    assert a.AutomodAdvancedConfig().link_pericolosi == 0  # di base spento: scelta del server


# AMD-030
def test_automod_link_pericolosi_si_salva_e_valori_strani_tornano_spenti():
    import json

    from core.repositories import automod_advanced_repo as repo

    base = repo._default_settings(1)
    from core.automod_advanced_logic import AutomodAdvancedConfig

    for valore, atteso in ((2, 2), (1, 1), (9, 0)):
        impostazioni = repo.AutomodAdvancedSettings(**{**base.__dict__, "config": AutomodAdvancedConfig(link_pericolosi=valore)})
        assert repo._from_json(1, repo._to_json(impostazioni)).config.link_pericolosi == atteso if valore != 9 else True
    brutto = json.loads(repo._to_json(base))
    brutto["link_pericolosi"] = 9
    assert repo._from_json(1, json.dumps(brutto)).config.link_pericolosi == 0


# AMD-030
@pytest.mark.asyncio
async def test_automod_il_controllo_usa_i_sospetti_solo_al_livello_due_e_un_guasto_non_ferma():
    from types import SimpleNamespace

    from cogs.automod import automod as cog
    from core.automod_advanced_logic import AutomodAdvancedConfig, MessageSignals

    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    msg = SimpleNamespace(guild=SimpleNamespace(id=1))
    brutto = MessageSignals(content="vedi https://cattivo.example/a")
    sospetto = MessageSignals(content="vedi https://grabify.link/x")
    assert await cog._link_pericolosi(msg, brutto, AutomodAdvancedConfig(link_pericolosi=1))
    assert not await cog._link_pericolosi(msg, sospetto, AutomodAdvancedConfig(link_pericolosi=1))
    assert await cog._link_pericolosi(msg, sospetto, AutomodAdvancedConfig(link_pericolosi=2))


# AMD-030
@pytest.mark.asyncio
async def test_togli_link_pericolosi_lascia_il_resto_del_testo():
    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    nuovo, tolti = await cl.togli_link_pericolosi("guarda https://cattivo.example/a e https://discord.com/x")
    assert tolti == 1 and nuovo == f"guarda {cl.SEGNO_BLOCCATO} e https://discord.com/x"
    assert await cl.togli_link_pericolosi("niente link") == ("niente link", 0)


# AMD-030
@pytest.mark.asyncio
async def test_e_link_pericoloso_e_i_punti_di_pubblicazione_usano_il_punto_unico():
    import pathlib

    li.stato.imposta("urlhaus", frozenset({"cattivo.example"}))
    assert await cl.e_link_pericoloso("https://cattivo.example/x")
    assert not await cl.e_link_pericoloso("https://bene.example/x")
    radice = pathlib.Path(__file__).resolve().parent.parent
    for percorso in (
        "cogs/utility/custom_commands.py", "cogs/utility/autoresponder.py", "cogs/utility/embed_builder.py",
        "cogs/utility/embed_avanzati.py", "cogs/utility/feed_alerts.py", "cogs/utility/alert_piattaforme.py",
        "core/greetings_uscite_logic.py", "core/web_editor.py", "core/web_servizi_logic.py", "core/feed_watcher.py",
    ):
        assert "core.controllo_link import" in (radice / percorso).read_text(encoding="utf-8"), percorso
