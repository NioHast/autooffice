"""Render blok PlantUML inline menjadi PNG untuk pipeline ``autooffice``.

Penulis menulis diagram sebagai code fence dengan caption wajib:

.. code-block:: markdown

   ```{.plantuml caption="Diagram pipeline"}
   @startuml
   Alice -> Bob: Halo
   @enduml
   ```

``render_blocks`` mengganti blok dengan gambar Markdown
``![caption](gambar/plantuml-<hash>.png)`` dan menulis PNG ke
``<base_dir>/gambar``. Nomor ``Gambar bab.n`` tidak dibuat di sini; stage
caption DOCX yang memberi nomor per bab.

Modul ini hanya menyediakan API render dan stage ``PlantUmlStage``; orkestrasi
urutan tetap milik ``autooffice.docx.pipeline``.

Setiap diagram di-hash dari isi PlantUML dan opsi render. Berkas PNG yang sudah
ada dipakai ulang tanpa memanggil PlantUML lagi.

Referensi: https://plantuml.com
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocgenError, StageError, ToolMissingError
from ..pipeline import BaseStage, StageName, StageResult

IMAGE_DIR = "gambar"
HASH_LENGTH = 12
DEFAULT_TIMEOUT = 180
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_ERROR_BYTES = 64 * 1024

PLANTUML_ENV_VAR = "AUTOOFFICE_PLANTUML"
JAVA_ENV_VAR = "AUTOOFFICE_JAVA"
JAVA_HOME_ENV_VAR = "JAVA_HOME"

PLANTUML_INSTALL_HINT = (
    "Unduh PlantUML dari https://plantuml.com/download atau pasang paket "
    f"PlantUML, lalu set {PLANTUML_ENV_VAR} ke path plantuml.jar/executable "
    "atau pastikan `plantuml` ada di PATH. Bila memakai jar, sediakan Java "
    f"lewat {JAVA_ENV_VAR}, {JAVA_HOME_ENV_VAR}, atau PATH."
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_HEADER_SIZE = 13
_PNG_MAX_CHUNK_LENGTH = 0x7FFFFFFF

_FENCE_OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_LANGUAGE_RE = re.compile(r"^\.?plantuml(?=$|[\s{])", re.IGNORECASE)
_CAPTION_RE = re.compile(
    r"""(?<![\w-])caption\s*=\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""",
    re.IGNORECASE,
)


class PlantUmlError(DocgenError):
    """Kesalahan input atau render PlantUML yang aman ditampilkan ke pengguna."""

    default_code = "PLANTUML"


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Opsi visual yang diteruskan ke PlantUML dan ikut di-hash."""

    dpi: int = 192
    background: str = "white"

    def __post_init__(self) -> None:
        if isinstance(self.dpi, bool) or not isinstance(self.dpi, int) or self.dpi < 1:
            raise ValueError("dpi render PlantUML harus bilangan bulat positif")
        if not isinstance(self.background, str) or not self.background.strip():
            raise ValueError("background render PlantUML harus string tidak kosong")

    def as_dict(self) -> dict[str, object]:
        return {"dpi": int(self.dpi), "background": self.background}

    def arguments(self) -> list[str]:
        return [
            "--skinparam",
            f"dpi={int(self.dpi)}",
            "--skinparam",
            f"backgroundColor={self.background}",
        ]


@dataclass(frozen=True, slots=True)
class _PlantUmlBlock:
    """Satu code fence PlantUML beserta posisinya di daftar baris."""

    start: int
    """Indeks baris pembuka (0-based)."""

    end: int
    """Indeks baris setelah penutup (0-based, eksklusif)."""

    line: int
    """Nomor baris pembuka (1-based) untuk pesan kesalahan."""

    code: str
    caption: str
    info: str
    indent: str


@dataclass(frozen=True, slots=True)
class _BlockPlan:
    """Rencana penggantian satu blok tanpa menyentuh berkas."""

    block: _PlantUmlBlock
    digest: str
    relative_path: str
    image_path: Path
    markdown: str


