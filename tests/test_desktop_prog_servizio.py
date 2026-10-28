"""
tests/test_desktop_prog_servizio.py
===================================
SPEC D.1, D.5-D.8, D.10, D.11 (#108): impostazioni locali, servizio, notifiche, appunti, funzioni da attivare.
"""

import io
import os
import stat
import sys
import urllib.error
from threading import Event
from types import SimpleNamespace

import pytest

from desktop.iyokai_desktop import appunti, notifiche, rpc_avanzato
from desktop.iyokai_desktop import impostazioni as imp
from desktop.iyokai_desktop.servizio import ErroreServizio, Servizio


# ------------------------------------------------------------ impostazioni
@pytest.mark.parametrize("url,ok", [
    ("https://p.example", True), ("https://p.example/sub/", True), ("http://localhost:8422", True), ("http://127.0.0.1:1", True),
    ("http://p.example", False), ("ftp://p.example", False), ("https://u:p@p.example", False), ("https://p.example?x=1", False), ("", False),
])
def test_indirizzo(url, ok):
    if ok:
        assert imp.indirizzo_valido(url).startswith(url.split("//")[0])
    else:
        with pytest.raises(imp.ErroreImpostazioni):
            imp.indirizzo_valido(url)


def test_cartelle_per_sistema():
    assert str(imp.cartella_config({"APPDATA": "C:/A"}, "win32")).replace("\\", "/") == "C:/A/iyokai-desktop"
    assert str(imp.cartella_config({"HOME": "/h"}, "darwin")) == "/h/Library/Application Support/iyokai-desktop"
    assert str(imp.cartella_config({"HOME": "/h"}, "linux")) == "/h/.config/iyokai-desktop"
    assert str(imp.cartella_config({"HOME": "/h", "XDG_CONFIG_HOME": "/x"}, "linux")) == "/x/iyokai-desktop"


def test_impostazioni_e_codice_privato(tmp_path):
    i = imp.Impostazioni(tmp_path / "c")
    assert i.codice() is None and i.ultimo_evento() == 0
    i.imposta_servizio("https://p.example/")
    i.imposta_app_id("123456789012345678")
    i.imposta_lingua("en")
    i.imposta_ultimo_evento(7)
    assert (i.leggi("servizio"), i.leggi("app_id"), i.leggi("lingua"), i.ultimo_evento()) == ("https://p.example", "123456789012345678", "en", 7)
    i.salva_codice(" dsk_segreto \n")
    assert i.codice() == "dsk_segreto" and "dsk_segreto" not in (tmp_path / "c" / "impostazioni.json").read_text()
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(os.stat(tmp_path / "c" / "codice.txt").st_mode) == 0o600
    assert i.dimentica_codice() and not i.dimentica_codice() and i.codice() is None
    for chiamata in (lambda: i.imposta_app_id("abc"), lambda: i.imposta_lingua("xx")):
        with pytest.raises(imp.ErroreImpostazioni):
            chiamata()


# ------------------------------------------------------------ servizio
class _Risposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _servizio(rispondi):
    visti = []

    def apri(richiesta, tempo):
        visti.append(richiesta)
        return rispondi(richiesta)

    return Servizio("https://p.example", "dsk_" + "a" * 43, apri), visti


def _errore_http(stato, corpo):
    return urllib.error.HTTPError("u", stato, "x", {}, io.BytesIO(corpo))


def test_chiamate_con_token_nell_intestazione_e_query():
    s, visti = _servizio(lambda r: _Risposta(b'{"eventi": [{"id": 1}]}'))
    assert s.eventi(dopo=5, tipo="menzione", attesa=3) == [{"id": 1}]
    r = visti[0]
    assert r.full_url == "https://p.example/api/desktop/eventi?dopo=5&tipo=menzione&attesa=3&limite=50"
    assert r.get_header("Authorization") == "Bearer dsk_" + "a" * 43 and "dsk_" not in r.full_url


def test_post_traduci_e_staff():
    s, visti = _servizio(lambda r: _Risposta(b'{"testo": "Hello", "esito": "ok"}'))
    assert s.traduci("Ciao", "en") == "Hello"
    assert visti[0].data == b'{"testo": "Ciao", "lingua": "en"}' and visti[0].get_method() == "POST"
    assert s.staff_azione(5, "timeout", target_id=1, minuti=5) == "ok"


