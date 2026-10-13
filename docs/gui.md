# The Deck (GUI)

```
chode gui            # standalone
/gui                 # from a running session (same history, same brain; Ctrl-C returns to the terminal)
chode gui --port 9000
```

Zero dependencies: Python's `http.server` + Server-Sent Events + one HTML page.

- **Header:** CHODE wordmark, provider · model, mode selector (changes the live session), cost or
  "plan", context %, busy indicator.
- **Chat:** your messages, streamed assistant text rendered as markdown, tool rows (click to expand
  output), notices.
- **Permission cards:** describe + diff; buttons `allow` / `always this tool` / `always "prefix…"` /
  `deny`; dangerous ones require clicking `yes, run it`. Question cards for `ask_user`.
- **Sidebar:** ORDER score + checks with quick `/order` `/ship` `/backup` `/tidy` `undo` buttons,
  todos, memories (× to forget), session info.
- **Composer:** Enter sends, Shift+Enter newline, `/commands` work (except terminal-only ones:
  `/gui /ride /import /resume /intro /exit`).

Security: bound to `127.0.0.1`; every route carries a random per-launch token; late joiners get the
transcript replayed from memory (last 400 events). Nothing is persisted by the page itself.
