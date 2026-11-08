"""
tests/test_moderation_limiti_motivo.py
======================================
Il motivo dei comandi di moderazione rispetta il limite del registro
di controllo di Discord (LIM-8): 512 caratteri, dichiarati
sull'opzione, così Discord rifiuta il testo prima che arrivi al bot.
"""

import discord
import pytest
from discord.ext import commands

from cogs.moderation._shared import MAX_REASON_LENGTH, audit_reason
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.softban_mute import ModerationSoftbanMuteCog

COMANDI_CON_MOTIVO = (
    ("mod-sanzioni", "warn"),
    ("mod-ban", "kick"),
    ("mod-ban", "ban"),
    ("mod-ban", "tempban"),
    ("mod-ban", "unban"),
    ("mod-sanzioni", "timeout"),
    ("mod-ban", "softban"),
    ("mod-sanzioni", "mute"),
    ("mod-sanzioni", "unmute"),
)


@pytest.fixture
async def albero():
    """I due cog veri dentro un bot non collegato."""
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(ModerationActionsCog(bot))
    await bot.add_cog(ModerationSoftbanMuteCog(bot))
    yield bot.tree
    await bot.remove_cog("ModerationActionsCog")
    await bot.remove_cog("ModerationSoftbanMuteCog")


@pytest.mark.parametrize("gruppo,nome", COMANDI_CON_MOTIVO)
async def test_il_motivo_dichiara_da_3_a_512_caratteri(albero, gruppo, nome):
    comando = albero.get_command(gruppo).get_command(nome)
    opzioni = {o["name"]: o for o in comando.to_dict(albero)["options"]}

    # MOD-065: il motivo è facoltativo nella firma (l'obbligo lo decide il server), ma se c'è ha questi limiti
    assert opzioni["reason"]["required"] is False
    assert opzioni["reason"]["autocomplete"] is True  # MOD-116: motivi pronti
    assert opzioni["reason"]["min_length"] == 3
    assert opzioni["reason"]["max_length"] == 512


def test_motivo_per_il_registro_tagliato_a_512():
    """Un prefisso aggiunto dal bot ("Softban: …") non fa superare il limite."""
    assert MAX_REASON_LENGTH == 512
    lungo = "Softban: " + "m" * 512

    tagliato = audit_reason(lungo)

    assert len(tagliato) == 512
    assert tagliato.endswith("…")
    assert audit_reason("breve") == "breve"
