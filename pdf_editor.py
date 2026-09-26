"""Easy PDF Editor - run START_EDITOR.bat on Windows."""
import os
import sys
import math
import traceback
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from tkinter import font as tkfont
import pymupdf as fitz
from PIL import Image, ImageTk
from pdf_engine import lines, change, save_atomic, move_text, resolve_font

APP = 'Easy PDF Editor'
PRACTICE = Path(__file__).with_name('Practice.pdf')
MARGIN = 28                      # canvas pixels around the page
MAX_RENDER = 4500                # bound raster memory for large drawings
ZOOM_MIN, ZOOM_MAX = .25, 4.0
ZOOM_STEPS = (.25, .5, .75, 1, 1.25, 1.5, 2, 3, 4)
HISTORY_LIMIT, HISTORY_BYTES = 20, 150_000_000

C = dict(bg='#f3f5f8', panel='#ffffff', border='#dde2ea', text='#1f2937', muted='#6b7280',
         faint='#9ca3af', accent='#2563eb', accent_dark='#1d4ed8', accent_soft='#e8f0fe',
         canvas='#e3e7ed', shadow='#c2c8d2', hover='#eef2f7', danger='#b42318',
         warning='#b45309', success='#15803d', tip='#111827')

TOOL_TIPS = {
    'edit': 'Click any text on the page to change it. Editable text is outlined when you hover over it.',
    'move': 'Drag text to a new spot and release to drop it. Escape cancels a drag; Undo puts it back.',
    'add': 'Click the page where the top-left corner of your new text should go.',
}


