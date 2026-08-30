from printdirector.config import load_config

def test_config(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("""printers:
- id: a
  name: A
  moonraker_url: http://x
  obs: {scene: A}
""", encoding="utf-8")
    assert load_config(p).printers[0].id == "a"
