from datetime import date

from odoo import fields


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT_MARGIN = 40
RIGHT_MARGIN = 555
ROW_HEIGHT = 24
FOOTER_Y = 35

CUSTOMER_BOX_X = 330
CUSTOMER_BOX_WIDTH = 225
CUSTOMER_BOX_PADDING = 10
CUSTOMER_NAME_WRAP = 30
ADDRESS_WRAP = 32


def build_statement_pdf(moves, company, partner):
    customer_box_top = 790
    rows = [_statement_row(move) for move in moves]
    total = sum(row['residual'] for row in rows)
    company_lines = _company_info_lines(company)
    customer_lines = _customer_info_lines(partner)
    customer_box_height = len(customer_lines) * 13 + CUSTOMER_BOX_PADDING * 2
    company_box_height = CUSTOMER_BOX_PADDING + 3 + len(company_lines) * 12
    table_top = customer_box_top - max(customer_box_height, company_box_height) - 40
    rows_per_page = max(1, (table_top - FOOTER_Y - 45) // ROW_HEIGHT)
    pages = [rows[index:index + rows_per_page] for index in range(0, len(rows), rows_per_page)]
    if not pages:
        pages = [[]]
    statement_date = _format_date(fields.Date.context_today(moves[:1]))
    streams = [_page_stream(
        page_rows, company, company_lines, customer_lines, customer_box_top,
        customer_box_height, table_top, page_number, len(pages),
        total if page_number == len(pages) else None,
        statement_date if page_number == 1 else None,
    ) for page_number, page_rows in enumerate(pages, start=1)]
    return _make_pdf(streams)


def _statement_row(move):
    return {
        'name': move.name or '',
        'invoice_date': _format_date(move.invoice_date),
        'due_date': _format_date(move.invoice_date_due),
        'amount': _format_amount(move.amount_residual, move.currency_id),
        'aging': move._soa_aging_label(),
        'overdue': move._soa_is_overdue(),
        'residual': move.amount_residual,
    }


def _format_date(value):
    if not value:
        return ''
    if isinstance(value, date):
        return value.strftime('%m/%d/%Y')
    return str(value)


def _format_amount(amount, currency):
    symbol = currency.symbol or currency.name or ''
    formatted = '{:,.2f}'.format(amount)
    return '%s %s' % (symbol, formatted) if currency.position == 'before' else '%s %s' % (formatted, symbol)


def _company_info_lines(company):
    lines = [(company.name or '', True)]
    for value in _address_lines(company.partner_id):
        for wrapped in _wrap_text(value, ADDRESS_WRAP):
            lines.append((wrapped, False))
    lines.append(('Tax ID: %s' % (company.vat or '-'), False))
    return lines


def _customer_info_lines(partner):
    lines = [('Customer Name:', True)]
    for name_line in _wrap_text(partner.name or '', CUSTOMER_NAME_WRAP):
        lines.append((name_line, True))
    for addr_line in _customer_address_lines(partner):
        lines.append((addr_line, False))
    lines.append(('NPWP: %s' % (partner.vat or '-'), False))
    return lines


def _page_stream(rows, company, company_lines, customer_lines,
                 customer_box_top, customer_box_height, table_top,
                 page_number, page_count, total, statement_date=None):
    commands = []
    y_position = customer_box_top - CUSTOMER_BOX_PADDING - 3
    _text_right(commands, CUSTOMER_BOX_X + CUSTOMER_BOX_WIDTH, 800, 'Statement of Account', 18, bold=True)
    for value, bold in company_lines:
        _text(commands, LEFT_MARGIN, y_position, value, 10 if bold else 9, bold=bold)
        y_position -= 12
    _rect_border(commands, CUSTOMER_BOX_X, customer_box_top - customer_box_height,
                 CUSTOMER_BOX_WIDTH, customer_box_height, stroke_red=True)
    y_position = customer_box_top - CUSTOMER_BOX_PADDING - 3
    for value, bold in customer_lines:
        _text(commands, CUSTOMER_BOX_X + CUSTOMER_BOX_PADDING, y_position, value, 9, bold=bold)
        y_position -= 13
    if statement_date:
        _text(commands, LEFT_MARGIN, table_top + 28, 'Date: %s' % statement_date, 9)
    _rect(commands, LEFT_MARGIN, table_top, RIGHT_MARGIN - LEFT_MARGIN, 20, fill_gray=0.9)
    headers = [('Invoice', 48), ('Invoice Date', 190), ('Due Date', 290), ('Amount Due', 385), ('Aging', 500)]
    for label, x_position in headers:
        _text(commands, x_position, table_top + 6, label, 9, bold=True)
    y_position = table_top - 14
    for row in rows:
        _text(commands, 48, y_position, row['name'], 9)
        _text(commands, 190, y_position, row['invoice_date'], 9)
        _text(commands, 290, y_position, row['due_date'], 9)
        _text_right(commands, 485, y_position, row['amount'], 9)
        _text_right(commands, 545, y_position, row['aging'], 9,
                    color='0.85 0.15 0.15' if row['overdue'] else None)
        _line(commands, LEFT_MARGIN, y_position - 6, RIGHT_MARGIN, y_position - 6)
        y_position -= ROW_HEIGHT
    if total is not None:
        _text(commands, 48, y_position - 10, 'Total', 10, bold=True)
        _text_right(commands, 485, y_position - 10, _format_amount(total, company.currency_id), 10, bold=True)
    _text(commands, LEFT_MARGIN, FOOTER_Y, company.name or '', 8)
    _text_right(commands, RIGHT_MARGIN, FOOTER_Y, 'Page %s of %s' % (page_number, page_count), 8)
    return '\n'.join(commands).encode('latin-1', 'replace')


def _text(commands, x_position, y_position, value, size, bold=False, color=None):
    font = 'F2' if bold else 'F1'
    if color:
        commands.append('%s rg' % color)
    commands.append('BT /%s %s Tf 1 0 0 1 %s %s Tm (%s) Tj ET' % (
        font, size, x_position, y_position, _escape(value)))
    if color:
        commands.append('0 0 0 rg')


def _text_right(commands, right_edge, y_position, value, size, bold=False, color=None):
    width = len(str(value)) * size * 0.52
    _text(commands, right_edge - width, y_position, value, size, bold, color)


def _line(commands, x_one, y_one, x_two, y_two):
    commands.append('0.75 G %s %s m %s %s l S' % (x_one, y_one, x_two, y_two))


def _rect(commands, x_position, y_position, width, height, fill_gray):
    commands.append('%s g %s %s %s %s re f 0 g' % (
        fill_gray, x_position, y_position, width, height))


def _rect_border(commands, x_position, y_position, width, height, stroke_red=False):
    color = '0.85 0.25 0.1 RG' if stroke_red else '0 G'
    commands.append('%s 0.8 w %s %s %s %s re S 0 G' % (
        color, x_position, y_position, width, height))


def _address_lines(partner):
    city_line = ' '.join(item for item in [
        partner.city,
        partner.state_id.code or partner.state_id.name,
        partner.zip,
    ] if item)
    values = [partner.street, partner.street2, city_line, partner.country_id.name]
    return [value for value in values if value]


def _customer_address_lines(partner):
    lines = []
    for value in _address_lines(partner):
        lines.extend(_wrap_text(value, 22))
    return lines or ['-']


def _wrap_text(value, width):
    words = str(value).split()
    lines = []
    current_line = ''
    for word in words:
        proposed_line = '%s %s' % (current_line, word) if current_line else word
        if current_line and len(proposed_line) > width:
            lines.append(current_line)
            current_line = word
        else:
            current_line = proposed_line
    if current_line:
        lines.append(current_line)
    return lines


def _escape(value):
    return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _make_pdf(streams):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', None,
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>']
    page_ids = []
    for stream in streams:
        page_ids.append(len(objects) + 1)
        objects.append(None)
        objects.append(b'<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream))
    objects[1] = ('<< /Type /Pages /Kids [%s] /Count %d >>' % (
        ' '.join('%s 0 R' % page_id for page_id in page_ids), len(page_ids))).encode()
    for page_id in page_ids:
        content_id = page_id + 1
        objects[page_id - 1] = ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] '
                                '/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
                                '/Contents %s 0 R >>' % (PAGE_WIDTH, PAGE_HEIGHT, content_id)).encode()
    result = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(('%s 0 obj\n' % object_id).encode())
        result.extend(content)
        result.extend(b'\nendobj\n')
    xref_offset = len(result)
    result.extend(('xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)).encode())
    for offset in offsets[1:]:
        result.extend(('%010d 00000 n \n' % offset).encode())
    result.extend(('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF' % (
        len(objects) + 1, xref_offset)).encode())
    return bytes(result)
