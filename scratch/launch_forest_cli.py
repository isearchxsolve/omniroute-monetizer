"""Launch lightweight parallel aider CLI sessions on forest models.

VS Code is too heavy for parallel sessions. aider is a single Python binary
(~50-100MB RAM) that speaks OpenAI-compatible endpoints — perfect for running
many concurrent coding agents in plain terminal windows.

Usage:
  python launch_forest_cli.py --list                 # show slots
  python launch_forest_cli.py nvidia-1               # launch 1 session
  python launch_forest_cli.py nvidia-1 nvidia-2 alibaba   # launch 3 parallel
  python launch_forest_cli.py nvidia-1 --dry-run     # print command, don't spawn
  python launch_forest_cli.py nvidia-1 --dir D:\myproject

Each slot = one forest key + a proven coding model. Keys are read from
state/forest_keys.json at launch (never hardcoded here).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

KEYS = Path(r"d:\omniroute-monetizer\state\forest_keys.json")

# Directories never loaded into the chat context
SKIP_DIRS = {
    "node_modules", ".next", ".venv", "venv", "__pycache__", ".git",
    ".pytest_cache", ".ruff_cache", ".aider.tags.cache.v4", ".swc",
    "dist", "build", ".turbo", ".cache", "htmlcov", ".neon_worktrees",
    ".continue", ".trae", ".zcode", ".uploads", "attached_assets",
    "gui-test-screenshots", ".github", ".vscode", ".idea",
}
# Extensions considered source files
SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".yml",
    ".yaml", ".toml", ".md", ".txt", ".sh", ".ps1", ".bat", ".css",
    ".html", ".sql", ".env.example", ".dockerfile",
}
SOURCE_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "makefile",
    ".env.example", "procfile", "requirements.txt", "package.json",
}
# NEVER load these into the chat (secrets / credentials / keys)
SECRET_PATTERNS = (
    ".env", ".env1", ".env.local", ".env.production", "hosts.yml",
    "credentials", "secret", ".pem", ".key", ".p12", ".pfx", "id_rsa",
    "wallet", "auth.json", "token.json",
)
# NEVER load logs into the chat (huge, often UTF-16, burn context)
LOG_EXTS = {".log"}
LOG_NAME_HINTS = ("server.log", "run.log", "output.log", "debug.log")
# NEVER load lockfiles (machine-generated, huge, zero editing value)
LOCKFILE_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                  "poetry.lock", "composer.lock", "gemfile.lock"}
MAX_FILES = 12          # cap on files added to chat
MAX_FILE_KB = 30        # skip non-source files bigger than this
MAX_SOURCE_KB = 80      # source files may be bigger (real modules are 30-60KB)
MAX_TOTAL_KB = 120      # ~30k tokens total context budget
# Docs that missions typically require UPDATING -> load editable, not read-only
EDITABLE_DOC_NAMES = {"unified.md", "plan.md", "readme.md", "changes.md",
                      "what_changed.md", "problem_tracker.md",
                      "neon_architect_problem_tracker.md"}
AIDER = r"C:\Users\Admin\.local\bin\aider.exe"
WRAPPER = Path(__file__).parent / "aider_session_wrapper.py"
MODEL_SETTINGS = Path(r"d:\omniroute-monetizer\state\aider_model_settings.yml")
MODEL_METADATA = Path(r"d:\omniroute-monetizer\state\aider_model_metadata.json")
LAUNCH_SPECS = Path(r"d:\omniroute-monetizer\state\launch_specs")
# Per-agent work logs: each slot's full conversation + every LLM call is
# captured here as it happens so the fleet can be monitored live.
FLEET_LOGS = Path(r"d:\omniroute-monetizer\state\fleet_logs")

# slot -> (provider, key_index, base_url, main_model, weak_model)
SLOTS = {
    "nvidia-1": ("nvidia", 0, "https://integrate.api.nvidia.com/v1",
                 "openai/nvidia/nemotron-3-super-120b-a12b", "openai/nvidia/nemotron-nano-12b-v2-vl"),
    "nvidia-2": ("nvidia", 1, "https://integrate.api.nvidia.com/v1",
                 "openai/nvidia/nemotron-3-super-120b-a12b", "openai/nvidia/nemotron-nano-12b-v2-vl"),
    "nvidia-3": ("nvidia", 2, "https://integrate.api.nvidia.com/v1",
                 "openai/nvidia/nemotron-3-ultra-550b-a55b", "openai/nvidia/nemotron-nano-12b-v2-vl"),
    "nvidia-4": ("nvidia", 3, "https://integrate.api.nvidia.com/v1",
                 "openai/nvidia/nemotron-3-super-120b-a12b", "openai/nvidia/nemotron-nano-12b-v2-vl"),
    "nvidia-5": ("nvidia", 4, "https://integrate.api.nvidia.com/v1",
                 "openai/nvidia/nemotron-3-super-120b-a12b", "openai/nvidia/nemotron-nano-12b-v2-vl"),
    "alibaba": ("alibaba", 0, "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                "openai/qwen3-coder-next", "openai/qwen3.5-flash"),
    "groq": ("groq", 0, "https://api.groq.com/openai/v1",
             "openai/llama-3.3-70b-versatile", "openai/llama-3.1-8b-instant"),
    "cohere": ("cohere", 0, "https://api.cohere.com/compatibility/v1",
               "openai/command-a-03-2025", "openai/command-r7b-12-2024"),
    "openrouter": ("openrouter", 0, "https://openrouter.ai/api/v1",
                   "openai/z-ai/glm-5.2:free", "openai/z-ai/glm-4.5-air"),
    # TokenRouter: 6 separate accounts, one slot each (per-account RPM ~8,
    # so parallel slots multiply effective throughput on qwen3.8-max-free)
    "tokenrouter-1": ("_tokenrouter", 0, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
    "tokenrouter-2": ("_tokenrouter", 1, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
    "tokenrouter-3": ("_tokenrouter", 2, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
    "tokenrouter-4": ("_tokenrouter", 3, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
    "tokenrouter-5": ("_tokenrouter", 4, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
    "tokenrouter-6": ("_tokenrouter", 5, "https://api.tokenrouter.com/v1",
                      "openai/qwen/qwen3.8-max-free", "openai/qwen/qwen3.8-max-free"),
}

# TokenRouter keys live in the BYOK installer (separate accounts), not forest_keys.json
TOKENROUTER_KEYS = [
    "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",
    "sk-EZecibMiCwvb6OFzsVvaYvE1B3Ld6H64xhPA7nKbOitkCUmg",
    "sk-2n1wQq1Anbca5mc3FcE0ThTfwl7aaqA54YUAd6SjqVjhGfyu",
    "sk-tr4CjC9GqwGmHTU2lfviVNPg9JyofZ8EXM0ATUTxhIOW69Vc",
]


def get_key(provider, idx):
    if provider == "_tokenrouter":
        return TOKENROUTER_KEYS[idx % len(TOKENROUTER_KEYS)]
    data = json.loads(KEYS.read_text())
    valid = [k for k in data[provider]["keys"] if k.get("verify") == "valid"]
    return valid[idx % len(valid)]["key"]


def is_secret_file(name):
    """True if the filename looks like a secrets/credentials file."""
    n = name.lower()
    # .env.example is safe (template); bare .env and variants are secrets
    if n == ".env.example":
        return False
    for pat in SECRET_PATTERNS:
        if n == pat or n.startswith(pat + ".") or pat in n:
            return True
    return False


def is_log_file(name):
    n = name.lower()
    return any(n.endswith(e) for e in LOG_EXTS) or n in LOG_NAME_HINTS


def is_lockfile(name):
    return name.lower() in LOCKFILE_NAMES


def is_utf8_readable(p, sample=4096):
    """Cheap check that the file decodes as UTF-8 (skips UTF-16/binary)."""
    try:
        with open(p, "rb") as f:
            head = f.read(sample)
        head.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def pick_files(workdir):
    """Shallow-scan the project and pick the most relevant files for the chat.

    Priority: state/audit evidence first (they anchor the goal), then docs
    (README/AGENTS/ARCHITECTURE), then config, then source.
    Hard rules: NEVER secrets (.env etc.), NEVER logs, NEVER non-UTF-8,
    and a tight total budget (~60KB / ~15k tokens) so the model's context
    window is never exhausted.
    Returns (editable, readonly) path lists.
    """
    root = Path(workdir)
    if not root.is_dir():
        return [], []

    evidence, docs, config, source, root_source = [], [], [], [], []
    seen_names = set()  # dedup by basename (avoid 3x ARCHITECTURE.md from clone dirs)

    def eligible(p: Path, cap: float):
        """Filter only — no budget here. Budget is applied during final
        selection so high-priority files can't be shut out by whatever the
        filesystem happened to iterate first."""
        if p.name.lower() in seen_names:
            return False
        try:
            kb = p.stat().st_size / 1024
        except OSError:
            return False
        if kb > cap or kb == 0:
            return False
        if is_secret_file(p.name) or is_log_file(p.name) or is_lockfile(p.name):
            return False
        return is_utf8_readable(p)

    def take(p: Path):
        seen_names.add(p.name.lower())
        return p

    # Depth-limited walk (root files matter most)
    for depth_dir in [root] + [d for d in root.iterdir() if d.is_dir() and d.name not in SKIP_DIRS]:
        try:
            entries = list(depth_dir.iterdir())
        except OSError:
            continue
        for p in entries:
            if not p.is_file():
                continue
            name = p.name.lower()
            ext = p.suffix.lower()
            if name in SKIP_DIRS:
                continue
            # never load aider's own history/state files
            if name.startswith(".aider."):
                continue
            # 1. evidence: state files, audit/handoff docs (NOT logs)
            if any(t in name for t in ("error", "fail", "audit", "handoff",
                                       "state.json", "working_memory", "autofix",
                                       "changes", "changelog", "postmortem")):
                if eligible(p, MAX_FILE_KB):
                    evidence.append(take(p))
            # 2. docs
            elif name.startswith("readme") or name in ("agents.md", "unified.md",
                 "architecture.md", "architecture.mdx", "design.md", "design_system.md"):
                if eligible(p, MAX_FILE_KB):
                    docs.append(take(p))
            # 3. config
            elif name in SOURCE_NAMES or name in ("docker-compose.yml", "docker-compose.yaml",
                 ".env.example", "pytest.ini", "pyproject.toml", "tsconfig.json",
                 "next.config.js", "next.config.mjs", "vite.config.js", "drizzle.config.ts"):
                if eligible(p, MAX_FILE_KB):
                    config.append(take(p))
            # 4. source — root-level modules collected separately so they can
            #    be prioritized FIRST (flat projects like neon_unified keep
            #    their real code at the root), then subdir source
            elif ext in SOURCE_EXTS:
                if eligible(p, MAX_SOURCE_KB):
                    (root_source if depth_dir == root else source).append(take(p))

    # Prioritize real code: .py modules before docs-before-scripts, and within
    # each group largest first (core modules are the big ones). This stops
    # fix_*.ps1 junk from eating the editable budget ahead of real source.
    def _rank(p):
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        ext = p.suffix.lower()
        if ext == ".py":
            group = 0
        elif ext in (".ps1", ".bat", ".sh", ".cmd"):
            group = 2
        else:
            group = 1
        return (group, -size)
    root_source.sort(key=_rank)

    # Root-level source wins the editable slots; subdir source fills the rest
    source = root_source + source

    # Final selection under the total budget, in priority order:
    # editable docs > config > source > evidence (capped) > readonly docs.
    # Editable material goes FIRST so read-only evidence can never eat the
    # editable budget (ases had 8 CHANGES*.md evidence files shut out all
    # source; crypto-trader had read-only failsafe scripts do the same).
    editable_docs = [p for p in docs if p.name.lower() in EDITABLE_DOC_NAMES]
    readonly_docs = [p for p in docs if p not in editable_docs]
    evidence = evidence[:4]  # cap evidence: it anchors the goal, not the work

    def _size(p):
        try:
            return p.stat().st_size / 1024
        except OSError:
            return 0

    picked, total_kb = [], 0
    for p in editable_docs + config + source + evidence + readonly_docs:
        if len(picked) >= MAX_FILES or total_kb + _size(p) > MAX_TOTAL_KB:
            continue
        picked.append(p)
        total_kb += _size(p)

    picked_set = {str(p) for p in picked}
    readonly = [str(p) for p in (evidence + readonly_docs) if str(p) in picked_set]
    editable = [str(p) for p in (editable_docs + config + source)
                if str(p) in picked_set and str(p) not in readonly]
    return editable[:8], readonly[:8]


def goal_files(workdir, goal):
    """Extract filenames mentioned in the goal and resolve them in the project.

    Guarantees that files the goal explicitly references (e.g. UNIFIED.md,
    docker_error.txt, .autofix-state.json) are always loaded into the chat,
    even if the generic picker's caps would push them out.
    """
    if not goal:
        return []
    import re
    found = []
    root = Path(workdir)
    # filename-like tokens: contain a dot, no spaces, plausible path chars
    for tok in re.findall(r"[\w./\\-]*\.[A-Za-z0-9_]+[\w.-]*", goal):
        # rstrip only: leading dots belong to dotfiles (.autofix-state.json)
        tok = tok.rstrip(".,;:()[]{}'\"")
        if not tok or tok.startswith("http") or len(tok) > 120:
            continue
        candidates = [root / tok, root / Path(tok).name]
        # also search one level deep
        try:
            for d in [root] + [x for x in root.iterdir() if x.is_dir() and x.name not in SKIP_DIRS]:
                candidates.append(d / Path(tok).name)
        except OSError:
            pass
        for c in candidates:
            try:
                if c.is_file():
                    # never load secrets or logs, even if the goal names them
                    if is_secret_file(c.name) or is_log_file(c.name):
                        break
                    if c.stat().st_size / 1024 > MAX_FILE_KB:
                        break
                    s = str(c)
                    if s not in found:
                        found.append(s)
                    break
            except OSError:
                continue
    return found


GITIGNORE_TEMPLATE = """# secrets - never commit
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*.pfx
id_rsa*
wallet*.json
hosts.yml
credentials*

