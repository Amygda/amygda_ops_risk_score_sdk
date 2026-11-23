"""Install the bundled risk-score agent skill into AI coding agents.

The skill ships inside this package (``amygda_ops_risk_score/skill/risk-score``)
so its version always matches the installed SDK. This module copies it to the
folders agents read skills from:

* ``.claude/skills/``  — Claude Code
* ``.agents/skills/``  — the shared Agent Skills folder read by OpenAI Codex,
  Cursor, GitHub Copilot and Gemini CLI

Usage (installed as the ``amygda-risk-skill`` command)::

    amygda-risk-skill install                  # this project, all agents
    amygda-risk-skill install --global         # every project on this machine
    amygda-risk-skill install --agent claude   # one agent only
    amygda-risk-skill uninstall
    amygda-risk-skill where                    # show the bundled skill
    amygda-risk-skill examples                 # guides, examples, sample data
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

SKILL_NAME = "risk-score"
MARKER_FILE = ".amygda-skill-version"
AGENTS_MD_START = "<!-- amygda-risk-score-skill:start -->"
AGENTS_MD_END = "<!-- amygda-risk-score-skill:end -->"

CLAUDE_DIR = Path(".claude") / "skills"
SHARED_DIR = Path(".agents") / "skills"

# Agent name -> skill folders it reads, relative to the project or home dir.
AGENT_TARGETS: dict[str, list[Path]] = {
    "all": [CLAUDE_DIR, SHARED_DIR],
    "claude": [CLAUDE_DIR],
    "codex": [SHARED_DIR],
    "cursor": [SHARED_DIR],
    "copilot": [SHARED_DIR],
    "gemini": [SHARED_DIR],
    "other": [SHARED_DIR],
}


# The guides, example notebooks and sample data live in the public SDK repo,
# not in the package, so every install isn't 5 MB bigger.
EXAMPLES_REPO = "https://codeload.github.com/Amygda/amygda_ops_risk_score_sdk"
EXAMPLES_DIR = "amygda_how_to"
_EXAMPLES_SRC = "how_to"


def bundled_skill_dir() -> Path:
    """Return the folder holding the skill shipped with this SDK."""
    return Path(__file__).resolve().parent / "skill" / SKILL_NAME


def _sdk_version() -> str:
    # Read from package metadata: importing the package pulls in plotting libs.
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("amygda-ops-risk-score")
    except PackageNotFoundError:
        from amygda_ops_risk_score import __version__

        return __version__


def _is_ours(dest: Path) -> bool:
    """True if ``dest`` is a skill folder this installer wrote earlier."""
    return (dest / MARKER_FILE).is_file()


def _copy_skill(dest: Path, force: bool) -> str:
    """Copy the bundled skill to ``dest``. Returns 'installed' or 'updated'."""
    src = bundled_skill_dir()
    if not (src / "SKILL.md").is_file():
        raise RuntimeError(
            f"Bundled skill not found at {src}. Reinstall the SDK: "
            "pip install --upgrade "
            "git+https://github.com/amygda/amygda_ops_risk_score_sdk.git"
        )
    status = "installed"
    if dest.exists():
        if not _is_ours(dest) and not force:
            raise FileExistsError(
                f"{dest} already exists and was not installed by "
                "amygda-risk-skill. Re-run with --force to replace it."
            )
        shutil.rmtree(dest)
        status = "updated"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))
    (dest / MARKER_FILE).write_text(_sdk_version() + "\n")
    return status


def _agents_md_section(skill_path: Path) -> str:
    return (
        f"{AGENTS_MD_START}\n"
        "## Amygda ops risk score\n\n"
        "When the user asks about risk scores, ops risk, equipment risk, "
        "predictive maintenance or the Amygda SDK, read "
        f"`{skill_path.as_posix()}/SKILL.md` and follow it. Load the files in "
        "its `references/` folder when SKILL.md says to.\n"
        f"{AGENTS_MD_END}\n"
    )


def _write_agents_md(base: Path, skill_rel: Path) -> Path:
    """Add or refresh a pointer to the skill in ``AGENTS.md``."""
    agents_md = base / "AGENTS.md"
    section = _agents_md_section(skill_rel)
    text = agents_md.read_text() if agents_md.exists() else ""
    if AGENTS_MD_START in text and AGENTS_MD_END in text:
        head, rest = text.split(AGENTS_MD_START, 1)
        _, tail = rest.split(AGENTS_MD_END, 1)
        text = head + section.rstrip("\n") + tail
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + section
    agents_md.write_text(text)
    return agents_md


def _remove_agents_md(base: Path) -> bool:
    agents_md = base / "AGENTS.md"
    if not agents_md.exists():
        return False
    text = agents_md.read_text()
    if AGENTS_MD_START not in text or AGENTS_MD_END not in text:
        return False
    head, rest = text.split(AGENTS_MD_START, 1)
    _, tail = rest.split(AGENTS_MD_END, 1)
    new = (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip("\n")
    if new:
        agents_md.write_text(new + "\n")
    else:
        agents_md.unlink()
    return True


def _base_dir(global_: bool, path: str | None) -> Path:
    if global_:
        return Path.home()
    return Path(path).expanduser().resolve() if path else Path.cwd()


def install(
    agent: str = "all",
    global_: bool = False,
    path: str | None = None,
    force: bool = False,
) -> list[Path]:
    """Install the skill for ``agent``. Returns the folders written."""
    if agent not in AGENT_TARGETS:
        raise ValueError(
            f"Unknown agent '{agent}'. Choose from: {', '.join(AGENT_TARGETS)}"
        )
    if agent == "other" and global_:
        raise ValueError("--agent other writes AGENTS.md, so it needs a project.")
    base = _base_dir(global_, path)
    written = []
    for rel in AGENT_TARGETS[agent]:
        dest = base / rel / SKILL_NAME
        status = _copy_skill(dest, force)
        print(f"  {status}: {dest}")
        written.append(dest)
    if agent == "other":
        md = _write_agents_md(base, SHARED_DIR / SKILL_NAME)
        print(f"  pointer added: {md}")
    return written


def uninstall(global_: bool = False, path: str | None = None) -> list[Path]:
    """Remove skill folders this installer wrote. Returns the folders removed."""
    base = _base_dir(global_, path)
    removed = []
    for rel in (CLAUDE_DIR, SHARED_DIR):
        dest = base / rel / SKILL_NAME
        if dest.exists() and _is_ours(dest):
            shutil.rmtree(dest)
            print(f"  removed: {dest}")
            removed.append(dest)
            # Tidy up folders we may have created, only if now empty.
            for folder in (dest.parent, dest.parent.parent):
                if folder != base and not any(folder.iterdir()):
                    folder.rmdir()
    if not global_ and _remove_agents_md(base):
        print(f"  pointer removed: {base / 'AGENTS.md'}")
    if not removed:
        print("  nothing to remove")
    return removed


def _download(url: str) -> bytes | None:
    """Fetch ``url``. Returns None when it doesn't exist (HTTP 404)."""
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Could not download the examples ({exc}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not download the examples ({exc.reason}). "
            "Check your internet connection and try again."
        ) from exc


