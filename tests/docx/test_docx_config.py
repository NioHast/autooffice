"""Tes unit untuk loader ``format.yaml`` dan ``structure.yaml``."""

import re
import shutil
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from autooffice.docx import config, paths
from autooffice.docx.config import load_format, load_structure
from autooffice.docx.errors import ConfigError

_EXPECTED_CONFIG_EXPORTS = frozenset(
    {
        "AbstractStyle",
        "AssetsFormat",
        "BackMatterItem",
        "BibliographyStyle",
        "BodyChapter",
        "BodyFont",
        "CaptionFont",
        "CaptionStyle",
        "CaptionsFormat",
        "CitationFormat",
        "CodeBorder",
        "CodeFont",
        "CodeFormat",
        "CodeTable",
        "FigureStyle",
        "FontFormat",
        "Format",
        "HeadingStyle",
        "ListSettings",
        "Margins",
        "MonoFont",
        "Numbering",
        "PageFormat",
        "Structure",
        "TocHeadingStyle",
        "format_override_warning",
        "load_format",
        "load_structure",
        "load_yaml_mapping",
        "parse_yaml_mapping",
    }
)


def _copy_format(tmp_path: Path, name: str = "undip-msi") -> Path:
    data_root = tmp_path / "data"
    target = data_root / "formats" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(paths.format_dir("undip-msi"), target)
    return data_root


def _set_empty_format_value(tmp_path: Path, key: str) -> Path:
    """Salin format lalu isi satu key teks dengan string kosong eksplisit."""

    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    yaml = YAML()
    data = yaml.load(format_yaml)
    node = data
    *parents, child = key.split(".")
    for part in parents:
        node = node[part]
    node[child] = ""
    with format_yaml.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.dump(data, handle)
    return data_root


def _write_structure(root: Path, name: str, text: str) -> Path:
    directory = root / "structures" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "structure.yaml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _minimal_structure(extra: str = "") -> str:
    return (
        "format: undip-msi\n\n"
        "toc: false\n\n"
        "lists:\n"
        "  figures: false\n"
        "  tables: false\n\n"
        "body:\n"
        '  - {id: pendahuluan, title: "Pendahuluan"}\n\n'
        "back_matter:\n"
        "  - {id: bibliography, source: generated}\n\n"
        "numbering:\n"
        "  body: ARABIC_DOTTED\n" + extra
    )


def test_config_public_api_complete() -> None:
    assert len(config.__all__) == 30
    missing = _EXPECTED_CONFIG_EXPORTS.difference(config.__all__)
    assert not missing, f"nama publik hilang: {sorted(missing)}"


def test_load_builtin_format() -> None:
    format_ = load_format("undip-msi")

    assert format_.id == "undip-msi"
    assert format_.page.margins.top == 2268  # 4 cm
    assert format_.page.margins.bottom == 1701  # 3 cm
    assert format_.font.body.size_half_points == 24  # 12 pt
    assert format_.font.body.line_spacing == 1.5
    assert format_.font.body.alignment == "justify"
    assert format_.abstract.font_family == "Times New Roman"
    assert format_.abstract.font_size_half_points == 20  # 10 pt
    assert format_.abstract.line_spacing == 1.0
    assert format_.abstract.space_before == 0
    assert format_.abstract.space_after == 0
    assert format_.abstract.alignment == "justify"
    assert format_.abstract.english_italic is True
    assert format_.figures.caption_alignment == "center"
    assert format_.figures.image_alignment == "center"
    assert format_.figures.space_before == 0
    assert format_.figures.space_after == 0
    assert format_.figures.first_line_indent == 0
    assert format_.code.alignment == "left"
    assert format_.toc_heading.heading_style == "TOCHeading"
    assert format_.toc_heading.font_family == "Times New Roman"
    assert format_.toc_heading.color == "000000"
    assert format_.toc_heading.alignment == "center"
    assert format_.toc_heading.first_line_indent == 0
    assert format_.bibliography_style.heading == "DAFTAR PUSTAKA"
    assert format_.bibliography_style.indent_left == 720
    assert format_.bibliography_style.indent_hanging == 720
    assert format_.citation.bibliography == "references.bib"
    assert format_.citation.csl.is_file()
    assert format_.assets.reference_docx.is_file()
    assert format_.assets.logo.is_file()
    assert not hasattr(format_.assets, "cover")
    assert not hasattr(format_.assets, "logo_width")


