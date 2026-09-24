"""Transactional PDF text editing. All mutations happen on an isolated copy."""
import copy
import html
import re
import math
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
            # Select uniform-format spans, so editing one style never flattens a mixed line.
            for span in spans:
                if span['text'].strip():
                    result.append(dict(rect=fitz.Rect(span['bbox']), text=span['text'],
                                       size=span['size'], color=span['color'],
                                       direction=line['dir'], spans=[span]))
    return result


def _change_once(data, page_number, rect, text, size, color, family='sans-serif',
           bold=False, old=None, match_original=False, italic=False):
    if not 4 <= size <= 144:
        raise ValueError('Choose a text size between 4 and 144 points.')
    rect = fitz.Rect(rect)
    with fitz.open(stream=data, filetype='pdf') as doc:
        page = doc[page_number]
        bounds = page.rect * page.derotation_matrix
        if not all(math.isfinite(v) for v in rect) or rect.is_empty or not bounds.contains(rect):
            raise ValueError('The text box must stay inside the page. Reduce its width or height.')
        matched_font = resolve_font(page, old['spans'][0], text)[0] if old and match_original else None
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
        if text.strip() and matched_font is not None:
            span = old['spans'][0]
            origin = fitz.Point(rect.x0, rect.y0 + span['origin'][1] - old['rect'].y0)
            standard = {normalized_font(n): n for n in fitz.Base14_fontnames}
            standard_name = standard.get(normalized_font(span['font']))
            if standard_name and '\n' not in text and all(ord(ch) < 256 for ch in text):
                if matched_font.text_length(text, fontsize=span['size']) > rect.width or rect.height < span['size']:
                    raise ValueError('The text does not fit in the original font. Enlarge the box or shorten the text.')
                page.insert_text(origin, text, fontname=standard_name, fontsize=span['size'],
                                 color=fitz.sRGB_to_pdf(span['color']), fill_opacity=span.get('alpha',255)/255)
            else:
                writer = fitz.TextWriter(bounds, color=fitz.sRGB_to_pdf(span['color']),
                                         opacity=span.get('alpha', 255)/255)
                overflow = writer.fill_textbox(rect, text, pos=origin, font=matched_font,
                                               fontsize=span['size'], warn=False)
                if overflow:
                    raise ValueError('The text does not fit in the original font. Enlarge the box or shorten the text.')
                writer.write_text(page)
        elif text.strip():
            css = ('* {margin:0; padding:0;} body {font-family:%s; font-size:%spt; '
                   'line-height:1.1; color:%s; font-weight:%s; font-style:%s;}' %
                   (family, size, color, 'bold' if bold else 'normal', 'italic' if italic else 'normal'))
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


def normalized_font(name):
    return re.sub(r'[^a-z0-9]', '', name.split('+')[-1].lower())


def resolve_font(page, span, text):
    """Reuse an embedded font only when it can encode the requested characters."""
    name = normalized_font(span['font'])
    def supports(font):
        return font.is_writable and all(ch.isspace() or font.has_glyph(ord(ch), fallback=False) for ch in text)
    for info in page.get_fonts(full=True):
        try:
            base, ext, kind, buffer = page.parent.extract_font(info[0])
            font = fitz.Font(fontbuffer=buffer) if buffer else fitz.Font(base.split('+')[-1])
            if name in (normalized_font(base), normalized_font(font.name)) and supports(font):
                return font, 'Original font: ' + span['font']
        except (ValueError, RuntimeError):
            continue
    # PDF standard fonts can be unembedded. These aliases preserve their face.
    standard = {normalized_font(n): n for n in fitz.Base14_fontnames}
    if name in standard:
        font = fitz.Font(standard[name])
        if supports(font):
            return font, 'Original standard font: ' + span['font']
    flags = span.get('flags', 0)
    bold, italic = bool(flags & 16), bool(flags & 2)
    if flags & 8 or any(n in name for n in ('courier', 'mono', 'consolas')):
        face = ('cobi' if italic else 'cobo') if bold else ('coit' if italic else 'cour')
    elif flags & 4 or any(n in name for n in ('times', 'georgia', 'serif')):
        face = ('tibi' if italic else 'tibo') if bold else ('tiit' if italic else 'tiro')
    else:
        face = ('hebi' if italic else 'hebo') if bold else ('heit' if italic else 'helv')
    font = fitz.Font(face)
    return font, 'Closest available: ' + font.name + ' (original: ' + span['font'] + ')'


