from __future__ import annotations

from email import policy
from email.parser import BytesParser

from fastapi import HTTPException, Request


async def parse_upload_files_request(request: Request) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise HTTPException(status_code=400, detail="请求必须是 multipart/form-data")

    body = await request.body()
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise HTTPException(status_code=400, detail="上传表单解析失败")

    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []

    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition") or ""
        part_filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if part_filename and name == "file":
            files.append((part_filename, payload))
        elif name:
            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset, errors="ignore").strip()

    if not files:
        raise HTTPException(status_code=400, detail="缺少上传文件字段 file")
    return files, fields


async def parse_upload_request(request: Request) -> tuple[str, bytes, dict[str, str]]:
    files, fields = await parse_upload_files_request(request)
    filename, file_content = files[0]
    return filename, file_content, fields
