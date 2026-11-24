# PostgreSQL locale per iYokai

Il database gira sulla stessa macchina del bot. Versione consigliata: **PostgreSQL 19**
(uscita il 19/11/2026). Il bot funziona dalla 14 in su, ma le versioni vecchie escono dal supporto
(la 14 dal 12/11/2026).

La porta resta **solo su localhost**: il database non va mai esposto su Internet.

## Linux (consigliato: installazione normale, senza Docker)

```bash
# repository ufficiale di PostgreSQL (Debian / Ubuntu)
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt install -y postgresql-19

# utente e database del bot (la password è quella che metti nel .env)
sudo -u postgres psql -c "CREATE USER iyokai WITH PASSWORD 'una-password-lunga';"
sudo -u postgres psql -c "CREATE DATABASE iyokai_bot OWNER iyokai;"
```

Nel `.env` del bot:

```
DATABASE_URL=postgresql://iyokai:una-password-lunga@127.0.0.1:5432/iyokai_bot
```

Le tabelle si creano da sole al primo avvio del bot (`core/migrations/`).
PostgreSQL parte da solo all'accensione della macchina (servizio `postgresql`).

## Con Docker (alternativa)

```bash
cd deploy/postgres
export POSTGRES_PASSWORD='una-password-lunga'   # la stessa del DATABASE_URL
docker compose up -d
```

Utente `iyokai`, database `iyokai_bot`, dati nella cartella `deploy/postgres/dati` (fuori da git).
Con `DB_DOCKER=1` nel `.env`, lo script di avvio accende da solo questo container se il database non risponde.

## Windows

Installer ufficiale: https://www.postgresql.org/download/windows/ (versione 19).
Poi crea utente e database con pgAdmin o con `psql` come sopra.

## Copie di sicurezza

Una copia al giorno, per esempio con cron alle 4:

```bash
pg_dump -Fc -U iyokai -h 127.0.0.1 iyokai_bot > /percorso/backup/iyokai_$(date +%F).dump
```

Per passare da una versione all'altra (es. 16 → 19): `pg_dump` con il programma della versione **nuova**,
poi `pg_restore` sul server nuovo. Con la 19, i dump fatti con `standard_conforming_strings = off`
non si caricano: il valore di base è `on`, non cambiarlo.
