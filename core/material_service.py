"""用户个人学习资料：私有存储、文本解析和个性化检索。"""
from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core.vision_ocr import (
    IMAGE_SUFFIXES,
    extract_text_from_image_bytes,
    extract_text_from_pdf_via_vision,
)
from schemas.material import MaterialSource

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "runtime" / "app.db"
_MATERIALS_ROOT = _PROJECT_ROOT / "runtime" / "data" / "materials"
# 文本类文件直接抽取；图片与扫描件交给多模态模型识别成文字，之后入库与检索流程完全一致。
_TEXT_SUFFIXES = {".docx", ".pdf", ".md", ".markdown", ".txt"}
_ALLOWED_SUFFIXES = _TEXT_SUFFIXES | set(IMAGE_SUFFIXES)
_MAX_FILE_BYTES = 20 * 1024 * 1024
# 公共别名：上传接口需要在**读入内存之前**就据此限流，
# 而校验发生在 add_material 内部（此时请求体已经完整进内存了）。
MAX_FILE_BYTES = _MAX_FILE_BYTES
ALLOWED_SUFFIXES = frozenset(_ALLOWED_SUFFIXES)


class MaterialService:
    """管理当前用户的资料文件和检索片段。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        _MATERIALS_ROOT.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_materials_user
                    ON materials(user_id, created_at DESC);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _decode_text(raw: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_docx(path: Path) -> str:
        from docx import Document

        document = Document(str(path))
        parts: list[str] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                parts.append(text)
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if values:
                    parts.append(" | ".join(values))
        return "\n\n".join(parts)

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        import fitz

        document = fitz.open(str(path))
        try:
            pages = [page.get_text("text").strip() for page in document]
        finally:
            document.close()
        return "\n\n".join(page for page in pages if page)

    def _extract_text(self, path: Path, suffix: str) -> str:
        if suffix in IMAGE_SUFFIXES:
            return extract_text_from_image_bytes(path.read_bytes())
        if suffix in {".txt", ".md", ".markdown"}:
            return self._decode_text(path.read_bytes())
        if suffix == ".docx":
            return self._extract_docx(path)
        if suffix == ".pdf":
            text = self._extract_pdf(path)
            if text.strip():
                return text
            # 扫描版 PDF 没有文字层，抽出来是空的——渲染成位图再交给多模态模型识别。
            # 此前这类文件会被判为"没有解析到文字"而直接拒绝。
            return extract_text_from_pdf_via_vision(path)
        raise ValueError("暂不支持这种文件格式")

    @staticmethod
    def _chunk_text(text: str, limit: int = 900, overlap: int = 120) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", text or "").strip()
        if not normalized:
            return []
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", normalized) if item.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > limit:
                if current:
                    chunks.append(current.strip())
                    current = ""
                start = 0
                while start < len(paragraph):
                    end = min(len(paragraph), start + limit)
                    chunks.append(paragraph[start:end].strip())
                    if end >= len(paragraph):
                        break
                    start = max(start + 1, end - overlap)
                continue
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if current and len(candidate) > limit:
                chunks.append(current.strip())
                current = paragraph
            else:
                current = candidate
        if current:
            chunks.append(current.strip())
        return [chunk for chunk in chunks if chunk]

    @staticmethod
    def _tokens(text: str) -> Counter:
        normalized = (text or "").lower()
        tokens = re.findall(r"[a-z0-9_]{2,}", normalized)
        cjk = re.findall(r"[\u4e00-\u9fff]", normalized)
        tokens.extend(cjk)
        tokens.extend("".join(cjk[index:index + 2]) for index in range(max(0, len(cjk) - 1)))
        return Counter(tokens)

    def list_materials(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, name, file_type, size_bytes, enabled, status, created_at, updated_at
                   FROM materials WHERE user_id = ? ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "file_type": row["file_type"],
                "size_bytes": row["size_bytes"],
                "enabled": bool(row["enabled"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_material(self, user_id: str, material_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM materials WHERE id = ? AND user_id = ?",
                (material_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def add_material(self, user_id: str, filename: str, data: bytes) -> dict:
        safe_name = Path(filename or "未命名资料").name.strip() or "未命名资料"
        suffix = Path(safe_name).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError("仅支持 DOCX、PDF、Markdown、TXT 和图片（PNG/JPG/WEBP 等）文件")
        if not data:
            raise ValueError("文件内容为空")
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError("单个文件不能超过 20 MB")

        material_id = uuid.uuid4().hex
        user_dir = _MATERIALS_ROOT / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        storage_path = (user_dir / f"{material_id}{suffix}").resolve()
        storage_path.write_bytes(data)
        try:
            extracted = self._extract_text(storage_path, suffix).strip()
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise
        if not extracted:
            storage_path.unlink(missing_ok=True)
            raise ValueError("没有从文件中解析到文字（图片或扫描件未能识别出内容）")

        now = self._now()
        item = {
            "id": material_id,
            "name": safe_name,
            "file_type": suffix.lstrip("."),
            "size_bytes": len(data),
            "enabled": True,
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO materials
                   (id, user_id, name, file_type, size_bytes, storage_path,
                    extracted_text, enabled, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'ready', ?, ?)""",
                (
                    material_id,
                    user_id,
                    safe_name,
                    item["file_type"],
                    len(data),
                    str(storage_path),
                    extracted,
                    now,
                    now,
                ),
            )
        return item

    def set_enabled(self, user_id: str, material_id: str, enabled: bool) -> dict | None:
        now = self._now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE materials SET enabled = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (1 if enabled else 0, now, material_id, user_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_material(user_id, material_id)

    def delete_material(self, user_id: str, material_id: str) -> bool:
        item = self.get_material(user_id, material_id)
        if item is None:
            return False
        storage_path = Path(item["storage_path"]).resolve()
        try:
            storage_path.relative_to(_MATERIALS_ROOT.resolve())
        except ValueError:
            storage_path = None
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM materials WHERE id = ? AND user_id = ?", (material_id, user_id))
        if storage_path is not None:
            storage_path.unlink(missing_ok=True)
        return True

    def build_context(
        self,
        user_id: str,
        material_ids: list[str] | None,
        query: str,
        max_chars: int = 9000,
    ) -> tuple[str, list[dict]]:
        if not material_ids:
            return "", []
        placeholders = ",".join("?" for _ in material_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT id, name, extracted_text FROM materials
                    WHERE user_id = ? AND enabled = 1 AND id IN ({placeholders})""",
                [user_id, *material_ids],
            ).fetchall()
        if not rows:
            return "", []

        query_tokens = self._tokens(query)
        candidates: list[tuple[float, str, dict]] = []
        for row in rows:
            for chunk in self._chunk_text(row["extracted_text"]):
                chunk_tokens = self._tokens(chunk)
                overlap = sum(min(count, chunk_tokens.get(token, 0)) for token, count in query_tokens.items())
                score = overlap / (1.0 + len(chunk) / 1200.0)
                candidates.append((score, chunk, {"id": row["id"], "name": row["name"]}))
        candidates.sort(key=lambda item: item[0], reverse=True)

        selected: list[tuple[str, dict]] = []
        used_chunks: set[str] = set()
        total = 0
        for _, chunk, source in candidates:
            if chunk in used_chunks:
                continue
            if selected and total + len(chunk) > max_chars:
                continue
            selected.append((chunk, source))
            used_chunks.add(chunk)
            total += len(chunk)
            if total >= max_chars or len(selected) >= 12:
                break

        sections: list[str] = []
        sources: list[dict] = []
        seen_sources: set[str] = set()
        for chunk, source in selected:
            sections.append(f"[资料：{source['name']}]\n{chunk}")
            if source["id"] not in seen_sources:
                excerpt = re.sub(r"\s+", " ", chunk).strip()
                # 用 MaterialSource 落定前端依赖的 {id,name,excerpt} 契约，
                # 而不是在这里手写一个无约束的 dict（该模型此前没有任何使用方）。
                sources.append(MaterialSource(
                    id=str(source["id"]),
                    name=str(source["name"]),
                    excerpt=excerpt[:180],
                ).model_dump())
                seen_sources.add(source["id"])
        return "\n\n---\n\n".join(sections), sources