"""Orkestrasi pipeline ``autooffice``.

API masuk utama adalah :class:`Pipeline` dan :meth:`Pipeline.run`, yang
menerima path ``document.md`` serta :class:`BuildOptions` dan mengembalikan
:class:`BuildResult`. Satu pass memuat dokumen, menjalankan stage sesuai
``CANONICAL_ORDER``, lalu menyimpan ``DocumentPackage`` hasil stage ``pandoc``
tepat satu kali setelah seluruh stage selesai.

Invariant:

- urutan, ``requires``, dan ``mutates`` stage divalidasi oleh
  :func:`validate_stage_order`;
- seluruh stage hanya memutasi package di memori;
- manifest Adeu disiapkan sebelum save dan ditulis setelah save;
- workspace dihapus di blok ``finally`` kecuali ``keep`` aktif.

Modul ini tidak memuat aturan format dokumen, tidak menjalankan Pandoc secara
langsung, dan tidak menulis output di luar kontrak stage. Dokumen kontrak ada
di ``docs/dev/pipeline/overview.md``.

Referensi: https://docs.python.org/3.15/reference/
"""

import logging
import shutil
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from .config import Format, Structure
from .document import Document, Project, load_project
from .errors import (
    ConfigError,
    DocgenError,
    OutputError,
    StageError,
    StageOrderError,
)
from .paths import output_directory, safe_relative_path

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from .package.package import DocumentPackage
    from .terms import Glossary

# ---------------------------------------------------------------------------
# Nama, urutan, dan metadata stage
# ---------------------------------------------------------------------------


class StageName(StrEnum):
    VALIDATE = "validate"
    PLANTUML = "plantuml"
    STYLE_REFERENCE = "style_reference"
    FRONT_MATTER = "front_matter"
    PANDOC = "pandoc"
    SECTIONS = "sections"
    CODE = "code"
    CAPTIONS = "captions"
    NORMALIZE = "normalize"
    EQUATIONS = "equations"
    NUMBERING = "numbering"
    BLANK_LINES = "blank_lines"
    TERMS = "terms"
    TOC = "toc"
    PAGE_NUMBERS = "page_numbers"
    LISTS = "lists"


CANONICAL_ORDER: tuple[StageName, ...] = (
    StageName.VALIDATE,
    StageName.PLANTUML,
    StageName.STYLE_REFERENCE,
    StageName.FRONT_MATTER,
    StageName.PANDOC,
    StageName.SECTIONS,
    StageName.CODE,
    StageName.CAPTIONS,
    StageName.NORMALIZE,
    StageName.EQUATIONS,
    StageName.NUMBERING,
    StageName.BLANK_LINES,
    StageName.TERMS,
    StageName.TOC,
    StageName.PAGE_NUMBERS,
    StageName.LISTS,
)


def canonical_prefix(name: StageName) -> tuple[StageName, ...]:
    """Stage yang wajib selesai sebelum ``name`` pada urutan kanonik."""

    return CANONICAL_ORDER[: CANONICAL_ORDER.index(name)]


@dataclass(frozen=True)
class StageSpec:
    name: StageName
    order: int
    module: str
    mutates: frozenset[str]
    idempotent: bool
    requires: tuple[StageName, ...] = ()