def test_errori_del_servizio():
    s, _ = _servizio(lambda r: (_ for _ in ()).throw(_errore_http(401, b'{"errore": "token_non_valido"}')))
    with pytest.raises(ErroreServizio) as e:
        s.io()
    assert (e.value.codice, e.value.stato) == ("token_non_valido", 401)
    s, _ = _servizio(lambda r: (_ for _ in ()).throw(urllib.error.URLError("giù")))
    with pytest.raises(ErroreServizio, match="rete_non_raggiungibile"):
        s.io()
    s, _ = _servizio(lambda r: _Risposta(b"non json"))
    with pytest.raises(ErroreServizio, match="risposta_non_valida"):
        s.io()
    s, _ = _servizio(lambda r: _Risposta(b"[1]"))
    with pytest.raises(ErroreServizio, match="risposta_non_valida"):
        s.io()
    s, _ = _servizio(lambda r: _Risposta(b"x" * (1024 * 1024 + 5)))
    with pytest.raises(ErroreServizio, match="risposta_troppo_grande"):
        s.io()


def test_rifiuto_dello_staff_torna_come_esito():
    s, _ = _servizio(lambda r: (_ for _ in ()).throw(_errore_http(403, b'{"esito": "nessun_permesso"}')))
    assert s.staff_azione(5, "annuncio", channel_id=1, testo="x") == "nessun_permesso"


def test_servizio_rifiuta_indirizzi_non_sicuri():
    with pytest.raises(imp.ErroreImpostazioni):
        Servizio("http://p.example", "x")


def test_nessun_reindirizzamento():
    from desktop.iyokai_desktop.servizio import _NessunReindirizzamento

    assert _NessunReindirizzamento().redirect_request(None, None, 302, "x", {}, "https://altro") is None


# ------------------------------------------------------------ notifiche
EV = {"id": 3, "tipo": "menzione", "autore": "Ann", "canale": "gen", "testo": "ciao", "quando": "2026-10-28T10:00:00+00:00",
      "link": "https://discord.com/channels/1/2/3"}


def test_titoli_e_righe():
    assert notifiche.titolo_evento(EV) == "Ann ti ha menzionato in #gen"
    assert notifiche.titolo_evento(EV, "en") == "Ann mentioned you in #gen"
    assert notifiche.titolo_evento({"tipo": "promemoria"}) == "Promemoria"
    assert notifiche.titolo_evento({"tipo": "altro"}) == "altro"
    assert notifiche.riga_storico(EV, 1) == "  1. 2026-10-28 10:00  Ann ti ha menzionato in #gen: ciao"


@pytest.mark.parametrize("link,ok", [
    ("https://discord.com/channels/1/2/3", True), ("https://discord.com/channels/@me/2/3", True),
    ("https://evil.example/channels/1/2/3", False), ("javascript:alert(1)", False), ("https://discord.com/channels/1/2/3/../x", False),
    ("https://discord.com.evil.example/channels/1/2/3", False), (None, False),
])
def test_salto_solo_a_link_discord(link, ok):
    aperti = []
    assert notifiche.salta_al_messaggio({"link": link}, apri=lambda u: aperti.append(u) or True) is ok
    assert aperti == ([link] if ok else [])


def test_comando_notifica_senza_testo_nella_riga_di_comando():
    cattivo = "'; Remove-Item -Recurse /; '"
    for piattaforma in ("win32", "darwin", "linux"):
        argomenti, extra = notifiche.comando_notifica(cattivo, cattivo, piattaforma)
        if piattaforma == "win32":
            assert not any(cattivo in a for a in argomenti) and extra["IYOKAI_TESTO"] == cattivo
        else:
            assert cattivo in argomenti  # argomento separato, mai dentro un copione composto
    assert notifiche.comando_notifica("t", "x", "linux")[0][:2] == ["notify-send", "--app-name=iYokai"]
    assert notifiche.comando_notifica("t" * 500, "x" * 500, "linux")[0][-2:] == ["t" * 80, "x" * 200]


def test_invia_notifica_mai_un_errore():
    assert notifiche.invia_notifica("t", "x", esegui=lambda *a, **k: SimpleNamespace(returncode=0)) is True
    assert notifiche.invia_notifica("t", "x", esegui=lambda *a, **k: SimpleNamespace(returncode=1)) is False

    def manca(*a, **k):
        raise FileNotFoundError

    assert notifiche.invia_notifica("t", "x", esegui=manca) is False


class _ServizioFinto:
    def __init__(self, eventi):
        self.eventi_da_dare = eventi
        self.chiamate = []

    def eventi(self, dopo=0, tipo=None, attesa=0, limite=50):
        self.chiamate.append((dopo, attesa))
        return [e for e in self.eventi_da_dare if e["id"] > dopo]


