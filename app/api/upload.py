import logging
import os
import shutil
import tempfile
import uuid
from pathlib import PurePosixPath
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.api.routes_auth import get_current_user
from app.models.user import User
from app.schemas.api_models import (
    BatchUploadResponse,
    BatchUploadResult,
    SingleUploadResponse,
)
from app.services.upload_service import create_knowledge_base_from_saved_pdf

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_PDF_BYTES = 100 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024


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


@router.post("/documents/upload", response_model=SingleUploadResponse, summary="上传单个PDF并构建知识库")
@router.post("/upload_pdf/", response_model=SingleUploadResponse, summary="上传单个PDF并构建知识库")
async def upload_single_pdf(
    file: UploadFile = File(...),
    collection_id: UUID | None = Query(default=None, description="可选：目标知识库集合 ID"),
    current_user: User = Depends(get_current_user),
):
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
        result = create_knowledge_base_from_saved_pdf(
            temp_pdf_path,
            safe_filename,
            user_id=current_user.id,
            collection_id=collection_id,
            content_type=file.content_type or "application/pdf",
        )
        return result

    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
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


@router.post("/upload_pdfs/", response_model=BatchUploadResponse, summary="批量上传多个PDF")
async def upload_multiple_pdfs(
    files: List[UploadFile] = File(...),
    collection_id: UUID | None = Query(default=None, description="可选：目标知识库集合 ID"),
    current_user: User = Depends(get_current_user),
):
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

            result_data = create_knowledge_base_from_saved_pdf(
                temp_pdf_path,
                safe_filename,
                user_id=current_user.id,
                collection_id=collection_id,
                content_type=file.content_type or "application/pdf",
            )
            result = BatchUploadResult(
                filename=safe_filename,
                knowledge_base_id=result_data["knowledge_base_id"],
                collection_id=result_data.get("collection_id"),
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
