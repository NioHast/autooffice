"""Tes determinisme output Pandoc pada custom properties DOCX."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.config import load_format
from autooffice.docx.package import DocumentPackage
from autooffice.docx.pipeline import ArtifactStore, Workspace
from autooffice.docx.stages.pandoc import PandocStage

FORMAT_ID = "undip-msi"
CUSTOM_PROPERTIES_PART = "docProps/custom.xml"
CUSTOM_PROPERTIES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.custom-properties+xml"
)
CUSTOM_PROPERTIES_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
    'custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/'
    '2006/docPropsVTypes">'
    '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" '
    'name="bibliography"><vt:lpwstr>__BIBLIOGRAPHY__</vt:lpwstr></property>'
    '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="3" '
    'name="csl"><vt:lpwstr>__CSL__</vt:lpwstr></property>'
    '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="4" '
    'name="reference-section-title"><vt:lpwstr>DAFTAR PUSTAKA</vt:lpwstr></property>'
    "</Properties>"
)


@pytest.fixture(scope="module")
def format_spec():
    return load_format(FORMAT_ID)


def _reference(tmp_path: Path, format_spec) -> Path:
    reference = tmp_path / "reference.docx"
    shutil.copyfile(format_spec.assets.reference_docx, reference)
    return reference


def _fake_pandoc_with_paths(tmp_path: Path, reference: Path) -> Path:
    """Buat fake Pandoc yang menulis path absolut csl/bibliography ke custom.xml."""

    script = tmp_path / "pandoc-with-paths.py"
    script.write_text(
        "import sys\n"
        "import zipfile\n"
        "from pathlib import Path\n"
        "from xml.sax.saxutils import escape\n"
        "\n"
        "args = sys.argv[1:]\n"
        "output = Path(args[args.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "\n"
        "def option(prefix):\n"
        "    for arg in args:\n"
        "        if arg.startswith(prefix + '='):\n"
        "            return arg.split('=', 1)[1]\n"
        "    raise SystemExit('missing option: ' + prefix)\n"
        "\n"
        f"template = {CUSTOM_PROPERTIES_TEMPLATE!r}\n"
        "custom = template.replace('__CSL__', escape(option('--csl')))\n"
        "custom = custom.replace('__BIBLIOGRAPHY__', escape(option('--bibliography')))\n"
        "\n"
        f"reference = Path({str(reference)!r})\n"
        "with zipfile.ZipFile(reference) as source, zipfile.ZipFile(\n"
        "    output, 'w', zipfile.ZIP_DEFLATED\n"
        ") as target:\n"
        "    for info in source.infolist():\n"
        "        data = source.read(info)\n"
        "        if info.filename == 'docProps/custom.xml':\n"
        "            data = custom.encode('utf-8')\n"
        "        target.writestr(info, data)\n",
        encoding="utf-8",
    )
    return script


def _format_for_root(root: Path, format_spec):
    csl = root / "format" / "citation.csl"
    csl.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(format_spec.citation.csl, csl)
    return (
        SimpleNamespace(
            path=csl.parent / "format.yaml",
            citation=SimpleNamespace(csl=csl, bibliography="references.bib"),
            bibliography_style=format_spec.bibliography_style,
        ),
        csl,
    )


def _context_for_root(
    root: Path,
    *,
    format_stub,
    fake_pandoc: Path,
    reference: Path,
):
    project = root / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "references.bib").write_text(
        "@book{pandoc2024,\n"
        "  author = {MacFarlane, John},\n"
        "  title = {Pandoc},\n"
        "  year = {2024}\n"
        "}\n",
        encoding="utf-8",
    )
    (project / "document.md").write_text(
        "# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
        encoding="utf-8",
    )
    workspace = Workspace(root=(project / ".laporan-build").resolve(), keep=True)
    workspace.ensure()
    markdown = workspace.path("markdown.md")
    markdown.write_text(
        "# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
        encoding="utf-8",
    )
    ctx = SimpleNamespace(
        document=SimpleNamespace(
            path=(project / "document.md").resolve(),
            body="# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
            metadata=SimpleNamespace(lang="id-ID", report_name="Tugas"),
            bibliography="references.bib",
        ),
        format=format_stub,
        options=SimpleNamespace(target="docx", keep=True),
        workspace=workspace,
        package=None,
        artifacts=ArtifactStore(),
        reference_docx=reference,
        glossary=None,
        word=None,
        pandoc=str(fake_pandoc),
        logger=None,
        dry_run=False,
    )
    ctx.artifacts.put("markdown", markdown)
    return ctx


def test_custom_properties_are_deterministic_across_checkout_roots(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake = _fake_pandoc_with_paths(tmp_path, reference)
    custom_parts: list[bytes] = []

    for name in ("checkout-a", "checkout-b"):
        root = tmp_path / name
        root.mkdir()
        format_stub, csl = _format_for_root(root, format_spec)
        ctx = _context_for_root(
            root,
            format_stub=format_stub,
            fake_pandoc=fake,
            reference=reference,
        )

        result = PandocStage().run(ctx)

        output = ctx.workspace.path("Tugas.docx")
        package = DocumentPackage.load(output)
        package.validate()
        custom = package.part(CUSTOM_PROPERTIES_PART)
        custom_parts.append(custom)
        text = custom.decode("utf-8")
        bibliography = (root / "project" / "references.bib").resolve()

        assert result.status == "ok"
        assert str(root) not in text
        assert str(csl.resolve()) not in text
        assert str(bibliography) not in text
        assert csl.name in text
        assert bibliography.name in text
        assert "reference-section-title" in text
        assert "DAFTAR PUSTAKA" in text
        assert package.part_info(CUSTOM_PROPERTIES_PART).content_type == (
            CUSTOM_PROPERTIES_CONTENT_TYPE
        )
        assert CUSTOM_PROPERTIES_PART in [
            relationship.target for relationship in package.relationships("")
        ]

    assert custom_parts[0] == custom_parts[1]
