__all__ = ["ChromaDB_VectorStore"]


def __getattr__(name):
    if name == "ChromaDB_VectorStore":
        # [CUSTOM] 避免导入包时触发向量嵌入初始化，按需再加载具体实现。
        from .chromadb_vector import ChromaDB_VectorStore

        return ChromaDB_VectorStore
    raise AttributeError(name)