def move_text(data, page_number, old, dx, dy):
    """Move text using original character positions in a fresh graphics context."""
    if not all(math.isfinite(v) for v in (dx, dy)):
        raise ValueError('Choose a valid position.')
    with fitz.open(stream=data, filetype='pdf') as doc:
        page = doc[page_number]
        bounds = page.rect * page.derotation_matrix
        target = old['rect'] + (dx, dy, dx, dy)
        if not bounds.contains(target):
            raise ValueError('Keep the whole text element inside the page.')
        if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
            raise ValueError("Finish this page's pending redactions before moving text.")
        if tuple(old['direction']) != (1.0, 0.0):
            raise ValueError('This version moves horizontal text elements only.')
        others = [x for x in lines(page) if not (x['rect'] == old['rect'] and x['text'] == old['text'])]
        for item in others:
            if item['rect'].intersects(old['rect']):
                raise ValueError('This text overlaps another element and cannot be moved safely.')
            if item['rect'].intersects(target):
                raise ValueError('That position overlaps other text. Drop it in a clear area.')
        # Extract character positions before removing the original. Recreate text in
        # a clean graphics context instead of nesting inherited Form XObject clips.
        span = old['spans'][0]
        chars = None
        for block in page.get_text('rawdict')['blocks']:
            for line in block.get('lines', []):
                for candidate in line['spans']:
                    if fitz.Rect(candidate['bbox']) == old['rect'] and ''.join(c['c'] for c in candidate['chars']) == old['text']:
                        chars = candidate['chars']
                        break
        if not chars:
            raise ValueError('Could not safely identify every character. No changes were made.')
        font, _ = resolve_font(page, span, old['text'])
        standard = {normalized_font(n): n for n in fitz.Base14_fontnames}
        face = standard.get(normalized_font(span['font']))
        use_standard = face is not None and all(ord(c['c']) < 256 for c in chars)
        page.add_redact_annot(old['rect'], fill=False, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        # Wrapping existing streams also prevents a page's unbalanced clip / CTM
        # from leaking into the new text instructions.
        page.wrap_contents()
        color = fitz.sRGB_to_pdf(span['color'])
        opacity = span.get('alpha',255)/255
        if use_standard:
            shape = page.new_shape()
            for char in chars:
                origin = fitz.Point(char['origin']) + (dx,dy)
                shape.insert_text(origin, char['c'], fontname=face, fontsize=span['size'],
                                  color=color, fill_opacity=opacity)
            shape.commit(overlay=True)
        else:
            writer = fitz.TextWriter(bounds, color=color, opacity=opacity)
            for char in chars:
                writer.append(fitz.Point(char['origin']) + (dx,dy), char['c'],
                              font=font, fontsize=span['size'])
            writer.write_text(page)
        return doc.tobytes(garbage=4, deflate=True)


def change(data, page_number, rect, text, size, color, family='sans-serif',
           bold=False, old=None, match_original=False, italic=False,
           auto_fit=False, fit_info=None):
    """Grow into available page space first, then reduce size only when needed."""
    if not auto_fit or not text.strip():
        return _change_once(data, page_number, rect, text, size, color, family,
                            bold, old, match_original, italic)
    box = fitz.Rect(rect)
    original_size = old['size'] if old and match_original else size
    if not math.isfinite(original_size) or not 4 <= original_size <= 144:
        raise ValueError('Choose a text size between 4 and 144 points.')
    with fitz.open(stream=data, filetype='pdf') as doc:
        page = doc[page_number]
        bounds = page.rect * page.derotation_matrix
        if not all(math.isfinite(v) for v in box) or box.is_empty or not bounds.contains(box):
            raise ValueError('Click inside the page to place your text.')
        obstacles = [x['rect'] for x in lines(page)
                     if not (old and x['rect'] == old['rect'] and x['text'] == old['text'])]
        # Keep interactive fields clear as well as surrounding printed text.
        obstacles.extend(fitz.Rect(w.rect) for w in (page.widgets() or []))
    def clear(r):
        return not any(r.intersects(o) for o in obstacles)
    candidates = [box] if clear(box) else []
    # Each obstacle's left edge is a useful width at which more height may be free.
    rights = {min(box.x1, bounds.x1), bounds.x1}
    rights.update(max(box.x0, o.x0-2) for o in obstacles if o.x0 > box.x0)
    for right in sorted(rights, reverse=True):
        if right <= box.x0+2:
            continue
        bottom = bounds.y1
        for obstacle in obstacles:
            if obstacle.x0 < right and obstacle.x1 > box.x0 and obstacle.y1 > box.y0:
                bottom = min(bottom, obstacle.y0-2)
        if bottom > box.y0+2:
            # Prefer a short, wide box before adding vertical wrapping space.
            for height in (box.height, bottom-box.y0):
                candidate = fitz.Rect(box.x0, box.y0, right, min(bottom,box.y0+height))
                if not candidate.is_empty and clear(candidate) and candidate not in candidates:
                    candidates.append(candidate)
    if not candidates:
        raise ValueError('No clear space here. Move the text to a blank area and try again.')
    def attempt(candidate, trial_size):
        adjusted = copy.deepcopy(old) if old else None
        if adjusted and match_original:
            span = adjusted['spans'][0]
            ratio = trial_size/original_size
            span['size'] = trial_size
            span['origin'] = (span['origin'][0], adjusted['rect'].y0 +
                              (span['origin'][1]-adjusted['rect'].y0)*ratio)
            adjusted['size'] = trial_size
        try:
            output = _change_once(data, page_number, candidate, text, trial_size,
                                  color, family, bold, adjusted, match_original, italic)
            return output
        except ValueError as exc:
            if 'does not fit' in str(exc):
                return None
            raise
    chosen = None
    for candidate in candidates:
        output = attempt(candidate, original_size)
        if output is not None:
            chosen = (output, candidate, original_size)
            break
    if chosen is None:
        # Bounded binary search finds a readable size, without silently clipping.
        best_size = 0
        for candidate in candidates:
            low, high = 4.0, original_size
            output = attempt(candidate, low)
            if output is None:
                continue
            best = output
            for _ in range(9):
                mid = (low+high)/2
                result = attempt(candidate, mid)
                if result is None:
                    high = mid
                else:
                    low, best = mid, result
            if low > best_size:
                best_size = low
                chosen = (best, candidate, low)
        if chosen is None:
            raise ValueError('There is not enough clear page space, even after automatic resizing. Use a shorter passage or move it to a larger blank area.')
    output, candidate, actual_size = chosen
    if fit_info is not None:
        fit_info.update(rect=tuple(candidate), size=actual_size,
                        resized=candidate != box, shrunk=actual_size < original_size-.01)
    return output