class Tooltip:
    """Small delayed hover tip for toolbar buttons."""
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self.job = widget, text, None, None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def schedule(self, _event):
        self.hide()
        self.job = self.widget.after(550, self.show)

    def show(self):
        self.job = None
        if not self.widget.winfo_viewable():
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f'+{x}+{y}')
        tk.Label(self.tip, text=self.text, bg=C['tip'], fg='white', padx=8, pady=4,
                 font='EditorSmall', justify='left').pack()

    def hide(self, _event=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP)
        self.geometry('1320x880')
        self.minsize(900, 600)
        self.configure(bg=C['bg'])
        self.doc = self.data = self.saved_data = self.path = None
        self.history, self.future = [], []   # entries: (pdf bytes, page index changed)
        self.page_index = 0
        self.zoom = 1.0
        self.fit = 'width'                   # 'width', 'page' or None for a fixed zoom
        self.photo, self.page_px, self.origin, self.scale = None, (0, 0), (MARGIN, MARGIN), 1
        self.page_lines, self.drag, self.fit_job = [], None, None
        self.thumbs, self.stale_thumbs, self.thumb_job = {}, {}, None
        self.mode = tk.StringVar(value='edit')
        self.status = tk.StringVar(value='Open a PDF to begin.')
        self.page_var, self.zoom_var = tk.StringVar(), tk.StringVar()
        # Screen points per PDF point, so 100% zoom means actual size.
        self.px_per_pt = self.winfo_fpixels('1i') / 72
        ui = max(1.0, self.winfo_fpixels('1i') / 96)
        self.thumb_w, self.thumb_h = int(118*ui), int(152*ui)
        self.thumb_slot, self.sidebar_w = self.thumb_h + int(34*ui), int(168*ui)
        self.mod = 'Command' if self.tk.call('tk', 'windowingsystem') == 'aqua' else 'Control'
        self.mod_label = 'Cmd' if self.mod == 'Command' else 'Ctrl'
        self.setup_style()
        self.build_menu()
        self.build_toolbar()
        self.build_statusbar()
        self.build_body()
        self.bind_keys()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.mode.trace_add('write', lambda *args: self.mode_changed())
        self.mode_changed()
        self.refresh()

    # ----------------------------------------------------------------- layout
    def setup_style(self):
        base = tkfont.nametofont('TkDefaultFont')
        family = 'Segoe UI' if sys.platform == 'win32' else base.actual('family')
        base.configure(family=family, size=10)
        tkfont.nametofont('TkTextFont').configure(family=family, size=10)
        tkfont.nametofont('TkMenuFont').configure(family=family, size=10)
        # Keep references: Tk deletes a named font when its Python object is collected.
        self.fonts = [tkfont.Font(self, name='EditorSmall', family=family, size=9),
                      tkfont.Font(self, name='EditorBold', family=family, size=10, weight='bold'),
                      tkfont.Font(self, name='EditorTitle', family=family, size=15, weight='bold'),
                      tkfont.Font(self, name='EditorEntry', family=family, size=12)]
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=C['bg'], foreground=C['text'], font='TkDefaultFont',
                        bordercolor=C['border'], lightcolor=C['panel'], darkcolor=C['border'],
                        troughcolor=C['bg'], focuscolor=C['accent'])
        style.configure('Panel.TFrame', background=C['panel'])
        style.configure('Hint.TFrame', background=C['accent_soft'])
        style.configure('Hint.TLabel', background=C['accent_soft'], foreground=C['accent_dark'])
        style.configure('Panel.TLabel', background=C['panel'])
        style.configure('Muted.TLabel', foreground=C['muted'])
        style.configure('PanelMuted.TLabel', background=C['panel'], foreground=C['muted'])
        style.configure('Heading.TLabel', background=C['panel'], foreground=C['muted'], font='EditorBold')
        style.configure('Title.TLabel', font='EditorTitle')
        style.configure('Error.TLabel', foreground=C['danger'])
        style.configure('Unsaved.TLabel', background=C['panel'], foreground=C['warning'])
        style.configure('Saved.TLabel', background=C['panel'], foreground=C['success'])
        style.configure('TSeparator', background=C['border'])
        # Flat toolbar buttons.
        style.configure('TB.TButton', background=C['panel'], borderwidth=0, relief='flat', width=-1,
                        padding=(10, 6), lightcolor=C['panel'], darkcolor=C['panel'])
        style.map('TB.TButton', background=[('disabled', C['panel']), ('pressed', C['border']),
                                            ('active', C['hover'])],
                  foreground=[('disabled', C['faint'])])
        style.configure('Accent.TButton', background=C['accent'], foreground='white', borderwidth=0,
                        padding=(14, 6), width=-1, lightcolor=C['accent'], darkcolor=C['accent'])
        style.map('Accent.TButton', background=[('disabled', '#9db8f2'), ('pressed', C['accent_dark']),
                                                ('active', C['accent_dark'])],
                  lightcolor=[('active', C['accent_dark'])], darkcolor=[('active', C['accent_dark'])],
                  foreground=[('disabled', '#eef3fd')])
        style.configure('Danger.TButton', foreground=C['danger'], padding=(12, 6))
        style.configure('TButton', padding=(12, 6))
        # Segmented tool selector.
        style.configure('Tool.Toolbutton', background=C['panel'], padding=(12, 6), borderwidth=0,
                        relief='flat', font='EditorBold', foreground=C['text'])
        style.map('Tool.Toolbutton',
                  background=[('selected', C['accent']), ('active', C['hover'])],
                  foreground=[('selected', 'white')])
        style.configure('TLabelframe', background=C['bg'], bordercolor=C['border'])
        style.configure('TLabelframe.Label', background=C['bg'], foreground=C['muted'], font='EditorBold')
        style.configure('TCheckbutton', background=C['bg'])
        style.map('TCheckbutton', background=[('active', C['bg'])])
        style.configure('TCombobox', padding=4)
        style.configure('TSpinbox', padding=4)
        style.configure('Toolbar.TCombobox', padding=3)

    def build_menu(self):
        m = self.mod_label
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=False)
        filemenu.add_command(label='Open PDF…', accelerator=f'{m}+O', command=self.open_pdf)
        if PRACTICE.exists():
            filemenu.add_command(label='Open Practice PDF', command=lambda: self.open_pdf(PRACTICE))
        filemenu.add_command(label='Save As…', accelerator=f'{m}+S', command=self.save)
        filemenu.add_separator()
        filemenu.add_command(label='Exit', command=self.close)
        self.editmenu = tk.Menu(menubar, tearoff=False)
        self.editmenu.add_command(label='Undo', accelerator=f'{m}+Z', command=self.undo)
        self.editmenu.add_command(label='Redo', accelerator=f'{m}+Y', command=self.redo)
        self.editmenu.add_separator()
        for key, label in (('edit', 'Edit Text'), ('move', 'Move Text'), ('add', 'Add Text')):
            self.editmenu.add_radiobutton(label=label, variable=self.mode, value=key,
                                          accelerator=key[0].upper())
        view = tk.Menu(menubar, tearoff=False)
        view.add_command(label='Zoom In', accelerator=f'{m}++', command=lambda: self.zoom_step(1))
        view.add_command(label='Zoom Out', accelerator=f'{m}+−', command=lambda: self.zoom_step(-1))
        view.add_command(label='Actual Size', accelerator=f'{m}+1', command=lambda: self.set_zoom(1))
        view.add_command(label='Fit Width', accelerator=f'{m}+0', command=lambda: self.set_fit('width'))
        view.add_command(label='Fit Page', command=lambda: self.set_fit('page'))
        view.add_separator()
        view.add_command(label='Previous Page', accelerator='Page Up', command=lambda: self.go(-1))
        view.add_command(label='Next Page', accelerator='Page Down', command=lambda: self.go(1))
        helpmenu = tk.Menu(menubar, tearoff=False)
        helpmenu.add_command(label='How to use', accelerator='F1', command=self.help)
        for label, menu in (('File', filemenu), ('Edit', self.editmenu), ('View', view), ('Help', helpmenu)):
            menubar.add_cascade(label=label, menu=menu)
        self.configure(menu=menubar)

    def build_toolbar(self):
        m = self.mod_label
        bar = ttk.Frame(self, style='Panel.TFrame', padding=(10, 7))
        bar.pack(fill='x')
        self.doc_controls = []

        def button(parent, text, command, tip, style='TB.TButton', side='left', needs_doc=True):
            b = ttk.Button(parent, text=text, command=command, style=style, takefocus=False)
            b.pack(side=side, padx=2)
            Tooltip(b, tip)
            if needs_doc:
                self.doc_controls.append(b)
            return b

        def separator(side='left'):
            ttk.Separator(bar, orient='vertical').pack(side=side, fill='y', padx=8, pady=3)

        button(bar, 'Open…', self.open_pdf, f'Open a PDF ({m}+O)', needs_doc=False)
        button(bar, 'Save As…', self.save, f'Save an edited copy ({m}+S)', style='Accent.TButton')
        separator()
        for key, label in (('edit', '✎  Edit Text'), ('move', '✥  Move Text'), ('add', '＋  Add Text')):
            b = ttk.Radiobutton(bar, text=label, variable=self.mode, value=key,
                                style='Tool.Toolbutton', takefocus=False)
            b.pack(side='left', padx=1)
            Tooltip(b, f'{label.split(maxsplit=1)[1]} ({key[0].upper()})\n{TOOL_TIPS[key]}')
        separator()
        self.undo_button = button(bar, '↶  Undo', self.undo, f'Undo ({m}+Z)')
        self.redo_button = button(bar, '↷  Redo', self.redo, f'Redo ({m}+Y)')

        button(bar, '?', self.help, 'How to use (F1)', side='right', needs_doc=False)
        separator('right')
        button(bar, '+', lambda: self.zoom_step(1), f'Zoom in ({m}++)', side='right')
        self.zoom_box = ttk.Combobox(bar, textvariable=self.zoom_var, width=9, style='Toolbar.TCombobox',
                                     values=['Fit width', 'Fit page'] + [f'{z:.0%}' for z in ZOOM_STEPS])
        self.zoom_box.pack(side='right', padx=2)
        self.zoom_box.bind('<<ComboboxSelected>>', self.zoom_from_box)
        self.zoom_box.bind('<Return>', self.zoom_from_box)
        self.zoom_box.bind('<FocusOut>', lambda e: self.refresh())
        self.doc_controls.append(self.zoom_box)
        button(bar, '−', lambda: self.zoom_step(-1), f'Zoom out ({m}+−)', side='right')
        separator('right')
        button(bar, '›', lambda: self.go(1), 'Next page (Page Down)', side='right')
        self.page_count = ttk.Label(bar, text='', style='PanelMuted.TLabel', width=6)
        self.page_count.pack(side='right')
        self.page_entry = ttk.Entry(bar, textvariable=self.page_var, width=5, justify='center')
        self.page_entry.pack(side='right', padx=4)
        self.page_entry.bind('<Return>', self.page_from_entry)
        self.page_entry.bind('<FocusOut>', lambda e: self.refresh())
        self.doc_controls.append(self.page_entry)
        button(bar, '‹', lambda: self.go(-1), 'Previous page (Page Up)', side='right')
        ttk.Separator(self).pack(fill='x')
        hint = ttk.Frame(self, style='Hint.TFrame', padding=(14, 6))
        hint.pack(fill='x')
        ttk.Label(hint, text='ℹ', style='Hint.TLabel', font='EditorBold').pack(side='left', padx=(0, 8))
        self.tip = ttk.Label(hint, style='Hint.TLabel')
        self.tip.pack(side='left', fill='x')

    def build_statusbar(self):
        ttk.Separator(self).pack(side='bottom', fill='x')
        bar = ttk.Frame(self, style='Panel.TFrame', padding=(12, 5))
        bar.pack(side='bottom', fill='x')
        ttk.Label(bar, textvariable=self.status, style='Panel.TLabel').pack(side='left')
        self.position_label = ttk.Label(bar, style='PanelMuted.TLabel')
        self.position_label.pack(side='right')
        self.saved_label = ttk.Label(bar, style='Saved.TLabel')
        self.saved_label.pack(side='right', padx=16)

    def build_body(self):
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True)
        sidebar = ttk.Frame(body, style='Panel.TFrame')
        sidebar.pack(side='left', fill='y')
        ttk.Label(sidebar, text='PAGES', style='Heading.TLabel', padding=(14, 10, 0, 4)).pack(anchor='w')
        holder = ttk.Frame(sidebar, style='Panel.TFrame')
        holder.pack(fill='both', expand=True)
        self.thumb_canvas = tk.Canvas(holder, width=self.sidebar_w, bg=C['panel'], highlightthickness=0,
                                      yscrollincrement=20)
        tscroll = ttk.Scrollbar(holder, orient='vertical', command=self.thumb_canvas.yview)
        def thumb_scrolled(*args):
            tscroll.set(*args)
            self.schedule_thumbs()
        self.thumb_canvas.configure(yscrollcommand=thumb_scrolled)
        self.thumb_canvas.pack(side='left', fill='both', expand=True)
        tscroll.pack(side='left', fill='y')
        self.thumb_canvas.bind('<Button-1>', self.thumb_click)
        self.thumb_canvas.bind('<Configure>', self.schedule_thumbs)
        ttk.Separator(body, orient='vertical').pack(side='left', fill='y')
        area = ttk.Frame(body)
        area.pack(side='left', fill='both', expand=True)
        self.canvas = tk.Canvas(area, bg=C['canvas'], highlightthickness=0,
                                xscrollincrement=20, yscrollincrement=20)
        ys = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        xs = ttk.Scrollbar(area, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas.bind('<Button-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag_motion)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<Motion>', self.hover)
        self.canvas.bind('<Leave>', lambda e: self.canvas.delete('highlight'))
        self.canvas.bind('<Configure>', self.canvas_resized)
        for canvas in (self.canvas, self.thumb_canvas):
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                canvas.bind(sequence, lambda e, c=canvas: self.wheel(e, c))

    def bind_keys(self):
        typing = (tk.Entry, ttk.Entry, tk.Text, tk.Spinbox)

        def key(sequence, action, while_typing=False):
            def handler(event):
                if self.grab_current() is not None:
                    return None
                if not while_typing and isinstance(self.focus_get(), typing):
                    return None
                action()
                return 'break'
            self.bind(sequence, handler)
        m = self.mod
        for letter, action in (('o', self.open_pdf), ('s', self.save), ('z', self.undo),
                               ('y', self.redo), ('Z', self.redo)):
            key(f'<{m}-{letter}>', action, while_typing=True)
        for sequence in ('plus', 'equal', 'KP_Add'):
            key(f'<{m}-{sequence}>', lambda: self.zoom_step(1), while_typing=True)
        for sequence in ('minus', 'KP_Subtract'):
            key(f'<{m}-{sequence}>', lambda: self.zoom_step(-1), while_typing=True)
        key(f'<{m}-Key-0>', lambda: self.set_fit('width'), while_typing=True)
        key(f'<{m}-Key-1>', lambda: self.set_zoom(1), while_typing=True)
        key('<Prior>', lambda: self.go(-1))
        key('<Next>', lambda: self.go(1))
        key('<Home>', lambda: self.show_page(0))
        key('<End>', lambda: self.show_page(len(self.doc) - 1 if self.doc else 0))
        for tool in ('edit', 'move', 'add'):
            key(f'<Key-{tool[0]}>', lambda value=tool: self.mode.set(value))
        key('<F1>', self.help, while_typing=True)
        self.bind('<Escape>', lambda e: self.cancel_drag())

    # ------------------------------------------------------------- utilities
    def report_callback_exception(self, exc, value, tb):
        traceback.print_exception(exc, value, tb)
        messagebox.showerror('Something went wrong', f'{value}\n\nYour original PDF has not been changed.', parent=self)

    @contextmanager
    def busy(self, *widgets):
        widgets = (self, self.canvas) + widgets
        for widget in widgets:
            widget.configure(cursor='watch')
        self.update_idletasks()
        try:
            yield
        finally:
            for widget in widgets:
                if widget.winfo_exists():
                    widget.configure(cursor='')

    def dirty(self):
        # Undo/redo restore the exact bytes object, so identity tracks the saved state cheaply.
        return self.data is not None and self.data is not self.saved_data

    def confirm_leave(self):
        if not self.dirty():
            return True
        answer = messagebox.askyesnocancel('Save your work?', 'You have unsaved changes. Save them before continuing?', parent=self)
        return self.save() if answer else answer is False

    def refresh(self):
        has_doc = self.doc is not None
        for widget in self.doc_controls:
            widget.state(['!disabled'] if has_doc else ['disabled'])
        self.undo_button.state(['!disabled'] if self.history else ['disabled'])
        self.redo_button.state(['!disabled'] if self.future else ['disabled'])
        self.editmenu.entryconfigure('Undo', state='normal' if self.history else 'disabled')
        self.editmenu.entryconfigure('Redo', state='normal' if self.future else 'disabled')
        name = self.path.name if self.path else None
        self.title(f'{"• " if self.dirty() else ""}{name} — {APP}' if name else APP)
        if has_doc:
            if self.focus_get() is not self.page_entry:
                self.page_var.set(str(self.page_index + 1))
            self.page_count.configure(text=f'of {len(self.doc)}')
            if self.focus_get() is not self.zoom_box:
                self.zoom_var.set(f'{self.zoom:.0%}')
            self.position_label.configure(text=f'{name}   ·   Page {self.page_index+1} of {len(self.doc)}   ·   {self.zoom:.0%}')
            if self.dirty():
                self.saved_label.configure(text='●  Unsaved changes', style='Unsaved.TLabel')
            else:
                self.saved_label.configure(text='✓  No unsaved changes', style='Saved.TLabel')
        else:
            self.page_var.set('')
            self.zoom_var.set('')
            self.page_count.configure(text='')
            self.position_label.configure(text='')
            self.saved_label.configure(text='')

    def mode_changed(self):
        self.cancel_drag()
        self.canvas.delete('highlight')
        self.tip.configure(text=TOOL_TIPS[self.mode.get()])
        self.canvas.configure(cursor='crosshair' if self.doc and self.mode.get() == 'add' else '')

    # ------------------------------------------------------------ open/save
    def open_pdf(self, path=None):
        if not self.confirm_leave():
            return
        path = path or filedialog.askopenfilename(parent=self, filetypes=[('PDF files', '*.pdf')])
        if not path:
            return
        doc = None
        try:
            doc = fitz.open(path)
            if not doc.is_pdf or not doc.page_count:
                raise ValueError('Please choose a PDF with at least one page.')
            if doc.needs_pass:
                pw = simpledialog.askstring('Password', 'Enter the PDF password:', show='*', parent=self)
                if pw is None:
                    return
                if not doc.authenticate(pw):
                    raise ValueError('That password did not unlock the PDF.')
                messagebox.showinfo('Unlocked PDF', 'Saved copies from this editor will not be password protected.', parent=self)
            if not doc.permissions & fitz.PDF_PERM_MODIFY:
                raise ValueError('This PDF does not permit editing. Request an editable copy from its owner.')
            if doc.get_sigflags() > 0:
                if not messagebox.askokcancel('Signed PDF', 'Editing can invalidate digital signatures. Continue with an edited copy?', parent=self):
                    return
            with self.busy():
                data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
                new_doc = fitz.open(stream=data, filetype='pdf')
            if self.doc:
                self.doc.close()
            self.doc, self.data, self.saved_data, self.path = new_doc, data, data, Path(path)
            self.history, self.future = [], []
            self.page_index = 0
            self.fit = 'width'
            self.layout_thumbs()
            self.mode_changed()
            self.render()
            self.canvas.yview_moveto(0)
            self.canvas.focus_set()
        except Exception as exc:
            messagebox.showerror('Cannot open PDF', str(exc), parent=self)
        finally:
            if doc:
                doc.close()

    def save(self):
        if not self.doc:
            messagebox.showinfo('Open a PDF first', 'Click Open to choose a file.', parent=self)
            return False
        path = filedialog.asksaveasfilename(parent=self, title='Save edited PDF', defaultextension='.pdf',
            initialdir=self.path.parent, initialfile=self.path.stem+'_edited.pdf', filetypes=[('PDF files', '*.pdf')])
        if not path:
            return False
        try:
            # samefile also catches case-insensitive and linked paths to the original.
            same = os.path.samefile(path, self.path)
        except OSError:
            same = Path(path).resolve() == self.path.resolve()
        if same:
            messagebox.showinfo('Keep your original', 'Choose a different filename so your original PDF stays safe.', parent=self)
            return False
        try:
            with self.busy():
                save_atomic(self.data, path)
            self.saved_data = self.data
            self.refresh()
            self.status.set(f'Saved: {path}')
            return True
        except Exception as exc:
            messagebox.showerror('Could not save', f'{exc}\n\nTry a different folder or close the PDF in other programs.', parent=self)
            return False

    # -------------------------------------------------------------- viewing
    def render(self):
        if not self.doc:
            self.draw_welcome()
            return
        self.cancel_drag()
        page = self.doc[self.page_index]
        self.canvas.update_idletasks()
        cw, ch = max(self.canvas.winfo_width(), 200), max(self.canvas.winfo_height(), 200)
        if self.fit:
            width_zoom = (cw - 2*MARGIN) / (page.rect.width * self.px_per_pt)
            height_zoom = (ch - 2*MARGIN) / (page.rect.height * self.px_per_pt)
            self.zoom = width_zoom if self.fit == 'width' else min(width_zoom, height_zoom)
        self.zoom = min(ZOOM_MAX, max(ZOOM_MIN, self.zoom),
                        MAX_RENDER / (max(page.rect.width, page.rect.height) * self.px_per_pt))
        self.scale = self.zoom * self.px_per_pt
        pix = page.get_pixmap(matrix=fitz.Matrix(self.scale, self.scale), alpha=False)
        self.photo = ImageTk.PhotoImage(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
        self.page_px = (pix.width, pix.height)
        self.canvas.delete('all')
        self.canvas.create_rectangle(0, 0, 0, 0, fill=C['shadow'], outline='', tags='shadow')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo, tags='page')
        self.place_page()
        self.page_lines = lines(page)
        self.highlight_thumb()
        self.status.set('Click text to edit it, or choose Add Text.' if self.page_lines else
                        'No editable text on this page. It may be scanned. Use Add Text to write on it.')
        self.refresh()

    def place_page(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        w, h = self.page_px
        ox, oy = max(MARGIN, (cw - w)//2), max(MARGIN, (ch - h)//2)
        self.origin = (ox, oy)
        self.canvas.coords('page', ox, oy)
        self.canvas.coords('shadow', ox+3, oy+4, ox+w+3, oy+h+4)
        self.canvas.configure(scrollregion=(0, 0, max(cw, w + 2*MARGIN), max(ch, h + 2*MARGIN)))

    def canvas_resized(self, _event):
        if not self.doc:
            self.draw_welcome()
            return
        self.canvas.delete('highlight', 'flash')
        self.place_page()
        if self.fit:
            # Re-fit once the window stops resizing.
            if self.fit_job:
                self.after_cancel(self.fit_job)
            self.fit_job = self.after(150, self.refit)

    def refit(self):
        self.fit_job = None
        if self.doc and self.fit:
            self.render()

    def draw_welcome(self):
        c = self.canvas
        c.delete('all')
        cw, ch = c.winfo_width(), c.winfo_height()
        c.configure(scrollregion=(0, 0, cw, ch))
        x, y = cw/2, ch/2
        c.create_rectangle(x-250, y-150, x+250, y+160, fill=C['panel'], outline=C['border'])
        c.create_polygon(x-22, y-112, x+10, y-112, x+24, y-98, x+24, y-62, x-22, y-62,
                         fill=C['accent_soft'], outline=C['accent'], width=2)
        c.create_line(x+10, y-112, x+10, y-98, x+24, y-98, fill=C['accent'], width=2)
        for dy in (-90, -81, -72):
            c.create_line(x-12, y+dy, x+14, y+dy, fill=C['accent'], width=2)
        c.create_text(x, y-25, text='Open a PDF to get started', font='EditorTitle', fill=C['text'])
        c.create_text(x, y+5, text='Edit, move and add text. Everything stays on your computer.',
                      fill=C['muted'])
        c.create_rectangle(x-80, y+35, x+80, y+73, fill=C['accent'], outline='', tags=('open', 'open_bg'))
        c.create_text(x, y+54, text='Open PDF…', fill='white', font='EditorBold', tags='open')
        c.tag_bind('open', '<Button-1>', lambda e: self.after_idle(self.open_pdf))
        c.tag_bind('open', '<Enter>', lambda e: (c.itemconfigure('open_bg', fill=C['accent_dark']),
                                                 c.configure(cursor='hand2')))
        c.tag_bind('open', '<Leave>', lambda e: (c.itemconfigure('open_bg', fill=C['accent']),
                                                 c.configure(cursor='')))
        if PRACTICE.exists():
            c.create_text(x, y+100, text='or try the Practice PDF', fill=C['accent'], tags='practice')
            c.tag_bind('practice', '<Button-1>', lambda e: self.after_idle(lambda: self.open_pdf(PRACTICE)))
            c.tag_bind('practice', '<Enter>', lambda e: c.configure(cursor='hand2'))
            c.tag_bind('practice', '<Leave>', lambda e: c.configure(cursor=''))
        c.create_text(x, y+128, text=f'Tip: {self.mod_label}+O opens a file from anywhere.',
                      fill=C['faint'], font='EditorSmall')

    def show_page(self, index):
        if not self.doc:
            return
        index = max(0, min(len(self.doc)-1, index))
        if index != self.page_index:
            self.page_index = index
            self.render()
            self.canvas.yview_moveto(0)
            self.canvas.xview_moveto(0)
        self.refresh()

    def go(self, offset):
        self.show_page(self.page_index + offset)

    def page_from_entry(self, _event=None):
        try:
            self.show_page(int(self.page_var.get()) - 1)
        except ValueError:
            pass
        self.canvas.focus_set()
        self.refresh()

    def set_zoom(self, zoom):
        if self.doc:
            self.fit, self.zoom = None, zoom
            self.render()

    def set_fit(self, fit):
        if self.doc:
            self.fit = fit
            self.render()

    def zoom_step(self, direction):
        if not self.doc:
            return
        if direction > 0:
            target = next((z for z in ZOOM_STEPS if z > self.zoom + .01), ZOOM_MAX)
        else:
            target = next((z for z in reversed(ZOOM_STEPS) if z < self.zoom - .01), ZOOM_MIN)
        self.set_zoom(target)

    def zoom_from_box(self, _event=None):
        value = self.zoom_var.get().strip().lower()
        self.canvas.focus_set()
        if value.startswith('fit'):
            self.set_fit('page' if 'page' in value else 'width')
            return
        try:
            self.set_zoom(float(value.rstrip('%')) / 100)
        except ValueError:
            self.refresh()

    def wheel(self, event, canvas):
        if event.num in (4, 5):
            steps = -1 if event.num == 4 else 1
        else:
            steps = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        if event.state & 0x0004 and canvas is self.canvas:
            self.zoom_step(-steps)
        elif event.state & 0x0001:
            canvas.xview_scroll(steps * 3, 'units')
        else:
            canvas.yview_scroll(steps * 3, 'units')

    # ------------------------------------------------------------ thumbnails
    def layout_thumbs(self):
        c = self.thumb_canvas
        c.delete('all')
        self.thumbs.clear()
        self.stale_thumbs.clear()
        if not self.doc:
            return
        w = self.sidebar_w
        for i in range(len(self.doc)):
            x0, y0 = (w - self.thumb_w)//2, i*self.thumb_slot + 8
            c.create_rectangle(x0-4, y0-4, x0+self.thumb_w+4, y0+self.thumb_h+4, outline='', width=3,
                               tags=('frame', f'frame{i}'))
            c.create_rectangle(x0, y0, x0+self.thumb_w, y0+self.thumb_h, fill='white',
                               outline=C['border'], tags=f'paper{i}')
            c.create_text(w//2, y0+self.thumb_h+15, text=str(i+1), fill=C['muted'],
                          font='EditorSmall', tags=('label', f'label{i}'))
        c.configure(scrollregion=(0, 0, w, len(self.doc)*self.thumb_slot + 8))
        c.yview_moveto(0)
        self.schedule_thumbs()

    def schedule_thumbs(self, *_args):
        if self.thumb_job is None and self.doc:
            self.thumb_job = self.after(30, self.render_visible_thumbs)

    def render_visible_thumbs(self):
        """Render one visible thumbnail per idle slice so large PDFs stay responsive."""
        self.thumb_job = None
        if not self.doc:
            return
        c = self.thumb_canvas
        first = max(0, int(c.canvasy(0) // self.thumb_slot))
        last = min(len(self.doc)-1, int(c.canvasy(c.winfo_height()) // self.thumb_slot))
        for i in range(first, last+1):
            if i not in self.thumbs:
                self.render_thumb(i)
                self.thumb_job = self.after(1, self.render_visible_thumbs)
                return

    def render_thumb(self, i):
        c, page = self.thumb_canvas, self.doc[i]
        s = min(self.thumb_w / page.rect.width, self.thumb_h / page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False)
        self.thumbs[i] = ImageTk.PhotoImage(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
        x = (self.sidebar_w - pix.width)//2
        y = i*self.thumb_slot + 8 + (self.thumb_h - pix.height)//2
        c.delete(f'img{i}')
        c.coords(f'paper{i}', x-1, y-1, x+pix.width, y+pix.height)
        c.coords(f'frame{i}', x-4, y-4, x+pix.width+3, y+pix.height+3)
        c.create_image(x, y, anchor='nw', image=self.thumbs[i], tags=f'img{i}')
        self.stale_thumbs.pop(i, None)

    def invalidate_thumb(self, i):
        # Keep showing the old image (Tk drops it once unreferenced) until the new one is drawn.
        if i in self.thumbs:
            self.stale_thumbs[i] = self.thumbs.pop(i)
        self.schedule_thumbs()

    def highlight_thumb(self):
        c = self.thumb_canvas
        c.itemconfigure('frame', outline='')
        c.itemconfigure('label', fill=C['muted'], font='EditorSmall')
        c.itemconfigure(f'frame{self.page_index}', outline=C['accent'])
        c.itemconfigure(f'label{self.page_index}', fill=C['accent'], font='EditorBold')
        # Keep the current page's thumbnail in view.
        total = len(self.doc)*self.thumb_slot + 8
        top, bottom = c.canvasy(0), c.canvasy(c.winfo_height())
        y0 = self.page_index*self.thumb_slot
        if y0 < top or y0 + self.thumb_slot > bottom:
            c.yview_moveto(max(0, y0 - self.thumb_slot) / total)
        self.schedule_thumbs()

    def thumb_click(self, event):
        if self.doc:
            index = int(self.thumb_canvas.canvasy(event.y) // self.thumb_slot)
            if 0 <= index < len(self.doc):
                self.show_page(index)

    # --------------------------------------------------------- page mapping
    def point(self, event):
        ox, oy = self.origin
        p = fitz.Point((self.canvas.canvasx(event.x)-ox)/self.scale, (self.canvas.canvasy(event.y)-oy)/self.scale)
        return p * self.doc[self.page_index].derotation_matrix

    def to_canvas(self, rect, pad=0):
        r = fitz.Rect(rect) * self.doc[self.page_index].rotation_matrix
        ox, oy = self.origin
        return (r.x0*self.scale+ox-pad, r.y0*self.scale+oy-pad, r.x1*self.scale+ox+pad, r.y1*self.scale+oy+pad)

    def hit(self, point):
        return next((item for item in self.page_lines if item['rect'].contains(point)), None)

    def hover(self, event):
        self.canvas.delete('highlight')
        if not self.doc or self.drag:
            return
        mode = self.mode.get()
        if mode == 'add':
            return
        item = self.hit(self.point(event))
        if item:
            self.canvas.create_rectangle(*self.to_canvas(item['rect'], 2), outline=C['accent'],
                                         width=2, tags='highlight')
        self.canvas.configure(cursor=('xterm' if mode == 'edit' else 'fleur') if item else '')

    def flash(self, rect):
        """Briefly outline a changed area so the result is easy to find."""
        if not rect or not self.doc:
            return
        self.canvas.delete('flash')
        self.canvas.create_rectangle(*self.to_canvas(rect, 3), outline=C['success'], width=2,
                                     dash=(6, 3), tags='flash')
        self.after(1600, lambda: self.canvas.delete('flash'))

    # --------------------------------------------------------------- editing
    def cancel_drag(self):
        self.drag = None
        self.canvas.delete('drag_outline')

    def press(self, event):
        self.canvas.focus_set()
        if not self.doc:
            return
        if self.mode.get() != 'move':
            self.click(event)
            return
        point = self.point(event)
        item = self.hit(point)
        if not item:
            self.status.set('Click and hold on a text element, then drag. Scanned words cannot be moved.')
            return
        if tuple(item['direction']) != (1.0, 0.0):
            self.status.set('This version moves horizontal text elements only.')
            return
        self.drag = (item, point)
        self.canvas.delete('highlight')
        self.drag_motion(event)

    def drag_motion(self, event):
        if not self.drag:
            return
        item, start = self.drag
        delta = self.point(event) - start
        self.canvas.delete('drag_outline')
        self.canvas.create_rectangle(*self.to_canvas(item['rect'] + (delta.x, delta.y, delta.x, delta.y), 2),
                                     outline=C['accent'], width=2, dash=(5, 3), tags='drag_outline')
        self.status.set(f'Move {delta.x:.1f} pt across, {delta.y:.1f} pt down. Release to place; Escape cancels.')

    def release(self, event):
        if not self.drag:
            return
        item, start = self.drag
        delta = self.point(event) - start
        self.cancel_drag()
        if abs(delta.x)+abs(delta.y) < 1:
            self.status.set('Drag a little further to move text.')
            return
        try:
            with self.busy():
                result = move_text(self.data, self.page_index, item, delta.x, delta.y)
            self.commit(result)
            self.flash(item['rect'] + (delta.x, delta.y, delta.x, delta.y))
            self.status.set('Text moved. Font and character spacing matched. Undo is available; Save As to keep your changes.')
        except Exception as exc:
            messagebox.showinfo('Text was not moved', str(exc), parent=self)

    def click(self, event):
        p = self.point(event)
        bounds = self.doc[self.page_index].rect * self.doc[self.page_index].derotation_matrix
        if not bounds.contains(p):
            return
        old = self.hit(p) if self.mode.get() == 'edit' else None
        if self.mode.get() == 'edit' and not old:
            self.status.set('No text here. Choose Add Text to place new text. Scanned words are part of an image.')
            return
        if old and tuple(old['direction']) != (1.0, 0.0):
            messagebox.showinfo('Angled text', 'This version edits horizontal text only.', parent=self)
            return
        self.canvas.delete('highlight')
        TextDialog(self, old, p, bounds)

    def commit(self, result):
        previous, page = self.data, self.page_index
        self.load_data(result)   # raises before history changes if the result cannot open
        self.history.append((previous, page))
        while len(self.history) > HISTORY_LIMIT or (
                len(self.history) > 1 and sum(len(d) for d, _ in self.history) > HISTORY_BYTES):
            self.history.pop(0)
        self.future.clear()
        self.refresh()

    def load_data(self, data, page=None):
        new_doc = fitz.open(stream=data, filetype='pdf')
        self.doc.close()
        self.doc, self.data = new_doc, data
        if page is not None:
            self.page_index = page
        self.invalidate_thumb(self.page_index)
        self.render()

    def undo(self):
        if self.history and self.grab_current() is None:
            data, page = self.history.pop()
            self.future.append((self.data, page))
            self.load_data(data, page)
            self.status.set(f'Undid a change on page {page+1}. Redo is available.')

    def redo(self):
        if self.future and self.grab_current() is None:
            data, page = self.future.pop()
            self.history.append((self.data, page))
            self.load_data(data, page)
            self.status.set(f'Redid a change on page {page+1}.')

    # ------------------------------------------------------------------ misc
    def help(self):
        HelpWindow(self)

    def close(self):
        if self.confirm_leave():
            if self.doc:
                self.doc.close()
            self.destroy()


class TextDialog(tk.Toplevel):
    """Edit an existing text element or add new text."""
    def __init__(self, editor, old, point, bounds):
        super().__init__(editor)
        self.editor, self.old = editor, old
        self.title('Edit text' if old else 'Add text')
        self.configure(bg=C['bg'])
        self.transient(editor)
        self.minsize(580, 540)
        self.x, self.y = (old['rect'].x0, old['rect'].y0) if old else (point.x, point.y)
        flags = old['spans'][0].get('flags', 0) if old else 0
        self.size = tk.StringVar(value=f'{old["size"]:.1f}' if old else '12')
        self.width = tk.StringVar(value=f'{min(bounds.x1-self.x, max(old["rect"].width+3, 80) if old else 240):.1f}')
        self.height = tk.StringVar(value=f'{min(bounds.y1-self.y, max(old["rect"].height+3, old["size"]*1.3) if old else 70):.1f}')
        self.family = tk.StringVar(value='sans-serif')
        self.bold = tk.BooleanVar(value=bool(flags & 16))
        self.italic = tk.BooleanVar(value=bool(flags & 2))
        self.match = tk.BooleanVar(value=bool(old))
        self.color = '#%06x' % old['color'] if old else '#000000'
        self.match_job = None

        body = ttk.Frame(self, padding=(22, 18, 22, 12))
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Edit text' if old else 'Add text', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, style='Muted.TLabel', text=(
            'Change the words below, then click Apply. You can Undo afterwards.' if old else
            'Type your text, pick its look, then click Apply.')).pack(anchor='w', pady=(2, 12))
        border = tk.Frame(body, bg=C['border'], padx=1, pady=1)
        border.pack(fill='both', expand=True)
        self.entry = tk.Text(border, height=6, wrap='word', font='EditorEntry', undo=True, relief='flat',
                             padx=10, pady=8, highlightthickness=0, bg=C['panel'], fg=C['text'],
                             insertbackground=C['text'], selectbackground=C['accent_soft'],
                             selectforeground=C['text'])
        self.entry.pack(fill='both', expand=True)
        self.entry.insert('1.0', old['text'] if old else '')

        if old:
            ttk.Checkbutton(body, text='Match original formatting (recommended)',
                            variable=self.match).pack(anchor='w', pady=(12, 0))
            self.font_note = ttk.Label(body, style='Muted.TLabel', wraplength=540)
            self.font_note.pack(anchor='w', padx=(24, 0))

        fmt = ttk.LabelFrame(body, text='Formatting', padding=(12, 8))
        fmt.pack(fill='x', pady=(12, 0))
        ttk.Label(fmt, text='Font').grid(row=0, column=0, sticky='w')
        font_box = ttk.Combobox(fmt, textvariable=self.family, state='readonly', width=11,
                                values=['sans-serif', 'serif', 'monospace'])
        font_box.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(fmt, text='Size').grid(row=0, column=2, sticky='w')
        size_box = ttk.Spinbox(fmt, textvariable=self.size, from_=4, to=144, increment=1, width=6)
        size_box.grid(row=0, column=3, padx=(6, 16))
        bold = ttk.Checkbutton(fmt, text='Bold', variable=self.bold)
        bold.grid(row=0, column=4, padx=(0, 8))
        italic = ttk.Checkbutton(fmt, text='Italic', variable=self.italic)
        italic.grid(row=0, column=5, padx=(0, 16))
        self.swatch = tk.Label(fmt, width=2, bg=self.color, relief='solid', borderwidth=1)
        self.swatch.grid(row=0, column=6)
        color_button = ttk.Button(fmt, text='Color…', command=self.pick_color)
        color_button.grid(row=0, column=7, padx=(6, 0))
        self.format_widgets = [(font_box, 'readonly'), (size_box, None), (bold, None),
                               (italic, None), (color_button, None)]

        box = ttk.LabelFrame(body, text='Starting box (points, 72 = 1 inch)', padding=(12, 8))
        box.pack(fill='x', pady=(10, 0))
        ttk.Label(box, text='Width').grid(row=0, column=0, sticky='w')
        ttk.Spinbox(box, textvariable=self.width, from_=1, to=10000, increment=10, width=8).grid(row=0, column=1, padx=(6, 16))
        ttk.Label(box, text='Height').grid(row=0, column=2, sticky='w')
        ttk.Spinbox(box, textvariable=self.height, from_=1, to=10000, increment=10, width=8).grid(row=0, column=3, padx=(6, 16))
        ttk.Label(box, style='Muted.TLabel', wraplength=540, text=(
            'Auto-fit grows the box into clear space first, and makes the text smaller only if needed.'
        )).grid(row=1, column=0, columnspan=5, sticky='w', pady=(6, 0))

        self.error = ttk.Label(body, style='Error.TLabel', wraplength=540)
        self.error.pack(anchor='w', pady=(8, 0))

        ttk.Separator(self).pack(fill='x')
        footer = ttk.Frame(self, padding=(22, 12))
        footer.pack(fill='x')
        ttk.Button(footer, text='Apply', style='Accent.TButton', command=self.apply).pack(side='right')
        ttk.Button(footer, text='Cancel', command=self.destroy).pack(side='right', padx=8)
        if old:
            ttk.Button(footer, text='Delete text', style='Danger.TButton',
                       command=lambda: self.apply(delete=True)).pack(side='left')
        ttk.Label(footer, style='Muted.TLabel',
                  text=f'{editor.mod_label}+Enter applies').pack(side='left', padx=12)

        self.bind('<Escape>', lambda e: self.destroy())
        self.bind(f'<{editor.mod}-Return>', lambda e: (self.apply(), 'break')[1])
        if old:
            self.match.trace_add('write', lambda *args: self.update_match())
            self.entry.bind('<KeyRelease>', self.schedule_match)
            self.update_match()
        self.center()
        self.grab_set()
        self.entry.focus_set()
        self.entry.tag_add('sel', '1.0', 'end-1c')

    def center(self):
        self.update_idletasks()
        e = self.editor
        w, h = max(self.winfo_reqwidth(), 620), max(self.winfo_reqheight(), 560)
        x = e.winfo_rootx() + (e.winfo_width() - w)//2
        y = e.winfo_rooty() + max(0, (e.winfo_height() - h)//3)
        self.geometry(f'{w}x{h}+{max(0, x)}+{max(0, y)}')

    def pick_color(self):
        chosen = colorchooser.askcolor(self.color, parent=self)[1]
        if chosen:
            self.color = chosen
            self.swatch.configure(bg=chosen)

    def schedule_match(self, _event=None):
        # Font lookups scan the page's fonts, so wait for a pause in typing.
        if self.match_job:
            self.after_cancel(self.match_job)
        self.match_job = self.after(300, self.update_match)

    def update_match(self):
        self.match_job = None
        matched = self.match.get()
        for widget, enabled_state in self.format_widgets:
            if matched:
                widget.state(['disabled'])
            else:
                widget.state(['!disabled'] + ([enabled_state] if enabled_state else []))
        self.swatch.configure(bg=self.color if not matched else '#%06x' % self.old['color'])
        if matched:
            self.size.set(f'{self.old["size"]:.1f}')
        try:
            page = self.editor.doc[self.editor.page_index]
            _, description = resolve_font(page, self.old['spans'][0], self.entry.get('1.0', 'end-1c'))
            self.font_note.configure(text=description if matched else 'Custom formatting: use the controls below.')
        except Exception as exc:
            self.font_note.configure(text=str(exc))

    @staticmethod
    def number(var, label):
        try:
            value = float(var.get())
        except ValueError:
            raise ValueError(f'{label} must be a number.') from None
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{label} must be a positive number.')
        return value

    def apply(self, delete=False):
        text = '' if delete else self.entry.get('1.0', 'end-1c')
        try:
            if not text.strip():
                if not self.old:
                    raise ValueError('Type some text first.')
                if not messagebox.askyesno('Delete this text?', 'Remove the selected text from the page?', parent=self):
                    return
            size = self.number(self.size, 'Text size')
            width = self.number(self.width, 'Box width')
            height = self.number(self.height, 'Box height')
            rect = fitz.Rect(self.x, self.y, self.x+width, self.y+height)
            info = {}
            with self.editor.busy(self):
                result = change(self.editor.data, self.editor.page_index, rect, text, size, self.color,
                                self.family.get(), self.bold.get(), self.old, match_original=self.match.get(),
                                italic=self.italic.get(), auto_fit=True, fit_info=info)
            self.editor.commit(result)
            self.destroy()
            self.editor.flash(info.get('rect'))
            if not text.strip():
                message = 'Text deleted. '
            elif info.get('shrunk'):
                message = f'Change applied and fitted at {info["size"]:.1f} pt. '
            else:
                message = 'Change applied. '
            self.editor.status.set(message + 'Undo is available; Save As to keep it.')
        except Exception as exc:
            self.error.configure(text=str(exc))


class HelpWindow(tk.Toplevel):
    def __init__(self, editor):
        super().__init__(editor)
        self.title('How to use Easy PDF Editor')
        self.configure(bg=C['panel'])
        self.transient(editor)
        x, y = editor.winfo_rootx() + max(0, (editor.winfo_width() - 660)//2), editor.winfo_rooty() + 40
        self.geometry(f'660x720+{x}+{y}')
        m = editor.mod_label
        footer = ttk.Frame(self, style='Panel.TFrame', padding=(0, 0, 16, 14))
        footer.pack(side='bottom', fill='x')
        ttk.Button(footer, text='Close', style='Accent.TButton', command=self.destroy).pack(side='right')
        text = tk.Text(self, wrap='word', relief='flat', padx=24, pady=18, bg=C['panel'], fg=C['text'],
                       font='TkDefaultFont', highlightthickness=0, spacing1=2, spacing3=2, cursor='arrow')
        scroll = ttk.Scrollbar(self, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        text.tag_configure('h1', font='EditorTitle', spacing3=8)
        text.tag_configure('h2', font='EditorBold', foreground=C['accent_dark'], spacing1=12, spacing3=4)
        text.tag_configure('muted', foreground=C['muted'])
        sections = [
            ('h1', 'Three easy steps\n'),
            ('', '1.  Open a PDF.\n2.  Pick a tool and click on the page.\n3.  Save As to create an edited copy. Your original is never changed.\n'),
            ('h2', 'Edit Text\n'),
            ('', 'Click any text element. Keep "Match original formatting" on to reuse the original font, '
                 'size and colour, or turn it off to choose your own. Clear the text or use "Delete text" to remove it.\n'),
            ('h2', 'Move Text\n'),
            ('', 'Drag a text element and release it in a clear area. Escape cancels a drag. '
                 'Fonts and character spacing are preserved.\n'),
            ('h2', 'Add Text\n'),
            ('', 'Click where the top-left corner of the new text should go. Added text can be edited or moved later.\n'),
            ('h2', 'Auto-fit\n'),
            ('', 'The text box grows into clear page space first, and the text is made smaller only if needed. '
                 'Nearby text and form fields are avoided; images and drawn lines are not, so review the result.\n'),
            ('h2', 'Keyboard shortcuts\n'),
            ('', f'{m}+O  Open      {m}+S  Save As      {m}+Z  Undo      {m}+Y  Redo\n'
                 f'E / M / A  Edit, Move or Add tool      Page Up / Page Down  Change page\n'
                 f'{m}+ + / −  Zoom      {m}+0  Fit width      {m}+1  Actual size      {m}+wheel  Zoom\n'),
            ('h2', 'Good to know\n'),
            ('muted', 'PDF layouts do not reflow like Word documents. Scanned text is an image: you can add text, '
                      'but words inside images cannot be changed (no OCR). Angled text and form-field editing are not '
                      'supported. On rotated pages, added text follows the original PDF coordinate direction. '
                      'All editing stays on your computer: no account, subscription or API key.\n'),
        ]
        for tag, content in sections:
            text.insert('end', content, tag or ())
        text.configure(state='disabled')
        self.bind('<Escape>', lambda e: self.destroy())


def main():
    if sys.platform == 'win32':
        # Crisp rendering on high-DPI Windows displays instead of blurry bitmap scaling.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    Editor().mainloop()


if __name__ == '__main__':
    main()
