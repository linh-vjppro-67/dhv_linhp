import unittest
from datetime import date
from backend.app import number_symbol


class DocumentSymbolTests(unittest.TestCase):
    def test_school_document_formats(self):
        expected = {
            'QUYẾT ĐỊNH': 'QĐ-ĐHHV', 'THÔNG BÁO': 'TB-ĐHHV',
            'KẾ HOẠCH': 'KH-ĐHHV', 'BÁO CÁO': 'BC-ĐHHV',
            'CÔNG VĂN': 'ĐHHV', 'TỜ TRÌNH': 'TTr-ĐHHV',
            'HỢP ĐỒNG': 'HĐ-ĐHHV', 'THOẢ THUẬN': 'TT-ĐHHV',
            'BIÊN BẢN': 'BB-ĐHHV', 'NGHỊ QUYẾT HỘI ĐỒNG TRƯỜNG': 'NQ-HĐT',
            'QUYẾT ĐỊNH HỘI ĐỒNG TRƯỜNG': 'QĐ-HĐT', 'GIẤY UỶ QUYỀN': 'GUQ-ĐHHV',
            'GIẤY XÁC NHẬN': 'GXN-ĐHHV', 'GIẤY GIỚI THIỆU': 'GGT-ĐHHV',
            'GIẤY CHỨNG NHẬN': 'GCN-ĐHHV', 'THƯ MỜI': 'TM-ĐHHV',
            'CHUYỂN ĐIỂM': 'CĐ-ĐHHV',
        }
        for kind, suffix in expected.items():
            with self.subTest(kind=kind):
                self.assertEqual(number_symbol(kind,1,date(2026,1,1),'OUT'),f'01/2026/{suffix}')
                self.assertEqual(number_symbol(kind,123,date(2027,1,1),'OUT'),f'123/2027/{suffix}')

    def test_incoming_includes_year(self):
        self.assertEqual(number_symbol('CÔNG VĂN',1,date(2026,1,1),'IN'),'01/2026/CVDEN')
        self.assertEqual(number_symbol('CÔNG VĂN ĐẾN',1,date(2026,1,1)),'01/2026/CVDEN')
        self.assertEqual(number_symbol('CÔNG VĂN ĐI',1,date(2026,1,1)),'01/2026/ĐHHV')

