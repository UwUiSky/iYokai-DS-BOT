"""Motore degli script dei tag (B25): funzioni, tetti e tentativi di fuga."""
import random
import time
from datetime import datetime, timezone

import pytest

from core import tag_script_logic as ts

ADESSO = datetime(2026, 11, 9, 15, 30, tzinfo=timezone.utc)


def ctx(**kw):
    kw.setdefault("adesso", ADESSO)
    kw.setdefault("rng", random.Random(1))
    return ts.Contesto(**kw)


async def run(testo, **kw):
    return (await ts.esegui(testo, ctx(**kw))).testo


# ------------------------------------------------------------------ testo semplice e condizioni
async def test_testo_senza_script_resta_uguale():
    assert await run("ciao {user} e {sconosciuto}") == "ciao {user} e {sconosciuto}"


async def test_se_vero_e_falso_con_alias():
    assert await run("{se:1==1|si|no}") == "si"
    assert await run("{if:1==2|si|no}") == "no"
    assert await run("{se:|si|no}") == "no"
    assert await run("{se:x|si}") == "si"
    assert await run("{se:0|si|no}") == "no"


async def test_se_confronti_numerici_e_testuali():
    assert await run("{se:10>9|a|b}") == "a"
    assert await run("{se:10<9|a|b}") == "b"
    assert await run("{se:3>=3|a|b}") == "a"
    assert await run("{se:ciao~ia|a|b}") == "a"
    assert await run("{se:ciao!~zz|a|b}") == "a"
    assert await run("{se:Ciao==ciao|a|b}") == "a"
    assert await run("{se:a!=b|a|b}") == "a"


async def test_se_valuta_solo_il_ramo_scelto():
    r = await ts.esegui("{se:1|ok|{calcola:1/0}}", ctx())
    assert r.testo == "ok" and r.errore is None


async def test_e_o_non():
    assert await run("{se:{e:1|1}|a|b}") == "a"
    assert await run("{se:{e:1|}|a|b}") == "b"
    assert await run("{se:{o:|1}|a|b}") == "a"
    assert await run("{se:{non:}|a|b}") == "a"


# ------------------------------------------------------------------ variabili
async def test_variabili_e_contesto():
    assert await run("{var:x=5}{x}") == "5"
    assert await run("{set:x=ciao}{x}!") == "ciao!"
    assert await run("{args}", valori={"args": "uno due"}) == "uno due"
    assert await run("{var:x=1}{var:x={calcola:{x}+1}}{x}") == "2"


