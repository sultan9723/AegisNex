from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class DocumentChunk:
    id: str
    source: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: str) -> list[DocumentChunk]: ...


def _make_chunk_id(source: str, index: int) -> str:
    return hashlib.sha256(f"{source}:{index}".encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class MarkdownLoader(DocumentLoader):
    def load(self, path: str) -> list[DocumentChunk]:
        content = Path(path).read_text(encoding="utf-8")
        source = str(path)
        chunks: list[DocumentChunk] = []
        lines = content.split("\n")
        current_heading = ""
        current_lines: list[str] = []
        chunk_index = 0

        for line in lines:
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        chunks.append(
                            DocumentChunk(
                                id=_make_chunk_id(source, chunk_index),
                                source=source,
                                content=text,
                                metadata={
                                    "title": current_heading or Path(path).stem,
                                    "headings": [h for h in [current_heading] if h],
                                    "format": "markdown",
                                    "created_at": _now_iso(),
                                },
                            )
                        )
                        chunk_index += 1
                current_heading = m.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, chunk_index),
                        source=source,
                        content=text,
                        metadata={
                            "title": current_heading or Path(path).stem,
                            "headings": [h for h in [current_heading] if h],
                            "format": "markdown",
                            "created_at": _now_iso(),
                        },
                    )
                )

        if not chunks:
            text = content.strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, 0),
                        source=source,
                        content=text,
                        metadata={
                            "title": Path(path).stem,
                            "headings": [],
                            "format": "markdown",
                            "created_at": _now_iso(),
                        },
                    )
                )

        return chunks


class TextLoader(DocumentLoader):
    def load(self, path: str) -> list[DocumentChunk]:
        content = Path(path).read_text(encoding="utf-8")
        source = str(path)
        chunks: list[DocumentChunk] = []
        lines = content.split("\n")
        chunk_size = 2000
        chunk_index = 0
        current_lines: list[str] = []

        for line in lines:
            current_lines.append(line)
            if len("\n".join(current_lines)) >= chunk_size:
                text = "\n".join(current_lines).strip()
                if text:
                    chunks.append(
                        DocumentChunk(
                            id=_make_chunk_id(source, chunk_index),
                            source=source,
                            content=text,
                            metadata={
                                "title": Path(path).stem,
                                "headings": [],
                                "format": "text",
                                "created_at": _now_iso(),
                            },
                        )
                    )
                    chunk_index += 1
                    current_lines = []

        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, chunk_index),
                        source=source,
                        content=text,
                        metadata={
                            "title": Path(path).stem,
                            "headings": [],
                            "format": "text",
                            "created_at": _now_iso(),
                        },
                    )
                )

        if not chunks:
            text = content.strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, 0),
                        source=source,
                        content=text,
                        metadata={
                            "title": Path(path).stem,
                            "headings": [],
                            "format": "text",
                            "created_at": _now_iso(),
                        },
                    )
                )

        return chunks


class PDFLoader(DocumentLoader):
    def load(self, path: str) -> list[DocumentChunk]:
        source = str(path)
        text = ""
        try:
            import PyPDF2

            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        except ImportError:
            try:
                import pdfplumber

                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
            except ImportError:
                text = Path(path).read_text(encoding="utf-8", errors="replace")

        if not text.strip():
            return []

        chunks: list[DocumentChunk] = []
        chunk_size = 2000
        chunk_index = 0
        paragraphs = text.split("\n\n")
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if current_chunk and len(current_chunk) + len(para) > chunk_size:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, chunk_index),
                        source=source,
                        content=current_chunk.strip(),
                        metadata={
                            "title": Path(path).stem,
                            "headings": [],
                            "format": "pdf",
                            "created_at": _now_iso(),
                        },
                    )
                )
                chunk_index += 1
                current_chunk = para
            else:
                current_chunk = (current_chunk + "\n\n" + para) if current_chunk else para

        if current_chunk.strip():
            chunks.append(
                DocumentChunk(
                    id=_make_chunk_id(source, chunk_index),
                    source=source,
                    content=current_chunk.strip(),
                    metadata={
                        "title": Path(path).stem,
                        "headings": [],
                        "format": "pdf",
                        "created_at": _now_iso(),
                    },
                )
            )

        return chunks