def _extract_how_to(archive: bytes, dest: Path) -> int:
    """Write the archive's ``how_to/`` folder into ``dest``. Returns files written."""
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            # <repo>-<ref>/how_to/...: keep only regular files under how_to/.
            if len(parts) < 3 or parts[1] != _EXAMPLES_SRC or not member.isfile():
                continue
            rel = parts[2:]
            if any(p in ("", ".", "..") for p in rel):
                continue
            target = dest.joinpath(*rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src is None:
                continue
            with src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    if count == 0:
        raise RuntimeError("The download had no examples in it.")
    return count


def examples(path: str | None = None, force: bool = False) -> Path:
    """Download the guides, example notebooks and sample data for this SDK.

    They go into ``amygda_how_to/`` in the current folder, or ``path``. The
    copy matches the installed SDK version when that version is published,
    and is the latest otherwise.
    """
    dest = Path(path).expanduser().resolve() if path else Path.cwd() / EXAMPLES_DIR
    if dest.exists() and any(dest.iterdir()):
        if not force:
            raise FileExistsError(
                f"{dest} already exists. Use --force to replace it, or --path "
                "to put the examples somewhere else."
            )
    version = _sdk_version()
    archive = _download(f"{EXAMPLES_REPO}/tar.gz/refs/tags/v{version}")
    source = f"SDK {version}"
    if archive is None:
        archive = _download(f"{EXAMPLES_REPO}/tar.gz/refs/heads/main")
        source = "the latest SDK"
        if archive is None:
            raise RuntimeError("Could not find the examples to download.")
    tmp = dest.with_name(dest.name + ".download")
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        count = _extract_how_to(archive, tmp)
        if dest.exists():
            shutil.rmtree(dest)
        tmp.rename(dest)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print(f"  {count} files from {source}: {dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amygda-risk-skill",
        description="Install the Amygda risk-score skill into AI coding agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="install or update the skill")
    p_install.add_argument(
        "--agent",
        default="all",
        choices=list(AGENT_TARGETS),
        help=(
            "which agent to install for (default: all). codex, cursor, copilot "
            "and gemini share .agents/skills; 'other' also adds a pointer to "
            "AGENTS.md for tools without skill support"
        ),
    )
    scope = p_install.add_mutually_exclusive_group()
    scope.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="install in your home folder so every project sees it",
    )
    scope.add_argument(
        "--path", help="project folder to install into (default: current folder)"
    )
    p_install.add_argument(
        "--force",
        action="store_true",
        help="replace an existing risk-score skill not installed by this command",
    )

    p_uninstall = sub.add_parser("uninstall", help="remove the installed skill")
    scope_u = p_uninstall.add_mutually_exclusive_group()
    scope_u.add_argument("--global", dest="global_", action="store_true")
    scope_u.add_argument("--path")

    sub.add_parser("where", help="show the skill bundled with this SDK")

    p_examples = sub.add_parser(
        "examples",
        help="download the guides, example notebooks and sample data",
    )
    p_examples.add_argument(
        "--path",
        help=f"folder to put them in (default: ./{EXAMPLES_DIR})",
    )
    p_examples.add_argument(
        "--force", action="store_true", help="replace the folder if it exists"
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            print(f"Amygda risk-score skill (SDK {_sdk_version()})")
            install(args.agent, args.global_, args.path, args.force)
            print(
                "\nDone. Start a new session in your agent and ask about "
                "'risk score' to use it."
            )
        elif args.command == "uninstall":
            uninstall(args.global_, args.path)
        elif args.command == "examples":
            print("Amygda guides, examples and sample data")
            dest = examples(args.path, args.force)
            print(
                f"\nDone. Open {dest / 'how_to.md'} for what is in there, then "
                f"run the notebooks from {dest / 'examples'}."
            )
        else:
            print(f"SDK {_sdk_version()}: {bundled_skill_dir()}")
    except (FileExistsError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
