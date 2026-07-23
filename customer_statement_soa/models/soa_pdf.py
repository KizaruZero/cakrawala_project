from datetime import date


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT_MARGIN = 40
RIGHT_MARGIN = 555
ROW_HEIGHT = 24
ROWS_PER_PAGE = 22


def build_statement_pdf(moves, company, partner):
    rows = [_statement_row(move) for move in moves]
    pages = [rows[index:index + ROWS_PER_PAGE] for index in range(0, len(rows), ROWS_PER_PAGE)]
    if not pages:
        pages = [[]]
    streams = [_page_stream(page_rows, company, partner, page_number, len(pages))
               for page_number, page_rows in enumerate(pages, start=1)]
    return _make_pdf(streams)


def _statement_row(move):
    return {
        'name': move.name or '',
        'invoice_date': _format_date(move.invoice_date),
        'due_date': _format_date(move.invoice_date_due),
        'amount': _format_amount(move.amount_residual, move.currency_id),
        'aging': move._soa_aging_label(),
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


def _page_stream(rows, company, partner, page_number, page_count):
    commands = []
    _text(commands, 225, 790, 'Customer Statement', 18, bold=True)
    _text(commands, LEFT_MARGIN, 750, company.name or '', 12, bold=True)
    _rect_border(commands, 330, 695, 225, 55, stroke_red=True)
    _text(commands, 340, 733, 'Customer Name', 10, bold=True)
    _text(commands, 430, 733, ': %s' % partner.name, 10, bold=True)
    _text(commands, 340, 712, 'NPWP', 10, bold=True)
    _text(commands, 430, 712, ': %s' % (partner.vat or '-'), 10, bold=True)
    _rect(commands, LEFT_MARGIN, 650, RIGHT_MARGIN - LEFT_MARGIN, 22, fill_gray=0.9)
    headers = [('Invoice', 48), ('Invoice Date', 190), ('Due Date', 290), ('Amount Due', 385), ('Aging', 500)]
    for label, x_position in headers:
        _text(commands, x_position, 657, label, 9, bold=True)
    y_position = 630
    total = 0.0
    for row in rows:
        _line(commands, LEFT_MARGIN, y_position - 7, RIGHT_MARGIN, y_position - 7)
        _text(commands, 48, y_position, row['name'], 9)
        _text(commands, 190, y_position, row['invoice_date'], 9)
        _text(commands, 290, y_position, row['due_date'], 9)
        _text_right(commands, 485, y_position, row['amount'], 9)
        _text_right(commands, 545, y_position, row['aging'], 9)
        total += row['residual']
        y_position -= ROW_HEIGHT
    _line(commands, LEFT_MARGIN, y_position - 7, RIGHT_MARGIN, y_position - 7)
    _text(commands, 48, y_position - 22, 'Total', 10, bold=True)
    _text_right(commands, 485, y_position - 22, _format_amount(total, company.currency_id), 10, bold=True)
    _text_right(commands, RIGHT_MARGIN, 35, 'Page %s of %s' % (page_number, page_count), 8)
    return '\n'.join(commands).encode('latin-1', 'replace')


def _text(commands, x_position, y_position, value, size, bold=False):
    font = 'F2' if bold else 'F1'
    commands.append('BT /%s %s Tf 1 0 0 1 %s %s Tm (%s) Tj ET' % (
        font, size, x_position, y_position, _escape(value)))


def _text_right(commands, right_edge, y_position, value, size, bold=False):
    width = len(str(value)) * size * 0.52
    _text(commands, right_edge - width, y_position, value, size, bold)


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
