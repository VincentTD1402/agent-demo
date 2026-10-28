"""Trích văn bản từ file tài liệu (txt, md, pdf, docx) và chia thành chunk."""

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile

from docx import Document as load_docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PyPdfError

SUPPORTED_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx"})
# Định dạng có cấu trúc heading (md gốc, hoặc docx đã đổi sang md): chia chunk theo tiêu đề
MARKDOWN_LIKE_EXTENSIONS = frozenset({".md", ".docx"})
_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


class UnsupportedDocumentError(Exception):
    """File không đọc được: sai định dạng, hỏng, mã hoá hoặc không phải UTF-8."""


def _suffix(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def is_supported(filename: str) -> bool:
    return _suffix(filename) in SUPPORTED_EXTENSIONS


def is_markdown_like(filename: str) -> bool:
    return _suffix(filename) in MARKDOWN_LIKE_EXTENSIONS


def extract_text(filename: str, data: bytes) -> str:
    suffix = _suffix(filename)
    if suffix == ".pdf":
        text = _pdf_text(data)
    elif suffix == ".docx":
        text = _docx_markdown(data)
    elif suffix in (".txt", ".md"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise UnsupportedDocumentError("File văn bản phải mã hoá UTF-8") from None
    else:
        raise UnsupportedDocumentError(f"Định dạng không hỗ trợ (chỉ nhận {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
    # Postgres không lưu được ký tự NUL trong text
    return text.replace("\x00", "").strip()


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise UnsupportedDocumentError("PDF có mật khẩu, không đọc được")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except UnsupportedDocumentError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError):
        raise UnsupportedDocumentError("PDF hỏng hoặc không đọc được") from None


def _docx_markdown(data: bytes) -> str:
    """Word -> Markdown theo đúng thứ tự: Heading N -> '#' * N, danh sách -> '-', bảng -> hàng '| a | b |'."""
    try:
        document = load_docx(BytesIO(data))
        blocks = [_docx_block(block) for block in document.iter_inner_content()]
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError, OSError):
        raise UnsupportedDocumentError("File Word hỏng hoặc không đọc được") from None
    return "\n\n".join(b for b in blocks if b)


def _docx_block(block: Paragraph | Table) -> str:
    if isinstance(block, Table):
        rows = ["| " + " | ".join(cell.text.strip().replace("\n", " ") for cell in row.cells) + " |" for row in block.rows]
        return "\n".join(rows)
    text = block.text.strip()
    style = (block.style.name or "") if block.style is not None else ""
    if text and style.startswith("Heading ") and style[8:].isdigit():
        return "#" * min(int(style[8:]), 3) + " " + text
    if text and style.startswith("List"):
        return "- " + text
    return text


def split_into_chunks(text: str, chunk_size: int, chunk_overlap: int, markdown: bool = False) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=min(chunk_overlap, chunk_size // 2))
    if not markdown:
        return [chunk for chunk in splitter.split_text(text) if chunk.strip()]
    # Cắt theo tiêu đề trước để chunk không vắt qua hai mục; sau đó cắt tiếp theo kích thước
    sections = MarkdownHeaderTextSplitter(_HEADERS, strip_headers=False).split_text(text)
    chunks = []
    for piece in splitter.split_documents(sections):
        content = piece.page_content.strip()
        if not content:
            continue
        # Mảnh thứ hai trở đi của một mục mất dòng tiêu đề: gắn lại đường dẫn tiêu đề để embedding còn ngữ cảnh
        if not content.startswith("#"):
            breadcrumb = " > ".join(piece.metadata[key] for _, key in _HEADERS if key in piece.metadata)
            if breadcrumb:
                content = f"{breadcrumb}\n\n{content}"
        chunks.append(content)
    return chunks