# ---------------------------------------------------------------------------
# Ekstraksi dan penggantian Markdown
# ---------------------------------------------------------------------------


def _strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _default_line_ending(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _location(path: str | Path | None, line: int) -> str:
    if path is None:
        return f"baris {line}: "
    return f"{path}:{line}: "


def _plantuml_attributes(info: str) -> str | None:
    """Kembalikan atribut bila info string adalah fence PlantUML.

    Bentuk yang didukung: ``{.plantuml caption="..."}``, ``.plantuml
    caption="..."``, dan ``plantuml``. ``None`` berarti fence biasa.
    """

    text = info.strip()
    if not text:
        return None
    if text.startswith("{"):
        if not text.endswith("}"):
            return None
        text = text[1:-1].strip()

    match = _LANGUAGE_RE.match(text)
    if match is None:
        return None

    attributes = text[match.end() :].strip()
    if attributes.startswith("{") and attributes.endswith("}"):
        attributes = attributes[1:-1].strip()
    return attributes


def _caption_from_attributes(attributes: str) -> str | None:
    match = _CAPTION_RE.search(attributes)
    if match is None:
        return None
    value = match.group("double")
    if value is None:
        value = match.group("single") or ""
    return value.replace('\\"', '"').replace("\\'", "'").strip()


def _closing_fence_re(fence_character: str, minimum: int) -> re.Pattern[str]:
    return re.compile(rf"^[ \t]*{re.escape(fence_character)}{{{minimum},}}[ \t]*$")


def extract_blocks(
    text: str,
    path: str | Path | None = None,
) -> list[_PlantUmlBlock]:
    """Ekstrak seluruh blok PlantUML dari ``text``.

    ``PlantUmlError`` dilempar bila caption wajib tidak ada, caption kosong,
    isi diagram kosong, atau blok PlantUML tidak ditutup. Fence non-PlantUML
    diabaikan sepenuhnya.
    """

    lines = text.splitlines(keepends=True)
    blocks: list[_PlantUmlBlock] = []
    index = 0

    while index < len(lines):
        opener = _FENCE_OPEN_RE.match(_strip_eol(lines[index]))
        if opener is None:
            index += 1
            continue

        fence = opener.group("fence")
        closing = _closing_fence_re(fence[0], len(fence))
        info = opener.group("info")
        start = index
        content: list[str] = []
        index += 1
        closed = False

        while index < len(lines):
            current = _strip_eol(lines[index])
            if closing.fullmatch(current):
                closed = True
                break
            content.append(current)
            index += 1

        attributes = _plantuml_attributes(info)
        line = start + 1

        if not closed:
            if attributes is not None:
                raise PlantUmlError(
                    f"{_location(path, line)}blok PlantUML tidak ditutup; "
                    f"tambahkan fence penutup {fence}.",
                    code="PLANTUML-INPUT",
                )
            break

        end = index + 1
        if attributes is not None:
            code = "\n".join(content)
            if not code.strip():
                raise PlantUmlError(
                    f"{_location(path, line)}isi diagram PlantUML kosong.",
                    code="PLANTUML-INPUT",
                )

            caption = _caption_from_attributes(attributes)
            if not caption:
                raise PlantUmlError(
                    f"{_location(path, line)}blok PlantUML wajib memiliki "
                    'caption; tulis caption="..." pada pembuka blok, mis. '
                    '```{.plantuml caption="Diagram pipeline"}.',
                    code="PLANTUML-INPUT",
                )

            blocks.append(
                _PlantUmlBlock(
                    start=start,
                    end=end,
                    line=line,
                    code=code,
                    caption=caption,
                    info=info.strip(),
                    indent=opener.group("indent"),
                )
            )

        index = end

    return blocks


def _normalize_code(code: str) -> str:
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def render_hash(
    code: str,
    options: RenderOptions | None = None,
) -> str:
    """Hash isi PlantUML dan opsi render; stabil untuk isi yang sama."""

    render_options = RenderOptions() if options is None else options
    payload = json.dumps(
        {
            "code": _normalize_code(code),
            "options": render_options.as_dict(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:HASH_LENGTH]


def _escape_alt_text(caption: str) -> str:
    return caption.replace("\\", "\\\\").replace("]", "\\]")


def _plan_blocks(
    blocks: list[_PlantUmlBlock],
    base_dir: str | Path,
    options: RenderOptions | None,
) -> list[_BlockPlan]:
    out_path = Path(base_dir)
    plans: list[_BlockPlan] = []

    for block in blocks:
        digest = render_hash(block.code, options)
        filename = f"plantuml-{digest}.png"
        relative_path = f"{IMAGE_DIR}/{filename}"
        plans.append(
            _BlockPlan(
                block=block,
                digest=digest,
                relative_path=relative_path,
                image_path=out_path / IMAGE_DIR / filename,
                markdown=f"![{_escape_alt_text(block.caption)}]({relative_path})",
            )
        )

    return plans


def _rewrite_markdown(text: str, plans: list[_BlockPlan]) -> str:
    """Ganti blok PlantUML dengan gambar Markdown tanpa mengubah baris lain."""

    if not plans:
        return text

    lines = text.splitlines(keepends=True)
    default_ending = _default_line_ending(text)
    pieces: list[str] = []
    cursor = 0

    for plan in sorted(plans, key=lambda item: item.block.start):
        block = plan.block
        if block.start < cursor or block.end < block.start:
            raise PlantUmlError(
                "Rencana penggantian PlantUML tumpang tindih.",
                code="PLANTUML-INPUT",
            )
        if block.end > len(lines):
            raise PlantUmlError(
                "Rencana penggantian PlantUML di luar batas berkas.",
                code="PLANTUML-INPUT",
            )

        pieces.extend(lines[cursor : block.start])
        ending = _line_ending(lines[block.start]) or default_ending
        if block.end == len(lines) and not _line_ending(lines[block.end - 1]):
            ending = ""
        pieces.append(f"{block.indent}{plan.markdown}{ending}")
        cursor = block.end

    pieces.extend(lines[cursor:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _find_candidate(value: str | Path) -> str | None:
    raw = str(value)
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return str(candidate)
    return shutil.which(raw)


def find_plantuml(explicit: str | Path | None = None) -> str | None:
    """Cari PlantUML dari path eksplisit, ``AUTOOFFICE_PLANTUML``, atau ``PATH``.

    Nilai environment boleh berupa ``plantuml.jar`` maupun executable
    ``plantuml``. ``None`` berarti PlantUML tidak ditemukan.
    """

    if explicit is not None:
        return _find_candidate(explicit)
    configured = os.environ.get(PLANTUML_ENV_VAR)
    if configured is not None:
        if not configured.strip():
            return None
        return _find_candidate(configured)
    return shutil.which("plantuml")


def _plantuml_missing_message(explicit: str | Path | None = None) -> str:
    if explicit is not None:
        return f"PlantUML tidak ditemukan: {explicit}. {PLANTUML_INSTALL_HINT}"
    configured = os.environ.get(PLANTUML_ENV_VAR)
    if configured is not None and not configured.strip():
        return (
            f"PlantUML tidak ditemukan: {PLANTUML_ENV_VAR} diisi kosong; hapus "
            f"variabel atau tunjuk plantuml.jar/executable PlantUML. "
            f"{PLANTUML_INSTALL_HINT}"
        )
    if configured is not None:
        return (
            f"PlantUML tidak ditemukan: {PLANTUML_ENV_VAR} menunjuk path yang "
            f"tidak dapat dijalankan: {configured!r}. {PLANTUML_INSTALL_HINT}"
        )
    return f"PlantUML tidak ditemukan di PATH. {PLANTUML_INSTALL_HINT}"


def _find_java() -> str | None:
    """Cari executable ``java`` untuk menjalankan ``plantuml.jar``."""

    configured = os.environ.get(JAVA_ENV_VAR)
    if configured is not None and configured.strip():
        return _find_candidate(configured)
    home = os.environ.get(JAVA_HOME_ENV_VAR)
    if home:
        executable = "java.exe" if os.name == "nt" else "java"
        candidate = Path(home).expanduser() / "bin" / executable
        if candidate.is_file():
            return str(candidate)
    return shutil.which("java")


def _tool_prefix(executable: str) -> list[str]:
    """Prefix perintah untuk jar, skrip Python, atau executable langsung."""

    suffix = Path(executable).suffix.lower()
    if suffix == ".jar":
        java = _find_java()
        if java is None:
            raise ToolMissingError(
                "java",
                "Java tidak ditemukan untuk menjalankan plantuml.jar; set "
                f"{JAVA_ENV_VAR} ke executable java, set {JAVA_HOME_ENV_VAR}, "
                "atau pastikan `java` ada di PATH.",
                code="PLANTUML-JAVA",
            )
        return [java, "-Djava.awt.headless=true", "-jar", executable]
    if suffix in {".py", ".pyw"}:
        return [sys.executable, executable]
    return [executable]


def _plantuml_command(executable: str, options: RenderOptions) -> list[str]:
    """Susun command PlantUML yang membaca sumber dari stdin."""

    return [
        *_tool_prefix(executable),
        "--png",
        "--charset",
        "UTF-8",
        "--disable-metadata",
        "--threads",
        "1",
        "--stop-on-error",
        "--no-error-image",
        "--pragma",
        "layout=smetana",
        *options.arguments(),
        "-secure",
        "-pipe",
    ]


def _render_error_detail(completed: subprocess.CompletedProcess[bytes]) -> str:
    raw = completed.stderr
    if not raw and len(completed.stdout) <= 2000:
        raw = completed.stdout
    detail = raw.decode("utf-8", "replace").strip()
    if not detail:
        return ""
    return f": {detail[-2000:]}"


def _png_problem(data: bytes) -> str | None:
    """Periksa struktur chunk PNG dan kembalikan alasan bila tidak lengkap."""

    if not data.startswith(_PNG_SIGNATURE):
        return "signature bukan PNG"
    position = len(_PNG_SIGNATURE)
    first = True
    seen_idat = False

    while position < len(data):
        if len(data) - position < 8:
            return "chunk terpotong"
        length = int.from_bytes(data[position : position + 4], "big")
        chunk_type = data[position + 4 : position + 8]
        position += 8
        if length > _PNG_MAX_CHUNK_LENGTH:
            return "panjang chunk tidak valid"
        if len(chunk_type) != 4 or not chunk_type.isalpha():
            return "tipe chunk tidak valid"
        if first and (chunk_type != b"IHDR" or length != _PNG_HEADER_SIZE):
            return "IHDR tidak valid"
        if not first and chunk_type == b"IHDR":
            return "IHDR ganda"

        end = position + length
        if end > len(data):
            return "chunk terpotong"
        payload = data[position:end]
        position = end
        if len(data) - position < 4:
            return "CRC terpotong"
        stored_crc = int.from_bytes(data[position : position + 4], "big")
        position += 4
        expected_crc = zlib.crc32(payload, zlib.crc32(chunk_type)) & 0xFFFFFFFF
        if stored_crc != expected_crc:
            return f"CRC chunk {chunk_type.decode('ascii', 'replace')} rusak"

        if first:
            if int.from_bytes(payload[0:4], "big") == 0 or int.from_bytes(payload[4:8], "big") == 0:
                return "dimensi IHDR nol"
            first = False
        if chunk_type == b"IDAT":
            seen_idat = True
        elif chunk_type == b"IEND":
            if length != 0:
                return "IEND tidak valid"
            if not seen_idat:
                return "IDAT tidak ditemukan"
            if position != len(data):
                return "data setelah IEND"
            return None

    return "IEND tidak ditemukan"


def _render_plantuml(
    code: str,
    output_png: str | Path,
    executable: str,
    options: RenderOptions,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> Path:
    """Render satu diagram ke ``output_png`` memakai PlantUML.

    Sumber dikirim melalui stdin dan PNG diambil dari stdout. Berkas target
    hanya ditulis setelah keluaran lolos batas ukuran dan validasi PNG.
    """

    target = Path(output_png)
    if target.is_file():
        return target

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PlantUmlError(
            f"Gagal menyiapkan folder gambar {target.parent}: {exc}",
            code="PLANTUML-OUTPUT",
        ) from exc

    command = _plantuml_command(executable, options)
    try:
        completed = subprocess.run(
            command,
            input=_normalize_code(code).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PlantUmlError(
            f"PlantUML melebihi batas waktu {timeout} detik untuk {target.name}.",
            code="PLANTUML-TIMEOUT",
        ) from exc
    except OSError as exc:
        uses_java = Path(executable).suffix.lower() == ".jar"
        label = (
            "Gagal menjalankan Java untuk PlantUML" if uses_java else "Gagal menjalankan PlantUML"
        )
        raise PlantUmlError(
            f"{label}: {exc}",
            code="PLANTUML-JAVA" if uses_java else "PLANTUML-EXEC",
        ) from exc

    if len(completed.stderr) > MAX_ERROR_BYTES:
        raise PlantUmlError(
            f"Output stderr PlantUML melebihi batas {MAX_ERROR_BYTES} byte untuk {target.name}.",
            code="PLANTUML-OUTPUT",
        )

    if completed.returncode != 0:
        if completed.returncode == 200:
            message = f"PlantUML gagal (kode 200): kesalahan sintaks diagram untuk {target.name}"
            code_name = "PLANTUML-SYNTAX"
        elif completed.returncode == 50:
            message = (
                f"PlantUML gagal (kode 50): tidak ada diagram untuk dirender pada {target.name}"
            )
            code_name = "PLANTUML-NO-DIAGRAM"
        else:
            message = f"PlantUML gagal (kode {completed.returncode}) untuk {target.name}"
            code_name = "PLANTUML-FAILED"
        raise PlantUmlError(
            f"{message}{_render_error_detail(completed)}",
            code=code_name,
        )

    output = completed.stdout
    if not output:
        raise PlantUmlError(
            f"PlantUML tidak menghasilkan PNG untuk {target.name}.",
            code="PLANTUML-OUTPUT",
        )
    if len(output) > MAX_OUTPUT_BYTES:
        raise PlantUmlError(
            f"Output PlantUML melebihi batas {MAX_OUTPUT_BYTES} byte untuk {target.name}.",
            code="PLANTUML-OUTPUT",
        )
    problem = _png_problem(output)
    if problem is not None:
        raise PlantUmlError(
            f"Output PlantUML bukan PNG valid untuk {target.name}: {problem}.",
            code="PLANTUML-OUTPUT",
        )

    try:
        target.write_bytes(output)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise PlantUmlError(
            f"Gagal menulis PNG PlantUML {target}: {exc}",
            code="PLANTUML-OUTPUT",
        ) from exc

    return target


def render_blocks(
    markdown: str,
    base_dir: str | Path,
    *,
    plantuml: str | Path | None = None,
    options: RenderOptions | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    path: str | Path | None = None,
) -> str:
    """Render semua blok PlantUML dan kembalikan Markdown hasil penggantian.

    PNG ditulis ke ``<base_dir>/gambar/plantuml-<hash>.png`` dan setiap blok
    diganti dengan ``![caption](gambar/plantuml-<hash>.png)``. Diagram yang
    PNG-nya sudah ada dipakai ulang tanpa memanggil PlantUML.

    ``PlantUmlError`` dilempar untuk input tidak valid atau render gagal.
    ``ToolMissingError`` dilempar bila masih ada diagram yang perlu dirender
    tetapi PlantUML tidak ditemukan.
    """

    blocks = extract_blocks(markdown, path=path)
    if not blocks:
        return markdown

    base_path = Path(base_dir)
    if base_path.exists() and not base_path.is_dir():
        raise PlantUmlError(f"base_dir bukan direktori: {base_path}", code="PLANTUML-OUTPUT")

    render_options = RenderOptions() if options is None else options
    plans = _plan_blocks(blocks, base_path, render_options)

    pending: dict[str, _BlockPlan] = {}
    for plan in plans:
        if plan.image_path.is_file():
            continue
        pending.setdefault(plan.digest, plan)

    if pending:
        executable = find_plantuml(plantuml)
        if executable is None:
            raise ToolMissingError("plantuml", _plantuml_missing_message(plantuml))
        for plan in pending.values():
            _render_plantuml(
                plan.block.code,
                plan.image_path,
                executable,
                render_options,
                timeout=timeout,
            )

    return _rewrite_markdown(markdown, plans)


class PlantUmlStage(BaseStage):
    """Materialisasi blok PlantUML sebelum ``front_matter``/Pandoc.

    ``plantuml.md`` dan artifact ``plantuml.markdown`` selalu ditulis, termasuk
    untuk dokumen tanpa blok PlantUML, agar stage ``front_matter`` memiliki
    sumber body yang eksplisit.
    """

    name = StageName.PLANTUML
    order = 20
    requires = (StageName.VALIDATE,)
    mutates = frozenset({"workspace"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        """Materialisasi blok PlantUML ke workspace dan artifact Markdown.

        Selalu menulis ``plantuml.md``, termasuk untuk dokumen tanpa blok, agar
        ``front_matter`` punya sumber body eksplisit. Melempar ``PlantUmlError``
        bila workspace tidak tersedia dan ``StageError`` bila konteks tidak
        memiliki ``document`` atau rendering gagal.
        """

        started = time.monotonic()
        document = getattr(ctx, "document", None)
        if document is None:
            raise StageError(
                self.name.value,
                "stage plantuml membutuhkan document pada konteks stage.",
                code="PLANTUML-NO-DOCUMENT",
            )
        body = getattr(document, "body", "") or ""
        document_path = getattr(document, "path", None)
        blocks = extract_blocks(body, path=document_path)

        workspace = getattr(ctx, "workspace", None)
        if workspace is None or not callable(getattr(workspace, "ensure", None)):
            raise PlantUmlError(
                "stage plantuml membutuhkan workspace untuk menyimpan gambar.",
                code="PLANTUML-WORKSPACE",
            )
        workspace.ensure()

        try:
            markdown = render_blocks(
                body,
                Path(workspace.root),
                path=document_path,
            )
        except DocgenError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise StageError(
                self.name.value,
                f"stage plantuml gagal: {exc}",
                cause=exc,
                path=document_path,
                code="PLANTUML-STAGE",
            ) from exc

        output = Path(workspace.path("plantuml.md"))
        previous = output.read_text(encoding="utf-8") if output.is_file() else None
        changed = previous != markdown
        if changed:
            output.write_text(markdown, encoding="utf-8", newline="\n")

        artifacts = getattr(ctx, "artifacts", None)
        if (
            artifacts is not None and "plantuml.markdown" not in artifacts.keys()  # noqa: SIM118 - Artifacts bukan Mapping
        ):
            artifacts.put("plantuml.markdown", output)

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "blocks": len(blocks),
                "markdown_bytes": len(markdown.encode("utf-8")),
            },
            artifacts=(output,),
        )


__all__ = [
    "PlantUmlError",
    "PlantUmlStage",
    "RenderOptions",
    "extract_blocks",
    "find_plantuml",
    "render_blocks",
    "render_hash",
]
