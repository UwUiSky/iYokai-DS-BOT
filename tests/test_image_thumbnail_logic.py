"""
tests/test_image_thumbnail_logic.py
=======================================
Test di core/image_thumbnail_logic.py — logica pura, nessuna
elaborazione immagine vera qui (quella è in
tests/test_image_thumbnail.py, con Pillow).
"""

from core.image_thumbnail_logic import (
    MAX_SOURCE_IMAGE_BYTES,
    bytes_to_data_uri,
    is_image_attachment,
    is_within_size_limit,
)


class TestIsImageAttachment:
    def test_content_type_immagine_standard(self):
        assert is_image_attachment("foto.png", "image/png") is True
        assert is_image_attachment("foto.jpg", "image/jpeg") is True

    def test_content_type_non_immagine(self):
        assert is_image_attachment("documento.pdf", "application/pdf") is False

    def test_content_type_svg_escluso_esplicitamente(self):
        # SVG è "image/*" ma non è raster — Pillow non lo apre in
        # modo affidabile senza librerie aggiuntive.
        assert is_image_attachment("logo.svg", "image/svg+xml") is False

    def test_content_type_heic_escluso_esplicitamente(self):
        assert is_image_attachment("foto.heic", "image/heic") is False

    def test_content_type_assente_ripiega_su_estensione_immagine(self):
        assert is_image_attachment("foto.png", None) is True

    def test_content_type_assente_ripiega_su_estensione_non_immagine(self):
        assert is_image_attachment("documento.pdf", None) is False

    def test_content_type_generico_ripiega_su_estensione(self):
        # Alcuni client mandano "application/octet-stream" per certi
        # upload anche quando il file è un'immagine vera.
        assert is_image_attachment("foto.webp", "application/octet-stream") is True

    def test_estensione_case_insensitive(self):
        assert is_image_attachment("FOTO.PNG", None) is True

    def test_nessuna_estensione_riconosciuta(self):
        assert is_image_attachment("script.py", None) is False


class TestIsWithinSizeLimit:
    def test_dimensione_sotto_il_limite(self):
        assert is_within_size_limit(1024) is True

    def test_dimensione_esattamente_al_limite(self):
        assert is_within_size_limit(MAX_SOURCE_IMAGE_BYTES) is True

    def test_dimensione_oltre_il_limite(self):
        assert is_within_size_limit(MAX_SOURCE_IMAGE_BYTES + 1) is False


class TestBytesToDataUri:
    def test_formato_corretto(self):
        uri = bytes_to_data_uri(b"contenuto finto", mime_type="image/webp")
        assert uri.startswith("data:image/webp;base64,")

    def test_contenuto_decodificabile(self):
        import base64
        originale = b"un po' di byte qualsiasi \x00\x01\x02"
        uri = bytes_to_data_uri(originale)
        parte_base64 = uri.split(",", 1)[1]
        assert base64.b64decode(parte_base64) == originale

    def test_mime_type_di_default(self):
        uri = bytes_to_data_uri(b"x")
        assert uri.startswith("data:image/webp;base64,")

    def test_bytes_vuoti_non_falliscono(self):
        uri = bytes_to_data_uri(b"")
        assert uri == "data:image/webp;base64,"
