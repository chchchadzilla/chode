import json

from chode.memory import MemoryStore, append_note, instruction_files, instructions_block, parse_reflection, tokenize


def test_tokenize_splits_identifiers():
    assert "camel" in tokenize("camelCaseName") and "case" in tokenize("camelCaseName")
    assert "snake" in tokenize("snake_case_name")
    assert "the" not in tokenize("the thing")


def test_store_add_search_forget(project):
    tmp, cfg, app = project
    m = MemoryStore(cfg)
    e = m.add("We decided to use SQLite for the cache because it needs no server", kind="decision")
    assert e and e["kind"] == "decision"
    assert m.add("  we DECIDED to use sqlite for the cache because it needs no server ", kind="decision")["id"] == e["id"]
    g = m.add("User likes short commit messages", kind="preference", scope="global")
    hits = m.search("sqlite cache")
    assert hits and hits[0][1]["id"] == e["id"]
    block = m.recall_block("cache")
    assert "SQLite" in block and "short commit" in block  # global preferences always ride along
    assert m.forget(e["id"]) and not m.forget("nope")
    assert len(m.all("project")) == 0 and len(m.all("global")) == 1
    md = m.export_markdown()
    assert "global" in md and g["id"] in md


def test_store_persists_across_instances(project):
    tmp, cfg, app = project
    MemoryStore(cfg).add("persist me", kind="fact")
    assert any(e["text"] == "persist me" for e in MemoryStore(cfg).all())


def test_instruction_files_precedence(project):
    tmp, cfg, app = project
    (tmp / "AGENTS.md").write_text("# agents\nbe terse", encoding="utf-8")
    (tmp / "CHODE.md").write_text("# chode\nproject rules", encoding="utf-8")
    sub = tmp / "pkg"
    sub.mkdir()
    (sub / "CLAUDE.md").write_text("nested claude rules here!", encoding="utf-8")
    import os
    os.chdir(sub)
    names = [n for n, _, _ in instruction_files() if n != "global"]
    assert names == ["CHODE.md", "AGENTS.md", "CLAUDE.md"]
    block = instructions_block()
    assert "project rules" in block and "be terse" in block and "nested claude" in block


def test_append_note_and_reflection(project):
    tmp, cfg, app = project
    p = append_note("remember the thing")
    assert p.read_text(encoding="utf-8").strip().endswith("- remember the thing")
    assert parse_reflection("junk") == []
    out = parse_reflection('here: [{"kind":"lesson","scope":"global","text":"tests first"}, {"text":"x"}]')
    assert out[0]["kind"] == "lesson" and out[1]["kind"] == "fact"
