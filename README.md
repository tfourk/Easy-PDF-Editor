# Easy PDF Editor

A straightforward Python desktop app for editing, adding, moving, and saving PDF text. Designed around clear buttons, automatic text fitting, and saving an edited copy of your original document.

PDF processing runs locally. No account, API key, or cloud upload is required. The first-time dependency installation needs internet access.

## Features

- **Edit text:** Click an existing text element and change its contents.
- **Add text:** Click anywhere on the page to place new text.
- **Move text:** Drag a text element to a new position with an outline preview.
- **Automatic font matching:** Reuse embedded or standard PDF fonts when possible, with a close substitute when necessary.
- **Automatic fitting:** Expand the text box into available space, then reduce font size only if needed.
- **Formatting controls:** Font family, size, color, bold, and italic.
- **Simple controls:** Regular tool buttons with a blue active state and explicit ON/OFF formatting buttons.
- **Undo and redo:** Restore previous edits and moves.
- **Page navigation:** Page list, Previous/Next, zoom, and Fit Width.
- **Save As:** Write an edited PDF while protecting the opened source file.
- **Unsaved-change prompts:** Choose whether to save before closing or opening another file.

## Quick start on Windows

1. Download and extract the project into a folder. Do not run it from inside a ZIP archive.
2. Install Python if needed. Python 3.12 or 3.13 is recommended; enable **Add python.exe to PATH** during installation.
3. Double-click **`START_EDITOR.bat`**.
4. Click **Open PDF**, make your changes, then click **Save As**.

The launcher creates a private `.venv` folder and installs the required packages automatically. Subsequent launches work offline once dependencies are installed.

Try the included **`Practice.pdf`** before editing your own documents.

## Manual installation

Requirements: Python 3.10 or newer, Tkinter, and the packages listed in [`requirements.txt`](requirements.txt).

Run these commands from the directory containing `pdf_editor.py`:

```bash
python -m venv .venv
```

Activate the environment on Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and start the editor:

```bash
python -m pip install -r requirements.txt
python pdf_editor.py
```

On Linux, Tkinter may need to be installed separately through your distribution's package manager, commonly as `python3-tk`. A graphical desktop is required.

## How to use it

### Edit existing text

1. Click **Edit Text**.
2. Click a text element on the page. A blue outline identifies selectable text when you hover over it.
3. Change the text in the dialog.
4. Leave **Match original formatting: ON** to reuse the existing font and styling where possible, or switch it OFF to use the formatting controls.
5. Click **Apply** and review the result.

Each selection represents one uniform-format text element. Mixed-style lines may have several independently editable elements.

To delete an element, clear its text, click **Apply**, and confirm the deletion.

### Add text

1. Click **Add Text**.
2. Click where the top-left corner of the text should appear.
3. Enter your text and choose its formatting.
4. Click **Apply**.

Added text can be edited and moved afterward.

### Move text

1. Click **Move Text**.
2. Click and hold a text element.
3. Drag the dashed outline to the desired location and release.

The original text remains visible until you release the mouse. Press **Escape** to cancel a drag, or use **Undo** after placing it.

The editor retains original character positions relative to one another, size, color, and opacity, with the original font or a close match. Text is placed in a fresh PDF graphics context to avoid carrying inherited clipping regions into the new location.

Drops outside the page or overlapping another text element are rejected.

### Automatic text fitting

Auto-fit is enabled whenever you apply an edit or add text:

1. Try the starting box at the requested or original font size.
2. Expand rightward and downward into available space.
3. Wrap text where supported and reduce the font size only if necessary.

The width and height fields provide starting dimensions; you normally do not need to adjust them. The status bar reports when the font size has been reduced.

Expansion avoids nearby text and interactive form fields. Images and drawn lines are **not** treated as obstacles, so review the result on forms and illustrated pages.

Auto-fit does not move surrounding content or create additional pages. If the text cannot fit at the minimum size of 4 points, the editor asks for a shorter passage or a different position.

### Save your changes

