"""
tests/test_catalogo_r2mod_snipe_utente.py
=========================================
`/utility messaggio utente:` (UTL-205): ognuno vede i propri messaggi cancellati, lo staff quelli di tutti, sempre in privato.
"""

import discord

from tests.test_snipe_messaggi import CANALE, GUILD, _cancella, _ix, _msg, ambiente  # noqa: F401
from tests.support.discord_fakes import fake_member


def _ix_con(user_id, manage_messages=False):
    ix = _ix()
    ix.user = fake_member(user_id=user_id)
    ix.channel.permissions_for = lambda who: discord.Permissions(manage_messages=manage_messages)
    return ix


async def _due_messaggi(cog):
    await cog.on_raw_message_delete(_cancella(_msg("di anna", autore=42)))
    await cog.on_raw_message_delete(_cancella(_msg("di berto", autore=43)))


# UTL-205
async def test_ognuno_vede_i_suoi_messaggi_in_privato(ambiente):
    cog, _ = ambiente
    await _due_messaggi(cog)
    ix = _ix_con(42)
    await cog.snipe.callback(cog, ix, fake_member(user_id=42))
    kw = ix.response.send_message.call_args.kwargs
    assert "di anna" in kw["embed"].description and kw["ephemeral"] is True


# UTL-205
async def test_senza_il_permesso_non_si_vedono_quelli_degli_altri(ambiente):
    cog, _ = ambiente
    await _due_messaggi(cog)
    ix = _ix_con(42)
    await cog.snipe.callback(cog, ix, fake_member(user_id=43))
    assert "embed" not in ix.response.send_message.call_args.kwargs
    assert ix.response.send_message.call_args.kwargs["ephemeral"] is True


# UTL-205
async def test_lo_staff_vede_quelli_di_tutti_e_senza_utente_resta_come_prima(ambiente):
    cog, _ = ambiente
    await _due_messaggi(cog)
    ix = _ix_con(900, manage_messages=True)
    await cog.snipe.callback(cog, ix, fake_member(user_id=42))
    assert "di anna" in ix.response.send_message.call_args.kwargs["embed"].description
    ix2 = _ix_con(900)
    await cog.snipe.callback(cog, ix2)
    kw = ix2.response.send_message.call_args.kwargs
    assert "di berto" in kw["embed"].description and not kw.get("ephemeral")


# UTL-205
async def test_di_una_persona_senza_messaggi_dice_che_non_c_e_niente(ambiente):
    cog, _ = ambiente
    await _due_messaggi(cog)
    ix = _ix_con(44, manage_messages=True)
    await cog.snipe.callback(cog, ix, fake_member(user_id=44))
    assert "Nessun messaggio" in ix.response.send_message.call_args.args[0]
