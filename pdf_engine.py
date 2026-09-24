"""Transactional PDF text editing. All mutations happen on an isolated copy."""
import html
import os
from pathlib import Path
import tempfile
import pymupdf as fitz

fitz.TOOLS.set_small_glyph_heights(True)


def lines(page):
    result = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            spans = line['spans']
            if not spans or not ''.join(s['text'] for s in spans).strip():
                continue
            result.append(dict(rect=fitz.Rect(line['bbox']),
                               text=''.join(s['text'] for s in spans),
                               size=spans[0]['size'], color=spans[0]['color'],
                               direction=line['dir'], spans=spans))
    return result


def change(data, page_number, rect, text, size, color, family='sans-serif',
           bold=False, old=None):
    if not 4 <= size <= 144:
        raise ValueError('Choose a text size between 4 and 144 points.')
    rect = fitz.Rect(rect)
    with fitz.open(stream=data, filetype='pdf') as doc:
        page = doc[page_number]
        bounds = page.rect * page.derotation_matrix
        if rect.is_empty or not bounds.contains(rect):
            raise ValueError('The text box must stay inside the page. Reduce its width or height.')
        if old:
            if tuple(old['direction']) != (1.0, 0.0):
                raise ValueError('This text is angled. This version edits horizontal text only.')
            if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
                raise ValueError('This page has pending redactions. Finish those in the original application first.')
            # Reject intersections with another line rather than deleting neighboring text.
            for other in lines(page):
                if other['rect'] == old['rect'] and other['text'] == old['text']:
                    continue
                if other['rect'].intersects(old['rect']):
                    raise ValueError('This text overlaps another line. It cannot safely be replaced here.')
            page.add_redact_annot(old['rect'], fill=False, cross_out=False)
            page.apply_redactions(images=0, graphics=0, text=0)
        if text.strip():
            css = ('* {margin:0; padding:0;} body {font-family:%s; font-size:%spt; '
                   'line-height:1.1; color:%s; font-weight:%s;}' %
                   (family, size, color, 'bold' if bold else 'normal'))
            safe = html.escape(text).replace('\n', '<br>')
            spare, scale = page.insert_htmlbox(rect, safe, css=css, scale_low=1)
            if spare < 0 or scale < .999:
                raise ValueError('The text does not fit. Make the box wider/taller, use smaller text, or shorten it.')
        return doc.tobytes(garbage=4, deflate=True)


def save_atomic(data, destination):
    destination = Path(destination)
    fd, name = tempfile.mkstemp(prefix='.pdf-editor-', suffix='.pdf', dir=destination.parent)
    os.close(fd)
    try:
        with open(name, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        with fitz.open(name) as check:
            if not check.is_pdf or check.page_count == 0:
                raise ValueError('The saved PDF could not be verified.')
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)
