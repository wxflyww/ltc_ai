from fastapi import APIRouter, File, UploadFile

from app.capabilities.contract_review.schemas import AttachmentInput, ContractReviewRequest
from app.capabilities.contract_review.service import review_contract
from app.core.errors import ValidationError
from app.core.response import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["contract-review"])


@router.post("/contract-review")
def contract_review_endpoint(request: ContractReviewRequest) -> dict:
    data = review_contract(request)
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body


def _ensure_md_file(file: UploadFile, label: str) -> None:
    filename = file.filename or ""
    if not filename.lower().endswith(".md"):
        raise ValidationError(f"{label}必须是.md文件")


async def _read_utf8_text(file: UploadFile, label: str) -> str:
    try:
        return (await file.read()).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{label}必须是UTF-8编码的.md文件") from exc


@router.post("/contract-review/upload-md")
async def contract_review_upload_md_endpoint(
    contract_file: UploadFile = File(...),
    attachment_files: list[UploadFile] | None = File(default=None),
) -> dict:
    _ensure_md_file(contract_file, "合同正文")
    contract_md = await _read_utf8_text(contract_file, "合同正文")
    if not contract_md.strip():
        raise ValidationError("合同正文md文件内容不能为空")

    attachments: list[AttachmentInput] = []
    for index, attachment_file in enumerate(attachment_files or [], start=1):
        _ensure_md_file(attachment_file, f"附件{index}")
        attachments.append(AttachmentInput(
            index=index,
            filename=attachment_file.filename or f"attachment-{index}.md",
            file_type="md",
            text=await _read_utf8_text(attachment_file, f"附件{index}"),
        ))

    data = review_contract(ContractReviewRequest(contract_md=contract_md, attachments=attachments))
    body = ApiResponse(data=data).to_dict()
    body.setdefault("traceId", "")
    body.setdefault("duration_seconds", 0.0)
    return body
