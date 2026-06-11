from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from rag import RAGSystem



knowledge_bases: Dict[str, "RAGSystem"] = {}


def register_knowledge_base(kb_id: str, rag_system: "RAGSystem") -> None:
    knowledge_bases[kb_id] = rag_system


def get_knowledge_base(kb_id: str) -> Optional["RAGSystem"]:
    return knowledge_bases.get(kb_id)


def list_knowledge_bases() -> list[dict]:
    kb_info = []
    for kb_id, rag_system in knowledge_bases.items():
        kb_info.append({
            "id": kb_id,
            "chunks_count": len(rag_system.chunks),
            "status": "ready"
        })
    return kb_info


def delete_knowledge_base(kb_id: str) -> bool:
    if kb_id not in knowledge_bases:
        return False
    del knowledge_bases[kb_id]
    return True


def clear_all_knowledge_bases() -> int:
    count = len(knowledge_bases)
    knowledge_bases.clear()
    return count


def count_knowledge_bases() -> int:
    return len(knowledge_bases)


def get_all_ids() -> list[str]:
    return list(knowledge_bases.keys())