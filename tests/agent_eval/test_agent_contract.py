"""Executable policy tests for the AutoOffice agent contract."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.targets import InputKind, parse_targets
from autooffice.design import fonts
from autooffice.design.tokens import load_tokens

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENTS_PATH = "AGENTS.md"
AGENT_RULES_PATH = "docs/dev/agent-rules.md"
RELEASE_PATH = "docs/dev/release.md"
ARCHIVE_DIRECTORY = "archive/autooffice-history"
LESSONS_PATH = f"{ARCHIVE_DIRECTORY}/lessons.jsonl"
EVAL_CASES_PATH = f"{ARCHIVE_DIRECTORY}/eval-cases.md"
ARCHIVE_README_PATH = f"{ARCHIVE_DIRECTORY}/README.md"
EXPORT_ARCHIVE_PATH = "tools/history/export_archive.py"

REQUIRED_LESSON_KEYS = (
    "id",
    "date",
    "phase",
    "category",
    "title",
    "problem",
    "resolution",
    "verification",
    "files",
    "commit",
    "evidence",
)
FORBIDDEN_IMPORT_ROOTS = frozenset({"win32com", "pythoncom", "pypdf"})

NEGATIVE_PATTERN = re.compile(
    r"\b(?:tidak|bukan|jangan|dilarang|no|never|not)\b",
    re.IGNORECASE,
)
HISTORY_PATTERN = re.compile(r"\b(?:riwayat|history)\b", re.IGNORECASE)
REWRITE_PATTERN = re.compile(
    r"(?:tulis ulang|menulis ulang|ditulis ulang|rewrite|rewritten|rewriting)",
    re.IGNORECASE,
)
REWRITE_COMMAND_PATTERN = re.compile(
    r"(?:git\s+rebase|commit\s+--amend|push\s+--force|force[- ]push)",
    re.IGNORECASE,
)
ENFORCEMENT_PATH_PATTERN = re.compile(r"(?<![\w./-])((?:tools|tests)/[A-Za-z0-9_./-]+?\.py)\b")
RULE_HEADING_PATTERN = re.compile(r"(?m)^##\s+(?:\d+[.)]\s|R\d+\b|Rule\b|Aturan\b)")
RULE_BULLET_PATTERN = re.compile(r"(?m)^-\s+(?:\*\*)?(?:R\d+\b|Rule\b|Aturan\b)")


def _policy_text(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"required policy file is missing: {relative}"
    return path.read_text(encoding="utf-8")


def _paragraphs(text: str) -> list[str]:
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def _contains_all(block: str, *patterns: str) -> bool:
    return all(re.search(pattern, block, re.IGNORECASE) for pattern in patterns)


def test_agents_md_forbids_pdf_and_all_targets() -> None:
    """Keep the CLI target surface free of removed pdf and all targets."""
    text = _policy_text(AGENTS_PATH)
    matching = [
        block
        for block in _paragraphs(text)
        if _contains_all(block, r"\bpdf\b", r"\ball\b", r"\btarget\b")
        and NEGATIVE_PATTERN.search(block)
    ]
    assert matching, "AGENTS.md must state that targets `pdf` and `all` do not exist"


def test_agents_md_forbids_com_automation() -> None:
    """Keep COM and Windows-only Office automation out of the project."""
    text = _policy_text(AGENTS_PATH)
    matching = [
        block
        for block in _paragraphs(text)
        if re.search(r"\bCOM\b", block) and NEGATIVE_PATTERN.search(block)
    ]
    assert matching, "AGENTS.md must forbid COM automation"


def test_agents_md_pins_arial_with_liberation_sans_measurement() -> None:
    """Freeze the Arial output family and Liberation Sans measurement font."""
    text = _policy_text(AGENTS_PATH)
    assert re.search(r"\bArial\b", text), "AGENTS.md must name Arial as the output family"
    assert "Liberation Sans" in text, "AGENTS.md must name Liberation Sans as the measurement font"
    measurement = re.search(
        r"(?is)(?:ukur|measure|metrik).{0,240}Liberation Sans"
        r"|Liberation Sans.{0,240}(?:ukur|measure|metrik)",
        text,
    )
    assert measurement, "AGENTS.md must connect Liberation Sans to text measurement"


def test_agents_md_requires_gate_before_commit() -> None:
    """Require the quality gate to pass before any commit."""
    text = _policy_text(AGENTS_PATH)
    assert "tools/quality/gate.py" in text, "AGENTS.md must name the quality gate command"
    ordering = re.search(
        r"(?is)\bgate\b.{0,240}\bcommit\b|\bcommit\b.{0,240}\bgate\b",
        text,
    )
    assert ordering, "AGENTS.md must require the gate before commit"


def test_agents_md_requires_execution_log_entry() -> None:
    """Require every solved execution problem to be recorded in the log."""
    text = _policy_text(AGENTS_PATH)
    assert "AUTO_OFFICE_EXECUTION_LOG.md" in text, (
        "AGENTS.md must name AUTO_OFFICE_EXECUTION_LOG.md"
    )
    record = re.search(
        r"(?is)\b(?:entri|entry)\b.{0,240}AUTO_OFFICE_EXECUTION_LOG\.md"
        r"|AUTO_OFFICE_EXECUTION_LOG\.md.{0,240}\b(?:entri|entry)\b",
        text,
    )
    assert record, "AGENTS.md must require an execution log entry"


def test_agents_md_declares_main_as_only_permanent_branch() -> None:
    """Permit only main as the permanent branch."""
    text = _policy_text(AGENTS_PATH)
    pattern = re.compile(
        r"(?is)(?:\b(?:hanya|only|satu-satunya)\b.{0,120}\bmain\b"
        r"|\bmain\b.{0,120}\b(?:permanen|permanent|satu-satunya|only)\b)"
    )
    assert pattern.search(text), "AGENTS.md must state that only `main` is permanent"


def test_agents_md_names_release_and_archive_tags() -> None:
    """Freeze the permanent tag names and the release tag shape."""
    text = _policy_text(AGENTS_PATH)
    assert "pre-pdf-removal" in text, "AGENTS.md must keep the `pre-pdf-removal` tag"
    assert "backup/main-before-msg-rewrite" in text, (
        "AGENTS.md must keep the `backup/main-before-msg-rewrite` tag"
    )
    version_tag = re.search(r"\bvX\.Y\.Z\b|\bv\d+\.\d+\.\d+\b", text)
    assert version_tag, "AGENTS.md must describe release tags as vX.Y.Z"


def test_agents_md_forbids_history_rewrite() -> None:
    """Keep history append-only; rewriting published history is forbidden."""
    text = _policy_text(AGENTS_PATH)
    history_blocks = [
        block
        for block in _paragraphs(text)
        if HISTORY_PATTERN.search(block) and REWRITE_PATTERN.search(block)
    ]
    command_blocks = [
        block
        for block in _paragraphs(text)
        if REWRITE_COMMAND_PATTERN.search(block) and NEGATIVE_PATTERN.search(block)
    ]
    assert history_blocks or command_blocks, "AGENTS.md must forbid rewriting Git history"
    assert not history_blocks or any(NEGATIVE_PATTERN.search(block) for block in history_blocks), (
        "AGENTS.md must state that history rewrite is forbidden"
    )


def test_agent_rules_has_at_least_twelve_rule_entries() -> None:
    """Require a substantial rule catalogue, using one heading convention."""
    text = _policy_text(AGENT_RULES_PATH)
    heading_count = len(RULE_HEADING_PATTERN.findall(text))
    bullet_count = len(RULE_BULLET_PATTERN.findall(text))
    if not heading_count:
        heading_count = len(re.findall(r"(?m)^## .+$", text))
    if not bullet_count:
        bullet_count = len(re.findall(r"(?m)^- (?!\[).+$", text))
    entry_count = max(heading_count, bullet_count)
    assert entry_count >= 12, (
        f"{AGENT_RULES_PATH} must contain at least 12 rules; "
        f"found {heading_count} '## ' headings and {bullet_count} '- ' entries"
    )


def test_agent_rules_references_existing_enforcement_files() -> None:
    """Every referenced enforcement path must exist in the repository."""
    text = _policy_text(AGENT_RULES_PATH)
    referenced = sorted(set(ENFORCEMENT_PATH_PATTERN.findall(text)))
    assert len(referenced) >= 2, (
        f"{AGENT_RULES_PATH} must reference at least two enforcement files; found {referenced}"
    )
    missing = [relative for relative in referenced if not (REPO_ROOT / relative).is_file()]
    assert missing == [], f"{AGENT_RULES_PATH} references missing files: {missing}"


def test_release_doc_references_archive_exporter() -> None:
    """Release instructions must document the archive exporter."""
    text = _policy_text(RELEASE_PATH)
    assert "tools/history/export_archive.py" in text, (
        f"{RELEASE_PATH} must reference tools/history/export_archive.py"
    )


def _read_lessons() -> list[dict[str, object]]:
    text = _policy_text(LESSONS_PATH)
    records: list[dict[str, object]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{LESSONS_PATH}:{number} is not valid JSON: {exc}")
        assert isinstance(raw, dict), f"{LESSONS_PATH}:{number} must be a JSON object"
        records.append(raw)
    return records


def test_lessons_jsonl_contains_all_log_entries() -> None:
    """Require one valid JSON lesson record for every dated log entry."""
    records = _read_lessons()
    assert len(records) >= 48, (
        f"{LESSONS_PATH} must contain all 48 dated log entries; found {len(records)}"
    )


def test_lessons_records_have_required_keys() -> None:
    """Require every lesson record to carry the full schema keys."""
    records = _read_lessons()
    assert records, f"{LESSONS_PATH} must contain at least one record"
    incomplete = [
        (index, sorted(set(REQUIRED_LESSON_KEYS) - set(record)))
        for index, record in enumerate(records, start=1)
        if not set(REQUIRED_LESSON_KEYS).issubset(record)
    ]
    assert incomplete == [], f"{LESSONS_PATH} records missing required keys: {incomplete[:5]}"


def test_eval_cases_has_at_least_twelve_case_blocks() -> None:
    """Require at least 12 reproducible evaluation cases."""
    text = _policy_text(EVAL_CASES_PATH)
    level_three = len(re.findall(r"(?m)^### .+$", text))
    level_four = len(re.findall(r"(?m)^#### .+$", text))
    case_count = max(level_three, level_four)
    assert case_count >= 12, (
        f"{EVAL_CASES_PATH} must contain at least 12 case blocks; "
        f"found {level_three} '### ' and {level_four} '#### ' headings"
    )


def test_archive_readme_documents_clone_and_bundle() -> None:
    """Archive restore instructions must cover clone and bundle files."""
    text = _policy_text(ARCHIVE_README_PATH)
    assert "git clone" in text, f"{ARCHIVE_README_PATH} must document `git clone`"
    bundle = re.search(r"autooffice-(?:<[^>\s]+>|[A-Za-z0-9._-]+)\.bundle", text)
    assert bundle, f"{ARCHIVE_README_PATH} must mention autooffice-<tag>.bundle"


def test_export_archive_help_exits_zero() -> None:
    """Run the archive exporter through an isolated help subprocess."""
    script = REPO_ROOT / EXPORT_ARCHIVE_PATH
    assert script.is_file(), f"missing archive exporter: {EXPORT_ARCHIVE_PATH}"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    assert completed.returncode == 0, (
        f"`python {EXPORT_ARCHIVE_PATH} --help` exited {completed.returncode}:\n{output}"
    )
    assert "usage" in output.lower(), (
        f"`python {EXPORT_ARCHIVE_PATH} --help` printed no usage:\n{output}"
    )


def test_parse_targets_accepts_docx_for_markdown() -> None:
    """Markdown input builds only DOCX."""
    assert parse_targets("docx", InputKind.MARKDOWN) == ("docx",)


@pytest.mark.parametrize("target", ["pptx", "slides"])
def test_parse_targets_accepts_deck_targets(target: str) -> None:
    """Deck input accepts the pptx and slides targets."""
    assert parse_targets(target, InputKind.DECK) == (target,)


@pytest.mark.parametrize(
    ("target", "kind"),
    [
        ("pdf", InputKind.MARKDOWN),
        ("all", InputKind.MARKDOWN),
        ("pdf", InputKind.DECK),
        ("all", InputKind.DECK),
    ],
    ids=["pdf-markdown", "all-markdown", "pdf-deck", "all-deck"],
)
def test_parse_targets_rejects_removed_targets(target: str, kind: InputKind) -> None:
    """The removed pdf and all targets are rejected for every input kind."""
    with pytest.raises(CliError, match="target tidak valid"):
        parse_targets(target, kind)


def test_theme_typography_family_is_arial() -> None:
    """Freeze the single typography family used by theme tokens."""
    tokens = load_tokens()
    assert tokens["typography"]["family"] == "Arial"
    assert fonts.FONT_FAMILY == "Arial", "renderer font family must stay Arial"


def test_font_assets_directory_contains_only_liberation_sans() -> None:
    """Keep the bundled font asset directory limited to Liberation Sans."""
    fonts_root = fonts.FONT_DIR.parent
    assert fonts_root.is_dir(), f"font asset root is missing: {fonts_root}"
    entries = sorted(path.name for path in fonts_root.iterdir())
    assert entries == ["liberation-sans"], (
        f"{fonts_root} must contain only `liberation-sans`; found {entries}"
    )


def test_font_files_exist_on_disk() -> None:
    """Every declared measurement font file must be present."""
    assert fonts.FONT_FILES, "FONT_FILES must list the bundled measurement fonts"
    missing = [name for name in fonts.FONT_FILES if not (fonts.FONT_DIR / name).is_file()]
    assert missing == [], f"font files missing from {fonts.FONT_DIR}: {missing}"


def _source_files() -> list[Path]:
    source_root = REPO_ROOT / "src"
    assert source_root.is_dir(), "source root is missing: src"
    return sorted(source_root.rglob("*.py"))


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []
    relative = path.relative_to(REPO_ROOT).as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    findings.append(f"{relative}:{node.lineno} imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                findings.append(f"{relative}:{node.lineno} imports from {node.module}")
    return findings


def test_source_has_no_forbidden_office_or_pdf_imports() -> None:
    """Reject real COM and PDF imports anywhere under src."""
    files = _source_files()
    assert files, "source tree contains no Python files"
    findings = [finding for path in files for finding in _forbidden_imports(path)]
    assert findings == [], "forbidden imports found:\n" + "\n".join(findings)