async def test_nome_variabile_non_valido_e_errore():
    r = await ts.esegui("{var:1x=5}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_nome_variabile"


async def test_valori_degli_utenti_sono_dati_non_script():
    r = await run("{args}", valori={"args": "{calcola:1+1} @everyone <@&123456789012345678>"})
    assert "{calcola:1+1}" in r  # non rieseguito
    assert "@everyone" not in r and "@\u200beveryone" in r
    assert "<@&123456789012345678>" not in r


async def test_tetto_variabili():
    testo = "".join("{var:v%d=1}" % i for i in range(ts.MAX_VARIABILI + 1))
    r = await ts.esegui(testo, ctx())
    assert r.errore and r.errore.chiave == "tag_script_troppe_variabili"


# ------------------------------------------------------------------ funzioni
async def test_lista_caso_ripeti_con_rng_fisso():
    assert await run("{lista:a|b|c}") in {"a", "b", "c"}
    n = int(await run("{caso:1-10}"))
    assert 1 <= n <= 10
    assert await run("{random:5-5}") == "5"
    assert len(await run("{ripeti:3|x}")) == 3
    assert 1 <= int(await run("{caso:6}")) <= 6


async def test_caso_intervallo_invalido():
    r = await ts.esegui("{caso:10-1}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_intervallo"
    r = await ts.esegui("{caso:abc}", ctx())
    assert r.errore


async def test_calcola():
    assert await run("{calcola:2+3*4}") == "14"
    assert await run("{calc:sqrt(16)}") == "4"
    r = await ts.esegui("{calcola:__import__('os')}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_calcolo"
    r = await ts.esegui("{calcola:9**9**9}", ctx())
    assert r.errore


async def test_maiuscole_sostituisci_lunghezza():
    assert await run("{maiuscolo:ciao}") == "CIAO"
    assert await run("{lower:CIAO}") == "ciao"
    assert await run("{titolo:ciao mondo}") == "Ciao Mondo"
    assert await run("{sostituisci:a-b-c|-|+}") == "a+b+c"
    assert await run("{lunghezza:ciao}") == "4"


async def test_regex_re2():
    assert await run(r"{regex:abc123|\d+|N}") == "abcN"
    r = await ts.esegui("{regex:aaa|(?=a)|x}", ctx())  # re2 non ha lookahead
    assert r.errore and r.errore.chiave == "tag_script_regex"
    r = await ts.esegui("{regex:%s|(a+)+$|x}" % ("a" * 1500 + "b"), ctx())
    assert r.errore is None  # tempo lineare: nessun blocco
    r = await ts.esegui("{regex:x|%s|y}" % ("a" * 300), ctx())
    assert r.errore and r.errore.chiave == "tag_script_regex"


async def test_data_e_tra():
    assert await run("{data:%d/%m/%Y %H:%M}") == "09/11/2026 15:30"
    assert await run("{data:%A %B}") == "lunedì novembre"
    assert await run("{date:%Y}") == "2026"
    r = await ts.esegui("{data:%c}", ctx())  # direttiva non ammessa
    assert r.errore and r.errore.chiave == "tag_script_formato_data"
    assert await run("{tra:2h}") == "<t:%d:R>" % int(ADESSO.timestamp() + 7200)
    assert await run("{tra:1h30m}") == "<t:%d:R>" % int(ADESSO.timestamp() + 5400)
    r = await ts.esegui("{tra:400g}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_durata"


async def test_escape():
    assert await run(r"\{se:1\|a\}") == "{se:1|a}"
    assert await run(r"{var:x=a\|b}{x}") == "a|b"


# ------------------------------------------------------------------ tetti
async def test_tetto_operazioni():
    testo = "{ripeti:50|{ripeti:50|{caso:1-2}}}"
    r = await ts.esegui(testo, ctx())
    assert r.errore and r.errore.chiave == "tag_script_troppi_passi"
    assert r.operazioni <= ts.MAX_OPERAZIONI + 1


async def test_tetto_profondita():
    testo = "{maiuscolo:" * (ts.MAX_PROFONDITA + 2) + "x" + "}" * (ts.MAX_PROFONDITA + 2)
    r = await ts.esegui(testo, ctx())
    assert r.errore and r.errore.chiave == "tag_script_troppo_profondo"
    ok = "{maiuscolo:" * 5 + "x" + "}" * 5
    assert await run(ok) == "X"


async def test_tetto_uscita():
    r = await ts.esegui("{ripeti:50|" + "x" * 200 + "}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_uscita_lunga"
    assert len(r.testo) <= ts.MAX_USCITA


async def test_tetto_valore_variabile():
    r = await ts.esegui("{var:a=" + "x" * 1500 + "}{var:b={a}{a}}", ctx())
    assert r.errore and r.errore.chiave == "tag_script_uscita_lunga"


async def test_tetto_tempo():
    t = [0.0]

    def orologio():
        t[0] += 0.5
        return t[0]

    r = await ts.esegui("{caso:1-2}{caso:1-2}{caso:1-2}{caso:1-2}", ctx(orologio=orologio, tempo_max=1.0))
    assert r.errore and r.errore.chiave == "tag_script_tempo"


async def test_script_troppo_lungo():
    r = await ts.esegui("x" * (ts.MAX_SCRIPT + 1), ctx())
    assert r.errore and r.errore.chiave == "tag_script_troppo_lungo"


async def test_graffe_non_chiuse_sono_testo():
    assert await run("{{{{ ciao") == "{{{{ ciao"
    t0 = time.monotonic()
    await run("{" * 4000)
    assert time.monotonic() - t0 < 1


# ------------------------------------------------------------------ fughe
@pytest.mark.parametrize("testo", [
    "{__import__('os').system('id')}",
    "{calcola:().__class__.__bases__[0].__subclasses__()}",
    "{calcola:open('/etc/passwd').read()}",
    "{x.__class__}",
    "{user.__class__.__mro__}",
    "{eval:1+1}", "{exec:1}", "{import:os}", "{file:/etc/passwd}", "{http:https://example.com}",
    "{0.__class__}", "{'a'.format}",
])
async def test_tentativi_di_fuga_restano_testo_o_errore(testo):
    r = await ts.esegui(testo, ctx())
    assert "root:" not in r.testo and "uid=" not in r.testo
    assert r.errore is None or r.errore.chiave.startswith("tag_script_")
    assert "<class" not in r.testo and "<module" not in r.testo


async def test_format_spec_non_alloca():
    r = await ts.esegui("{args:>999999999}", ctx(valori={"args": "x"}))
    assert len(r.testo) < 100


async def test_il_modulo_non_usa_eval_exec_ne_jinja():
    import inspect
    import re
    sorgente = inspect.getsource(ts)
    for vietato in (r"\beval\(", r"\bexec\(", "jinja", r"(?<!re2\.)(?<!re\.)\bcompile\(", "__import__", "format_map", r"\.format\("):
        assert not re.search(vietato, sorgente), vietato


async def test_regex_si_ferma_prima_di_costruire_una_sostituzione_enorme(monkeypatch):
    chiamate = []
    vero = ts._compila

    class Spia:
        def __init__(self, p):
            self.p = p

        def sub(self, con, testo):
            chiamate.append(con)
            return self.p.sub(con, testo)

    monkeypatch.setattr(ts, "_compila", lambda m: Spia(vero(m)))
    r = await ts.esegui("{regex:%s|a|%s}" % ("a" * 1500, "b" * 1900), ctx())
    assert r.errore and r.errore.chiave == "tag_script_uscita_lunga"
    assert callable(chiamate[0])  # la sostituzione si controlla pezzo per pezzo, non a cose fatte
