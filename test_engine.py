import tempfile
import unittest
from pathlib import Path
import pymupdf as fitz
from pdf_engine import lines, change, save_atomic


def fixture(rotation=0):
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(35, 35, 480, 170), color=(0, .3, .5), fill=(.9, .95, 1))
    page.insert_text((50, 70), 'Original text', fontsize=12)
    page.insert_text((50, 100), 'Keep this neighbor', fontsize=12)
    page.set_rotation(rotation)
    doc.new_page().insert_text((50, 70), 'Second page')
    data = doc.tobytes()
    doc.close()
    return data


class EngineTests(unittest.TestCase):
    def test_replace_preserves_neighbors_and_graphics(self):
        data = fixture()
        with fitz.open(stream=data, filetype='pdf') as doc:
            old = lines(doc[0])[0]
        out = change(data, 0, fitz.Rect(50, 60, 250, 85), 'Changed successfully', 12, '#103070', old=old)
        with fitz.open(stream=out, filetype='pdf') as doc:
            self.assertNotIn('Original', doc[0].get_text())
            self.assertIn('Changed successfully', doc[0].get_text())
            self.assertIn('Keep this neighbor', doc[0].get_text())
            self.assertTrue(doc[0].get_drawings())
            self.assertIn('Second page', doc[1].get_text())
            doc[0].get_pixmap().save('test_render.png')

    def test_unicode_save_reopen(self):
        out = change(fixture(), 0, (50, 200, 400, 270), 'Café — Québec\nAdded text', 14, '#000000')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.pdf'
            save_atomic(out, path)
            with fitz.open(path) as doc:
                self.assertIn('Québec', doc[0].get_text())
                self.assertIn('Added text', doc[0].get_text())
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_overflow_is_transactional(self):
        data = fixture()
        with fitz.open(stream=data, filetype='pdf') as doc:
            old = lines(doc[0])[0]
        with self.assertRaises(ValueError):
            change(data, 0, (50, 50, 60, 55), 'Too much text', 20, '#000000', old=old)
        with fitz.open(stream=data, filetype='pdf') as doc:
            self.assertIn('Original text', doc[0].get_text())

    def test_rotated_coordinates(self):
        for rotation in (0, 90, 180, 270):
            data = fixture(rotation)
            with fitz.open(stream=data, filetype='pdf') as doc:
                page = doc[0]
                old = lines(page)[0]
                point = old['rect'].tl
                back = point * page.rotation_matrix * page.derotation_matrix
                self.assertAlmostEqual(point.x, back.x, places=3)
                self.assertAlmostEqual(point.y, back.y, places=3)
            out = change(data, 0, (50, 60, 250, 85), 'Replacement', 12, '#000000', old=old)
            with fitz.open(stream=out, filetype='pdf') as doc:
                self.assertEqual(doc[0].rotation, rotation)
                self.assertIn('Replacement', doc[0].get_text())

    def test_delete_and_reedit(self):
        data = change(fixture(), 0, (50, 200, 350, 250), 'New addition', 14, '#000000')
        with fitz.open(stream=data, filetype='pdf') as doc:
            old = next(x for x in lines(doc[0]) if 'New addition' in x['text'])
        data = change(data, 0, (50, 200, 350, 250), '', 14, '#000000', old=old)
        with fitz.open(stream=data, filetype='pdf') as doc:
            self.assertNotIn('New addition', doc[0].get_text())
            self.assertIn('Original text', doc[0].get_text())

    def test_pending_redaction_not_applied(self):
        with fitz.open(stream=fixture(), filetype='pdf') as doc:
            old = lines(doc[0])[0]
            doc[0].add_redact_annot((50, 90, 200, 105))
            data = doc.tobytes()
        with self.assertRaisesRegex(ValueError, 'pending redactions'):
            change(data, 0, (50, 60, 250, 85), 'Replacement', 12, '#000000', old=old)

    def test_reject_outside_page(self):
        with self.assertRaises(ValueError):
            change(fixture(), 0, (-10, 0, 100, 50), 'Outside', 12, '#000000')


if __name__ == '__main__':
    unittest.main()
