"""Tes build Markdown/DOCX: hasil artefak dan dry-run keep-intermediate."""

from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.build import build_markdown
from autooffice.docx.command import DocxResult

REPORT_NAME = "Laporan Uji"


def _markdown(tmp_path: Path) -> Path:
    (tmp_path / "references.bib").write_text(
        "@article{pandoc2024,\n  title = {Pandoc},\n  author = {Doe, Jane},\n  year = {2024},\n}\n",
        encoding="utf-8",
    )
    source = tmp_path / "document.md"
    source.write_text(
        "---\n"
        'title: "Uji CLI"\n'
        'author: "Penulis"\n'
        f'report_name: "{REPORT_NAME}"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "---\n\n"
        "# Pendahuluan\n\nTeks pendahuluan.\n\n"
        "# Pembahasan\n\nTeks pembahasan.\n\n"
        "# Penutup\n\nTeks penutup.\n",
        encoding="utf-8",
    )
    return source


def _install_build_docx(
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_manifest: bool = True,
    with_terms: bool = False,
    with_workspace: bool = False,
    warnings: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_build_docx(
        *,
        input: Path,
        out: Path | None = None,
        terms: bool = False,
        keep_intermediate: bool = False,
    ) -> DocxResult:
        calls.append(
            {
                "input": input,
                "out": out,
                "terms": terms,
                "keep_intermediate": keep_intermediate,
            }
        )
        output_dir = input.parent if out is None else out
        output_dir.mkdir(parents=True, exist_ok=True)
        docx = output_dir / f"{REPORT_NAME}.docx"
        docx.write_bytes(b"PK fake docx")
        manifest = None
        if with_manifest:
            manifest = input.parent / ".laporan" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("{}", encoding="utf-8")
        terms_path = None
        if with_terms:
            terms_path = input.parent / ".laporan" / "istilah-baru.txt"
            terms_path.parent.mkdir(parents=True, exist_ok=True)
            terms_path.write_text("istilah", encoding="utf-8")
        workspace = None
        if with_workspace:
            workspace = input.parent / ".laporan-build"
            workspace.mkdir(parents=True, exist_ok=True)
        return DocxResult(
            docx=docx,
            manifest=manifest,
            terms=terms_path,
            warnings=warnings,
            workspace=workspace,
        )

    monkeypatch.setattr("autooffice.docx.command.build_docx", fake_build_docx)
    return calls


def test_build_markdown_docx_lists_manifest_terms_and_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    calls = _install_build_docx(
        monkeypatch,
        with_terms=True,
        with_workspace=True,
        warnings=("caption hilang",),
    )

    outcome = build_markdown(source, ("docx",), terms=True, keep_intermediate=True)

    docx = tmp_path / f"{REPORT_NAME}.docx"
    manifest = tmp_path / ".laporan" / "manifest.json"
    terms = tmp_path / ".laporan" / "istilah-baru.txt"
    assert outcome.files == (docx, manifest, terms)
    assert outcome.warnings == ("caption hilang",)
    assert outcome.notes == (f"workspace dipertahankan: {tmp_path / '.laporan-build'}",)
    assert outcome.dry_run is False
    assert calls == [
        {
            "input": source,
            "out": None,
            "terms": True,
            "keep_intermediate": True,
        }
    ]


def test_build_markdown_rejects_pdf_target(tmp_path: Path) -> None:
    source = _markdown(tmp_path)

    with pytest.raises(CliError, match="target tidak valid") as error:
        build_markdown(source, ("pdf",))

    assert error.value.code == "CLI-TARGET-INVALID"
    assert error.value.exit_code == 2


def test_build_markdown_rejects_all_target(tmp_path: Path) -> None:
    source = _markdown(tmp_path)

    with pytest.raises(CliError, match="target tidak valid") as error:
        build_markdown(source, ("all",))

    assert error.value.code == "CLI-TARGET-INVALID"
    assert error.value.exit_code == 2


def test_build_markdown_dry_run_keep_intermediate_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _markdown(tmp_path)
    calls = _install_build_docx(monkeypatch)

    outcome = build_markdown(source, ("docx",), dry_run=True, keep_intermediate=True)

    assert calls == []
    assert outcome.dry_run is True
    assert outcome.files == (
        tmp_path / f"{REPORT_NAME}.docx",
        tmp_path / ".laporan" / "manifest.json",
    )
    assert f"intermediate dipertahankan: {tmp_path / '.laporan-build'}" in outcome.notes
    assert not (tmp_path / ".laporan-build").exists()
    assert capsys.readouterr().out == ""


def test_build_markdown_requires_at_least_one_target(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="minimal satu target") as error:
        build_markdown(tmp_path / "document.md", ())

    assert error.value.code == "CLI-TARGET-MISSING"
    assert error.value.exit_code == 2


def test_build_markdown_expands_out_before_build_and_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    calls = _install_build_docx(monkeypatch, with_manifest=False)

    outcome = build_markdown(source, ("docx",), out=Path("~/records"))

    expected = home / "records"
    assert calls[0]["out"] == expected
    assert outcome.files[0] == expected / f"{REPORT_NAME}.docx"
