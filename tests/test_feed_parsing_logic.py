"""
tests/test_feed_parsing_logic.py
====================================
Test di core/feed_parsing_logic.py con fixture XML scritte a mano
ma STRUTTURALMENTE fedeli ai formati reali (RSS 2.0 standard, Atom
nella forma usata da YouTube/Reddit) — non recuperabili dal vivo in
questo ambiente (rete del sandbox limitata a un elenco fisso di
domini), quindi costruite seguendo lo standard pubblicato, non
inventate a caso.
"""

from core.feed_parsing_logic import find_new_entries, parse_feed, render_alert_message

RSS_DI_ESEMPIO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Esempio Reddit r/programming</title>
    <item>
      <title>Nuovo post recente</title>
      <link>https://reddit.com/r/programming/post2</link>
      <guid>reddit-post-2</guid>
    </item>
    <item>
      <title>Post più vecchio</title>
      <link>https://reddit.com/r/programming/post1</link>
      <guid>reddit-post-1</guid>
    </item>
  </channel>
</rss>
"""

RSS_CON_DATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>3</title><link>https://e.com/3</link><guid>post-3</guid>
    <pubDate>Sat, 03 Oct 2026 12:00:00 GMT</pubDate></item>
  <item><title>2</title><link>https://e.com/2</link><guid>post-2</guid>
    <pubDate>Fri, 02 Oct 2026 12:00:00 GMT</pubDate></item>
  <item><title>1</title><link>https://e.com/1</link><guid>post-1</guid>
    <pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate></item>
</channel></rss>
"""

ATOM_DI_ESEMPIO = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Canale YouTube di esempio</title>
  <entry>
    <id>yt:video:VIDEO_NUOVO</id>
    <title>Video più recente</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VIDEO_NUOVO"/>
  </entry>
  <entry>
    <id>yt:video:VIDEO_VECCHIO</id>
    <title>Video precedente</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VIDEO_VECCHIO"/>
  </entry>
</feed>
"""


class TestParseFeed:
    def test_analizza_rss_2_0(self):
        voci = parse_feed(RSS_DI_ESEMPIO)
        assert len(voci) == 2
        assert voci[0].entry_id == "reddit-post-2"
        assert voci[0].title == "Nuovo post recente"
        assert voci[0].link == "https://reddit.com/r/programming/post2"

    def test_analizza_atom(self):
        voci = parse_feed(ATOM_DI_ESEMPIO)
        assert len(voci) == 2
        assert voci[0].entry_id == "yt:video:VIDEO_NUOVO"
        assert voci[0].title == "Video più recente"
        assert voci[0].link == "https://www.youtube.com/watch?v=VIDEO_NUOVO"

    def test_xml_malformato_restituisce_lista_vuota_senza_sollevare(self):
        assert parse_feed("<rss><channel><item>non chiuso") == []

    def test_formato_sconosciuto_restituisce_lista_vuota(self):
        assert parse_feed("<qualcosa><altro/></qualcosa>") == []

    def test_rss_senza_channel_restituisce_lista_vuota(self):
        assert parse_feed("<rss version=\"2.0\"></rss>") == []

    def test_item_senza_guid_usa_il_link_come_id(self):
        rss_senza_guid = """<rss version="2.0"><channel>
            <item><title>Test</title><link>https://esempio.com/1</link></item>
        </channel></rss>"""
        voci = parse_feed(rss_senza_guid)
        assert voci[0].entry_id == "https://esempio.com/1"

    def test_item_senza_titolo_ha_un_placeholder(self):
        rss_senza_titolo = """<rss version="2.0"><channel>
            <item><guid>x</guid><link>https://esempio.com/1</link></item>
        </channel></rss>"""
        voci = parse_feed(rss_senza_titolo)
        assert voci[0].title == "(senza titolo)"


class TestFindNewEntries:
    def test_prima_verifica_mai_fatta_non_restituisce_nulla(self):
        voci = parse_feed(RSS_DI_ESEMPIO)
        # last_seen_entry_id=None -> nessuna voce è "nuova", anche
        # se il feed ha contenuto: altrimenti il primo controllo
        # pubblicherebbe l'intero storico in un colpo solo.
        assert find_new_entries(voci, last_seen_entry_id=None) == []

    def test_trova_solo_le_voci_dopo_l_ultima_vista(self):
        voci = parse_feed(RSS_DI_ESEMPIO)
        nuove = find_new_entries(voci, last_seen_entry_id="reddit-post-1")
        assert len(nuove) == 1
        assert nuove[0].entry_id == "reddit-post-2"

    def test_nessuna_voce_nuova_se_l_ultima_vista_e_la_piu_recente(self):
        voci = parse_feed(RSS_DI_ESEMPIO)
        nuove = find_new_entries(voci, last_seen_entry_id="reddit-post-2")
        assert nuove == []

    # M 11.5: se l'ultimo elemento visto sparisce dal feed non si
    # ripubblica tutto (prima: "id mai visto = tutte le voci").
    def test_id_sparito_senza_data_ricordata_non_pubblica_nulla(self):
        voci = parse_feed(RSS_CON_DATE)
        assert find_new_entries(voci, last_seen_entry_id="sparito") == []

    def test_id_sparito_pubblica_solo_le_voci_piu_recenti_della_data_ricordata(self):
        from datetime import datetime, timezone

        voci = parse_feed(RSS_CON_DATE)
        ricordata = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
        nuove = find_new_entries(voci, "sparito", ricordata)
        assert [v.entry_id for v in nuove] == ["post-3"]

    def test_id_presente_ignora_la_data(self):
        from datetime import datetime, timezone

        voci = parse_feed(RSS_CON_DATE)
        vecchia = datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert [v.entry_id for v in find_new_entries(voci, "post-2", vecchia)] == ["post-3"]

    def test_date_lette_da_rss_e_atom(self):
        from core.feed_parsing_logic import data_piu_recente

        voci = parse_feed(RSS_CON_DATE)
        assert voci[0].published.isoformat() == "2026-10-03T12:00:00+00:00"
        assert data_piu_recente(voci) == voci[0].published
        atom = parse_feed(
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>a</id><title>t</title>'
            '<published>2026-10-01T08:30:00+02:00</published></entry></feed>'
        )
        assert atom[0].published.isoformat() == "2026-10-01T08:30:00+02:00"
        assert parse_feed(RSS_DI_ESEMPIO)[0].published is None


class TestRenderAlertMessage:
    def test_sostituisce_tutti_i_placeholder(self):
        risultato = render_alert_message(
            "{label}: {title} -> {link}", label="Canale X", title="Video Y", link="https://esempio.com"
        )
        assert risultato == "Canale X: Video Y -> https://esempio.com"

    def test_template_senza_placeholder_resta_invariato(self):
        assert render_alert_message("Testo fisso", "L", "T", "https://x.com") == "Testo fisso"

    def test_placeholder_sconosciuto_non_solleva_e_resta_intatto(self):
        # SEC-6: render_template sostituisce SOLO i placeholder che
        # conosce; quello sconosciuto (typo dell'utente) resta
        # scritto com'era, gli altri vengono comunque sostituiti.
        template = "{label}: {titolo_sbagliato}"
        risultato = render_alert_message(template, "L", "T", "https://x.com")
        assert risultato == "L: {titolo_sbagliato}"
