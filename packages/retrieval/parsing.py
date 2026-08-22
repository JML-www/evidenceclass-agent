"""Markdown, text, and text-PDF parsing with stable hierarchical chunks."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from .contracts import KnowledgeChunk, ParsedSection, SourceRegistration
from .errors import DocumentParseError

PARSER_VERSION = "document-parser.v0.1"
CHUNK_POLICY_VERSION = "hierarchical-chunks.v0.1"
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?:chapter\s+\d+|第[一二三四五六七八九十百\d]+[章节]|\d+(?:\.\d+)*[、.])\s*(.+)$",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*")


@dataclass(frozen=True)
class ParsedDocument:
    parser_version: str
    sections: tuple[ParsedSection, ...]


def count_tokens(text: str) -> int:
    """Dependency-free, deterministic budget estimate for Chinese and ASCII text."""

    return len(TOKEN_PATTERN.findall(text))


def _nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


class DocumentParser:
    def parse(self, path: str | Path, *, title: str) -> ParsedDocument:
        source = Path(path)
        suffix = source.suffix.casefold()
        if suffix not in SUPPORTED_SUFFIXES:
            raise DocumentParseError(
                f"unsupported document type {suffix!r}; expected Markdown, TXT, or PDF"
            )
        if not source.is_file():
            raise DocumentParseError(f"document does not exist: {source.name}")
        if suffix == ".pdf":
            sections = self._parse_pdf(source, title=title)
        else:
            try:
                text = source.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise DocumentParseError(f"UTF-8 decode failed at byte {exc.start}") from exc
            sections = self._parse_structured_text(text, fallback_heading=title, page=None)
        if not sections:
            raise DocumentParseError("no extractable text was found")
        return ParsedDocument(parser_version=PARSER_VERSION, sections=tuple(sections))

    def _parse_pdf(self, path: Path, *, title: str) -> list[ParsedSection]:
        try:
            reader = PdfReader(path, strict=True)
        except Exception as exc:
            raise DocumentParseError(f"PDF open failed: {exc}") from exc
        pages: list[list[str]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                extracted = page.extract_text()
            except Exception as exc:
                raise DocumentParseError("PDF text extraction failed", page=page_number) from exc
            if extracted is None:
                raise DocumentParseError("PDF page has no extractable text", page=page_number)
            pages.append(_nonempty_lines(extracted))

        repeated_headers, repeated_footers = self._repeated_margins(pages)
        sections: list[ParsedSection] = []
        for page_number, lines in enumerate(pages, start=1):
            if lines and lines[0] in repeated_headers:
                lines = lines[1:]
            if lines and lines[-1] in repeated_footers:
                lines = lines[:-1]
            cleaned = "\n".join(lines)
            if not cleaned.strip():
                raise DocumentParseError(
                    "PDF page became empty after repeated header/footer removal",
                    page=page_number,
                )
            sections.extend(
                self._parse_structured_text(
                    cleaned,
                    fallback_heading=f"{title} > page {page_number}",
                    page=page_number,
                )
            )
        return sections

    @staticmethod
    def _repeated_margins(pages: list[list[str]]) -> tuple[set[str], set[str]]:
        if len(pages) < 2:
            return set(), set()
        threshold = max(2, math.ceil(len(pages) * 0.6))
        headers = Counter(lines[0] for lines in pages if lines)
        footers = Counter(lines[-1] for lines in pages if lines)
        return (
            {value for value, count in headers.items() if count >= threshold},
            {value for value, count in footers.items() if count >= threshold},
        )

    @staticmethod
    def _parse_structured_text(
        text: str, *, fallback_heading: str, page: int | None
    ) -> list[ParsedSection]:
        heading_stack: list[str] = []
        current_heading = fallback_heading
        buffer: list[str] = []
        sections: list[ParsedSection] = []

        def flush() -> None:
            content = "\n".join(buffer).strip()
            if content:
                sections.append(ParsedSection(page=page, heading=current_heading, content=content))
            buffer.clear()

        for raw_line in text.replace("\r\n", "\n").split("\n"):
            heading_match = HEADING_PATTERN.match(raw_line.strip())
            numbered_match = NUMBERED_HEADING_PATTERN.match(raw_line.strip())
            if heading_match:
                flush()
                level = len(heading_match.group(1))
                heading_stack[:] = heading_stack[: level - 1]
                while len(heading_stack) < level - 1:
                    heading_stack.append(fallback_heading)
                heading_stack.append(heading_match.group(2).strip())
                current_heading = " > ".join(heading_stack)
            elif numbered_match and len(raw_line.strip()) <= 120:
                flush()
                current_heading = numbered_match.group(0).strip()
            else:
                buffer.append(raw_line.rstrip())
        flush()
        return sections


class HierarchicalChunker:
    def __init__(self, *, max_tokens: int = 220, overlap_tokens: int = 30) -> None:
        if max_tokens < 20:
            raise ValueError("max_tokens must be at least 20")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(
        self, registration: SourceRegistration, parsed: ParsedDocument
    ) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        ordinal = 0
        for section in parsed.sections:
            for content in self._split_window(section.content):
                content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                stable_input = "\x1f".join(
                    (
                        registration.document_id,
                        registration.version,
                        str(section.page or 0),
                        section.heading,
                        str(ordinal),
                        content_sha256,
                        CHUNK_POLICY_VERSION,
                    )
                )
                chunk_id = "chk_" + hashlib.sha256(stable_input.encode("utf-8")).hexdigest()[:32]
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        document_id=registration.document_id,
                        workspace_id=registration.workspace_id,
                        source_id=registration.source_id,
                        source_uri=registration.source_uri,
                        title=registration.title,
                        version=registration.version,
                        page=section.page,
                        heading=section.heading,
                        ordinal=ordinal,
                        content=content,
                        content_sha256=content_sha256,
                        token_count=max(1, count_tokens(content)),
                    )
                )
                ordinal += 1
        return chunks

    def _split_window(self, content: str) -> list[str]:
        matches = list(TOKEN_PATTERN.finditer(content))
        if not matches:
            return []
        if len(matches) <= self.max_tokens:
            return [content.strip()]
        windows: list[str] = []
        start_token = 0
        while start_token < len(matches):
            end_token = min(start_token + self.max_tokens, len(matches))
            start_char = matches[start_token].start()
            end_char = matches[end_token - 1].end()
            excerpt = content[start_char:end_char].strip()
            if excerpt:
                windows.append(excerpt)
            if end_token == len(matches):
                break
            start_token = end_token - self.overlap_tokens
        return windows