_RAW_STAGE_SPECS: tuple[tuple[StageName, int, str, frozenset[str], bool], ...] = (
    (StageName.VALIDATE, 10, "stages/validate.py", frozenset(), True),
    (StageName.PLANTUML, 20, "stages/plantuml.py", frozenset({"workspace"}), True),
    (
        StageName.STYLE_REFERENCE,
        30,
        "stages/style_reference.py",
        frozenset({"workspace", "cache"}),
        True,
    ),
    (
        StageName.FRONT_MATTER,
        35,
        "stages/front_matter.py",
        frozenset({"workspace"}),
        True,
    ),
    (StageName.PANDOC, 40, "stages/pandoc.py", frozenset({"package"}), True),
    (
        StageName.SECTIONS,
        50,
        "stages/sections.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (StageName.CODE, 60, "stages/code.py", frozenset({"word/document.xml"}), True),
    (
        StageName.CAPTIONS,
        70,
        "stages/captions.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (
        StageName.NORMALIZE,
        80,
        "stages/normalize.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (
        StageName.EQUATIONS,
        90,
        "stages/equations.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (
        StageName.NUMBERING,
        100,
        "stages/numbering.py",
        frozenset({"word/document.xml", "word/numbering.xml"}),
        True,
    ),
    (
        StageName.BLANK_LINES,
        110,
        "stages/blank_lines.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (
        StageName.TERMS,
        120,
        "stages/terms.py",
        frozenset({"word/document.xml", "word/styles.xml"}),
        True,
    ),
    (
        StageName.TOC,
        130,
        "stages/toc.py",
        frozenset({"word/document.xml"}),
        True,
    ),
    (
        StageName.PAGE_NUMBERS,
        140,
        "stages/page_numbers.py",
        frozenset(
            {
                "word/document.xml",
                "word/header*.xml",
                "word/footer*.xml",
                "word/_rels/document.xml.rels",
                "[Content_Types].xml",
            }
        ),
        True,
    ),
    (
        StageName.LISTS,
        150,
        "stages/lists.py",
        frozenset({"word/document.xml"}),
        True,
    ),
)

_CANONICAL_SPECS: list[StageSpec] = []
_CANONICAL_PREFIX: list[StageName] = []
for _name, _order, _module, _mutates, _idempotent in _RAW_STAGE_SPECS:
    _CANONICAL_SPECS.append(
        StageSpec(
            name=_name,
            order=_order,
            module=_module,
            mutates=_mutates,
            idempotent=_idempotent,
            requires=tuple(_CANONICAL_PREFIX),
        )
    )
    _CANONICAL_PREFIX.append(_name)
CANONICAL_STAGES: tuple[StageSpec, ...] = tuple(_CANONICAL_SPECS)

_KNOWN_PARTS = frozenset(
    {
        "workspace",
        "cache",
        "package",
        "word/document.xml",
        "word/numbering.xml",
        "word/styles.xml",
        "word/header*.xml",
        "word/footer*.xml",
        "word/_rels/document.xml.rels",
        "[Content_Types].xml",
    }
)


def validate_stage_order(stages: Sequence[StageSpec] = CANONICAL_STAGES) -> None:
    """Validasi daftar stage terhadap urutan dan guard kanonik.

    Melempar :class:`StageOrderError` bila nama duplikat, urutan atau nilai
    ``order`` tidak sesuai ``CANONICAL_ORDER``, ``requires`` bukan prefix
    kanonik, ``mutates`` memuat part tidak dikenal, atau deklarasi
    ``idempotent`` tidak diizinkan. Argumen tidak dimutasi.
    """

    names = [spec.name for spec in stages]
    if len(names) != len(set(names)):
        raise StageOrderError("nama stage duplikat")
    if tuple(names) != CANONICAL_ORDER:
        missing = [name for name in CANONICAL_ORDER if name not in names]
        extra = [name for name in names if name not in CANONICAL_ORDER]
        detail: list[str] = []
        if missing:
            detail.append("hilang: " + ", ".join(str(name) for name in missing))
        if extra:
            detail.append("tambahan: " + ", ".join(str(name) for name in extra))
        if not missing and not extra:
            detail.append("urutan tidak sama dengan kontrak")
        raise StageOrderError("urutan stage tidak kanonik (" + "; ".join(detail) + ")")

    orders = [spec.order for spec in stages]
    if orders != sorted(set(orders)):
        raise StageOrderError("nilai order stage harus unik dan naik")
    for index, spec in enumerate(stages):
        if spec.mutates - _KNOWN_PARTS:
            unknown = ", ".join(sorted(spec.mutates - _KNOWN_PARTS))
            raise StageOrderError(f"stage '{spec.name}' memutasi part tidak dikenal: {unknown}")
        if spec.idempotent is False:
            raise StageOrderError(
                f"stage '{spec.name}' tidak boleh mendeklarasikan idempotent=False"
            )
        if tuple(spec.requires) != CANONICAL_ORDER[:index]:
            raise StageOrderError(f"requires stage '{spec.name}' bukan prefix urutan kanonik")

    positions = {name: position for position, name in enumerate(CANONICAL_ORDER)}
    guards = (
        (StageName.STYLE_REFERENCE, StageName.FRONT_MATTER),
        (StageName.FRONT_MATTER, StageName.PANDOC),
        (StageName.SECTIONS, StageName.CODE),
        (StageName.CODE, StageName.CAPTIONS),
        (StageName.CAPTIONS, StageName.NORMALIZE),
        (StageName.NORMALIZE, StageName.EQUATIONS),
        (StageName.EQUATIONS, StageName.BLANK_LINES),
        (StageName.TERMS, StageName.TOC),
        (StageName.TOC, StageName.PAGE_NUMBERS),
        (StageName.PAGE_NUMBERS, StageName.LISTS),
    )
    for before, after in guards:
        if positions[before] >= positions[after]:
            raise StageOrderError(f"urutan guard gagal: '{before}' harus sebelum '{after}'")


# ---------------------------------------------------------------------------
# Protokol stage
# ---------------------------------------------------------------------------


class BaseStage(ABC):
    name: ClassVar[StageName]
    order: ClassVar[int]
    requires: ClassVar[tuple[StageName, ...]] = ()
    mutates: ClassVar[frozenset[str]] = frozenset()
    idempotent: ClassVar[bool] = True

    def enabled(self, ctx: StageContext) -> bool:
        return True

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult:
        raise NotImplementedError


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: Literal["ok", "skipped"]
    changed: bool
    duration_ms: int
    metrics: Mapping[str, int | float | str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    artifacts: tuple[Path, ...] = ()


# ---------------------------------------------------------------------------
# Opsi, workspace, artifact, dan report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildOptions:
    keep: bool = False
    terms: bool = False
    manifest: bool = True
    adeu: bool = True


def _is_link(path: Path) -> bool:
    """True untuk symlink maupun junction Windows tanpa mengikuti target."""

    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction is not None and is_junction())


@dataclass
class Workspace:
    root: Path
    keep: bool
    _ensured: bool = field(default=False, init=False, compare=False)

    def _require_exact_root(self) -> Path:
        """Resolve root dan tolak link yang mengarah ke identitas lain.

        Root workspace boleh berupa symlink/junction hanya bila hasil
        resolve-nya tepat ``<parent-resolved>/<nama-root>``. Junction
        ``.laporan-build`` ke ``.git``, ``assets``, atau direktori lain tidak
        boleh dipakai karena ``cleanup`` akan menghapus isi target.
        """

        is_link = _is_link(self.root)
        try:
            resolved = self.root.resolve(strict=True) if is_link else self.root.resolve()
            expected = self.root.parent.resolve() / self.root.name
        except (OSError, RuntimeError) as exc:
            raise OutputError(
                f"workspace tidak dapat di-resolve: {self.root}: {exc}",
                code="OUTPUT-WORKSPACE",
                path=self.root,
            ) from exc
        if resolved != expected:
            raise OutputError(
                f"workspace symlink/junction mengarah ke target lain: {self.root} -> {resolved}",
                code="OUTPUT-WORKSPACE",
                path=self.root,
            )
        return resolved

    def _remove_link(self) -> None:
        """Hapus symlink/junction itu sendiri tanpa menyentuh target."""

        try:
            self.root.unlink()
        except OSError:
            self.root.rmdir()

    def ensure(self) -> Path:
        self._require_exact_root()
        if self.root.exists() and not self.root.is_dir():
            raise OutputError(
                f"workspace bukan direktori: {self.root}",
                code="OUTPUT-WORKSPACE",
                path=self.root,
            )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputError(
                f"workspace tidak dapat dibuat: {exc}",
                code="OUTPUT-WORKSPACE",
                path=self.root,
            ) from exc
        self._require_exact_root()
        self._ensured = True
        return self.root

    def path(self, name: str) -> Path:
        self._require_exact_root()
        try:
            return safe_relative_path(
                name,
                base=self.root,
                label="workspace",
                code="OUTPUT-WORKSPACE",
            )
        except ConfigError as exc:
            raise OutputError(
                exc.message,
                code="OUTPUT-WORKSPACE",
                path=self.root,
                key=name,
            ) from exc

    def intermediate(self, name: str) -> Path:
        return self.path(name)

    def cleanup(self) -> None:
        if self.keep:
            return
        try:
            if _is_link(self.root):
                self._remove_link()
                return
            self._require_exact_root()
            if self.root.is_file():
                self.root.unlink()
            elif self.root.is_dir():
                shutil.rmtree(self.root)
        except OSError as exc:
            raise OutputError(
                f"gagal membersihkan workspace: {exc}",
                code="OUTPUT-WORKSPACE",
                path=self.root,
            ) from exc

    @property
    def exists(self) -> bool:
        return self.root.exists()


class ArtifactStore:
    _STANDARD_KEYS = frozenset(
        {"markdown", "reference_docx", "pandoc_docx", "manifest", "terms_review", "docx"}
    )

    def __init__(self) -> None:
        self._items: dict[str, Path] = {}

    def _check_key(self, key: str) -> None:
        if key in self._STANDARD_KEYS:
            return
        if any(
            key.startswith(f"{stage.value}.") or key.startswith(f"{stage.value}/")
            for stage in StageName
        ):
            return
        raise OutputError(
            f"key artifact '{key}' tidak memakai prefix stage",
            code="OUTPUT-ARTIFACT",
            key=key,
        )

    def put(self, key: str, path: Path) -> None:
        self._check_key(key)
        if key in self._items:
            raise OutputError(
                f"artifact '{key}' sudah ada dan tidak boleh ditimpa",
                code="OUTPUT-ARTIFACT",
                key=key,
            )
        self._items[key] = Path(path)

    def get(self, key: str) -> Path:
        self._check_key(key)
        try:
            return self._items[key]
        except KeyError as exc:
            raise OutputError(
                f"artifact '{key}' tidak ditemukan",
                code="OUTPUT-ARTIFACT",
                key=key,
            ) from exc

    def require(self, key: str) -> Path:
        return self.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._items)


