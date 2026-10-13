"""Shared runtime state (one App per process) so tool executors, the agent loop,
the REPL and the GUI all see the same checkpoints, skills, todos, MCP and UI."""


class App:
    def __init__(self, cfg, ui=None):
        from .session import Checkpoints
        from .skills import discover_skills, ensure_builtin_skills
        self.cfg = cfg
        self.checkpoints = Checkpoints()
        ensure_builtin_skills()
        self.skills = discover_skills()
        self.todos = []               # [{"text": str, "status": "pending|in_progress|done"}]
        self.mcp = None               # McpManager
        self.ui = ui                  # TerminalUI / WebUI
        self.pending_context = []     # extra context prepended to the next user message
        self.touched_files = []       # files modified this session (for /diff, autocommit)
        self.session_events = []      # ledger events this session (for conscience reflection)
        self.client = None            # LLMClient (set by the REPL/GUI)
        self.perms = None             # Permissions
        self.history = None           # live conversation (list) — GUI/subagents peek at it
        self.oneshot = False
        self.memory_hits = 0
        self.memory = None            # memory.MemoryStore (lazy)
        self.index = None             # rag.Index (lazy)
        self.hooks = None             # hooks.HookRunner
        self.agent_depth = 0          # spawn_agent nesting
        self.session_id = self.checkpoints.session_id

    def memory_store(self):
        if self.memory is None:
            from .memory import MemoryStore
            self.memory = MemoryStore(self.cfg)
        return self.memory

    def rag_index(self):
        if self.index is None:
            from .rag import Index
            self.index = Index(cfg=self.cfg)
            self.index.load()
        return self.index

    def touch(self, path):
        p = str(path)
        if p not in self.touched_files:
            self.touched_files.append(p)


APP = None


def app():
    return APP


def set_app(a):
    global APP
    APP = a
    return a