Click **Save As** and choose a different filename from the opened PDF. The editor writes and validates a temporary file before replacing the destination.

The source file remains unchanged. Existing destination files require overwrite confirmation.

There is no autosave or crash recovery. Save regularly.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open PDF |
| `Ctrl+S` | Save As |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Escape` | Cancel a drag or close the text dialog |
| Mouse wheel | Scroll the page |

Inside the text dialog, `Ctrl+Z` undoes typing. Document undo history holds up to 20 changes, subject to its memory budget.

## Limitations

- **Scanned PDFs:** You can add text, but words embedded in an image cannot be edited or moved. OCR is not included.
- **Fixed layouts:** PDFs do not reflow like word-processing documents. Nearby paragraphs stay in place.
- **Font fidelity:** Exact font matching is not always possible. Missing characters, subset fonts, unusual spacing, stretched text, and outlined text may require substitutions or render differently.
- **Text direction:** Horizontal text elements are supported. Internally angled or vertical text is not editable or movable.
- **Rotated pages:** Page rotation is handled for selection and movement. Added text follows the original page coordinate direction and may appear rotated on screen.
- **Form fields:** Forms can be viewed, but interactive field editing and movement are not implemented.
- **Decorations:** Separate underline strokes and other page graphics do not move with text.
- **Protected PDFs:** Password-protected files require a valid password and permission to modify. Saved copies are unencrypted.
- **Digital signatures:** Editing can invalidate signatures; the app prompts before proceeding with a signed PDF.
- **Redactions:** Pages with pending redactions and overlapping text have safeguards that may block an edit. This app is not a security-grade redaction tool.

## Project files

| File | Purpose |
| --- | --- |
| `pdf_editor.py` | Tkinter desktop interface |
| `pdf_engine.py` | PDF editing, movement, font matching, auto-fit, and saving |
| `START_EDITOR.bat` | Windows setup and launcher |
| `requirements.txt` | Python dependencies |
| `Practice.pdf` | Sample PDF for trying the editor |
| `test_engine.py` | Core PDF editing regression tests |
| `test_movement.py` | Text movement and font matching tests |
| `test_autofit.py` | Automatic box expansion and font sizing tests |
| `README.txt` | Bundled plain-text instructions |

Place this README alongside these files in your repository. If you retain an outer `Easy_PDF_Editor` directory, run installation and test commands from inside that directory.

## Testing

From the application directory, run:

```bash
python -m unittest -v test_engine test_movement test_autofit
```

The current suite contains 17 regression tests covering text replacement, Unicode additions, save/reopen, overflow protection, preservation of neighboring content, movement on rotated pages, font matching, repeated moves from clipped PDF form objects, and automatic fitting.

PDF engine tests were run on Linux with PyMuPDF 1.26.6. The Windows launcher and desktop interface have not been verified on a Windows machine as part of this validation.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| The launcher cannot find Python | Install Python, enable its PATH option, and run the launcher again. |
| Dependency installation fails | Check your internet connection and the error shown in the launcher window. If the environment is damaged, delete only this project's `.venv` folder and retry. |
| Clicking a word does nothing | It may be scanned text, a form field, or unsupported text. Use Add Text where appropriate. |
| Text becomes too small | Use a shorter passage or move it to a larger clear area. Auto-fit reduces size only after trying available space. |
| Text looks different after editing | Check the font-match message. The PDF may use an unavailable or incomplete embedded font. |
| Text disappears or changes unexpectedly | Undo the operation and retain the original PDF. Report the steps and provide a non-sensitive sample PDF if possible. |
| Saving fails | Close the destination PDF in other programs or choose a writable folder. |

## Dependencies and licensing

The application uses PyMuPDF, Pillow, and Python's Tkinter interface. Dependency requirements are defined in `requirements.txt`.

This README does not grant a license to the application source. Add an appropriate `LICENSE` file before distributing the repository under a chosen license, and review the licenses bundled with its dependencies, including PyMuPDF's AGPL/commercial licensing terms.
