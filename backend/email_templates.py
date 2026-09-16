"""Vietnamese office email templates; rendering never sends email."""
from datetime import date
from html import escape

MONTHLY_SUBJECT = '[NHẮC] THỰC HIỆN ĐỊNH KỲ GỬI BÁO CÁO THÁNG VÀ PHƯƠNG HƯỚNG HOẠT ĐỘNG THÁNG TIẾP THEO'


def monthly_reminder(month: date):
    deadline = month.replace(day=28)
    weekday = ['thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy', 'Chủ nhật'][deadline.weekday()]
    return {
        'subject': MONTHLY_SUBJECT,
        'send_date': month.replace(day=25).isoformat(),
        'deadline': deadline.isoformat(),
        'content': 'Kính gửi: Các đơn vị thuộc Trường\n\n'
        'Căn cứ email của Văn phòng Trường gửi ngày 30/3/2026 nhắc các đơn vị chủ động gửi định kỳ, chậm nhất ngày 28 hàng tháng về việc thực hiện báo cáo kết quả thực hiện nhiệm vụ trong tháng trước và phương hướng nhiệm vụ trọng tâm của tháng tiếp theo.\n\n'
        'Bằng email này, Văn phòng Trường kính đề nghị các đơn vị gửi báo cáo đầy đủ, đúng hạn để đảm bảo tiến độ tổng hợp chung.\n\n'
        f'Hạn chót nhận báo cáo vào {weekday}, ngày {deadline:%d/%m/%Y}.\n\n'
        'Trân trọng cảm ơn sự phối hợp của các đơn vị./.',
    }


def monthly_report(month: date, unit: str):
    following = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return {
        'subject': f'Báo cáo kết quả thực hiện nhiệm vụ tháng {month:%m/%Y} và phương hướng hoạt động tháng {following:%m/%Y}',
        'content': 'Kính gửi: Văn phòng Trường,\n\n'
        f'{unit} kính gửi báo cáo kết quả thực hiện nhiệm vụ trong tháng {month:%m/%Y} và phương hướng nhiệm vụ trọng tâm của tháng {following:%m/%Y}. File chi tiết đính kèm theo email.\n\nTrân trọng./.',
    }


def incoming_email(title: str, units: list[str], symbol: str, issued: date | None, approval: str):
    return {
        'subject': title,
        'content': f'Kính gửi: {", ".join(units)}\n\n'
        'Theo ý kiến chỉ đạo xử lý văn bản đến của Phó Hiệu trưởng - TS. Lương Thị Hòa đối với '
        f'Công văn đến số {symbol or "[số công văn]"} ngày {issued.strftime("%d/%m/%Y") if issued else "[ngày công văn]"}. '
        f'{title}: đồng ý đề xuất của Văn phòng Trường – {approval}\n\n'
        'Văn phòng Trường kính chuyển văn bản đến quý đơn vị.\n\nTrân trọng./.',
    }


def template_html(template):
    return ''.join('<p>' + escape(paragraph).replace('\n', '<br>') + '</p>' for paragraph in template['content'].split('\n\n'))