@dataclass
class BuildReport:
    stages: list[StageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def record(self, result: StageResult) -> None:
        self.stages.append(result)
        self.warnings.extend(result.warnings)

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)

    @property
    def changed(self) -> int:
        return sum(1 for result in self.stages if result.changed)


# ---------------------------------------------------------------------------
# Konteks stage
# ---------------------------------------------------------------------------


@dataclass
class StageContext:
    document: Document
    structure: Structure
    format: Format
    options: BuildOptions

    repo_root: Path
    package_root: Path
    output_dir: Path
    workspace: Workspace

    package: DocumentPackage | None
    artifacts: ArtifactStore
    logger: logging.LoggerAdapter[logging.Logger]
    report: BuildReport

    reference_docx: Path | None
    glossary: Glossary | Path | None
    pandoc: Any | None

    dry_run: bool = False


@dataclass(frozen=True)
class BuildResult:
    document: Path
    docx: Path | None
    manifest: Path | None
    warnings: tuple[str, ...]
    stages: tuple[StageResult, ...]
    kept_workspace: Path | None


# ---------------------------------------------------------------------------
# Helper output
# ---------------------------------------------------------------------------


def _resolve_output_dir(
    output_dir: Path,
    workspace_root: Path,
    keep: bool = False,
) -> Path:
    """Expanded output dir yang hanya boleh berada di dalam workspace bila kept.

    Workspace dibersihkan di ``finally`` kecuali ``keep`` aktif, sehingga
    output di dalamnya akan hilang sebelum :class:`BuildResult` dikembalikan
    pada build biasa. Saat workspace dipertahankan, output di dalam workspace
    aman. Path dibandingkan setelah ``resolve`` agar symlink dan path relatif
    tidak melewati guard.
    """

    expanded = Path(output_dir).expanduser()
    try:
        candidate = expanded.resolve()
        workspace = workspace_root.resolve()
    except OSError as exc:
        raise OutputError(
            f"direktori output tidak dapat diresolusi: {exc}",
            code="OUTPUT-WORKSPACE",
            path=expanded,
        ) from exc
    if (candidate == workspace or workspace in candidate.parents) and not keep:
        raise OutputError(
            "direktori output tidak boleh berada di dalam workspace build; "
            f"pilih direktori lain atau aktifkan keep: {expanded}",
            code="OUTPUT-WORKSPACE",
            path=expanded,
        )
    return expanded


