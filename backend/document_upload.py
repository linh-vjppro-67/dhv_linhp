"""Validate document uploads and convert Word documents for the PDF workflow."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pymupdf
from docx import Document
from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool


def convert_docx(content: bytes) -> bytes:
    return convert_word(content, '.docx')


def convert_word(content: bytes, suffix: str) -> bytes:
    if suffix == '.docx':
        try:
            Document(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(422, 'Tệp DOCX không hợp lệ') from exc
    elif not content.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        raise HTTPException(422, 'Tệp DOC không hợp lệ')
    executable = os.getenv('LIBREOFFICE_PATH') or shutil.which('soffice')
    if not executable:
        mac = Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
        executable = str(mac) if mac.is_file() else None
    if not executable:
        raise HTTPException(503, 'Máy chủ chưa cài LibreOffice để xử lý Word')
    with tempfile.TemporaryDirectory(prefix='dhv-docx-') as directory:
        root = Path(directory)
        source = root / ('document' + suffix)
        source.write_bytes(content)
        try:
            result = subprocess.run(
                [executable, '-env:UserInstallation=' + (root / 'profile').as_uri(),
                 '--headless', '--convert-to', 'pdf:writer_pdf_Export',
                 '--outdir', str(root), str(source)],
                capture_output=True, timeout=90, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(422, 'Chuyển Word sang PDF quá thời gian, vui lòng thử tệp nhỏ hơn') from exc
        except OSError as exc:
            raise HTTPException(503, 'Không khởi động được LibreOffice để xử lý Word') from exc
        output = root / 'document.pdf'
        if result.returncode or not output.is_file():
            raise HTTPException(422, 'Không chuyển được Word sang PDF, vui lòng kiểm tra tệp')
        return output.read_bytes()


def normalize_document(content: bytes, suffix: str) -> bytes:
    if suffix == '.docx':
        content = convert_docx(content)
    elif suffix == '.doc':
        content = convert_word(content, suffix)
    try:
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            if pdf.needs_pass:
                raise HTTPException(422, 'PDF được bảo vệ bằng mật khẩu')
            if not len(pdf):
                raise HTTPException(422, 'Văn bản không có trang')
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, 'Tệp PDF không hợp lệ') from exc
    return content


async def read_document_upload(file: UploadFile, limit: int = 25 * 1024 * 1024) -> bytes:
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.pdf', '.doc', '.docx'}:
        raise HTTPException(400, 'Chỉ chấp nhận tệp PDF, DOC hoặc DOCX')
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f'Tệp vượt quá {limit // (1024 * 1024)} MB')
    return await run_in_threadpool(normalize_document, content, suffix)
