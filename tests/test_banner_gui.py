import json
import time
import urllib.request

import pytest

from chode.banner import collision_png, collision_svg, icon_svg, image_backend, make_banner


def test_svg_and_icon(tmp_path):
    p = collision_svg("CH", "ODE", "CHODE", "tagline & co", tmp_path / "b.svg")
    svg = open(p, encoding="utf-8").read()
    assert svg.startswith("<svg") and "CHODE" in svg and "tagline &amp; co" in svg
    assert icon_svg(tmp_path / "i.svg").endswith("i.svg")


def test_png_if_pillow(tmp_path):
    pytest.importorskip("PIL")
    p = collision_png("CH", "ODE", "CHODE", "t", tmp_path / "b.png", width=400, height=130)
    assert p and (tmp_path / "b.png").stat().st_size > 1000


def test_make_banner_no_api(project):
    tmp, cfg, app = project
    assert image_backend(cfg) is None
    res = make_banner(cfg, "my-proj", "tag", tmp / "assets", use_api=False)
    assert "svg" in res and "icon" in res and "ai" not in res


def test_deck_server(project, mock_llm):
    """Boot the Deck on a free port with a scripted model; drive it over HTTP."""
    import threading
    from http.server import ThreadingHTTPServer
    from chode.gui import Deck, make_handler
    tmp, cfg, app = project
    with mock_llm(script=["hi from the deck"]) as m:
        cfg["base_urls"]["local"] = m.url
        cfg["gui"] = {"open_browser": False}
        deck = Deck(cfg)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(deck))
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        deck.start()
        base = f"http://127.0.0.1:{port}"
        try:
            r = urllib.request.urlopen(base + "/", timeout=5)
            assert "the Deck" in r.read().decode()
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/t/wrongtoken/state", timeout=5)
            api = f"{base}/t/{deck.token}"
            st = json.loads(urllib.request.urlopen(api + "/state", timeout=5).read())
            assert st["mode"] == "yolo" and "order" in st and st["provider"] == "local"
            req = urllib.request.Request(api + "/send", data=json.dumps({"message": "hello"}).encode(),
                                         headers={"Content-Type": "application/json"})
            assert json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"]
            for _ in range(50):
                time.sleep(0.1)
                if any(ev["kind"] == "text_end" for ev in deck.ui.transcript):
                    break
            kinds = [ev["kind"] for ev in deck.ui.transcript]
            assert "user" in kinds and "text_end" in kinds
            assert any(ev.get("text") == "hi from the deck" for ev in deck.ui.transcript if ev["kind"] == "text_end")
            req = urllib.request.Request(api + "/mode", data=json.dumps({"mode": "plan"}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            assert cfg["mode"] == "plan"
        finally:
            httpd.shutdown()
            httpd.server_close()