class SOPLoader(DocumentLoader):
    def load(self, path: str) -> list[DocumentChunk]:
        content = Path(path).read_text(encoding="utf-8")
        source = str(path)
        lines = content.split("\n")
        frontmatter: dict[str, Any] = {}
        body_lines: list[str] = []
        in_frontmatter = False
        frontmatter_closed = False

        for line in lines:
            if not frontmatter_closed and line.strip() == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                frontmatter_closed = True
                continue
            if in_frontmatter and not frontmatter_closed:
                if ":" in line:
                    key, _, value = line.partition(":")
                    frontmatter[key.strip()] = value.strip()
            else:
                body_lines.append(line)

        body = "\n".join(body_lines)
        title = str(frontmatter.get("title", frontmatter.get("name", Path(path).stem)))
        doc_id = str(frontmatter.get("id", frontmatter.get("doc_id", "")))
        version = str(frontmatter.get("version", ""))

        chunks: list[DocumentChunk] = []
        current_heading = ""
        current_lines: list[str] = []
        chunk_index = 0

        for line in body.split("\n"):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        chunks.append(
                            DocumentChunk(
                                id=_make_chunk_id(source, chunk_index),
                                source=source,
                                content=text,
                                metadata={
                                    "title": title,
                                    "headings": [h for h in [title, current_heading] if h],
                                    "format": "sop",
                                    "doc_id": doc_id,
                                    "version": version,
                                    "frontmatter": frontmatter,
                                    "created_at": _now_iso(),
                                },
                            )
                        )
                        chunk_index += 1
                current_heading = m.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, chunk_index),
                        source=source,
                        content=text,
                        metadata={
                            "title": title,
                            "headings": [h for h in [title, current_heading] if h],
                            "format": "sop",
                            "doc_id": doc_id,
                            "version": version,
                            "frontmatter": frontmatter,
                            "created_at": _now_iso(),
                        },
                    )
                )

        if not chunks:
            text = body.strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, 0),
                        source=source,
                        content=text,
                        metadata={
                            "title": title,
                            "headings": [],
                            "format": "sop",
                            "doc_id": doc_id,
                            "version": version,
                            "frontmatter": frontmatter,
                            "created_at": _now_iso(),
                        },
                    )
                )

        return chunks


