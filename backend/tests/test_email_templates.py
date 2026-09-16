import unittest
from datetime import date
from backend.email_templates import monthly_reminder, monthly_report, incoming_email, template_html


class EmailTemplateTests(unittest.TestCase):
    def test_monthly_dates_and_weekday(self):
        template = monthly_reminder(date(2026, 9, 1))
        self.assertEqual(template['send_date'], '2026-09-25')
        self.assertEqual(template['deadline'], '2026-09-28')
        self.assertIn('thứ Hai, ngày 28/09/2026', template['content'])
        self.assertIn('30/3/2026', template['content'])
        self.assertEqual(monthly_reminder(date(2028, 2, 29))['deadline'], '2028-02-28')

    def test_report_month_rollover_and_unit(self):
        template = monthly_report(date(2026, 12, 1), 'Viện Văn hóa Doanh nghiệp')
        self.assertIn('tháng 12/2026', template['content'])
        self.assertIn('tháng 01/2027', template['content'])
        self.assertIn('Viện Văn hóa Doanh nghiệp kính gửi', template['content'])

    def test_incoming_content_and_html_escaping(self):
        template = incoming_email('Trích yếu <script>', ['Đơn vị A', 'Đơn vị B'], '123/CV', date(2026, 9, 15), 'Đề xuất đã duyệt')
        self.assertEqual(template['subject'], 'Trích yếu <script>')
        self.assertIn('Kính gửi: Đơn vị A, Đơn vị B', template['content'])
        self.assertIn('123/CV ngày 15/09/2026', template['content'])
        self.assertIn('TS. Lương Thị Hòa', template['content'])
        self.assertIn('Đề xuất đã duyệt', template['content'])
        self.assertNotIn('<script>', template_html(template))
