"""The desktop interface: Tk widgets only, no browser engine anywhere.

Everything the app shows is drawn with the standard library's tkinter — the
plasmid map on a Canvas, the sequence in a Text widget, features and primers
in Treeviews. `app.view_model` does the layout maths so this file is only
widgets and event handlers.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import settings, view_model as vm
from .pcr import analyse_primer, Conditions, clean, design_pcr
from .snapgene import Feature, Primer, Segment, SnapGeneFile
from .version import APP_NAME, __version__

MONO = ("Menlo", 11) if sys.platform == "darwin" else ("DejaVu Sans Mono", 10)
MONO_SMALL = (MONO[0], MONO[1] - 1)
BG = "#11141a"
PANEL = "#171b23"
TEXT = "#e6e9ef"
MUTED = "#98a2b3"
ACCENT = "#5b9dff"
OK = "#3bc9a0"
WARN = "#f0b429"
LINE = "#2a313d"

MAP_SIZE = 560


class DnaApp(tk.Tk):
    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x840")
        self.minsize(960, 640)
        self.configure(bg=BG)

        self.plasmid: SnapGeneFile | None = None
        self.path: str | None = None
        self.library: dict[str, Any] = {"dir": None, "files": [], "error": None}

        self._style()
        self._menu()
        self._header()
        self._tabs()
        self._status("준비되었습니다.")

        self.refresh_library()
        if path:
            self.open_file(path)

    # ------------------------------------------------------------- chrome

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL,
                        bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG, foreground=MUTED,
                        padding=(14, 7), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", PANEL)],
                  foreground=[("selected", TEXT)])
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Header.TLabel", background=PANEL, foreground=TEXT,
                        font=(MONO[0], 13, "bold"))
        style.configure("Sub.TLabel", background=PANEL, foreground=MUTED)
        style.configure("TButton", background=PANEL, foreground=TEXT, borderwidth=1,
                        focusthickness=0, padding=(10, 4))
        style.map("TButton", background=[("active", LINE)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", "#4a8ae8")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT,
                        insertcolor=TEXT, borderwidth=1)
        style.configure("TCombobox", fieldbackground=PANEL, foreground=TEXT)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, borderwidth=0, rowheight=22)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED,
                        borderwidth=0)
        style.map("Treeview", background=[("selected", "#294066")],
                  foreground=[("selected", TEXT)])
        style.configure("TCheckbutton", background=BG, foreground=MUTED)
        style.configure("TLabelframe", background=BG, foreground=MUTED)
        style.configure("TLabelframe.Label", background=BG, foreground=MUTED)

    def _menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="열기…", accelerator="Cmd+O", command=self.ask_open)
        file_menu.add_command(label="저장", accelerator="Cmd+S", command=self.save)
        file_menu.add_command(label="다른 이름으로 저장…", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="플라스미드 폴더 지정…", command=self.ask_library_dir)
        file_menu.add_separator()
        file_menu.add_command(label="끝내기", command=self.destroy)
        menubar.add_cascade(label="파일", menu=file_menu)
        self.config(menu=menubar)
        self.bind_all("<Command-o>", lambda _e: self.ask_open())
        self.bind_all("<Control-o>", lambda _e: self.ask_open())
        self.bind_all("<Command-s>", lambda _e: self.save())
        self.bind_all("<Control-s>", lambda _e: self.save())

    def _header(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text=APP_NAME, style="Header.TLabel").pack(side="left")
        self.file_label = ttk.Label(bar, text="파일 없음", style="Sub.TLabel")
        self.file_label.pack(side="left", padx=12)
        self.status_label = ttk.Label(bar, text="", style="Sub.TLabel")
        self.status_label.pack(side="right")
        ttk.Button(bar, text="저장", command=self.save).pack(side="right", padx=4)
        ttk.Button(bar, text="열기…", command=self.ask_open).pack(side="right")

    def _tabs(self) -> None:
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self.tab_library = ttk.Frame(self.tabs, padding=10)
        self.tab_map = ttk.Frame(self.tabs, padding=10)
        self.tab_seq = ttk.Frame(self.tabs, padding=10)
        self.tab_feat = ttk.Frame(self.tabs, padding=10)
        self.tab_primer = ttk.Frame(self.tabs, padding=10)
        self.tab_pcr = ttk.Frame(self.tabs, padding=10)
        for frame, label in [(self.tab_library, "라이브러리"), (self.tab_map, "맵"),
                             (self.tab_seq, "서열"), (self.tab_feat, "Features"),
                             (self.tab_primer, "Primers"), (self.tab_pcr, "Pfu-X PCR")]:
            self.tabs.add(frame, text=label)
        self._build_library()
        self._build_map()
        self._build_sequence()
        self._build_features()
        self._build_primers()
        self._build_pcr()

    def _status(self, message: str, error: bool = False) -> None:
        self.status_label.configure(text=message, foreground=("#ff6b6b" if error else OK))
        self.after(6000, lambda: self.status_label.configure(text="")
                   if self.status_label.cget("text") == message else None)

    # ---------------------------------------------------------- library

    def _build_library(self) -> None:
        top = ttk.Frame(self.tab_library)
        top.pack(fill="x")
        ttk.Label(top, text="플라스미드 폴더", style="Muted.TLabel").pack(side="left")
        self.lib_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.lib_var)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        entry.bind("<Return>", lambda _e: self.set_library_dir(self.lib_var.get()))
        ttk.Button(top, text="찾아보기…", command=self.ask_library_dir).pack(side="left")
        ttk.Button(top, text="지정", style="Accent.TButton",
                   command=lambda: self.set_library_dir(self.lib_var.get())).pack(
            side="left", padx=4)
        ttk.Button(top, text="새로고침", command=self.refresh_library).pack(side="left")
        ttk.Button(top, text="해제", command=self.clear_library_dir).pack(side="left", padx=4)

        self.lib_note = ttk.Label(
            self.tab_library, style="Muted.TLabel",
            text="폴더를 지정해 두면 다음에 앱을 열 때도 기억됩니다. 하위 폴더 한 단계까지 찾습니다.")
        self.lib_note.pack(anchor="w", pady=(6, 8))

        self.lib_tree = ttk.Treeview(self.tab_library, columns=("folder", "size", "modified"),
                                     show="tree headings", height=14)
        self.lib_tree.heading("#0", text="파일")
        self.lib_tree.heading("folder", text="폴더")
        self.lib_tree.heading("size", text="크기")
        self.lib_tree.heading("modified", text="수정")
        self.lib_tree.column("#0", width=380)
        self.lib_tree.column("folder", width=160)
        self.lib_tree.column("size", width=90, anchor="e")
        self.lib_tree.column("modified", width=150)
        self.lib_tree.pack(fill="both", expand=True)
        self.lib_tree.bind("<Double-1>", self._open_selected_library_file)
        self.lib_tree.tag_configure("current", foreground=ACCENT)

        ttk.Button(self.tab_library, text="선택한 파일 열기",
                   command=self._open_selected_library_file).pack(anchor="w", pady=6)

        ttk.Label(self.tab_library, text="최근 연 파일", style="Muted.TLabel").pack(anchor="w")
        self.recent_list = tk.Listbox(self.tab_library, height=5, bg=PANEL, fg=TEXT,
                                      highlightthickness=0, borderwidth=0,
                                      selectbackground="#294066", font=MONO_SMALL)
        self.recent_list.pack(fill="x", pady=(2, 0))
        self.recent_list.bind("<Double-1>", self._open_selected_recent)

    def refresh_library(self) -> None:
        self.library = settings.list_library()
        self.recent = settings.recent_files()
        if self.library.get("dir"):
            self.lib_var.set(self.library["dir"])
        self.lib_tree.delete(*self.lib_tree.get_children())
        if self.library.get("error"):
            self.lib_tree.insert("", "end", text=self.library["error"])
        for entry in self.library.get("files", []):
            tags = ("current",) if self.path == entry["path"] else ()
            self.lib_tree.insert("", "end", text=entry["name"], values=(
                entry["folder"] or "·", f"{round(entry['size'] / 1024):,} KB",
                entry["modified"]), tags=tags)
        self.recent_list.delete(0, "end")
        for entry in self.recent:
            self.recent_list.insert("end", f"{entry['name']}   —   {entry['path']}")

    def ask_library_dir(self) -> None:
        chosen = filedialog.askdirectory(title="플라스미드 폴더 선택")
        if chosen:
            self.set_library_dir(chosen)

    def set_library_dir(self, path: str) -> None:
        try:
            full = settings.set_library_dir(path)
        except ValueError as exc:
            self._status(str(exc), error=True)
            return
        self.refresh_library()
        self._status(f"폴더를 기억했습니다: {full}")

    def clear_library_dir(self) -> None:
        settings.clear_library_dir()
        self.lib_var.set("")
        self.refresh_library()
        self._status("폴더 지정을 해제했습니다.")

    def _library_path_at(self, item: str) -> str | None:
        name = self.lib_tree.item(item, "text")
        folder = self.lib_tree.item(item, "values")[0] if self.lib_tree.item(item, "values") else ""
        for entry in self.library.get("files", []):
            if entry["name"] == name and (entry["folder"] or "·") == folder:
                return entry["path"]
        return None

    def _open_selected_library_file(self, _event=None) -> None:
        selection = self.lib_tree.selection()
        if not selection:
            self._status("열 파일을 선택하세요.", error=True)
            return
        path = self._library_path_at(selection[0])
        if path:
            self.open_file(path)

    def _open_selected_recent(self, _event=None) -> None:
        index = self.recent_list.curselection()
        if index:
            self.open_file(self.recent[index[0]]["path"])

    # ------------------------------------------------------------- file

    def ask_open(self) -> None:
        path = filedialog.askopenfilename(
            title="플라스미드 열기",
            initialdir=self.library.get("dir") or os.path.expanduser("~"),
            filetypes=[("SnapGene DNA", "*.dna"), ("모든 파일", "*.*")])
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        try:
            plasmid = SnapGeneFile.read(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"파일을 열 수 없습니다:\n{exc}")
            return
        self.plasmid = plasmid
        self.path = os.path.abspath(path)
        settings.note_recent(self.path)
        self.refresh_all()
        self._status(f"{os.path.basename(self.path)}을(를) 열었습니다.")

    def save(self) -> None:
        if not self.plasmid or not self.path:
            self._status("저장할 파일이 없습니다.", error=True)
            return
        try:
            self.plasmid.write(self.path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"저장하지 못했습니다:\n{exc}")
            return
        settings.note_recent(self.path)
        self.refresh_library()
        self._status(f"저장했습니다: {self.path}")

    def save_as(self) -> None:
        if not self.plasmid:
            return
        path = filedialog.asksaveasfilename(
            title="다른 이름으로 저장", defaultextension=".dna",
            initialfile=os.path.basename(self.path or "plasmid.dna"),
            initialdir=self.library.get("dir") or os.path.expanduser("~"),
            filetypes=[("SnapGene DNA", "*.dna")])
        if not path:
            return
        self.path = path
        self.save()
        self.refresh_all()

    # ----------------------------------------------------------- refresh

    def refresh_all(self) -> None:
        name = os.path.basename(self.path) if self.path else "파일 없음"
        if self.plasmid:
            topology = "circular" if self.plasmid.is_circular else "linear"
            self.file_label.configure(
                text=f"{name} · {len(self.plasmid.sequence):,} bp · {topology}")
        else:
            self.file_label.configure(text="파일 없음")
        self.draw_map()
        self.draw_sequence()
        self.fill_features()
        self.fill_primers()
        self.refresh_library()

    # --------------------------------------------------------------- map

    def _build_map(self) -> None:
        wrap = ttk.Frame(self.tab_map)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, width=MAP_SIZE, height=MAP_SIZE, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(side="left")
        side = ttk.Frame(wrap, padding=(14, 0))
        side.pack(side="left", fill="both", expand=True)
        self.map_title = ttk.Label(side, text="—", style="TLabel", font=(MONO[0], 12, "bold"))
        self.map_title.pack(anchor="w")
        self.map_meta = ttk.Label(side, text="", style="Muted.TLabel")
        self.map_meta.pack(anchor="w", pady=(2, 8))
        self.legend = tk.Listbox(side, bg=PANEL, fg=TEXT, highlightthickness=0,
                                 borderwidth=0, font=MONO_SMALL,
                                 selectbackground="#294066")
        self.legend.pack(fill="both", expand=True)

    def draw_map(self) -> None:
        self.canvas.delete("all")
        self.legend.delete(0, "end")
        if not self.plasmid:
            self.map_title.configure(text="—")
            self.map_meta.configure(text="")
            return
        length = len(self.plasmid.sequence)
        cx = cy = MAP_SIZE / 2
        radius = MAP_SIZE * 0.33
        self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                                outline=LINE, width=9)

        step = max(500, round(length / 12 / 500) * 500)
        for pos in range(0, length, step):
            angle = 90.0 - 360.0 * pos / length
            x1, y1 = vm.polar(cx, cy, radius + 8, angle)
            x2, y2 = vm.polar(cx, cy, radius + 14, angle)
            self.canvas.create_line(x1, y1, x2, y2, fill=MUTED)
            tx, ty = vm.polar(cx, cy, radius + 28, angle)
            self.canvas.create_text(tx, ty, text=f"{pos or 1:,}", fill=MUTED,
                                    font=(MONO[0], 8))

        for arc in vm.map_arcs(self.plasmid.features, length):
            r = radius - arc["ring"] * 16
            self.canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                                   start=arc["start_angle"], extent=arc["extent"],
                                   style="arc", outline=arc["color"], width=9)
            if arc["directionality"] in (1, 2):
                at = arc["start_angle"] + (arc["extent"] if arc["directionality"] == 1 else 0)
                tip = vm.polar(cx, cy, r, at)
                back = at + (6 if arc["directionality"] == 1 else -6)
                self.canvas.create_polygon(
                    *tip, *vm.polar(cx, cy, r - 7, back), *vm.polar(cx, cy, r + 7, back),
                    fill=arc["color"], outline=arc["color"])
            if arc["label"]:
                lx, ly = vm.polar(cx, cy, r - 15, arc["mid_angle"])
                self.canvas.create_text(lx, ly, text=arc["label"], fill=TEXT,
                                        font=(MONO[0], 8))

        title = os.path.basename(self.path or "plasmid.dna")
        self.canvas.create_text(cx, cy - 8, text=title.replace(".dna", ""), fill=TEXT,
                                font=(MONO[0], 12, "bold"))
        self.canvas.create_text(cx, cy + 12, text=f"{length:,} bp", fill=MUTED,
                                font=(MONO[0], 9))
        self.map_title.configure(text=title)
        self.map_meta.configure(
            text=f"{length:,} bp · {'환형' if self.plasmid.is_circular else '선형'} · "
                 f"feature {len(self.plasmid.features)}개 · "
                 f"저장된 프라이머 {len(self.plasmid.primers)}개")
        for feat in self.plasmid.features:
            arrow = {1: "→", 2: "←"}.get(feat.directionality, " ")
            self.legend.insert("end", f"{arrow} {feat.name}  "
                                      f"({feat.start:,}–{feat.end:,}, {feat.type})")

    # ---------------------------------------------------------- sequence

    def _build_sequence(self) -> None:
        bar = ttk.Frame(self.tab_seq)
        bar.pack(fill="x")
        ttk.Label(bar, text="이동", style="Muted.TLabel").pack(side="left")
        self.goto_var = tk.StringVar(value="1")
        ttk.Entry(bar, textvariable=self.goto_var, width=9).pack(side="left", padx=4)
        ttk.Button(bar, text="가기", command=self.goto_position).pack(side="left")
        self.show_rc = tk.BooleanVar(value=False)
        self.show_tracks = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="상보가닥", variable=self.show_rc,
                        command=self.draw_sequence).pack(side="left", padx=(12, 4))
        ttk.Checkbutton(bar, text="feature 트랙", variable=self.show_tracks,
                        command=self.draw_sequence).pack(side="left")

        wrap = ttk.Frame(self.tab_seq)
        wrap.pack(fill="both", expand=True, pady=8)
        self.seq_text = tk.Text(wrap, wrap="none", font=MONO, bg=PANEL, fg=TEXT,
                                insertbackground=TEXT, borderwidth=0, highlightthickness=0,
                                height=24, selectbackground="#294066")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.seq_text.yview)
        scroll.pack(side="right", fill="y")
        self.seq_text.pack(side="left", fill="both", expand=True)
        self.seq_text.configure(yscrollcommand=scroll.set, state="disabled")

        edit = ttk.Labelframe(self.tab_seq, text="서열 편집", padding=10)
        edit.pack(fill="x")
        self.edit_start = tk.StringVar()
        self.edit_end = tk.StringVar()
        self.edit_new = tk.StringVar()
        ttk.Label(edit, text="시작", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(edit, textvariable=self.edit_start, width=10).grid(row=0, column=1, padx=4)
        ttk.Label(edit, text="끝", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(edit, textvariable=self.edit_end, width=10).grid(row=0, column=3, padx=4)
        ttk.Label(edit, text="새 서열 (비우면 삭제)",
                  style="Muted.TLabel").grid(row=0, column=4, padx=(12, 4))
        ttk.Entry(edit, textvariable=self.edit_new).grid(row=0, column=5, sticky="ew", padx=4)
        ttk.Button(edit, text="적용", style="Accent.TButton",
                   command=self.apply_edit).grid(row=0, column=6, padx=4)
        edit.columnconfigure(5, weight=1)
        ttk.Label(edit, style="Muted.TLabel",
                  text="편집 범위에 걸친 feature는 남은 부분으로 잘리고, 완전히 포함된 feature는 삭제됩니다."
                  ).grid(row=1, column=0, columnspan=7, sticky="w", pady=(6, 0))

    def draw_sequence(self) -> None:
        self.seq_text.configure(state="normal")
        self.seq_text.delete("1.0", "end")
        if not self.plasmid:
            self.seq_text.configure(state="disabled")
            return
        rows = vm.sequence_rows(self.plasmid.sequence, self.plasmid.features,
                                show_complement=self.show_rc.get(),
                                show_tracks=self.show_tracks.get())
        colors: dict[str, str] = {}
        for index, row in enumerate(rows, start=1):
            self.seq_text.insert("end", row["text"] + "\n")
            if row["kind"] in ("sequence", "complement"):
                self.seq_text.tag_add("gutter", f"{index}.0", f"{index}.{row['gutter']}")
            for col_start, col_end, color in row["spans"]:
                tag = colors.setdefault(color, f"c{len(colors)}")
                self.seq_text.tag_add(tag, f"{index}.{col_start}", f"{index}.{col_end}")
        for color, tag in colors.items():
            self.seq_text.tag_configure(tag, foreground=color)
        self.seq_text.tag_configure("gutter", foreground=MUTED)
        self.seq_text.configure(state="disabled")

    def goto_position(self) -> None:
        if not self.plasmid:
            return
        try:
            pos = int(self.goto_var.get().replace(",", ""))
        except ValueError:
            self._status("숫자를 입력하세요.", error=True)
            return
        pos = max(1, min(pos, len(self.plasmid.sequence)))
        rows = vm.sequence_rows(self.plasmid.sequence, self.plasmid.features,
                                show_complement=self.show_rc.get(),
                                show_tracks=self.show_tracks.get())
        for index, row in enumerate(rows, start=1):
            if row["kind"] == "sequence" and row["first"] <= pos <= row["last"]:
                self.seq_text.see(f"{index}.0")
                break

    def apply_edit(self) -> None:
        if not self.plasmid:
            return
        try:
            start = int(self.edit_start.get().replace(",", ""))
            end = int(self.edit_end.get().replace(",", ""))
        except ValueError:
            self._status("편집할 범위를 숫자로 입력하세요.", error=True)
            return
        if not (1 <= start <= end <= len(self.plasmid.sequence)):
            self._status("편집 범위가 서열 길이를 벗어났습니다.", error=True)
            return
        replacement = clean(self.edit_new.get())
        if not messagebox.askyesno(
                APP_NAME,
                f"{start:,}–{end:,} ({end - start + 1:,} bp)를 "
                f"{replacement or '(삭제)'}로 바꿀까요?"):
            return
        self.plasmid.apply_edit(start, end, replacement)
        self.edit_new.set("")
        self.refresh_all()
        self._status("서열을 편집했습니다. 저장하려면 Cmd+S를 누르세요.")

    # ---------------------------------------------------------- features

    def _build_features(self) -> None:
        columns = ("type", "dir", "start", "end", "length", "color", "segments")
        self.feat_tree = ttk.Treeview(self.tab_feat, columns=columns,
                                      show="tree headings", height=12)
        headings = {"type": "종류", "dir": "방향", "start": "시작", "end": "끝",
                    "length": "길이", "color": "색", "segments": "조각"}
        self.feat_tree.heading("#0", text="이름")
        self.feat_tree.column("#0", width=260)
        for key, label in headings.items():
            self.feat_tree.heading(key, text=label)
            self.feat_tree.column(key, width=90, anchor="w")
        self.feat_tree.pack(fill="both", expand=True)
        self.feat_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_feature_detail())

        form = ttk.Frame(self.tab_feat)
        form.pack(fill="x", pady=8)
        self.f_name = tk.StringVar()
        self.f_type = tk.StringVar(value="misc_feature")
        self.f_dir = tk.StringVar(value="forward")
        self.f_start = tk.StringVar()
        self.f_end = tk.StringVar()
        self.f_color = tk.StringVar(value="#3366ff")
        fields = [("이름", self.f_name, 22), ("종류", self.f_type, 16),
                  ("시작", self.f_start, 9), ("끝", self.f_end, 9), ("색", self.f_color, 10)]
        col = 0
        for label, var, width in fields:
            ttk.Label(form, text=label, style="Muted.TLabel").grid(row=0, column=col, padx=(0, 4))
            ttk.Entry(form, textvariable=var, width=width).grid(row=0, column=col + 1, padx=(0, 10))
            col += 2
        ttk.Label(form, text="방향", style="Muted.TLabel").grid(row=0, column=col, padx=(0, 4))
        ttk.Combobox(form, textvariable=self.f_dir, width=9, state="readonly",
                     values=("forward", "reverse", "없음")).grid(row=0, column=col + 1)
        buttons = ttk.Frame(self.tab_feat)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="선택 항목에 적용", command=self.update_feature).pack(side="left")
        ttk.Button(buttons, text="추가", style="Accent.TButton",
                   command=self.add_feature).pack(side="left", padx=6)
        ttk.Button(buttons, text="삭제", command=self.delete_feature).pack(side="left")
        ttk.Button(buttons, text="서열에서 보기",
                   command=self.show_feature_in_sequence).pack(side="left", padx=6)

        self.feat_detail = tk.Text(self.tab_feat, height=11, wrap="word", font=MONO_SMALL,
                                   bg=PANEL, fg=TEXT, borderwidth=0, highlightthickness=0)
        self.feat_detail.pack(fill="both", expand=True, pady=(8, 0))
        self.feat_detail.configure(state="disabled")

    def fill_features(self) -> None:
        self.feat_tree.delete(*self.feat_tree.get_children())
        if not self.plasmid:
            return
        for index, feat in enumerate(self.plasmid.features):
            direction = {1: "→ forward", 2: "← reverse"}.get(feat.directionality, "없음")
            self.feat_tree.insert("", "end", iid=str(index), text=feat.name, values=(
                feat.type, direction, f"{feat.start:,}", f"{feat.end:,}",
                f"{feat.end - feat.start + 1:,}", feat.color,
                f"{len(feat.segments)}개"))

    def _selected_feature(self) -> int | None:
        selection = self.feat_tree.selection()
        return int(selection[0]) if selection else None

    def show_feature_detail(self) -> None:
        index = self._selected_feature()
        self.feat_detail.configure(state="normal")
        self.feat_detail.delete("1.0", "end")
        if index is not None and self.plasmid:
            feat = self.plasmid.features[index]
            self.feat_detail.insert("1.0", vm.feature_detail(feat))
            self.f_name.set(feat.name)
            self.f_type.set(feat.type)
            self.f_dir.set({1: "forward", 2: "reverse"}.get(feat.directionality, "없음"))
            self.f_start.set(str(feat.start))
            self.f_end.set(str(feat.end))
            self.f_color.set(feat.color)
        self.feat_detail.configure(state="disabled")

    def _feature_from_form(self, existing: Feature | None = None) -> Feature | None:
        try:
            start = int(self.f_start.get().replace(",", ""))
            end = int(self.f_end.get().replace(",", ""))
        except ValueError:
            self._status("시작과 끝을 숫자로 입력하세요.", error=True)
            return None
        if not self.plasmid or not (1 <= start <= end <= len(self.plasmid.sequence)):
            self._status("좌표가 서열 범위를 벗어났습니다.", error=True)
            return None
        directionality = {"forward": 1, "reverse": 2}.get(self.f_dir.get(), 0)
        color = self.f_color.get().strip() or "#cccccc"
        return Feature(
            name=self.f_name.get().strip() or "new feature",
            type=self.f_type.get().strip() or "misc_feature",
            directionality=directionality,
            segments=[Segment(start, end, color,
                              existing.segments[0].translated if existing else False)],
            notes=dict(existing.notes) if existing else {},
            translation=existing.translation if existing else "",
        )

    def add_feature(self) -> None:
        feat = self._feature_from_form()
        if not feat or not self.plasmid:
            return
        self.plasmid.features.append(feat)
        self.plasmid.features.sort(key=lambda f: (f.start, f.end))
        self.refresh_all()
        self._status(f"{feat.name} feature를 추가했습니다.")

    def update_feature(self) -> None:
        index = self._selected_feature()
        if index is None or not self.plasmid:
            self._status("수정할 feature를 선택하세요.", error=True)
            return
        feat = self._feature_from_form(self.plasmid.features[index])
        if not feat:
            return
        self.plasmid.features[index] = feat
        self.refresh_all()
        self._status(f"{feat.name} feature를 수정했습니다.")

    def delete_feature(self) -> None:
        index = self._selected_feature()
        if index is None or not self.plasmid:
            self._status("삭제할 feature를 선택하세요.", error=True)
            return
        feat = self.plasmid.features[index]
        if not messagebox.askyesno(APP_NAME, f"{feat.name} feature를 삭제할까요?"):
            return
        del self.plasmid.features[index]
        self.refresh_all()
        self._status("삭제했습니다.")

    def show_feature_in_sequence(self) -> None:
        index = self._selected_feature()
        if index is None or not self.plasmid:
            return
        feat = self.plasmid.features[index]
        self.goto_var.set(str(feat.start))
        self.edit_start.set(str(feat.start))
        self.edit_end.set(str(feat.end))
        self.tabs.select(self.tab_seq)
        self.goto_position()

    # ----------------------------------------------------------- primers

    def _build_primers(self) -> None:
        columns = ("length", "gc", "tm", "binding")
        self.primer_tree = ttk.Treeview(self.tab_primer, columns=columns,
                                        show="tree headings", height=10)
        self.primer_tree.heading("#0", text="이름")
        self.primer_tree.column("#0", width=240)
        for key, label, width in [("length", "길이", 70), ("gc", "GC%", 70),
                                  ("tm", "Tm", 90), ("binding", "결합 위치", 320)]:
            self.primer_tree.heading(key, text=label)
            self.primer_tree.column(key, width=width, anchor="w")
        self.primer_tree.pack(fill="both", expand=True)
        self.primer_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_primer())

        self.primer_seq = tk.Text(self.tab_primer, height=3, wrap="char", font=MONO_SMALL,
                                  bg=PANEL, fg=TEXT, borderwidth=0, highlightthickness=0)
        self.primer_seq.pack(fill="x", pady=8)

        form = ttk.Frame(self.tab_primer)
        form.pack(fill="x")
        self.p_name = tk.StringVar()
        ttk.Label(form, text="이름", style="Muted.TLabel").pack(side="left")
        ttk.Entry(form, textvariable=self.p_name, width=28).pack(side="left", padx=6)
        ttk.Button(form, text="선택 항목에 적용", command=self.update_primer).pack(side="left")
        ttk.Button(form, text="추가", style="Accent.TButton",
                   command=self.add_primer).pack(side="left", padx=6)
        ttk.Button(form, text="삭제", command=self.delete_primer).pack(side="left")
        ttk.Button(form, text="PCR에 forward로", command=lambda: self.send_to_pcr("fwd")
                   ).pack(side="left", padx=(16, 4))
        ttk.Button(form, text="reverse로", command=lambda: self.send_to_pcr("rev")).pack(side="left")

    def fill_primers(self) -> None:
        self.primer_tree.delete(*self.primer_tree.get_children())
        if not self.plasmid:
            return
        conditions = self._conditions()
        for index, primer in enumerate(self.plasmid.primers):
            report = analyse_primer(primer.name, primer.sequence, self.plasmid.sequence,
                                    self.plasmid.is_circular, conditions)
            binding = report.binding
            where = (f"{binding.start:,}–{binding.end:,} "
                     f"({'top →' if binding.strand == 0 else 'bottom ←'}, "
                     f"{binding.matched_len} nt 일치)") if binding else "찾지 못함"
            self.primer_tree.insert("", "end", iid=str(index), text=primer.name, values=(
                report.length, f"{report.gc:.1f}",
                "–" if report.tm_anneal != report.tm_anneal else f"{report.tm_anneal:.1f} °C",
                where))

    def _selected_primer(self) -> int | None:
        selection = self.primer_tree.selection()
        return int(selection[0]) if selection else None

    def show_primer(self) -> None:
        index = self._selected_primer()
        if index is None or not self.plasmid:
            return
        primer = self.plasmid.primers[index]
        self.p_name.set(primer.name)
        self.primer_seq.delete("1.0", "end")
        self.primer_seq.insert("1.0", primer.sequence)

    def _primer_from_form(self) -> Primer | None:
        sequence = clean(self.primer_seq.get("1.0", "end"))
        if not sequence:
            self._status("프라이머 서열을 입력하세요.", error=True)
            return None
        return Primer(self.p_name.get().strip() or "new primer", sequence)

    def add_primer(self) -> None:
        primer = self._primer_from_form()
        if not primer or not self.plasmid:
            return
        self.plasmid.primers.append(primer)
        self.fill_primers()
        self._status(f"{primer.name} 프라이머를 추가했습니다.")

    def update_primer(self) -> None:
        index = self._selected_primer()
        if index is None or not self.plasmid:
            self._status("수정할 프라이머를 선택하세요.", error=True)
            return
        primer = self._primer_from_form()
        if not primer:
            return
        self.plasmid.primers[index] = primer
        self.fill_primers()
        self._status("프라이머를 수정했습니다.")

    def delete_primer(self) -> None:
        index = self._selected_primer()
        if index is None or not self.plasmid:
            self._status("삭제할 프라이머를 선택하세요.", error=True)
            return
        primer = self.plasmid.primers[index]
        if not messagebox.askyesno(APP_NAME, f"{primer.name} 프라이머를 삭제할까요?"):
            return
        del self.plasmid.primers[index]
        self.fill_primers()
        self._status("삭제했습니다.")

    def send_to_pcr(self, side: str) -> None:
        index = self._selected_primer()
        if index is None or not self.plasmid:
            self._status("프라이머를 선택하세요.", error=True)
            return
        primer = self.plasmid.primers[index]
        (self.fwd_name if side == "fwd" else self.rev_name).set(primer.name)
        target = self.fwd_seq if side == "fwd" else self.rev_seq
        target.delete("1.0", "end")
        target.insert("1.0", primer.sequence)
        self.tabs.select(self.tab_pcr)

    # --------------------------------------------------------------- pcr

    def _build_pcr(self) -> None:
        top = ttk.Frame(self.tab_pcr)
        top.pack(fill="x")
        self.fwd_name = tk.StringVar(value="forward")
        self.rev_name = tk.StringVar(value="reverse")
        for column, (label, var) in enumerate([("Forward primer", self.fwd_name),
                                               ("Reverse primer", self.rev_name)]):
            box = ttk.Labelframe(top, text=label, padding=8)
            box.grid(row=0, column=column, sticky="nsew", padx=(0, 10))
            ttk.Entry(box, textvariable=var, width=26).pack(fill="x")
            text = tk.Text(box, height=3, wrap="char", font=MONO_SMALL, bg=PANEL, fg=TEXT,
                           borderwidth=0, highlightthickness=0)
            text.pack(fill="both", expand=True, pady=(6, 0))
            if column == 0:
                self.fwd_seq = text
            else:
                self.rev_seq = text
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        conditions = ttk.Labelframe(top, text="반응 조건", padding=8)
        conditions.grid(row=0, column=2, sticky="nsew")
        self.cond_vars: dict[str, tk.StringVar] = {}
        rows = [("primer_conc_nM", "프라이머 (nM)", "250"), ("na_mM", "Na⁺ (mM)", "10"),
                ("mg_mM", "Mg²⁺ (mM)", "2"), ("dntp_mM", "dNTP (mM)", "0.2"),
                ("ta_offset", "Ta = min(Tm) − (°C)", "5"),
                ("extension_s_per_kb", "신장 (초/kb)", "30"),
                ("cycles", "사이클 수", "30"), ("reaction_uL", "반응 부피 (µL)", "50")]
        for row, (key, label, default) in enumerate(rows):
            ttk.Label(conditions, text=label, style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=default)
            self.cond_vars[key] = var
            ttk.Entry(conditions, textvariable=var, width=8).grid(row=row, column=1, padx=4)
        ttk.Button(conditions, text="PCR 조건 계산", style="Accent.TButton",
                   command=self.calculate_pcr).grid(row=len(rows), column=0, columnspan=2,
                                                    sticky="ew", pady=(8, 0))

        self.pcr_out = tk.Text(self.tab_pcr, wrap="word", font=MONO_SMALL, bg=PANEL, fg=TEXT,
                               borderwidth=0, highlightthickness=0)
        self.pcr_out.pack(fill="both", expand=True, pady=(10, 0))
        self.pcr_out.configure(state="disabled")

    def _conditions(self) -> Conditions:
        values: dict[str, Any] = {}
        for key, var in getattr(self, "cond_vars", {}).items():
            try:
                values[key] = float(var.get())
            except ValueError:
                continue
        return Conditions.from_dict(values)

    def calculate_pcr(self) -> None:
        primers = [
            {"name": self.fwd_name.get() or "forward", "sequence": self.fwd_seq.get("1.0", "end")},
            {"name": self.rev_name.get() or "reverse", "sequence": self.rev_seq.get("1.0", "end")},
        ]
        primers = [p for p in primers if clean(p["sequence"])]
        if not primers:
            self._status("프라이머 서열을 입력하세요.", error=True)
            return
        template = self.plasmid.sequence if self.plasmid else None
        circular = bool(self.plasmid.is_circular) if self.plasmid else False
        conditions = {k: v.get() for k, v in self.cond_vars.items()}
        result = design_pcr(primers, template, circular, conditions)
        self.pcr_out.configure(state="normal")
        self.pcr_out.delete("1.0", "end")
        self.pcr_out.insert("1.0", vm.pcr_report(result))
        self.pcr_out.configure(state="disabled")
        self._status("계산했습니다.")


def main(path: str | None = None) -> None:
    app = DnaApp(path)
    app.mainloop()
