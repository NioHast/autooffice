"""Daftar style token syntax highlighting Pandoc yang didukung format.

Daftar ini diukur dari Pandoc 3.13. Key ``code.highlight`` di ``format.yaml``
hanya boleh memakai salah satu styleId di sini agar typo tidak diabaikan.
"""

PANDOC_HIGHLIGHT_STYLES: tuple[str, ...] = (
    "AlertTok",
    "AnnotationTok",
    "AttributeTok",
    "BaseNTok",
    "BuiltInTok",
    "CharTok",
    "CommentTok",
    "CommentVarTok",
    "ConstantTok",
    "ControlFlowTok",
    "DataTypeTok",
    "DecValTok",
    "DocumentationTok",
    "ErrorTok",
    "ExtensionTok",
    "FloatTok",
    "FunctionTok",
    "ImportTok",
    "InformationTok",
    "KeywordTok",
    "NormalTok",
    "OperatorTok",
    "OtherTok",
    "PreprocessorTok",
    "RegionMarkerTok",
    "SpecialCharTok",
    "SpecialStringTok",
    "StringTok",
    "VariableTok",
    "VerbatimStringTok",
    "WarningTok",
)

__all__ = ["PANDOC_HIGHLIGHT_STYLES"]
