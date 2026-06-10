import logging
import os
import shutil
import tempfile
import uuid
from pathlib import PurePosixPath
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException

from app.schemas.api_models import (
    AnswerResponse,
    BatchUploadResponse,
    BatchUploadResult,
    QuestionRequest,
    SingleUploadResponse,
)
from app.services.kb_registry import (
    clear_all_knowledge_bases,
    count_knowledge_bases,
    delete_knowledge_base,
    list_knowledge_bases,
)
from app.services.upload_service import create_knowledge_base_from_saved_pdf
from utils.utils import check_network

from app.services.chat_service import build_chat_state_from_request, chat_with_rag_state
from app.services.agent_chat_service import chat_with_agent_state

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 100 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024

app = FastAPI(
    title="RAG PDF 智能问答系统",
    description="基于FastAPI的PDF知识库问答服务"
)


def _validate_pdf_upload_filename(raw_filename: str | None) -> str:
    if raw_filename is None or not str(raw_filename).strip():
        raise HTTPException(status_code=400, detail="缺少有效的文件名")

    name = str(raw_filename).strip()
    if "\x00" in name:
        raise HTTPException(status_code=400, detail="文件名包含非法字符")

    normalized = name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if len(parts) != 1:
        raise HTTPException(
            status_code=400,
            detail="文件名不能包含路径、目录分隔符或路径穿越序列",
        )

    base = parts[0]
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="文件名无效")

    if len(base) > 255:
        raise HTTPException(status_code=400, detail="文件名过长")

    if not base.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 格式（扩展名须为 .pdf）")

    return base


def _assert_pdf_magic_and_nonempty(path: str) -> None:
    size = os.path.getsize(path)
    if size == 0:
        raise HTTPException(status_code=400, detail="上传文件为空")

    with open(path, "rb") as f:
        header = f.read(5)

    if len(header) < 4 or not header.startswith(b"%PDF"):
        raise HTTPException(
            status_code=415,
            detail="文件内容与 PDF 格式不符（请以真实 PDF 文件上传）",
        )


@app.post("/upload_pdf/", response_model=SingleUploadResponse, summary="上传单个PDF并构建知识库")
async def upload_single_pdf(file: UploadFile = File(...)):
    temp_dir: str | None = None
    safe_filename = ""

    try:
        safe_filename = _validate_pdf_upload_filename(file.filename)

        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}.pdf")

        total_written = 0
        with open(temp_pdf_path, "wb") as buffer:
            while True:
                chunk = await file.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break

                total_written += len(chunk)
                if total_written > MAX_PDF_BYTES:
                    raise HTTPException(status_code=413, detail="PDF 文件超过允许的大小上限")

                buffer.write(chunk)

        _assert_pdf_magic_and_nonempty(temp_pdf_path)

        logger.info("开始构建知识库: temp_path=%s, client_filename=%s", temp_pdf_path, safe_filename)
        result = create_knowledge_base_from_saved_pdf(temp_pdf_path, safe_filename)
        return result

    except HTTPException:
        raise
    except OSError as e:
        logger.exception("保存或读取上传 PDF 时发生系统错误: %s", e)
        raise HTTPException(status_code=500, detail="保存或读取上传文件失败，请稍后重试")
    except ValueError as e:
        logger.warning("上传 PDF 参数或数据无效: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("上传 PDF 时发生未预期错误")
        raise HTTPException(
            status_code=500,
            detail="服务器处理上传请求时发生错误，请稍后重试",
        ) from e
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        await file.close()


@app.post("/upload_pdfs/", response_model=BatchUploadResponse, summary="批量上传多个PDF")
async def upload_multiple_pdfs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个PDF文件")

    results = []
    uploaded_count = 0
    failed_count = 0

    for file in files:
        temp_dir = None
        try:
            safe_filename = _validate_pdf_upload_filename(file.filename)

            temp_dir = tempfile.mkdtemp()
            temp_pdf_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}.pdf")

            total_written = 0
            with open(temp_pdf_path, "wb") as buffer:
                while True:
                    chunk = await file.read(COPY_CHUNK_BYTES)
                    if not chunk:
                        break
                    total_written += len(chunk)
                    if total_written > MAX_PDF_BYTES:
                        raise HTTPException(status_code=413, detail="PDF 文件超过允许的大小上限")
                    buffer.write(chunk)

            _assert_pdf_magic_and_nonempty(temp_pdf_path)

            result_data = create_knowledge_base_from_saved_pdf(temp_pdf_path, safe_filename)
            result = BatchUploadResult(
                filename=safe_filename,
                knowledge_base_id=result_data["knowledge_base_id"],
                status=result_data["status"],
                message=result_data["message"],
                chunks_count=result_data["chunks_count"],
            )
            results.append(result)
            uploaded_count += 1

        except HTTPException as e:
            results.append(
                BatchUploadResult(
                    filename=file.filename or "unknown.pdf",
                    status="error",
                    message=e.detail,
                )
            )
            failed_count += 1

        except Exception as e:
            results.append(
                BatchUploadResult(
                    filename=file.filename or "unknown.pdf",
                    status="error",
                    message=str(e),
                )
            )
            failed_count += 1

        finally:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            await file.close()

    return {
        "results": results,
        "total_uploaded": uploaded_count,
        "total_failed": failed_count,
    }


