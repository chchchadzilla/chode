from chode import conscience


def test_default_and_learned(project):
    text = conscience.load()
    assert "## Principles" in text and "## Learned" in text
    assert conscience.add_learned("confirm before deleting branches")
    assert not conscience.add_learned("confirm before deleting branches")  # dedupe
    assert "confirm before deleting branches" in conscience.load()
    assert conscience.block(200).startswith("Your conscience")


def test_ledger_and_reflection(project):
    tmp, cfg, app = project
    conscience.log("danger_denied", command="rm -rf /", detail="recursive delete")
    conscience.log("undo", detail="restored x")
    tail = conscience.tail(2)
    assert tail[-1]["event"] == "undo" and len(app.session_events) == 2
    assert "refused a dangerous command" in conscience.format_event(tail[0])
    assert "×1" in conscience.session_summary(app.session_events)
    prompt = conscience.reflect_prompt(app.session_events)
    assert "ledger" in prompt and "rm -rf" in prompt
    assert conscience.apply_reflection("NONE") is False
    assert conscience.apply_reflection("Ask before force-pushing shared branches.")


def test_learned_is_bounded(project):
    for i in range(80):
        conscience.add_learned(f"lesson number {i}")
    learned = conscience.load().split("## Learned")[1].strip().splitlines()
    assert len(learned) <= conscience.MAX_LEARNED_LINES
