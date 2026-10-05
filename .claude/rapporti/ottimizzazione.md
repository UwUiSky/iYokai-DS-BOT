# Quaderno dell'ottimizzazione

Ogni rilievo ha una misura. "Da misurare" vuol dire: visto leggendo,
non ancora provato con i numeri.

| Data | Dove | Problema | Misura | Rimedio proposto | Stato |
|---|---|---|---|---|---|
| 04/10 | PERF-1 (`REVIEW.md`) | Una o più query al database per ogni messaggio | da misurare | Cache con tetto delle impostazioni lette a ogni messaggio | aperto |
| 04/10 | PERF-2 | `get_guild_setting` senza cache | da misurare | `BoundedCache` con scadenza, svuotata alla scrittura | aperto |
| 04/10 | PERF-3 | Tabelle che crescono senza limite | da misurare | Scadenza in `core/retention_worker.py` | aperto |
| 04/10 | PERF-4 | Cicli vocali: 4–6 query al minuto per canale | da misurare | Una query sola per giro | aperto |
| 04/10 | PERF-5 | Chiamate al registro di controllo evitabili | da misurare | Usare l'evento che porta già il dato | aperto |
| 04/10 | PERF-6 | Calo settimanale e mensile fatto utente per utente | da misurare | Un solo `UPDATE` | aperto |
| 04/10 | PERF-7 | Feed scaricati uno alla volta | da misurare | Scaricamento in parallelo con tetto | aperto |
| 05/10 | `cogs/security/verify.py` | Configurazione letta dal database a ogni ingresso | da misurare | Cache con tetto | issue #133 |
