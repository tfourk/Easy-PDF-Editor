EASY PDF EDITOR
==============
QUICK START - WINDOWS
1. Extract the entire ZIP to a folder. Do not run inside the ZIP.
2. Double-click START_EDITOR.bat.
3. Click Open PDF, click text to edit it, and click Save As.

Python 3.12 or 3.13 is recommended. If Python is missing, the launcher
explains how to install it. First launch downloads the required packages
into this folder's private .venv. Later launches work offline.

EDIT EXISTING TEXT
Select Edit Text, then click a line on the page. A blue outline appears
when you move over an editable line. Type your replacement, choose the
size/color/font, then Apply. Each operation replaces one line.
If it does not fit, enlarge the box or reduce the font size. Dimensions
are in points (72 points = one inch). Review the result on the page.
Clear the text box and Apply to delete the selected line.

ADD TEXT
Select Add Text and click where the top-left corner should go. Type your
text and Apply. Text added by the editor can be clicked and edited again.
Use Undo then add again if you need to change its location.

SAVE
Save As writes a normal PDF which opens in other PDF readers. The app
requires a different filename from the opened PDF, protecting the source.
Existing destination files get the operating system's overwrite prompt.
Files are saved through a temporary file and replaced only after validation.
Unsaved work triggers a Save / Discard / Cancel prompt when opening another
file or exiting. Undo/Redo holds up to 20 changes with a memory budget.
There is no crash recovery or autosave: save regularly.

KEYBOARD
Ctrl+O: Open    Ctrl+S: Save As    Ctrl+Z: Undo    Ctrl+Y: Redo
Mouse wheel: scroll. Use page list, Previous/Next, zoom and Fit Width.
Inside the text dialog, Ctrl+Z undoes your typing.

WHAT TO EXPECT
- PDFs are fixed layouts. Nearby paragraphs do not move automatically.
- Replacement uses a substitute sans-serif, serif or monospace font.
  Exact original fonts, spacing, mixed styles and alignment may differ.
- Replacement removes the original selected text, retaining page images
  and vector drawings. It is not a security-grade redaction utility.
- Scanned words are pixels. This version adds text to scanned pages but
  does not OCR or edit the text inside images.
- Horizontal text is supported. Angled/vertical text is not editable.
- Page rotations are handled for clicking. Added text follows the original
  page coordinate direction, so it may appear rotated on a rotated page.
- Forms can be viewed but form-field editing is not implemented.
- Encrypted files require a valid password and permission to modify.
  Saved copies are unencrypted. Digital signatures may be invalidated.
- Overlapping text and pages with pending redaction annotations are blocked
  for replacement to avoid accidentally changing unrelated text.
- All PDF processing happens locally. No account, upload, API key or fee.

OTHER SYSTEMS / MANUAL LAUNCH
Use Python 3.10+ with Tkinter installed:
  python -m pip install -r requirements.txt
  python pdf_editor.py
On Linux, Tkinter may require your distribution's python3-tk package.

FILES
pdf_editor.py       Desktop interface
pdf_engine.py       Transactional edits and safe save
START_EDITOR.bat    Windows setup and launcher
requirements.txt   Dependencies
test_engine.py     Regression tests (python -m unittest -v test_engine)
Practice.pdf       A sample PDF for trying the editor

VALIDATION
PDF engine tests were run in Linux with PyMuPDF 1.26.6, including replacing
text, retaining adjacent text and graphics, Unicode additions, overflow
rollback, save/reopen, rotated-page coordinates and multi-page retention.
The Windows launcher and desktop UI require a local Windows run; they were
not executed on a Windows machine here.

DEPENDENCIES / LICENSING
PyMuPDF: https://pymupdf.readthedocs.io/ (AGPL/commercial license)
Pillow: https://python-pillow.org/ (HPND license)
Review dependency licenses before redistributing this application.
