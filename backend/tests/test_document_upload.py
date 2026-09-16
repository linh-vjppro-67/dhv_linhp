import asyncio
import io
import unittest
from unittest.mock import patch

import pymupdf
from docx import Document
from fastapi import HTTPException, UploadFile
from backend.document_upload import read_document_upload, normalize_document


class DocumentUploadTests(unittest.TestCase):
    def setUp(self):
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40, 40), 'Converted document')
            self.pdf = pdf.tobytes()

    def test_pdf_preserved_and_invalid_inputs_rejected(self):
        self.assertEqual(normalize_document(self.pdf, '.pdf'), self.pdf)
        for name, data, status in [('bad.pdf', b'invalid', 422), ('bad.docx', b'invalid', 422), ('bad.doc', b'invalid', 422), ('bad.exe', self.pdf, 400)]:
            with self.subTest(name=name), self.assertRaises(HTTPException) as caught:
                asyncio.run(read_document_upload(UploadFile(filename=name, file=io.BytesIO(data))))
            self.assertEqual(caught.exception.status_code, status)

    def test_docx_conversion_and_size_limit(self):
        with patch('backend.document_upload.convert_docx', return_value=self.pdf) as convert:
            result = asyncio.run(read_document_upload(UploadFile(filename='file.DOCX', file=io.BytesIO(b'word'))))
            self.assertEqual(result, self.pdf)
            convert.assert_called_once_with(b'word')
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(read_document_upload(UploadFile(filename='file.pdf', file=io.BytesIO(b'1234')), limit=3))
        self.assertEqual(caught.exception.status_code, 413)

    def test_legacy_doc_upload_uses_word_converter(self):
        with patch('backend.document_upload.convert_word', return_value=self.pdf) as convert:
            result = asyncio.run(read_document_upload(UploadFile(filename='file.DOC', file=io.BytesIO(b'legacy'))))
            self.assertEqual(result, self.pdf)
            convert.assert_called_once_with(b'legacy', '.doc')

    def test_missing_converter_reports_configuration_error(self):
        word = Document()
        word.add_paragraph('Test')
        stream = io.BytesIO()
        word.save(stream)
        with patch.dict('os.environ', {'LIBREOFFICE_PATH': ''}), patch('backend.document_upload.shutil.which', return_value=None), patch('backend.document_upload.Path.is_file', return_value=False):
            with self.assertRaises(HTTPException) as caught:
                normalize_document(stream.getvalue(), '.docx')
            self.assertEqual(caught.exception.status_code, 503)
