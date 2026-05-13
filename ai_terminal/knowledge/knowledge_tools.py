"""运维知识库工具 — RAG 检索与知识管理。"""

from __future__ import annotations

from typing import Any

from wuwei.memory.knowledge_store import InMemoryKnowledgeStore, KnowledgeChunk
from wuwei.memory.embedder import SimpleEmbedder, Embedder


class OpsKnowledgeBase:
    """运维知识库。"""

    def __init__(
        self,
        store_path: str | None = None,
        embedder: Embedder | None = None,
    ):
        self.embedder = embedder or SimpleEmbedder()
        self.store = InMemoryKnowledgeStore(embedder=self.embedder)
        self._store_path = store_path

    async def ingest(
        self,
        text: str,
        source: str = "",
        tags: list[str] | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """导入文档到知识库。返回分块数量。"""
        chunks = self._split_text(text, chunk_size, chunk_overlap)
        knowledge_chunks = []
        for i, chunk_text in enumerate(chunks):
            kc = KnowledgeChunk(
                id=f"{source}_{i}" if source else f"chunk_{i}",
                content=chunk_text,
                source=source,
                metadata={"tags": tags or [], "chunk_index": i},
            )
            knowledge_chunks.append(kc)

        await self.store.add_batch(knowledge_chunks)
        return len(knowledge_chunks)

    def _split_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        """智能分块：按段落优先，其次按句子。"""
        # 先按段落分
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) + 2 <= chunk_size:
                current = current + "\n\n" + para if current else para
            else:
                if current:
                    chunks.append(current)
                # 段落本身太长则按句子分
                if len(para) > chunk_size:
                    sentences = para.replace("。", "。\n").replace(". ", ".\n").split("\n")
                    sub_current = ""
                    for sent in sentences:
                        sent = sent.strip()
                        if not sent:
                            continue
                        if len(sub_current) + len(sent) + 1 <= chunk_size:
                            sub_current = sub_current + " " + sent if sub_current else sent
                        else:
                            if sub_current:
                                chunks.append(sub_current)
                            sub_current = sent
                    if sub_current:
                        current = sub_current
                    else:
                        current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        # 处理重叠
        if overlap > 0 and len(chunks) > 1:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                prev_tail = chunks[i - 1][-overlap:]
                overlapped.append(prev_tail + " " + chunks[i])
            return overlapped

        return chunks

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """搜索知识库。"""
        results = await self.store.search(query, top_k=top_k)
        return [
            {
                "content": r.content,
                "source": r.source,
                "score": r.score,
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
            "total_chunks": len(self.store._chunks),
            "sources": list(set(c.source for c in self.store._chunks if c.source)),
        }


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
