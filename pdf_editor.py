"""Easy PDF Editor - run START_EDITOR.bat on Windows."""
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
from pathlib import Path
import hashlib
import traceback
import pymupdf as fitz
from PIL import Image, ImageTk
from pdf_engine import lines, change, save_atomic, move_text, resolve_font


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Easy PDF Editor')
        self.geometry('1280x850')
        self.drag = None
        self.minsize(850, 600)
        self.doc = None
        self.data = None
        self.path = None
        self.saved_hash = None
        self.history, self.future = [], []
        self.page_index = 0
        self.zoom = 1.25
        self.mode = tk.StringVar(value='edit')
        self.status = tk.StringVar(value='Start here: click Open PDF.')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton', padding=(10, 8), font=('Segoe UI', 10))
        style.configure('TLabel', font=('Segoe UI', 10))
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill='x')
        ttk.Button(bar, text='1  Open PDF', command=self.open_pdf).pack(side='left', padx=3)
        self.tool_buttons = {}
        for key, label in [('edit', 'Edit Text'), ('move', 'Move Text'), ('add', 'Add Text')]:
            button = tk.Button(bar, text=label, font=('Segoe UI', 10, 'bold'),
                               padx=12, pady=8, relief='raised', borderwidth=2,
                               command=lambda value=key: self.select_tool(value))
            button.pack(side='left', padx=4)
            self.tool_buttons[key] = button
        ttk.Button(bar, text='3  Save As...', command=self.save).pack(side='left', padx=12)
        self.undo_button = ttk.Button(bar, text='Undo', command=self.undo)
        self.undo_button.pack(side='left', padx=3)
        self.redo_button = ttk.Button(bar, text='Redo', command=self.redo)
        self.redo_button.pack(side='left', padx=3)
        ttk.Button(bar, text='Help', command=self.help).pack(side='right')
        self.tip = ttk.Label(self, text='Open a PDF, then click a line of text to change it.', padding=(15, 8))
        self.tip.pack(fill='x')
        nav = ttk.Frame(self, padding=(12, 4))
        nav.pack(fill='x')
        ttk.Button(nav, text='< Previous', command=lambda: self.go(-1)).pack(side='left')
        self.page_label = ttk.Label(nav, text='No PDF open', width=20, anchor='center')
        self.page_label.pack(side='left')
        ttk.Button(nav, text='Next >', command=lambda: self.go(1)).pack(side='left')
        ttk.Button(nav, text='−', command=lambda: self.zoom_by(-.25)).pack(side='right')
        ttk.Button(nav, text='+', command=lambda: self.zoom_by(.25)).pack(side='right')
        ttk.Button(nav, text='Fit Width', command=self.fit_width).pack(side='right')
        body = ttk.Frame(self)
        body.pack(fill='both', expand=True)
        sidebar = ttk.Frame(body, width=145, padding=8)
        sidebar.pack(side='left', fill='y')
        ttk.Label(sidebar, text='Pages').pack(anchor='w')
        self.pages = tk.Listbox(sidebar, width=14, font=('Segoe UI', 11), exportselection=False)
        self.pages.pack(fill='both', expand=True)
        self.pages.bind('<<ListboxSelect>>', self.select_page)
        area = ttk.Frame(body)
        area.pack(side='left', fill='both', expand=True)
        self.canvas = tk.Canvas(area, bg='#d9dfe7', highlightthickness=0)
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
        self.bind('<Escape>', lambda e: self.cancel_drag())
        self.canvas.bind('<Motion>', self.hover)
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.canvas.bind('<Button-4>', lambda e: self.canvas.yview_scroll(-3, 'units'))
        self.canvas.bind('<Button-5>', lambda e: self.canvas.yview_scroll(3, 'units'))
        ttk.Label(self, textvariable=self.status, padding=10, relief='sunken').pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Control-o>', lambda e: self.open_pdf() if self.grab_current() is None else None)
        self.bind('<Control-s>', lambda e: self.save() if self.grab_current() is None else None)
        self.bind('<Control-z>', lambda e: self.undo() if self.grab_current() is None else None)
        self.bind('<Control-y>', lambda e: self.redo() if self.grab_current() is None else None)
        self.refresh_buttons()
        self.mode_changed()

    def report_callback_exception(self, exc, value, tb):
        traceback.print_exception(exc, value, tb)
        messagebox.showerror('Something went wrong', f'{value}\n\nYour original PDF has not been changed.', parent=self)

    def dirty(self):
        return self.data is not None and hashlib.sha256(self.data).digest() != self.saved_hash

    def confirm_leave(self):
        if not self.dirty():
            return True
        answer = messagebox.askyesnocancel('Save your work?', 'You have unsaved changes. Save them before continuing?', parent=self)
        return self.save() if answer else answer is False

    def open_pdf(self):
        if not self.confirm_leave():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('PDF files', '*.pdf')])
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
            data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(stream=data, filetype='pdf')
            self.data, self.path = data, Path(path)
            self.saved_hash = hashlib.sha256(data).digest()
            self.history, self.future = [], []
            self.page_index = 0
            self.pages.delete(0, 'end')
            for i in range(len(self.doc)):
                self.pages.insert('end', f'Page {i+1}')
            self.fit_width()
        except Exception as exc:
            messagebox.showerror('Cannot open PDF', str(exc), parent=self)
        finally:
            if doc:
                doc.close()

    def refresh_buttons(self):
        self.undo_button.configure(state='normal' if self.history else 'disabled')
        self.redo_button.configure(state='normal' if self.future else 'disabled')
        name = self.path.name if self.path else 'Open a PDF to begin'
        self.title(f'{"* " if self.dirty() else ""}{name} — Easy PDF Editor')

    def select_tool(self, value):
        self.mode.set(value)
        self.mode_changed()

    def mode_changed(self):
        for key, button in self.tool_buttons.items():
            active = key == self.mode.get()
            button.configure(bg='#165dba' if active else '#f0f3f7',
                             fg='white' if active else '#182330',
                             activebackground='#104d9b' if active else '#dce7f5',
                             activeforeground='white' if active else '#182330',
                             relief='sunken' if active else 'raised')
        self.cancel_drag()
        if self.mode.get() == 'move':
            self.tip.configure(text='Drag a text element to move it. Font and character spacing are matched. Escape cancels; Undo restores.')
            self.canvas.configure(cursor='fleur')
            return
        self.tip.configure(text=('Click a text element to edit it. Match Original preserves its formatting.' if self.mode.get() == 'edit'
                                 else 'Click the page where the TOP LEFT corner of your new text should go.'))
        self.canvas.configure(cursor='crosshair' if self.mode.get() == 'add' else '')

    def render(self):
        if not self.doc:
            return
        self.cancel_drag()
        page = self.doc[self.page_index]
        # Bound raster memory for unusually large engineering drawings.
        self.zoom = min(self.zoom, 4500 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        self.photo = ImageTk.PhotoImage(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
        self.canvas.delete('all')
        self.canvas.create_image(20, 20, anchor='nw', image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, pix.width+40, pix.height+40))
        self.page_lines = lines(page)
        self.page_label.configure(text=f'Page {self.page_index+1} / {len(self.doc)}')
        self.pages.selection_clear(0, 'end')
        self.pages.selection_set(self.page_index)
        self.pages.see(self.page_index)
        self.status.set(f'{self.zoom:.0%} zoom | ' + ('Click text to edit, or choose Add Text.' if self.page_lines else 'No editable text on this page. It may be scanned. Use Add Text to write on it.'))
        self.refresh_buttons()

    def point(self, event):
        p = fitz.Point((self.canvas.canvasx(event.x)-20)/self.zoom, (self.canvas.canvasy(event.y)-20)/self.zoom)
        return p * self.doc[self.page_index].derotation_matrix

    def hit(self, point):
        return next((item for item in self.page_lines if item['rect'].contains(point)), None)

    def hover(self, event):
        self.canvas.delete('highlight')
        if not self.doc or self.mode.get() not in ('edit', 'move') or self.drag:
            return
        item = self.hit(self.point(event))
        if item:
            r = item['rect'] * self.doc[self.page_index].rotation_matrix
            self.canvas.create_rectangle(*(v*self.zoom+20 for v in r), outline='#1373d1', width=2, tags='highlight')

    def cancel_drag(self):
        self.drag = None
        self.canvas.delete('drag_preview')
        self.canvas.delete('drag_outline')

    def press(self, event):
        if self.mode.get() != 'move':
            self.click(event)
            return
        if not self.doc:
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
        rect = (item['rect'] + (delta.x, delta.y, delta.x, delta.y)) * self.doc[self.page_index].rotation_matrix
        self.canvas.delete('drag_outline')
        self.canvas.create_rectangle(*(v*self.zoom+20 for v in rect),
                                     outline='#1373d1', width=2, dash=(5, 3), tags='drag_outline')
        self.status.set(f'Move {delta.x:.1f} pt across, {delta.y:.1f} pt down. Release to place; Escape cancels.')

    def release(self, event):
        if not self.drag:
            return
        item, start = self.drag
        delta = self.point(event) - start
        self.cancel_drag()
        if abs(delta.x)+abs(delta.y) < 1:
            return
        try:
            result = move_text(self.data, self.page_index, item, delta.x, delta.y)
            self.commit(result)
            self.status.set('Text moved. Font and character spacing matched. Undo is available. Save As to keep your changes.')
        except Exception as exc:
            messagebox.showinfo('Text was not moved', str(exc), parent=self)

    def commit(self, result):
        self.history.append(self.data)
        while len(self.history) > 20 or (len(self.history)>1 and sum(map(len, self.history))>150_000_000):
            self.history.pop(0)
        self.future.clear()
        self.load_data(result)

    def click(self, event):
        if not self.doc:
            return
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
        self.text_dialog(old, p, bounds)

    @staticmethod
    def toggle_button(parent, label, variable):
        button = ttk.Button(parent, command=lambda: variable.set(not variable.get()))
        def update(*args):
            if button.winfo_exists():
                button.configure(text=f'{label}: {"ON" if variable.get() else "OFF"}')
        trace = variable.trace_add('write', update)
        button.bind('<Destroy>', lambda event: variable.trace_remove('write', trace) if event.widget is button else None)
        update()
        return button

    def text_dialog(self, old, p, bounds):
        box = tk.Toplevel(self)
        box.title('Edit text' if old else 'Add text')
        box.geometry('660x620')
        box.transient(self)
        box.grab_set()
        frame = ttk.Frame(box, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Change the text below, then click Apply. Use Undo if needed.').pack(anchor='w')
        entry = tk.Text(frame, height=7, wrap='word', font=('Segoe UI', 12), undo=True)
        entry.pack(fill='both', expand=True, pady=10)
        entry.insert('1.0', old['text'] if old else '')
        x, y = (old['rect'].x0, old['rect'].y0) if old else (p.x, p.y)
        size = tk.StringVar(value=f'{old["size"]:.1f}' if old else '12')
        width = tk.StringVar(value=f'{min(bounds.x1-x, max(old["rect"].width+3, 80) if old else 240):.1f}')
        height = tk.StringVar(value=f'{min(bounds.y1-y, max(old["rect"].height+3, old["size"]*1.3) if old else 70):.1f}')
        family = tk.StringVar(value='sans-serif')
        original_flags = old['spans'][0].get('flags', 0) if old else 0
        bold = tk.BooleanVar(value=bool(original_flags & 16))
        italic = tk.BooleanVar(value=bool(original_flags & 2))
        match = tk.BooleanVar(value=bool(old))
        color = ['#%06x' % old['color'] if old else '#000000']
        form = ttk.Frame(frame)
        form.pack(fill='x')
        for row, (label, var) in enumerate([('Text size (points)', size), ('Box width (points)', width), ('Box height (points)', height)]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(form, textvariable=var, width=12).grid(row=row, column=1, padx=10)
        ttk.Combobox(form, textvariable=family, values=['sans-serif', 'serif', 'monospace'], state='readonly', width=14).grid(row=0, column=2)
        self.toggle_button(form, 'Bold', bold).grid(row=1, column=2)
        self.toggle_button(form, 'Italic', italic).grid(row=1, column=3)
        def pick():
            chosen = colorchooser.askcolor(color[0], parent=box)[1]
            if chosen:
                color[0] = chosen
                color_button.configure(text=f'Color: {chosen}')
        color_button = ttk.Button(form, text=f'Color: {color[0]}', command=pick)
        color_button.grid(row=2, column=2)
        if old:
            match_check = self.toggle_button(frame, 'Match original formatting', match)
            match_check.pack(anchor='w', pady=(10, 0))
            font_note = ttk.Label(frame, wraplength=610)
            font_note.pack(anchor='w', pady=4)
            def update_match(*args):
                try:
                    _, description = resolve_font(self.doc[self.page_index], old['spans'][0], entry.get('1.0', 'end-1c'))
                    font_note.configure(text=description if match.get() else 'Custom formatting: use the controls above.')
                    for widget in form.winfo_children():
                        grid = widget.grid_info()
                        if (grid.get('column') == 1 and grid.get('row') == 0) or grid.get('column', 0) >= 2:
                            if isinstance(widget, ttk.Combobox):
                                widget.configure(state='disabled' if match.get() else 'readonly')
                            else:
                                widget.configure(state='disabled' if match.get() else 'normal')
                except Exception as exc:
                    font_note.configure(text=str(exc))
            match.trace_add('write', update_match)
            entry.bind('<KeyRelease>', update_match)
            update_match()
        ttk.Label(frame, text='Auto-fit is ON: the box grows into clear space; font size reduces only if needed.\nUse Move Text on the main screen to drag text without changing its formatting.', wraplength=610).pack(anchor='w', pady=10)
        error = ttk.Label(frame, text='', foreground='#ae2525', wraplength=550)
        error.pack(anchor='w')
        def apply():
            try:
                text = entry.get('1.0', 'end-1c')
                if not text.strip():
                    if not old:
                        raise ValueError('Type some text first.')
                    if not messagebox.askyesno('Delete this line?', 'The text box is empty. Remove this line?', parent=box):
                        return
                r = fitz.Rect(x, y, x+float(width.get()), y+float(height.get()))
                fit_info = {}
                result = change(self.data, self.page_index, r, text, float(size.get()), color[0], family.get(), bold.get(), old, match_original=match.get(), italic=italic.get(), auto_fit=True, fit_info=fit_info)
                self.commit(result)
                box.destroy()
                self.status.set('Change applied. ' + (f'Automatically fitted at {fit_info["size"]:.1f} pt. ' if fit_info.get('shrunk') else 'Text box automatically sized. ') + 'Review the result; Undo is available. Save As to keep it.')
            except Exception as exc:
                error.configure(text=str(exc))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(10, 0))
        ttk.Button(buttons, text='Apply', command=apply).pack(side='right')
        ttk.Button(buttons, text='Cancel', command=box.destroy).pack(side='right', padx=8)
        box.bind('<Escape>', lambda e: box.destroy())
        entry.focus_set()
        entry.tag_add('sel', '1.0', 'end-1c')

    def load_data(self, data):
        new_doc = fitz.open(stream=data, filetype='pdf')
        self.doc.close()
        self.doc, self.data = new_doc, data
        self.render()

    def undo(self):
        if self.history:
            self.future.append(self.data)
            self.load_data(self.history.pop())

    def redo(self):
        if self.future:
            self.history.append(self.data)
            self.load_data(self.future.pop())

    def save(self):
        if not self.doc:
            messagebox.showinfo('Open a PDF first', 'Click Open PDF to choose a file.', parent=self)
            return False
        path = filedialog.asksaveasfilename(parent=self, title='Save edited PDF', defaultextension='.pdf',
            initialdir=self.path.parent, initialfile=self.path.stem+'_edited.pdf', filetypes=[('PDF files', '*.pdf')])
        if not path:
            return False
        if Path(path).resolve() == self.path.resolve():
            messagebox.showinfo('Keep your original', 'Choose a different filename so your original PDF stays safe.', parent=self)
            return False
        try:
            save_atomic(self.data, path)
            self.saved_hash = hashlib.sha256(self.data).digest()
            self.refresh_buttons()
            self.status.set(f'Saved successfully: {path}')
            return True
        except Exception as exc:
            messagebox.showerror('Could not save', f'{exc}\n\nTry a different folder or close the PDF in other programs.', parent=self)
            return False

    def select_page(self, event):
        selected = self.pages.curselection()
        if selected and selected[0] != self.page_index:
            self.page_index = selected[0]
            self.render()
            self.canvas.yview_moveto(0)

    def go(self, offset):
        if self.doc:
            self.page_index = max(0, min(len(self.doc)-1, self.page_index+offset))
            self.render()
            self.canvas.yview_moveto(0)

    def zoom_by(self, amount):
        self.zoom = min(3, max(.25, self.zoom+amount))
        self.render()

    def fit_width(self):
        if self.doc:
            self.update_idletasks()
            self.zoom = min(3, max(.15, (self.canvas.winfo_width()-45)/self.doc[self.page_index].rect.width))
            self.render()

    def help(self):
        messagebox.showinfo('Three easy steps',
            '1. Open PDF.\n2. Select Edit Text and click an existing line, or choose Add Text and click a blank area.\n3. Click Save As to create an edited copy.\n\n'
            'MOVE TEXT: select Move Text, then drag a text element. Escape cancels. Moving preserves original fonts and spacing.\n\n'
            'Undo: Ctrl+Z   Redo: Ctrl+Y   Save As: Ctrl+S\n\n'
            'Review each change before saving. PDF layouts do not reflow like Word. '
            'Match Original reuses the original font when possible, otherwise a close substitute. '
            'Each uniform-format text element can be edited separately.\n\n'
            'Scanned text is an image: you can add text, but this app does not OCR or change words inside images. '
            'Angled text and form-field editing are not supported. '
            'On rotated pages, added text follows the original PDF coordinate direction.\n\n'
            'All editing stays on your computer. No subscription or API key.', parent=self)

    def close(self):
        if self.confirm_leave():
            if self.doc:
                self.doc.close()
            self.destroy()


if __name__ == '__main__':
    Editor().mainloop()