# deps / build
node_modules/
.venv/
.venv*/
venv/
__pycache__/
*.pyc
.next/
dist/
build/
.pytest_cache/
.ruff_cache/
htmlcov/

# aider / tooling state
.aider.*
.gitignore.bak
"""


def ensure_git_repo(workdir: str):
    """Make sure the project is inside a git repo so aider can build its
    repo-map (full-project symbol index) and auto-commit every edit
    (rollback safety).

    Uses `git rev-parse --show-toplevel` — NOT a `.git` existence check —
    because some projects (oioi, ases_v3_1) live inside a PARENT repo;
    running `git init` there would create a shadow nested repo.

    If no repo exists anywhere above: git init + .gitignore (secrets
    excluded) + baseline commit. Existing repos are left untouched.
    """
    root = Path(workdir)
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=workdir, capture_output=True, text=True,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        return  # already inside a repo (own or parent's) — leave it alone
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=False)
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=workdir, check=False)
    subprocess.run(
        ["git", "-c", "user.name=forest-agent",
         "-c", "user.email=forest-agent@local",
         "commit", "-q", "-m", "baseline: pre-fleet snapshot",
         "--allow-empty"],
        cwd=workdir, check=False,
    )


def detect_test_cmd(workdir: str):
    """Auto-detect the project's test command so aider can RUN tests after
    every edit (--test-cmd + --auto-test). Without this the agents can edit
    files but never verify their fixes.

    Returns (cmd, lang_hint) or (None, None).
    """
    root = Path(workdir)
    # Python: pytest config or a tests dir / test_*.py files
    py_markers = ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"]
    has_py_cfg = any((root / m).exists() for m in py_markers)
    has_tests_dir = (root / "tests").is_dir() or (root / "test").is_dir()
    has_test_py = any(root.glob("test_*.py")) or any(root.glob("*/test_*.py"))
    if has_py_cfg or has_tests_dir or has_test_py:
        # prefer an explicit tests dir if present (incl. backend/tests layout)
        if (root / "tests").is_dir():
            return "python -m pytest tests/ -x -q", "python"
        if (root / "test").is_dir():
            return "python -m pytest test/ -x -q", "python"
        if (root / "backend" / "tests").is_dir():
            return "python -m pytest backend/tests/ -x -q", "python"
        return "python -m pytest -x -q", "python"
    # Node: package.json with a real "test" script (not the npm placeholder)
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            script = (data.get("scripts") or {}).get("test", "")
            if script and "no test specified" not in script:
                return "npm test", "javascript"
        except (OSError, ValueError):
            pass
    return None, None


def write_model_settings():
    """Write a model-settings file that forces litellm to treat every forest
    model as a plain OpenAI-compatible model pointed at its own base URL.

    Without this, litellm re-parses names like 'qwen/qwen3.8-max-free' and
    treats 'qwen' as a provider, crashing with 'No active credentials for
    provider: qwen'. extra_params are merged straight into the
    litellm.completion() kwargs by aider (models.py send_completion).
    """
    lines = []
    seen = set()
    for slot, (prov, _kidx, base, main, weak) in SLOTS.items():
        for name in (main, weak):
            if name in seen:
                continue
            seen.add(name)
            lines.append(f"- name: {name}")
            # diff edit format = SEARCH/REPLACE patches. REQUIRED so large
            # files (30-60KB modules) are edited by patching, not by the
            # model re-outputting the whole file ("whole" format is
            # impossible beyond a few KB and is what blocked the agent).
            lines.append("  edit_format: diff")
            lines.append("  extra_params:")
            lines.append("    custom_llm_provider: openai")
            lines.append(f"    api_base: {base}")
    MODEL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    MODEL_SETTINGS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return MODEL_SETTINGS


# Real context windows per model (tokens). Without this, aider assumes 0 and
# cannot detect/warn about context exhaustion (the 323k-token blowup).
MODEL_CONTEXT = {
    "openai/nvidia/nemotron-3-super-120b-a12b": 1000000,
    "openai/nvidia/nemotron-3-ultra-550b-a55b": 1000000,
    "openai/nvidia/nemotron-nano-12b-v2-vl": 128000,
    "openai/qwen3-coder-next": 262144,
    "openai/qwen3.5-flash": 1000000,
    "openai/llama-3.3-70b-versatile": 128000,
    "openai/llama-3.1-8b-instant": 128000,
    "openai/command-a-03-2025": 256000,
    "openai/command-r7b-12-2024": 128000,
    "openai/z-ai/glm-5.2:free": 200000,
    "openai/z-ai/glm-4.5-air": 128000,
    "openai/qwen/qwen3.8-max-free": 262144,
}


def write_model_metadata():
    """Write a model-metadata JSON so aider knows each model's context window.

    Format matches aider's bundled resources/model-metadata.json (loaded via
    register_litellm_models -> model_info_manager.local_model_metadata).
    """
    meta = {}
    for name, ctx in MODEL_CONTEXT.items():
        meta[name] = {
            "max_tokens": min(ctx, 32768),
            "max_input_tokens": ctx,
            "max_output_tokens": min(ctx, 32768),
            "litellm_provider": "openai",
            "mode": "chat",
        }
    MODEL_METADATA.parent.mkdir(parents=True, exist_ok=True)
    MODEL_METADATA.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return MODEL_METADATA


def build_cmd(slot, workdir, goal=None, load_files=True, auto_test=True,
              extra_files=None, map_tokens=4096):
    provider, kidx, base, main, weak = SLOTS[slot]
    key = get_key(provider, kidx)
    settings = write_model_settings()
    metadata = write_model_metadata()
    cmd = [
        AIDER,
        "--model", main,
        "--weak-model", weak,
        "--openai-api-base", base,
        "--model-settings-file", str(settings),
        "--model-metadata-file", str(metadata),
        # Full-project scanning: aider builds a tree-sitter symbol map of the
        # ENTIRE repo (--map-tokens) so the model sees every file/symbol and
        # can pull in whatever it needs, instead of only a fixed preload list.
        # --subtree-only keeps the map inside this project dir.
        "--map-tokens", str(map_tokens),
        "--subtree-only",
        # NOTE: --yes-always is deliberately OMITTED.
        # aider's handle_shell_commands() calls confirm_ask(explicit_yes_required=True).
        # With yes=True, that path auto-answers "n" (rejects ALL shell commands).
        # Without --yes-always, confirm_ask falls through to input() which gets
        # EOF from DEVNULL stdin -> defaults to "y" -> shell commands auto-run.
        # --no-fancy-input forces plain input() (not prompt_toolkit) so EOF works.
        "--no-fancy-input",
        "--no-detect-urls",
        "--no-check-update",
        "--no-show-model-warnings",
    ]
    # Live monitoring: capture each agent's work as it happens.
    #  - chat-history-file : readable conversation (user goal + assistant replies)
    #  - llm-history-file  : FULL request/response of every LLM call (most detail)
    #  - input-history-file: user inputs (goal text)
    FLEET_LOGS.mkdir(parents=True, exist_ok=True)
    cmd += [
        "--chat-history-file", str(FLEET_LOGS / f"{slot}_chat.md"),
        "--llm-history-file", str(FLEET_LOGS / f"{slot}_llm.jsonl"),
        "--input-history-file", str(FLEET_LOGS / f"{slot}_input.md"),
    ]
    # Script-execution tooling: let aider RUN the project's tests after every
    # edit and iterate on failures (the whole point of "fix until green").
    if auto_test:
        test_cmd, _lang = detect_test_cmd(workdir)
        if test_cmd:
            cmd += ["--test-cmd", test_cmd, "--auto-test"]
    if load_files:
        editable, readonly = pick_files(workdir)
        # Explicit --file passthrough always wins an editable slot (use for
        # large core modules the auto-picker's budget can't fit)
        for f in (extra_files or []):
            fp = str((Path(workdir) / f).resolve() if not Path(f).is_absolute() else Path(f).resolve())
            if fp not in editable:
                editable.insert(0, fp)
        # Files named in the goal are always loaded (read-only context),
        # but never duplicate a file that is already editable
        gf = goal_files(workdir, goal)
        readonly = [f for f in (gf + readonly) if f not in editable]
        for f in editable:
            cmd += ["--file", f]
        for f in readonly:
            cmd += ["--read", f]
    if goal:
        cmd += ["-m", goal]
    env = dict(os.environ)
    env["OPENAI_API_KEY"] = key
    env["OPENAI_API_BASE"] = base
    return cmd, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slots", nargs="*", help="slot names to launch")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dir", default=os.getcwd(), help="working dir for the session")
    ap.add_argument("--goal", default=None, help="initial goal/task sent to the agent on start")
    ap.add_argument("--goal-file", default=None,
                    help="read the goal text from this file (overrides --goal); "
                         "use for extensive multi-paragraph goals")
    ap.add_argument("--file", action="append", default=[],
                    help="extra file to load EDITABLE (repeatable); use for "
                         "large core modules the auto-picker's budget can't fit")
    ap.add_argument("--no-files", action="store_true",
                    help="do not auto-load project files into the chat")
    ap.add_argument("--no-test", action="store_true",
                    help="do not auto-detect/run the project's test command after edits")
    ap.add_argument("--map-tokens", type=int, default=4096,
                    help="repo-map token budget (default 4096; lower for small-context models)")
    args = ap.parse_args()

    if args.list or not args.slots:
        print("Available slots (slot -> provider/model):")
        for s, (prov, _, base, main, _) in SLOTS.items():
            print(f"  {s:12s} {main}")
        print("\nLaunch: python launch_forest_cli.py nvidia-1 alibaba groq")
        return 0

    goal = args.goal
    if args.goal_file:
        goal = Path(args.goal_file).read_text(encoding="utf-8").strip()

    # Full-project scanning requires a git repo (repo-map + auto-commits).
    # Auto-init missing repos with a secrets-safe .gitignore + baseline commit.
    # Skipped on --dry-run: a dry run must never modify the project.
    if not args.dry_run:
        ensure_git_repo(args.dir)

    LAUNCH_SPECS.mkdir(parents=True, exist_ok=True)
    for slot in args.slots:
        if slot not in SLOTS:
            print(f"unknown slot: {slot} (use --list)")
            continue
        cmd, env = build_cmd(slot, args.dir, goal=goal,
                             load_files=not args.no_files,
                             auto_test=not args.no_test,
                             extra_files=args.file,
                             map_tokens=args.map_tokens)
        n_files = cmd.count("--file") + cmd.count("--read")
        redacted = [c if not c.startswith("sk-") and not c.startswith("nvapi-") else "<KEY>" for c in cmd]
        if args.dry_run:
            print(f"[{slot}] {n_files} files loaded | FULL CMD:")
            print("  " + " ".join(redacted))
            continue
        print(f"[{slot}] {n_files} files loaded | {' '.join(redacted[:12])} ...")
        # Write a secret-free spec; the API key travels via environment only.
        spec_path = LAUNCH_SPECS / f"{slot}.json"
        spec_path.write_text(
            json.dumps({"slot": slot, "cmd": cmd, "cwd": args.dir}, indent=2),
            encoding="utf-8",
        )
        # Spawn the wrapper (not aider directly) in a NEW console window so
        # sessions run in parallel AND the window stays open after the task
        # completes (aider -m exits by design; the wrapper blocks on input).
        subprocess.Popen(
            [sys.executable, str(WRAPPER), str(spec_path)],
            env=env, cwd=args.dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        print(f"  -> spawned new terminal window for '{slot}' (stays open after task)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
