"""
tests/test_catalogo_r2mod_stat_moderatore.py
============================================
`/mod-casi caso classifica-staff moderatore:` (MOD-040): conteggi per tipo e per periodo. Database vero.
"""

from tests.test_moderation_caso_note_warn import G, _amb, _casi, _inter  # noqa: F401
from cogs.moderation.case_system import ModerationCaseSystemCog
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_member


# MOD-040
async def test_le_statistiche_contano_per_tipo_e_periodo_e_non_i_casi_nascosti_o_altrui():
    await _casi()  # moderatore 10: warn, ban, warn; moderatore 11: warn
    await moderation_repo._pool.execute("UPDATE moderation_cases SET created_at = now() - INTERVAL '20 days' WHERE case_number = 2")
    await moderation_repo._pool.execute("UPDATE moderation_cases SET created_at = now() - INTERVAL '200 days' WHERE case_number = 4")
    n = await moderation_repo.create_case(G, 5, 10, "kick", "x")
    await moderation_repo._pool.execute("UPDATE moderation_cases SET hidden = TRUE WHERE case_number = $1", n)
    s = await moderation_repo.statistiche_moderatore(G, 10)
    assert s["per_tipo"] == {"warn": 2, "ban": 1}
    assert s["periodi"] == {7: 1, 30: 2, 90: 2}
    assert (await moderation_repo.statistiche_moderatore(G, 99))["per_tipo"] == {}


# MOD-040
async def test_il_comando_mostra_le_statistiche_sopra_i_casi():
    await _casi()
    inter, _ = _inter()
    cog = ModerationCaseSystemCog(bot=None)
    await cog.staff_ranking.callback(cog, inter, fake_member(10))
    descrizione = inter.response.send_message.call_args.kwargs["embed"].description
    assert "warn 2" in descrizione and "ban 1" in descrizione and "Ultimi 7 giorni" in descrizione
    assert len(descrizione) <= 4096