class RetrospectiveLoader(DocumentLoader):
    SECTION_ALIASES: dict[str, list[str]] = {
        "date": ["date", "incident date"],
        "incident_id": ["incident id", "incident_id", "id", "incident id:"],
        "severity": ["severity", "severity:"],
        "service": ["service", "service(s)", "services", "affected service"],
        "impact": ["impact", "impact summary", "impact:"],
        "root_cause": ["root cause", "root_cause", "root cause:"],
        "detection": ["detection", "how detected", "detection:"],
        "resolution": ["resolution", "fix", "remediation", "resolution:"],
        "timeline": ["timeline", "timeline:"],
        "action_items": ["action items", "follow-up", "follow ups", "action items:"],
    }

    _VALUE_EXTRACTORS: dict[str, list[str]] = {
        "date": ["date", "incident date"],
        "incident_id": ["incident id", "incident_id", "id"],
        "severity": ["severity"],
        "service": ["service"],
    }

    @staticmethod
    def _extract_value(text: str, keys: list[str]) -> str:
        for line in text.split("\n"):
            for key in keys:
                prefix = key + ":"
                if line.strip().lower().startswith(prefix):
                    return line.strip()[len(prefix) :].strip()
        return ""

    def load(self, path: str) -> list[DocumentChunk]:
        content = Path(path).read_text(encoding="utf-8")
        source = str(path)
        title = Path(path).stem.replace("-", " ").replace("_", " ").title()

        parsed: dict[str, Any] = {"title": title, "sections": {}}
        current_section = "preamble"
        section_lines: list[str] = []

        for line in content.split("\n"):
            stripped = line.strip().rstrip(":")
            lower = stripped.lower()
            matched = None
            for section_key, aliases in self.SECTION_ALIASES.items():
                for alias in aliases:
                    if lower == alias or lower.startswith(alias + " "):
                        matched = section_key
                        break
                if matched:
                    break
            if matched:
                if section_lines:
                    parsed["sections"][current_section] = "\n".join(section_lines).strip()
                current_section = matched
                section_lines = [line]
            else:
                section_lines.append(line)

        if section_lines:
            parsed["sections"][current_section] = "\n".join(section_lines).strip()

        # Extract metadata values from sections
        incident_id = ""
        severity_val = ""
        service_val = ""
        date_val = ""
        for section_name, section_content in parsed["sections"].items():
            for meta_key, aliases in self._VALUE_EXTRACTORS.items():
                if meta_key == "incident_id" and not incident_id:
                    incident_id = self._extract_value(section_content, aliases)
                elif meta_key == "severity" and not severity_val:
                    severity_val = self._extract_value(section_content, aliases)
                elif meta_key == "service" and not service_val:
                    service_val = self._extract_value(section_content, aliases)
                elif meta_key == "date" and not date_val:
                    date_val = self._extract_value(section_content, aliases)

        chunks: list[DocumentChunk] = []
        chunk_index = 0
        sections = parsed.get("sections", {})
        for section_name, section_content in sections.items():
            if section_content:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, chunk_index),
                        source=source,
                        content=f"## {section_name.title()}\n{section_content}",
                        metadata={
                            "title": title,
                            "headings": [title, section_name],
                            "format": "retrospective",
                            "section": section_name,
                            "incident_id": incident_id,
                            "severity": severity_val,
                            "service": service_val,
                            "date": date_val,
                            "created_at": _now_iso(),
                        },
                    )
                )
                chunk_index += 1

        if not chunks:
            text = content.strip()
            if text:
                chunks.append(
                    DocumentChunk(
                        id=_make_chunk_id(source, 0),
                        source=source,
                        content=text,
                        metadata={
                            "title": title,
                            "headings": [],
                            "format": "retrospective",
                            "created_at": _now_iso(),
                        },
                    )
                )

        return chunks


_SUPPORTED_EXTENSIONS = {".md", ".mdx", ".txt", ".log", ".pdf"}


def _get_loader(path: str) -> DocumentLoader | None:
    name = Path(path).name.lower()
    if name.endswith(".sop.md") or path.endswith(".sop"):
        return SOPLoader()
    if name.endswith((".retro.md", ".retrospective.md")) or path.endswith(".retro"):
        return RetrospectiveLoader()
    ext = Path(path).suffix.lower()
    loaders: dict[str, DocumentLoader] = {
        ".md": MarkdownLoader(),
        ".mdx": MarkdownLoader(),
        ".txt": TextLoader(),
        ".log": TextLoader(),
        ".pdf": PDFLoader(),
    }
    return loaders.get(ext)


def load_document(path: str) -> list[DocumentChunk]:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Document not found: {path}")
    loader = _get_loader(path)
    if loader is None:
        raise ValueError(f"Unsupported document format: {path}")
    return loader.load(path)


def load_directory(directory: str, recursive: bool = True) -> list[DocumentChunk]:
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"Directory not found: {directory}")
    all_chunks: list[DocumentChunk] = []
    for root, dirs, files in os.walk(directory):
        if not recursive:
            dirs.clear()
        for file in files:
            fp = os.path.join(root, file)
            ext = Path(file).suffix.lower()
            if ext in _SUPPORTED_EXTENSIONS or file.endswith(
                (".sop.md", ".retro.md", ".sop", ".retro")
            ):
                try:
                    all_chunks.extend(load_document(fp))
                except Exception:
                    continue
    return all_chunks
