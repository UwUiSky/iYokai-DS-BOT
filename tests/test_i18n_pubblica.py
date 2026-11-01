"""
tests/test_i18n_pubblica.py
===========================
SPEC 21.1 (NF-06): un testo che leggono tutti (messaggio non effimero, canale, log dello staff,
messaggio privato a un'altra persona) è nella lingua del SERVER, non in quella personale di chi
ha usato il comando. Ogni `testo_per` che finisce in un invio così deve avere `pubblica=True`.
"""

import ast
import pathlib

RADICE = pathlib.Path(__file__).resolve().parent.parent
NOMI_IGNORATI = {"discord", "self", "interaction", "logger", "asyncio"}
INVII_AI_LOG = {"post_to_mod_log", "_send_log", "_log_e_risposta", "_log", "_scrivi_nel_log", "_log_violation"}


def _nome(nodo):
    return getattr(nodo, "id", None) or getattr(nodo, "attr", None)


def _testo_personale(nodo):
    return (
        isinstance(nodo, ast.Call)
        and _nome(nodo.func) == "testo_per"
        and not any(k.arg == "pubblica" for k in nodo.keywords)
    )


def _effimero(chiamata):
    for k in chiamata.keywords:
        if k.arg == "ephemeral":
            return not (isinstance(k.value, ast.Constant) and k.value.value is False)
    return False


def _invio_pubblico(nodo, rinvio_effimero):
    if not isinstance(nodo, ast.Call):
        return False
    nome = _nome(nodo.func)
    if nome in INVII_AI_LOG:
        return True
    if not isinstance(nodo.func, ast.Attribute):
        return False
    destinatario = ast.unparse(nodo.func.value)
    if nome == "send_message" or destinatario.endswith("followup"):
        if destinatario.endswith("followup") and rinvio_effimero and not any(k.arg == "ephemeral" for k in nodo.keywords):
            return False  # dopo defer(ephemeral=True) il seguito resta effimero
        return not _effimero(nodo)
    return nome in ("send", "reply")


def _argomenti(chiamata):
    return list(chiamata.args) + [k.value for k in chiamata.keywords]


def _passaggi(funzione):
    """(nomi letti, testo_per presenti, nomi scritti) per ogni assegnazione o `x.metodo(...)`."""
    for nodo in ast.walk(funzione):
        if isinstance(nodo, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and nodo.value is not None:
            bersagli = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            scritti = {x.id for b in bersagli for x in ast.walk(b) if isinstance(x, ast.Name)}
            valori = [nodo.value]
        elif (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and isinstance(nodo.func.value, ast.Name)
            and nodo.func.value.id not in NOMI_IGNORATI
            and not _invio_pubblico(nodo, False)
        ):
            scritti = {nodo.func.value.id}
            valori = _argomenti(nodo)
        else:
            continue
        figli = [x for v in valori for x in ast.walk(v)]
        letti = {x.id for x in figli if isinstance(x, ast.Name)} - NOMI_IGNORATI
        yield letti, [x for x in figli if _testo_personale(x)], scritti - NOMI_IGNORATI


def _testi_personali_in_invii_pubblici(sorgente):
    trovati = []
    for funzione in ast.walk(ast.parse(sorgente)):
        if not isinstance(funzione, ast.AsyncFunctionDef):
            continue
        rinvio_effimero = any(
            isinstance(c, ast.Call) and _nome(c.func) == "defer" and _effimero(c) for c in ast.walk(funzione)
        )
        pubblici, segnati = set(), []
        for c in ast.walk(funzione):
            if _invio_pubblico(c, rinvio_effimero):
                figli = [x for a in _argomenti(c) for x in ast.walk(a)]
                pubblici |= {x.id for x in figli if isinstance(x, ast.Name)} - NOMI_IGNORATI
                segnati += [x for x in figli if _testo_personale(x)]
        passaggi = list(_passaggi(funzione))
        cambiato = True
        while cambiato:
            cambiato = False
            for letti, _, scritti in passaggi:
                if scritti & pubblici and not letti <= pubblici:
                    pubblici |= letti
                    cambiato = True
        segnati += [x for letti, testi, scritti in passaggi if scritti & pubblici for x in testi]
        trovati += sorted({x.lineno for x in segnati})
    return trovati


def test_i_testi_dei_messaggi_pubblici_sono_nella_lingua_del_server():
    trovati = []
    for percorso in sorted((RADICE / "cogs").rglob("*.py")):
        righe = _testi_personali_in_invii_pubblici(percorso.read_text(encoding="utf-8"))
        trovati += [f"{percorso.relative_to(RADICE)}:{r}" for r in righe]
    assert trovati == []


def test_il_controllo_riconosce_un_embed_mandato_nel_canale():
    sorgente = (
        "async def f(interaction, canale):\n"
        "    embed = discord.Embed(title=await testo_per(interaction, 'a'))\n"
        "    embed.add_field(name=await testo_per(interaction, 'b'), value='x')\n"
        "    await interaction.response.send_message(await testo_per(interaction, 'c'), ephemeral=True)\n"
        "    await canale.send(embed=embed)\n"
    )
    assert _testi_personali_in_invii_pubblici(sorgente) == [2, 3]


def test_il_controllo_accetta_le_risposte_effimere_e_pubblica_true():
    sorgente = (
        "async def f(interaction):\n"
        "    await interaction.response.defer(ephemeral=True)\n"
        "    embed = discord.Embed(title=await testo_per(interaction, 'a'))\n"
        "    await interaction.followup.send(embed=embed)\n"
        "    await interaction.channel.send(await testo_per(interaction, 'b', pubblica=True))\n"
    )
    assert _testi_personali_in_invii_pubblici(sorgente) == []
