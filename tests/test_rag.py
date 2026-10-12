from chode.rag import Index, chunk_lines, format_results, list_source_files


def test_chunking():
    assert chunk_lines([]) == []
    assert chunk_lines(["x"] * 10, size=50) == [(1, 10)]
    ch = chunk_lines(["x"] * 120, size=50, overlap=8)
    assert ch[0] == (1, 50) and ch[1][0] == 43 and ch[-1][1] == 120


def test_build_search_incremental(project):
    tmp, cfg, app = project
    (tmp / "auth.py").write_text("def verify_password(user, pw):\n    return hash_password(pw) == user.pw_hash\n", encoding="utf-8")
    (tmp / "billing.py").write_text("def charge_card(card, amount):\n    return stripe.charge(card, amount)\n", encoding="utf-8")
    (tmp / "image.png").write_bytes(b"\x89PNG\x00\x00")
    idx = Index(tmp, cfg)
    st = idx.build()
    assert st["files"] == 2 and st["chunks"] == 2
    assert ".chode/" in (tmp / ".gitignore").read_text(encoding="utf-8")
    res = idx.search("verify password hash")
    assert res and res[0]["path"] == "auth.py" and "verify_password" in res[0]["snippet"]
    assert "auth.py:1-" in format_results(res)
    st2 = Index(tmp, cfg)
    assert st2.load() and st2.build()["changed"] == 0
    (tmp / "billing.py").write_text("def refund(card):\n    pass\n", encoding="utf-8")
    assert Index(tmp, cfg).build()["changed"] >= 1
    idx3 = Index(tmp, cfg)
    idx3.load()
    assert idx3.search("refund card")[0]["path"] == "billing.py"
    assert format_results([]).startswith("No matches")


def test_embeddings_hybrid(project, mock_llm):
    tmp, cfg, app = project
    (tmp / "a.py").write_text("alpha beta gamma\n", encoding="utf-8")
    (tmp / "b.py").write_text("delta epsilon zeta\n", encoding="utf-8")
    with mock_llm() as m:
        cfg["base_urls"]["local"] = m.url
        from chode.llm import LLMClient
        client = LLMClient(cfg)
        idx = Index(tmp, cfg)
        st = idx.build(embed=client.embed)
        assert st["embedded"] and idx.dims == 3
        res = idx.search("alpha", embed=client.embed)
        assert res and res[0]["path"] == "a.py"
        again = Index(tmp, cfg)
        assert again.load() and again.vectors is not None


def test_list_source_files_prefers_git(project):
    tmp, cfg, app = project
    (tmp / "keep.py").write_text("x", encoding="utf-8")
    (tmp / "ignored.log").write_text("x", encoding="utf-8")
    (tmp / ".gitignore").write_text("*.log\n", encoding="utf-8")
    names = [p.name for p in list_source_files(tmp)]
    assert "keep.py" in names and "ignored.log" not in names
