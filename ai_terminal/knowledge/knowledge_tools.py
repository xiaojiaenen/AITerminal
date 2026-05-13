"""运维知识库工具 — RAG 检索与知识管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wuwei.memory.embedder import Embedder, SimpleEmbedder
from wuwei.memory.knowledge_store import InMemoryKnowledgeStore, KnowledgeChunk


class OpsKnowledgeBase:
    """运维知识库（支持 JSONL 持久化）。"""

    def __init__(
        self,
        store_path: str | None = None,
        embedder: Embedder | None = None,
    ):
        self.embedder = embedder or SimpleEmbedder()
        self.store = InMemoryKnowledgeStore(embedder=self.embedder)

        if store_path:
            self._store_path = self._resolve_store_path(Path(store_path).expanduser())
        else:
            self._store_path = self._resolve_store_path(
                Path("~/.ai-terminal/knowledge/knowledge.jsonl").expanduser()
            )

        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _resolve_store_path(self, path: Path) -> Path:
        """Allow config values to point at either a directory or a JSONL file."""
        if path.exists() and path.is_dir():
            return path / "knowledge.jsonl"
        if path.suffix.lower() == ".jsonl":
            return path
        return path / "knowledge.jsonl"

    async def ingest(
        self,
        text: str,
        source: str = "",
        tags: list[str] | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """导入文档到知识库。返回分块数量。"""
        # 直接使用 wuwei 的 ingest（内部处理分块和嵌入）
        chunks = await self.store.ingest(
            text=text,
            source=source or f"manual_{len(self.store._chunks)}",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if tags:
            for c in chunks:
                c.metadata["tags"] = tags
        self._save()
        return len(chunks)

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """搜索知识库。"""
        results = await self.store.search(query, limit=top_k)
        return [
            {
                "text": r.text,
                "source": r.source,
                "title": r.title or "",
                "metadata": r.metadata,
            }
            for r in results
        ]

    async def ingest_file(self, file_path: str, tags: list[str] | None = None) -> int:
        """从文件导入知识。"""
        from pathlib import Path

        p = Path(file_path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        text = p.read_text(encoding="utf-8")
        return await self.ingest(text, source=str(p), tags=tags)

    def get_stats(self) -> dict[str, Any]:
        """获取知识库统计。"""
        return {
            "total_chunks": len(self.store._chunks.values()),
            "sources": list({c.source for c in self.store._chunks.values() if c.source}),
        }

    def _load(self) -> None:
        """从 JSONL 文件加载知识。"""
        import json

        if not self._store_path.exists():
            return

        for line in self._store_path.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                chunk = KnowledgeChunk(
                    id=data["id"],
                    text=data["text"],
                    source=data.get("source", ""),
                    namespace=data.get("namespace", ""),
                    title=data.get("title", ""),
                    metadata=data.get("metadata", {}),
                )
                self.store._chunks[chunk.id] = chunk
            except (json.JSONDecodeError, KeyError):
                continue

    def _save(self) -> None:
        """保存知识到 JSONL 文件。"""
        import json

        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for c in self.store._chunks.values():
            lines.append(json.dumps({
                "id": c.id,
                "text": c.text,
                "source": c.source,
                "namespace": c.namespace,
                "title": c.title or "",
                "metadata": c.metadata,
            }, ensure_ascii=False))
        self._store_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def register_knowledge_tools(registry: Any, knowledge: OpsKnowledgeBase) -> None:
    """注册知识库相关工具。"""

    @registry.tool(
        name="ingest_knowledge",
        description="导入运维文档到知识库。支持文本内容或文件路径。",
    )
    async def ingest_knowledge(
        text: str = "",
        file_path: str = "",
        source: str = "",
        tags: list[str] | None = None,
    ) -> dict:
        if file_path:
            count = await knowledge.ingest_file(file_path, tags=tags)
            return {"ingested": True, "chunks": count, "source": file_path}
        elif text:
            count = await knowledge.ingest(text, source=source, tags=tags)
            return {"ingested": True, "chunks": count, "source": source}
        else:
            return {"ingested": False, "error": "需要提供 text 或 file_path"}

    @registry.tool(
        name="search_knowledge",
        description="从运维知识库中搜索相关信息。",
    )
    async def search_knowledge(query: str, top_k: int = 5) -> dict:
        results = await knowledge.search(query, top_k=top_k)
        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    @registry.tool(
        name="knowledge_stats",
        description="获取知识库统计信息。",
    )
    async def knowledge_stats() -> dict:
        return knowledge.get_stats()