def test_ciclo_avvisi_mostra_i_nuovi_e_ricorda_l_ultimo():
    s = _ServizioFinto([{**EV, "id": 3}, {**EV, "id": 4, "tipo": "parola"}])
    visti = []
    assert notifiche.ciclo_avvisi(s, 3, "it", invia=lambda t, x: visti.append(t)) == 4
    assert visti == ["Ann ha scritto una tua parola chiave in #gen"] and s.chiamate == [(3, 20)]


def test_ascolto_si_ferma_riprova_e_non_nasconde_il_token(tmp_path):
    i = imp.Impostazioni(tmp_path)
    ferma = Event()

    class Instabile:
        def __init__(self):
            self.n = 0

        def eventi(self, **k):
            self.n += 1
            if self.n == 1:
                raise ErroreServizio("rete_non_raggiungibile")
            ferma.set()
            return [{**EV, "id": 9}]

    visti = []
    notifiche.avvisi_in_ascolto(Instabile(), i, ferma, invia=lambda t, x: visti.append(t), passo_errore=0.01)
    assert i.ultimo_evento() == 9 and len(visti) == 1

    class Revocato:
        def eventi(self, **k):
            raise ErroreServizio("token_non_valido", 401)

    with pytest.raises(ErroreServizio, match="token_non_valido"):
        notifiche.avvisi_in_ascolto(Revocato(), i, Event())


# ------------------------------------------------------------ appunti
def test_comandi_appunti_per_sistema():
    assert appunti.comandi("darwin") == (["pbpaste"], ["pbcopy"])
    assert appunti.comandi("win32")[1] == ["clip"]
    assert appunti.comandi("linux", disponibile=lambda n: n in ("wl-paste", "wl-copy"))[1] == ["wl-copy"]
    assert appunti.comandi("linux", disponibile=lambda n: n == "xclip")[0][0] == "xclip"
    with pytest.raises(appunti.ErroreAppunti, match="strumento_mancante"):
        appunti.comandi("linux", disponibile=lambda n: None)


def test_traduci_appunti_e_risposte():
    scritto = []

    class S:
        def traduci(self, testo, lingua):
            return f"[{lingua}] {testo}"

        def risposte(self):
            return [{"nome": "ciao", "testo": "Ciao a tutti!"}]

    assert appunti.traduci_appunti(S(), "en", leggi_=lambda: "Ciao", scrivi_=scritto.append) == "[en] Ciao" and scritto == ["[en] Ciao"]
    for testo, codice in (("", "appunti_vuoti"), ("x" * 3001, "appunti_troppo_lunghi")):
        with pytest.raises(appunti.ErroreAppunti, match=codice):
            appunti.traduci_appunti(S(), "en", leggi_=lambda t=testo: t, scrivi_=scritto.append)
    assert appunti.copia_risposta(S(), " Ciao ", scrivi_=scritto.append) == "Ciao a tutti!" and scritto[-1] == "Ciao a tutti!"
    with pytest.raises(appunti.ErroreAppunti, match="risposta_non_trovata"):
        appunti.copia_risposta(S(), "no", scrivi_=scritto.append)


def test_leggi_scrivi_appunti_con_strumento_finto():
    lettura = appunti.leggi(esegui=lambda *a, **k: SimpleNamespace(stdout=" testo \n".encode()), piattaforma="darwin")
    assert lettura == "testo"
    visti = []
    appunti.scrivi("é", esegui=lambda c, **k: visti.append((c, k["input"])), piattaforma="darwin")
    assert visti == [(["pbcopy"], "é".encode())]

    def rotto(*a, **k):
        raise OSError

    with pytest.raises(appunti.ErroreAppunti, match="lettura_fallita"):
        appunti.leggi(esegui=rotto, piattaforma="darwin")
    with pytest.raises(appunti.ErroreAppunti, match="scrittura_fallita"):
        appunti.scrivi("x", esegui=rotto, piattaforma="darwin")


# ------------------------------------------------------------ D.11
def test_funzioni_che_aspettano_discord_restano_spente():
    assert {s for _, s, _ in rpc_avanzato.elenco()} == {"rpc.notifications.read", "rpc.voice.write", "rpc.voice.read"}
    for nome in rpc_avanzato.FUNZIONI:
        with pytest.raises(rpc_avanzato.DaAttivare) as e:
            rpc_avanzato.attiva(nome, approvata=True)
        assert e.value.scope.startswith("rpc.")
    with pytest.raises(KeyError):
        rpc_avanzato.attiva("inventata")
