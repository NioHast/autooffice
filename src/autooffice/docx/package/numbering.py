"""Helper angka Romawi untuk pipeline DOCX.

Modul ini adalah sumber tunggal konversi token angka Romawi ke bilangan bulat
dan sebaliknya. Pembacaan nomor bab dari teks sudah dihapus: heading memakai
numbering native Word dan nomor bab dihitung dari urutan heading bernomor.
Modul ini murni dan tidak bergantung pada Markdown, XML, maupun package DOCX.

Referensi: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1
"""

__all__ = [
    "roman_to_int",
    "to_roman",
]

_ROMAN_VALUES: dict[str, int] = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

_ROMAN_MAP: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def roman_to_int(token: str) -> int | None:
    """Konversi token angka Romawi menjadi bilangan bulat.

    Huruf besar dan kecil diterima. ``None`` dikembalikan bila token kosong
    atau memuat karakter di luar ``I V X L C D M``. Token non-kanonis seperti
    ``"IIII"`` tetap dijumlahkan sebagai penjumlahan simbol.
    """

    total = 0
    previous = 0
    for character in reversed(token.upper()):
        value = _ROMAN_VALUES.get(character)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def to_roman(value: int) -> str:
    """Konversi bilangan bulat menjadi angka Romawi kapital.

    Nilai nol atau negatif menghasilkan string kosong, sama seperti helper
    ``roman`` pada lapisan Markdown.
    """

    if value <= 0:
        return ""
    remaining = value
    out: list[str] = []
    for number, symbol in _ROMAN_MAP:
        while remaining >= number:
            out.append(symbol)
            remaining -= number
    return "".join(out)