# ---------------------------------------------------------------------------
# Registrasi stage
# ---------------------------------------------------------------------------


def _default_stage_classes() -> tuple[type[BaseStage], ...]:
    from .stages import default_stages

    return default_stages()


def _specs_for_classes(
    stages: Sequence[type[BaseStage]],
) -> tuple[StageSpec, ...]:
    """Validasi kelas stage terhadap daftar kanonik dan kembalikan spec."""

    if not stages:
        raise StageOrderError("pipeline tidak memiliki stage")
    by_name: dict[StageName, type[BaseStage]] = {}
    for stage in stages:
        raw_name = stage.name
        try:
            name = raw_name if isinstance(raw_name, StageName) else StageName(raw_name)
        except ValueError as exc:
            raise StageOrderError(f"nama stage tidak dikenal: {raw_name!r}") from exc
        if name in by_name:
            raise StageOrderError(f"stage '{name}' terdaftar lebih dari sekali")
        by_name[name] = stage

    specs: list[StageSpec] = []
    for spec in CANONICAL_STAGES:
        registered = by_name.get(spec.name)
        if registered is None:
            raise StageOrderError(f"stage '{spec.name}' tidak terdaftar")
        if registered.order != spec.order:
            raise StageOrderError(
                f"stage '{spec.name}' memakai order {registered.order}, harus {spec.order}"
            )
        if tuple(getattr(registered, "requires", ())) != spec.requires:
            raise StageOrderError(f"requires stage '{spec.name}' bukan prefix urutan kanonik")
        if frozenset(getattr(registered, "mutates", frozenset())) - _KNOWN_PARTS:
            unknown = ", ".join(
                sorted(frozenset(getattr(registered, "mutates", frozenset())) - _KNOWN_PARTS)
            )
            raise StageOrderError(f"stage '{spec.name}' memutasi part tidak dikenal: {unknown}")
        if bool(getattr(registered, "idempotent", True)) != spec.idempotent:
            raise StageOrderError(f"stage '{spec.name}' salah mendeklarasikan idempotent")
        specs.append(spec)

    extra = sorted(set(by_name) - {spec.name for spec in CANONICAL_STAGES})
    if extra:
        raise StageOrderError("stage tidak dikenal: " + ", ".join(str(name) for name in extra))
    return tuple(specs)