@app.post("/ask/", response_model=AnswerResponse, summary="提问接口（Agent 默认入口）")
async def ask_question(request: QuestionRequest):
    try:
        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        result = chat_with_agent_state(request)

        return {
            "answer": result["answer"],
            "knowledge_base_id": request.knowledge_base_id,
            "history": result["history"],
            "debug": result["debug"],
            "mode": "agent",
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@app.post("/ask_rag/", response_model=AnswerResponse, summary="经典 RAG 提问接口（回退模式）")
async def ask_question_rag(request: QuestionRequest):
    try:
        if not check_network():
            raise HTTPException(status_code=500, detail="网络连接异常，无法调用AI服务")

        state = build_chat_state_from_request(request)
        answer, updated_history = chat_with_rag_state(state)

        return {
            "answer": answer,
            "knowledge_base_id": state.knowledge_base_id,
            "history": updated_history,
            "debug": None,
            "mode": "rag",
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("经典 RAG 问答时出错: %s", str(e))
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

@app.get("/knowledge_bases", summary="获取所有知识库列表")
async def get_knowledge_bases():
    kb_info = list_knowledge_bases()
    return {
        "total": count_knowledge_bases(),
        "knowledge_bases": kb_info,
    }


@app.delete("/knowledge_base/{kb_id}", summary="删除知识库")
async def delete_kb(kb_id: str):
    success = delete_knowledge_base(kb_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识库不存在")

    return {"message": f"知识库 {kb_id} 已删除"}


@app.delete("/clear_all_knowledge_bases", summary="清空所有知识库")
async def clear_all_kbs():
    count = clear_all_knowledge_bases()
    return {"message": f"已清空所有 {count} 个知识库"}


@app.get("/health", summary="健康检查")
async def health_check():
    network_ok = check_network()
    return {
        "status": "healthy" if network_ok else "network_error",
        "network_connected": network_ok,
        "active_knowledge_bases": count_knowledge_bases(),
    }


@app.get("/", summary="API文档")
async def root():
    return {
        "message": "RAG PDF 智能问答系统 API",
        "docs_url": "/docs",
        "endpoints": {
            "upload_single": "POST /upload_pdf/ - 上传单个PDF",
            "upload_multiple": "POST /upload_pdfs/ - 批量上传多个PDF",
            "ask": "POST /ask/ - Agent 问答主入口",
            "ask_rag": "POST /ask_rag/ - 经典RAG回退入口",
            "list_kbs": "GET /knowledge_bases - 查看所有知识库",
            "delete_kb": "DELETE /knowledge_base/{id} - 删除指定知识库"
}
    }