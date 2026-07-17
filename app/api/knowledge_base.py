from fastapi import APIRouter, HTTPException

from app.services.kb_registry import (
    clear_all_knowledge_bases,
    count_knowledge_bases,
    delete_knowledge_base,
    list_knowledge_bases,
)

router = APIRouter()


@router.get("/knowledge_bases", summary="获取所有知识库列表")
async def get_knowledge_bases():
    kb_info = list_knowledge_bases()
    return {
        "total": count_knowledge_bases(),
        "knowledge_bases": kb_info,
    }


@router.delete("/knowledge_base/{kb_id}", summary="删除知识库")
async def delete_kb(kb_id: str):
    success = delete_knowledge_base(kb_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识库不存在")

    return {"message": f"知识库 {kb_id} 已删除"}


@router.delete("/clear_all_knowledge_bases", summary="清空所有知识库")
async def clear_all_kbs():
    count = clear_all_knowledge_bases()
    return {"message": f"已清空所有 {count} 个知识库"}