# ---------------------------------------------------------------------------
# Adeu hook
# ---------------------------------------------------------------------------


def _adeu_options(options: BuildOptions) -> Any:
    from .adeu.paragraph_ids import AdeuOptions

    if not options.adeu:
        return AdeuOptions(bookmarks=False, manifest=False, source_scan=False)
    manifest_enabled = bool(options.manifest)
    return AdeuOptions(
        bookmarks=True,
        manifest=manifest_enabled,
        source_scan=manifest_enabled,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """Jalankan rangkaian stage kanonik untuk satu dokumen.

    ``stages`` opsional dipakai untuk injeksi saat pengujian; bila ``None``,
    daftar stage bawaan dimuat dari :mod:`autooffice.docx.stages`. Konstruktor
    memvalidasi nama, order, ``requires``, ``mutates``, dan ``idempotent``
    terhadap kontrak kanonik lalu melempar :class:`StageOrderError` bila ada
    yang tidak cocok.
    """

    def __init__(self, stages: Sequence[type[BaseStage]] | None = None) -> None:
        stage_classes = _default_stage_classes() if stages is None else tuple(stages)
        self.specs: tuple[StageSpec, ...] = _specs_for_classes(stage_classes)
        validate_stage_order(self.specs)
        self.stages: tuple[BaseStage, ...] = tuple(stage() for stage in stage_classes)
        self._spec_by_name = {spec.name: spec for spec in self.specs}

    # -- konteks --------------------------------------------------------

    def make_context(
        self,
        project: Project,
        options: BuildOptions,
        *,
        output_dir: Path,
        workspace: Workspace | None = None,
    ) -> StageContext:
        """Bangun konteks untuk seluruh stage dalam satu pass.

        Workspace default berada di ``.laporan-build`` samping dokumen dan baru
        dibuat saat ``Workspace.ensure`` dipanggil. Konteks awal belum memiliki
        package; stage ``pandoc`` mengisinya. Tidak ada berkas output yang
        ditulis di sini.
        """

        effective_workspace = workspace or Workspace(
            root=project.document.path.parent / ".laporan-build",
            keep=options.keep,
        )
        logger = logging.LoggerAdapter(
            logging.getLogger("autooffice.docx.pipeline"),
            {"document": str(project.document.path)},
        )
        return StageContext(
            document=project.document,
            structure=project.structure,
            format=project.format,
            options=options,
            repo_root=Path(__file__).resolve().parents[3],
            package_root=Path(__file__).resolve().parent,
            output_dir=output_dir,
            workspace=effective_workspace,
            package=None,
            artifacts=ArtifactStore(),
            logger=logger,
            report=BuildReport(),
            reference_docx=None,
            glossary=project.assets.glossary,
            pandoc=None,
        )

    # -- eksekusi -------------------------------------------------------

    def _run_batch(
        self,
        stages: Sequence[BaseStage],
        ctx: StageContext,
    ) -> None:
        """Jalankan stage berurutan dan catat hasilnya ke report konteks.

        Stage yang dinonaktifkan dicatat sebagai ``skipped``. Exception
        ``DocgenError`` diteruskan; exception lain dibungkus menjadi
        :class:`StageError` dengan kode ``STAGE-UNHANDLED``.
        """

        for stage in stages:
            spec = self._spec_by_name[stage.name]
            if not stage.enabled(ctx):
                result = StageResult(
                    stage=spec.name.value,
                    status="skipped",
                    changed=False,
                    duration_ms=0,
                    warnings=(f"stage '{spec.name.value}' dinonaktifkan oleh opsi build.",),
                )
            else:
                ctx.logger.debug("stage %s dimulai", spec.name.value)
                try:
                    result = stage.run(ctx)
                except DocgenError:
                    raise
                except Exception as exc:  # pragma: no cover - pengaman kontrak
                    raise StageError(
                        spec.name.value,
                        f"stage '{spec.name.value}' gagal: {exc}",
                        cause=exc,
                        path=ctx.document.path,
                        code="STAGE-UNHANDLED",
                    ) from exc
            ctx.report.record(result)
            ctx.logger.info(
                "stage %s: %s (%d ms, changed=%s)",
                result.stage,
                result.status,
                result.duration_ms,
                result.changed,
            )

    def run(
        self,
        document_path: str | Path,
        options: BuildOptions,
        *,
        output_dir: Path | None = None,
    ) -> BuildResult:
        """Jalankan build penuh untuk ``document_path``.

        Memuat project, menjalankan seluruh stage, lalu mengembalikan
        :class:`BuildResult` yang hanya memuat path output benar-benar ada.
        ``output_dir`` menimpa aturan ``output_directory`` bawaan.

        Melempar ``DocumentError``/``ConfigError`` saat input tidak valid,
        :class:`StageError` saat stage gagal, dan :class:`OutputError` saat
        workspace atau output tidak dapat ditulis. Workspace selalu dibersihkan
        di ``finally`` kecuali ``options.keep`` bernilai benar.
        """

        project = load_project(document_path)
        warnings = list(project.warnings)

        workspace_root = project.document.path.parent / ".laporan-build"
        if output_dir is None:
            output_dir = output_directory(project.document.path)
        output_dir = _resolve_output_dir(output_dir, workspace_root, keep=options.keep)
        workspace = Workspace(root=workspace_root, keep=options.keep)
        ctx = self.make_context(project, options, output_dir=output_dir, workspace=workspace)

        manifest = None
        manifest_path: Path | None = None
        docx_path: Path | None = None

        try:
            self._run_batch(self.stages, ctx)
            if ctx.package is None:
                raise StageError(
                    StageName.PANDOC.value,
                    "package DOCX tidak terbentuk setelah stage pandoc",
                    path=ctx.document.path,
                    code="STAGE-PACKAGE",
                )

            report_name = ctx.document.metadata.report_name
            docx_path = output_dir / f"{report_name}.docx"
            try:
                docx_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise OutputError(
                    f"direktori output tidak dapat dibuat: {exc}",
                    code="OUTPUT-DIRECTORY",
                    path=docx_path.parent,
                ) from exc

            from .adeu.paragraph_ids import (
                prepare_manifest,
                write_prepared_manifest,
            )

            adeu_options = _adeu_options(options)
            manifest = prepare_manifest(
                ctx.package,
                docx_name=docx_path.name,
                options=adeu_options,
                source_dir=(ctx.document.path.parent if adeu_options.source_scan else None),
            )

            # Satu-satunya save package target. Semua stage postprocess sudah
            # selesai dan Adeu hook sudah menyiapkan manifest di memori.
            ctx.package.save(docx_path)
            ctx.artifacts.put("docx", docx_path)

            if manifest is not None:
                manifest_path = write_prepared_manifest(manifest, ctx.document.path)
                if manifest_path is not None:
                    ctx.artifacts.put("manifest", manifest_path)

            if not docx_path.is_file():
                raise OutputError(
                    "DOCX tidak terbentuk di direktori output setelah pipeline selesai.",
                    code="OUTPUT-DOCX",
                    path=docx_path,
                )

            return BuildResult(
                document=project.document.path,
                docx=docx_path,
                manifest=manifest_path,
                warnings=tuple(warnings + ctx.report.warnings),
                stages=tuple(ctx.report.stages),
                kept_workspace=workspace.root if options.keep else None,
            )
        finally:
            active = sys.exc_info()[1]
            try:
                workspace.cleanup()
            except Exception as cleanup_error:
                if active is None:
                    raise
                message = f"gagal membersihkan workspace setelah build gagal: {cleanup_error}"
                ctx.logger.warning(message)
                active.add_note(message)