def test_data_root_uses_package_not_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = paths.data_root()
    assert root == paths.package_root() / "data"
    assert root.is_dir()


@pytest.mark.parametrize(
    "key",
    [
        "name",
        "font.monospace.family",
        "abstract.font",
        "headings.styles.heading1.font_family",
        "headings.styles.heading2.font_family",
        "headings.styles.heading3.font_family",
        "toc_heading.heading_style",
        "toc_heading.font",
        "captions.figure.label",
        "captions.table.label",
        "captions.figure.font.family",
        "captions.table.font.family",
        "code.style",
        "code.font.family",
        "bibliography_style.heading",
        "bibliography_style.font",
        "citation.bibliography",
        "citation.locale",
        "assets.logo",
        "assets.reference_docx",
    ],
)
def test_explicit_empty_text_value_rejected(tmp_path: Path, key: str) -> None:
    data_root = _set_empty_format_value(tmp_path, key)

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)

    assert error.value.code == "CFG-REQUIRED"
    assert error.value.key == key


def test_all_builtin_structures_load() -> None:
    assignment = load_structure("assignment")
    assert assignment.toc is False
    assert assignment.lists.figures is False
    assert assignment.lists.tables is False
    assert not hasattr(assignment, "cover")
    assert not hasattr(assignment, "front_matter")

    proposal = load_structure("proposal")
    assert proposal.toc is True
    assert proposal.lists.figures is False
    assert proposal.lists.tables is False

    thesis = load_structure("thesis")
    assert thesis.toc is True
    assert thesis.lists.figures is True
    assert thesis.lists.tables is True
    assert any(item.id == "appendices" for item in thesis.back_matter)


