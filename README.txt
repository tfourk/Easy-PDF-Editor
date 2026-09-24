EASY PDF EDITOR - VERSION 4
===========================
QUICK START - WINDOWS
1. Extract the entire ZIP to a folder. Do not run inside the ZIP.
2. Double-click START_EDITOR.bat.
3. Click Open PDF, click text to edit it, and click Save As.

Python 3.12 or 3.13 is recommended. If Python is missing, the launcher
explains how to install it. First launch downloads the required packages
into this folder's private .venv. Later launches work offline.

EDIT EXISTING TEXT
Select Edit Text, then click a line on the page. A blue outline appears
when you move over an editable text element. Type your replacement and Apply.
The Match Original button is ON by default: it preserves font, size, color and style.
Each operation edits one uniform-format element, so mixed styles can be
edited separately. Turn Match Original OFF to choose custom formatting.
Auto-fit automatically enlarges the box into available space. It keeps the
original font size when possible, then reduces the size only if needed. Dimensions
are in points (72 points = one inch). Review the result on the page.
Clear the text box and Apply to delete the selected line.

MOVE TEXT
Click the Move Text button, click and hold on a text element, drag the dashed outline
to its new position, then release. The original text stays visible until
you drop it. Escape cancels a drag. Undo returns it to its previous position.
Moving places characters into fresh PDF text instructions, avoiding inherited
clipping regions that can hide portions of moved text. Original character
positions, size, color and opacity are retained; fonts are reused or matched
as closely as available. Unusual stretched or outlined text may differ.
The background and neighboring text stay in place. Drops outside the page
or overlapping another text element are rejected with an explanation.
Move is available for both original and newly added text, including pages
rotated 90/180/270 degrees. Internally angled text is still unsupported.
Drawn decorations such as separate underline strokes are page graphics and
do not move with text. Interactive form widgets are not movable text.

FONT MATCHING
Match Original first tries the PDF's embedded font and checks character
coverage. Standard PDF fonts are reused for single-line Latin text. If the
original font cannot encode your new words, a close serif, sans-serif or
monospace font is chosen with matching bold/italic styling. The dialog
reports the original font or closest substitute. Extended Unicode may use
additional fallback glyphs. Standard fonts may use an equivalent face for
multiline/Unicode edits. Original baseline, size and color are retained.
Unusual character spacing, text effects or transforms can change when you
rewrite words; dragging retains character positions with the closest available font.

ADD TEXT
Select Add Text and click where the top-left corner should go. Type your
text and Apply. Text added by the editor can be clicked and edited again.
Use Move Text to change its location after adding it.

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
- Original font matching is enabled by default. A close substitute is used
  if necessary; the dialog tells you which font is available.
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
test_engine.py     Original editing regression tests
test_movement.py   Dragging and font matching regression tests
                  Run: python -m unittest -v test_engine test_movement
Practice.pdf       A sample PDF for trying the editor

VALIDATION
PDF engine tests were run in Linux with PyMuPDF 1.26.6, including replacing
text, retaining adjacent text and graphics, Unicode additions, overflow
rollback, save/reopen, rotated-page coordinates and multi-page retention.
The regression suite also covers dragging, repeated moves, collisions, embedded and
standard fonts, move-then-edit, mixed styles, image preservation, and a
rendering comparison of moved styled text. Version 3 also checks every letter
after five successive moves from a clipped PDF form object. Total: 14 tests.
The Windows launcher and desktop UI require a local Windows run; they were
not executed on a Windows machine here.

DEPENDENCIES / LICENSING
PyMuPDF: https://pymupdf.readthedocs.io/ (AGPL/commercial license)
Pillow: https://python-pillow.org/ (HPND license)
Review dependency licenses before redistributing this application.

VERSION 4 UI
Edit Text, Move Text and Add Text are ordinary push buttons. The active tool
is blue. Bold, Italic and Match Original are buttons labelled ON or OFF.
No radio-button selectors or checkboxes remain.

If a particular PDF still loses characters, keep the original and provide
that PDF for diagnosis; complex font encodings can need file-specific fixes.

AUTOMATIC TEXT FITTING (VERSION 4)
Auto-fit is always enabled when you Apply edits or add text. The width and
height fields are starting dimensions; you do not need to adjust them.
The editor first tries the original size, then expands right/down into clear
page space. If necessary it wraps text and reduces font size down to a
minimum of 4 points. Match Original keeps the font, color and style even
when size must change. A status message reports a reduced size.
Nearby text and interactive form fields are protected from box expansion.
Lines and images are not treated as obstacles; review the visual result.
The editor does not move other content or add pages automatically. If no
space is available at the minimum size, it asks for a shorter passage or a
new position instead of clipping text. Undo remains available.
Auto-fit tests cover expansion at original size, constrained shrinking with
neighbors preserved, and multiline added text. Total regression tests: 17.
