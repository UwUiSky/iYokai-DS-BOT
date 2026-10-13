"""Aiuti di test per music_sessions (la produzione assegna solo con assign_free_worker)."""


async def assegna(repo, guild_id: int, channel_id: int, worker_index: int) -> None:
    await repo._pool.execute(
        "INSERT INTO music_sessions (guild_id, channel_id, worker_index) VALUES ($1,$2,$3) "
        "ON CONFLICT (guild_id, channel_id) DO UPDATE SET worker_index = EXCLUDED.worker_index",
        guild_id,
        channel_id,
        worker_index,
    )


async def occupati(repo) -> set[int]:
    righe = await repo._pool.fetch("SELECT DISTINCT worker_index FROM music_sessions")
    return {r["worker_index"] for r in righe}