def test_unknown_format_key_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    format_yaml.write_text(
        format_yaml.read_text(encoding="utf-8") + "\nbogus_key: 1\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"


def test_legacy_format_key_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    format_yaml.write_text(
        format_yaml.read_text(encoding="utf-8") + "\npresets: []\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "format.presets"


def test_abstract_unknown_key_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    format_yaml.write_text(
        text.replace(
            "  english_italic: true\n\nheadings:",
            "  english_italic: true\n  bogus: 1\n\nheadings:",
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "abstract.bogus"


def test_abstract_defaults_inherit_body_when_omitted(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    without_abstract = re.sub(
        r"^abstract:\n(?:[ \t].*\n|\n)*",
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert "abstract:" not in without_abstract
    format_yaml.write_text(without_abstract, encoding="utf-8", newline="\n")

    format_ = load_format("undip-msi", root=data_root)
    body = format_.font.body
    assert format_.abstract.font_family == body.family
    assert format_.abstract.font_size_half_points == body.size_half_points
    assert format_.abstract.line_spacing == body.line_spacing
    assert format_.abstract.space_before == 0
    assert format_.abstract.space_after == 0
    assert format_.abstract.alignment == body.alignment
    assert format_.abstract.english_italic is True


def test_abstract_english_italic_must_be_boolean(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    format_yaml.write_text(
        text.replace("  english_italic: true", '  english_italic: "yes"'),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-TYPE"
    assert error.value.key == "abstract.english_italic"


def test_missing_margin_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    text = re.sub(r"^\s*top:\s*4cm\s*$\n", "", text, count=1, flags=re.MULTILINE)
    format_yaml.write_text(text, encoding="utf-8", newline="\n")

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-REQUIRED"
    assert "margins" in (error.value.key or "")


def test_format_id_must_match_directory(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path, name="wrong-name")

    with pytest.raises(ConfigError) as error:
        load_format("wrong-name", root=data_root)
    assert error.value.code == "CFG-TYPE"
    assert "format" in (error.value.key or "")


def test_format_assets_reject_logo_width(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    format_yaml.write_text(
        text.replace(
            "  reference_docx: reference.docx\n",
            "  reference_docx: reference.docx\n  logo_width: 4.88cm\n",
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "assets.logo_width"


def test_format_assets_reject_cover(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    format_yaml.write_text(
        text.replace(
            "  reference_docx: reference.docx\n",
            "  reference_docx: reference.docx\n  cover:\n    show_lecturer: true\n",
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "assets.cover"


def test_reference_docx_unreadable_raises_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = _copy_format(tmp_path)

    def unreadable(*_args: object, **_kwargs: object) -> object:
        raise PermissionError("akses ditolak")

    monkeypatch.setattr("autooffice.docx.config.format.zipfile.ZipFile", unreadable)

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)

    assert error.value.code == "CFG-ASSET-INVALID"
    assert error.value.key == "assets.reference_docx"
    assert "tidak dapat dibaca" in str(error.value)


def test_figures_legacy_alignment_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yaml = data_root / "formats" / "undip-msi" / "format.yaml"
    text = format_yaml.read_text(encoding="utf-8")
    format_yaml.write_text(
        text.replace("  caption_alignment: center\n", "  alignment: center\n"),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "figures.alignment"


def test_structure_toc_flag(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace("toc: false", "toc: true"),
    )

    structure = load_structure("contoh", root=data_root)
    assert structure.toc is True

    _write_structure(data_root, "tanpa-toc", _minimal_structure())
    without_toc = load_structure("tanpa-toc", root=data_root)
    assert without_toc.toc is False


def test_structure_lists_flags(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace(
            "  figures: false\n  tables: false\n",
            "  figures: true\n  tables: true\n",
        ),
    )

    structure = load_structure("contoh", root=data_root)
    assert structure.lists.tables is True
    assert structure.lists.figures is True

    _write_structure(data_root, "tanpa-daftar", _minimal_structure())
    without_lists = load_structure("tanpa-daftar", root=data_root)
    assert without_lists.lists.tables is False
    assert without_lists.lists.figures is False


def test_structure_front_matter_and_cover_keys_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "front-matter",
        _minimal_structure() + "\nfront_matter:\n  - {id: cover, source: generated}\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("front-matter", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "structure.front_matter"

    _write_structure(
        data_root,
        "cover",
        _minimal_structure() + "\ncover:\n  show_lecturer: true\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("cover", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "structure.cover"


def test_structure_toc_and_lists_are_required(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    without_toc = _minimal_structure().replace("toc: false\n\n", "")
    _write_structure(data_root, "tanpa-toc", without_toc)
    with pytest.raises(ConfigError) as error:
        load_structure("tanpa-toc", root=data_root)
    assert error.value.code == "CFG-REQUIRED"
    assert error.value.key == "structure.toc"

    without_lists = _minimal_structure().replace(
        "lists:\n  figures: false\n  tables: false\n\n", ""
    )
    _write_structure(data_root, "tanpa-lists", without_lists)
    with pytest.raises(ConfigError) as error:
        load_structure("tanpa-lists", root=data_root)
    assert error.value.code == "CFG-REQUIRED"
    assert error.value.key == "structure.lists"


def test_structure_unknown_keys(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure() + "\nfoo: 1\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"

    _write_structure(
        data_root,
        "contoh",
        _minimal_structure() + "\nchapters: []\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "structure.chapters"


def test_structure_body_unique(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace(
            '  - {id: pendahuluan, title: "Pendahuluan"}\n',
            '  - {id: pendahuluan, title: "Pendahuluan"}\n'
            '  - {id: pendahuluan, title: "Pendahuluan"}\n',
        ),
    )

    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-DUPLICATE"
