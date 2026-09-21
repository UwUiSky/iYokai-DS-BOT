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

    def test_id_mai_visto_restituisce_tutte_le_voci(self):
        # Il feed potrebbe essere stato completamente sostituito
        # (raro, ma possibile) - meglio pubblicare tutto quello che
        # c'è ora piuttosto che bloccarsi in silenzio per sempre.
        voci = parse_feed(RSS_DI_ESEMPIO)
        nuove = find_new_entries(voci, last_seen_entry_id="id-che-non-esiste-piu")
        assert len(nuove) == 2


class TestRenderAlertMessage:
    def test_sostituisce_tutti_i_placeholder(self):
        risultato = render_alert_message(
            "{label}: {title} -> {link}", label="Canale X", title="Video Y", link="https://esempio.com"
        )
        assert risultato == "Canale X: Video Y -> https://esempio.com"

    def test_template_senza_placeholder_resta_invariato(self):
        assert render_alert_message("Testo fisso", "L", "T", "https://x.com") == "Testo fisso"

    def test_placeholder_sconosciuto_non_solleva_e_lascia_il_template_originale(self):
        template = "{label}: {titolo_sbagliato}"
        risultato = render_alert_message(template, "L", "T", "https://x.com")
        assert risultato == template
