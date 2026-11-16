"""Parser ``structure.yaml`` dan aturan struktur dokumen.

Modul ini memuat :func:`load_structure` serta parser body, back matter,
numbering, TOC, dan daftar. Aturan source back matter dan ID bab adalah
tanggung jawab khusus struktur dan tidak dipakai parser format.

Semua kegagalan input dilempar sebagai ``ConfigError`` dengan kode stabil;
modul ini tidak menulis berkas dan tidak menyediakan fallback struktur.
Kontrak data ada di ``docs/dev/formats.md``.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .. import paths as path_mod
from ..errors import ConfigError
from .common import _boolean, _enum, _text, load_yaml_mapping
from .models import (
    BackMatterItem,
    BodyChapter,
    ListSettings,
    Numbering,
    Structure,
)
from .validation import (
    _check_unknown,
    _err,
    _expect_list,
    _expect_mapping,
    _required,
)

_STRUCTURE_KEYS = frozenset({"format", "body", "back_matter", "toc", "numbering", "lists"})
_BACK_MATTER_RULES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "bibliography": frozenset({"generated"}),
        "appendices": frozenset({"document"}),
    }
)
_BODY_KEYS = frozenset({"id", "title"})
_BACK_KEYS = frozenset({"id", "source"})
_NUMBERING_KEYS = frozenset({"body", "sub_dot", "subsub_dot"})
_LISTS_KEYS = frozenset({"figures", "tables"})
_BODY_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _parse_body(data: Any, *, path: Path) -> tuple[BodyChapter, ...]:
    """Validasi ``body``: minimal satu bab, ID unik, dan judul unik casefold."""

    entries = _expect_list(data, path=path, key="body")
    if not entries:
        raise _err(
            "body minimal memuat satu bab",
            code="CFG-REQUIRED",
            path=path,
            key="body",
        )
    result: list[BodyChapter] = []
    ids: set[str] = set()
    titles: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"body[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BODY_KEYS, path=path, key=key)
        chapter_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if not _BODY_ID_RE.fullmatch(chapter_id):
            raise _err(
                f"ID bab '{chapter_id}' tidak valid; gunakan [a-z][a-z0-9-]*",
                code="CFG-TYPE",
                path=path,
                key=f"{key}.id",
            )
        if chapter_id in ids:
            raise _err(
                f"ID bab '{chapter_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        ids.add(chapter_id)
        title = _text(
            _required(item, "title", path=path, key=key),
            path=path,
            key=f"{key}.title",
        )
        normalized = _normalize_title(title)
        if normalized in titles:
            raise _err(
                f"judul bab '{title}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.title",
            )
        titles.add(normalized)
        result.append(BodyChapter(id=chapter_id, title=title))
    return tuple(result)


def _parse_back_matter(data: Any, *, path: Path) -> tuple[BackMatterItem, ...]:
    """Validasi ``back_matter`` opsional; ID dan source harus sesuai aturan."""

    if data is None:
        return ()
    entries = _expect_list(data, path=path, key="back_matter")
    result: list[BackMatterItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"back_matter[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BACK_KEYS, path=path, key=key)
        item_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if item_id not in _BACK_MATTER_RULES:
            raise _err(
                f"ID back matter '{item_id}' tidak didukung",
                code="CFG-UNKNOWN-FRONT-MATTER",
                path=path,
                key=f"{key}.id",
            )
        if item_id in seen:
            raise _err(
                f"ID back matter '{item_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        seen.add(item_id)
        source = _text(
            _required(item, "source", path=path, key=key),
            path=path,
            key=f"{key}.source",
        )
        if source not in _BACK_MATTER_RULES[item_id]:
            allowed = ", ".join(sorted(_BACK_MATTER_RULES[item_id]))
            raise _err(
                f"back matter '{item_id}' tidak mendukung source '{source}'; gunakan {allowed}",
                code="CFG-CONDITIONAL",
                path=path,
                key=f"{key}.source",
            )
        result.append(BackMatterItem(id=item_id, source=source))
    return tuple(result)


def _parse_numbering(data: Any, *, path: Path) -> Numbering:
    mapping = _expect_mapping(data, path=path, key="numbering")
    _check_unknown(mapping, _NUMBERING_KEYS, path=path, key="numbering")
    return Numbering(
        body=_enum(
            _required(mapping, "body", path=path, key="numbering"),
            path=path,
            key="numbering.body",
            choices=("BAB_ROMAN", "ARABIC_DOTTED"),
        ),
        sub_dot=_boolean(mapping.get("sub_dot"), path=path, key="numbering.sub_dot", default=True),
        subsub_dot=_boolean(
            mapping.get("subsub_dot"),
            path=path,
            key="numbering.subsub_dot",
            default=True,
        ),
    )


def _parse_lists(data: Any, *, path: Path) -> ListSettings:
    mapping = _expect_mapping(data, path=path, key="lists")
    _check_unknown(mapping, _LISTS_KEYS, path=path, key="lists")
    return ListSettings(
        figures=_boolean(
            _required(mapping, "figures", path=path, key="lists"),
            path=path,
            key="lists.figures",
        ),
        tables=_boolean(
            _required(mapping, "tables", path=path, key="lists"),
            path=path,
            key="lists.tables",
        ),
    )


def load_structure(structure_id: str, *, root: Path | None = None) -> Structure:
    """Muat dan validasi ``structures/<structure_id>/structure.yaml``.

    Mengembalikan ``Structure`` immutable. ``root`` opsional mengganti
    direktori data paket. Semua kegagalan skema, referensi format, dan
    kombinasi field dilempar sebagai ``ConfigError``.
    """

    path_mod.validate_id(structure_id, kind="struktur")
    directory = path_mod.structure_dir(structure_id, root=root)
    path = directory / "structure.yaml"
    if not path.is_file():
        raise ConfigError(
            f"struktur '{structure_id}': structure.yaml tidak ditemukan",
            code="CFG-STRUCTURE-MISSING",
            path=path,
        )
    data = load_yaml_mapping(path, label="structure.yaml")
    _check_unknown(
        data,
        _STRUCTURE_KEYS,
        path=path,
        key="structure",
    )
    format_id = _text(
        _required(data, "format", path=path, key="structure"),
        path=path,
        key="format",
    )
    path_mod.validate_id(format_id, kind="format")

    numbering = _parse_numbering(
        _required(data, "numbering", path=path, key="structure"),
        path=path,
    )
    toc = _boolean(
        _required(data, "toc", path=path, key="structure"),
        path=path,
        key="toc",
    )
    lists = _parse_lists(
        _required(data, "lists", path=path, key="structure"),
        path=path,
    )
    body = _parse_body(
        _required(data, "body", path=path, key="structure"),
        path=path,
    )
    back_matter = _parse_back_matter(data.get("back_matter"), path=path)

    return Structure(
        id=structure_id,
        format_id=format_id,
        path=directory,
        data=MappingProxyType(dict(data)),
        body=body,
        back_matter=back_matter,
        toc=toc,
        numbering=numbering,
        lists=lists,
    )
