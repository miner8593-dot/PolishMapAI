from __future__ import annotations

import json
import logging
import math
import os
import queue
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from decimal import Decimal
from pathlib import Path

# PyInstaller's standard Tk runtime hook runs before application code and may
# leave Tcl 8.6.15 with a backslash-form library path that it rejects on
# Windows. Override it before the first Tk interpreter is constructed.
if getattr(sys, "_MEIPASS", ""):
    runtime = Path(os.getenv("LOCALAPPDATA", Path.home())) / "PolishMapAI" / "tcl-runtime"
    tcl_runtime = runtime / "tcl8.6"
    tk_runtime = runtime / "tk8.6"
    if not (tcl_runtime / "init.tcl").exists():
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copytree(Path(sys._MEIPASS) / "_tcl_data", tcl_runtime, dirs_exist_ok=True)
        shutil.copytree(Path(sys._MEIPASS) / "_tk_data", tk_runtime, dirs_exist_ok=True)
    os.environ["TCL_LIBRARY"] = tcl_runtime.as_posix()
    os.environ["TK_LIBRARY"] = tk_runtime.as_posix()

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .coordinates import format_coordinates, parse_coordinates
from .mp import MpDocument, MpSection, geometry_issues
from .shapefile_io import export_objects, import_objects
from .spatial import BBox, IndexedObject, SpatialIndex, intersects, section_bbox


LOGGER = logging.getLogger("polishmapai.performance")
MAX_PRIMITIVES = 12_000
RENDER_BUDGET_SECONDS = 0.012
DRAG_THRESHOLD = 5
SCALES = [50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PolishMapAI — Без имени")
        self.geometry("1280x800"); self.minsize(900, 560)
        self.doc = MpDocument([], [])
        self.index = SpatialIndex()
        self.selected: list[MpSection] = []
        self.mode = "select"
        self.pending: list[tuple[float, float]] = []
        self.zoom = 1.0; self.center = [0.0, 0.0]
        self.drag_start = None; self.drag_kind = None; self.drag_preview = (0, 0)
        self.undo_stack = []; self.redo_stack = []
        self.clipboard_objects: list[MpSection] = []
        self.level = tk.IntVar(value=0)
        self.status = tk.StringVar(value="Готово")
        self.scale_text = tk.StringVar(value="100 км")
        self.loading_cancel = threading.Event(); self.worker_queue: queue.Queue = queue.Queue()
        self.render_after = None; self.wheel_after = None; self.resize_after = None
        self.render_generation = 0; self.render_state = None; self.drag_node = None
        self.last_render_stats = {}
        self.render_reason = "viewport"; self.first_frame_pending = False
        self.context_coordinate = (0.0, 0.0)
        self.last_cursor_coordinate = None; self.goto_marker = None
        self.last_hit_point = None; self.last_hit_ids = (); self.hit_cycle = 0
        self.metrics: list[str] = []
        self.view_options = self._load_view_options()
        self.view_vars = {
            name: tk.BooleanVar(value=value)
            for name, value in self.view_options.items()
            if isinstance(value, bool)
        }
        self._build_menu(); self._build_ui(); self._bind_keys(); self._update_commands()
        self.protocol("WM_DELETE_WINDOW", self.request_exit)

    # ----- interface -------------------------------------------------
    def _build_menu(self):
        bar = tk.Menu(self)
        self.file_menu = tk.Menu(bar, tearoff=False)
        self._cmd(self.file_menu, "Создать…", self.new_file, "Ctrl+N")
        self._cmd(self.file_menu, "Открыть…", self.open_file, "Ctrl+O")
        self._cmd(self.file_menu, "Добавить…", self.add_mp)
        self._cmd(self.file_menu, "Закрыть", self.close_file)
        self.file_menu.add_separator()
        self._cmd(self.file_menu, "Сохранить", self.save_file, "Ctrl+S")
        self._cmd(self.file_menu, "Сохранить как…", self.save_as, "Ctrl+Shift+S")
        imp = tk.Menu(self.file_menu, tearoff=False); self._cmd(imp, "Shapefile ESRI (*.shp)", self.import_shapefile)
        exp = tk.Menu(self.file_menu, tearoff=False); self._cmd(exp, "Shapefile ESRI (*.shp)", self.export_shapefile); self._cmd(exp, "Polish MP / копия проекта", self.save_as)
        self.file_menu.add_cascade(label="Импорт", menu=imp); self.file_menu.add_cascade(label="Экспорт", menu=exp)
        self._cmd(self.file_menu, "Свойства карты", self.map_properties)
        self._cmd(self.file_menu, "Журнал сообщений", self.show_log)
        self.file_menu.add_separator(); self._cmd(self.file_menu, "Выход", self.request_exit)

        self.edit_menu = tk.Menu(bar, tearoff=False)
        for label, command, key in [("Отменить", self.undo, "Ctrl+Z"), ("Вернуть", self.redo, "Ctrl+Y"), ("Вырезать", self.cut, "Ctrl+X"), ("Копировать", self.copy, "Ctrl+C"), ("Вставить", self.paste, "Ctrl+V"), ("Удалить", self.delete_selected, "Del")]:
            self._cmd(self.edit_menu, label, command, key)
        selection = tk.Menu(self.edit_menu, tearoff=False)
        for label, kind, key in [("Все объекты", None, "Ctrl+A"), ("Все точки", "POINT", ""), ("Все полилинии", "LINE", ""), ("Все полигоны", "POLYGON", ""), ("Все дороги", "ROAD", "")]:
            self._cmd(selection, label, lambda k=kind: self.select_all(k), key)
        self.edit_menu.add_cascade(label="Выделить", menu=selection)
        self._cmd(self.edit_menu, "Очистить выделение", self.clear_selection)
        self._cmd(self.edit_menu, "Обратить выделение", self.invert_selection)
        self.edit_menu.add_separator(); self._cmd(self.edit_menu, "Найти…", self.find_object, "Ctrl+F")

        self.view_menu = tk.Menu(bar, tearoff=False)
        self._cmd(self.view_menu, "Увеличить", lambda: self.change_zoom(1.25), "+")
        self._cmd(self.view_menu, "Уменьшить", lambda: self.change_zoom(0.8), "−")
        scale_menu = tk.Menu(self.view_menu, tearoff=False)
        for scale in SCALES: scale_menu.add_command(label=self._format_scale(scale), command=lambda s=scale: self.set_physical_scale(s))
        self.view_menu.add_cascade(label="Масштаб", menu=scale_menu)
        self._cmd(self.view_menu, "Вся карта", self.zoom_all, "Home")
        level_menu = tk.Menu(self.view_menu, tearoff=False)
        for level in range(0, 7): level_menu.add_radiobutton(label=f"Уровень {level}", variable=self.level, value=level, command=self.schedule_render)
        self.view_menu.add_cascade(label="Уровни детализации", menu=level_menu)
        theme = tk.Menu(self.view_menu, tearoff=False); theme.add_radiobutton(label="Временное оформление", value="temporary", variable=tk.StringVar(value="temporary"))
        self.view_menu.add_cascade(label="Темы/скины карты", menu=theme)
        for key, label in [("grid", "Сетка"), ("labels", "Подписи"), ("label_outline", "Окантовка подписей"), ("polygon_outlines", "Контуры полигонов"), ("transparent_polygons", "Прозрачные полигоны"), ("road_classes", "Классы дорог"), ("addresses", "Адреса"), ("coverage", "Область покрытия")]:
            self.view_menu.add_checkbutton(label=label, variable=self.view_vars[key], command=self._view_changed)
        self.view_menu.add_separator(); self._cmd(self.view_menu, "Обновить", self.render_viewport, "F5"); self._cmd(self.view_menu, "Перейти к координатам…", self.goto_coordinates, "Ctrl+G")

        favorites = tk.Menu(bar, tearoff=False); self._cmd(favorites, "Добавить текущий вид", self.add_favorite); self._cmd(favorites, "Список избранного…", self.show_favorites)
        tools = tk.Menu(bar, tearoff=False)
        for label, mode in [("Выбор", "select"), ("Рука", "pan"), ("Создать POI", "POI"), ("Создать полилинию", "POLYLINE"), ("Создать полигон", "POLYGON")]: self._cmd(tools, label, lambda m=mode: self.set_mode(m))
        tools.add_separator(); self._cmd(tools, "Проверить геометрию", self.check_geometry)
        neural = tk.Menu(bar, tearoff=False); self._cmd(neural, "Открыть настройки нейросети…", self.neural_info)
        help_menu = tk.Menu(bar, tearoff=False); self._cmd(help_menu, "О программе", lambda: messagebox.showinfo("О программе", "PolishMapAI\nНезависимый clean-room редактор.\nТема: «Временное оформление»; Garmin TYP пока не поддерживается."))
        for label, menu in [("Файл", self.file_menu), ("Правка", self.edit_menu), ("Вид", self.view_menu), ("Избранное", favorites), ("Инструменты", tools), ("Нейросеть", neural), ("Справка", help_menu)]: bar.add_cascade(label=label, menu=menu)
        self.config(menu=bar)

    def _cmd(self, menu, label, command, accelerator=""):
        menu.add_command(label=label, command=command, accelerator=accelerator)

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=3); toolbar.pack(fill="x")
        for text, command in [("Новый", self.new_file), ("Открыть", self.open_file), ("Сохранить", self.save_file), ("↶", self.undo), ("↷", self.redo)]: ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=1)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=4)
        for text, mode in [("↖ Выбор", "select"), ("Узлы", "nodes"), ("✋ Рука", "pan"), ("● POI", "POI"), ("╱ Линия", "POLYLINE"), ("△ Полигон", "POLYGON")]: ttk.Button(toolbar, text=text, command=lambda m=mode: self.set_mode(m)).pack(side="left", padx=1)
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.change_zoom(1.25)).pack(side="left", padx=(6, 0)); ttk.Button(toolbar, text="−", width=3, command=lambda: self.change_zoom(.8)).pack(side="left")
        self.scale_combo = ttk.Combobox(toolbar, textvariable=self.scale_text, values=[self._format_scale(s) for s in SCALES], width=10, state="readonly"); self.scale_combo.pack(side="left", padx=4); self.scale_combo.bind("<<ComboboxSelected>>", self._scale_selected)
        ttk.Label(toolbar, text="Детализация:").pack(side="left"); ttk.Spinbox(toolbar, from_=0, to=24, width=3, textvariable=self.level, command=self.schedule_render).pack(side="left")
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True)
        map_frame = ttk.Frame(pane); prop_frame = ttk.Frame(pane, padding=6); pane.add(map_frame, weight=4); pane.add(prop_frame, weight=1)
        self.canvas = tk.Canvas(map_frame, background="#f3f3f0", cursor="arrow", highlightthickness=0); self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize); self.canvas.bind("<Button-1>", self.on_press); self.canvas.bind("<B1-Motion>", self.on_drag); self.canvas.bind("<ButtonRelease-1>", self.on_release); self.canvas.bind("<Double-Button-1>", self.on_double_click); self.canvas.bind("<Button-3>", self.on_context); self.canvas.bind("<Motion>", self.on_motion); self.canvas.bind("<MouseWheel>", self.on_wheel); self.canvas.bind("<Shift-MouseWheel>", self.on_wheel); self.canvas.bind("<Control-MouseWheel>", self.on_wheel)
        ttk.Label(prop_frame, text="Свойства объектов", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.selection_label = ttk.Label(prop_frame, text="Ничего не выбрано"); self.selection_label.pack(anchor="w")
        self.prop_tree = ttk.Treeview(prop_frame, columns=("value",), show="tree headings"); self.prop_tree.heading("#0", text="Поле"); self.prop_tree.heading("value", text="Значение"); self.prop_tree.pack(fill="both", expand=True, pady=5); self.prop_tree.bind("<Double-1>", self.edit_property)
        progress_frame = ttk.Frame(self); progress_frame.pack(fill="x"); self.progress = ttk.Progressbar(progress_frame, mode="determinate"); self.cancel_button = ttk.Button(progress_frame, text="Отмена загрузки", command=self.loading_cancel.set)
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=3).pack(fill="x")

    def _bind_keys(self):
        bindings = {"<Control-n>": self.new_file, "<Control-o>": self.open_file, "<Control-s>": self.save_file, "<Control-Shift-S>": self.save_as, "<Control-z>": self.undo, "<Control-y>": self.redo, "<Control-x>": self.cut, "<Control-c>": self.copy, "<Control-v>": self.paste, "<Control-a>": self.select_all, "<Control-f>": self.find_object, "<Control-g>": self.goto_coordinates, "<Delete>": self.delete_selected, "<Home>": self.zoom_all, "<F5>": self.render_viewport, "<Escape>": self.cancel_interaction}
        for key, command in bindings.items(): self.bind(key, lambda e, c=command: c())

    # ----- loading/indexing -----------------------------------------
    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Polish map", "*.mp"), ("Все файлы", "*.*")])
        if path and self._can_discard_changes(): self.open_path(path)

    def open_path(self, path):
        self.loading_cancel.clear(); self.progress.configure(value=0); self.progress.pack(side="left", fill="x", expand=True); self.cancel_button.pack(side="right")
        started = time.perf_counter(); self.status.set("Фоновая загрузка MP…")
        def progress(done, total): self.worker_queue.put(("progress", done, total))
        def work():
            try:
                document = MpDocument.load(path, progress, self.loading_cancel.is_set)
                index = SpatialIndex(); index.build(document.objects(), cancelled=self.loading_cancel.is_set)
                self.worker_queue.put(("loaded", document, index, time.perf_counter() - started))
            except Exception as exc: self.worker_queue.put(("error", exc))
        threading.Thread(target=work, daemon=True).start(); self.after(25, self._poll_worker)

    def _poll_worker(self):
        try:
            while True:
                event = self.worker_queue.get_nowait()
                if event[0] == "progress": self.progress.configure(maximum=max(1, event[2]), value=event[1]); self.status.set(f"Загрузка: {event[1]:,} / {event[2]:,} строк")
                elif event[0] == "loaded":
                    _, self.doc, self.index, elapsed = event; self.selected.clear(); self.undo_stack.clear(); self.redo_stack.clear(); self.progress.pack_forget(); self.cancel_button.pack_forget(); self.title(f"PolishMapAI — {self.doc.path.name}"); self.first_frame_pending=True; self.zoom_all(); self._metric("open", elapsed, f"objects={len(self.index.items)}"); self.status.set(f"Загружено {len(self.index.items):,} объектов за {elapsed:.2f} с"); self._update_commands(); return
                else:
                    self.progress.pack_forget(); self.cancel_button.pack_forget(); exc = event[1]; self.status.set(str(exc));
                    if not isinstance(exc, InterruptedError): messagebox.showerror("Ошибка открытия", str(exc))
                    return
        except queue.Empty: pass
        self.after(25, self._poll_worker)

    def add_mp(self):
        path = filedialog.askopenfilename(filetypes=[("Polish map", "*.mp")])
        if not path: return
        try:
            other = MpDocument.load(path); self.push_undo(); self.doc.sections.extend(other.sections); self.doc.dirty = True; self.rebuild_index(); self.render_viewport()
        except Exception as exc: messagebox.showerror("Добавление", str(exc))

    # ----- renderer/navigation --------------------------------------
    def visible_bbox(self, margin=0.0) -> BBox:
        lat0, lon0 = self.screen_to_world(-margin, self.canvas.winfo_height() + margin); lat1, lon1 = self.screen_to_world(self.canvas.winfo_width() + margin, -margin)
        return lon0, lat0, lon1, lat1

    def render_viewport(self):
        if self.render_after: self.after_cancel(self.render_after); self.render_after = None
        self.render_generation += 1
        generation = self.render_generation
        started = time.perf_counter(); self.canvas.delete("map"); self.canvas.delete("overlay")
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.view_vars["grid"].get():
            for x in range(0, width, 100): self.canvas.create_line(x, 0, x, height, fill="#dedbd0", tags=("map",))
            for y in range(0, height, 100): self.canvas.create_line(0, y, width, y, fill="#dedbd0", tags=("map",))
        candidates = self.index.query(self.visible_bbox(80)) if self.index.items else []
        candidates.sort(key=lambda item: 0 if item.section.name.upper() in {"POLYGON", "RGN80"} else 1)
        self.render_state = {
            "generation": generation, "started": started, "candidates": candidates,
            "position": 0, "primitives": 0, "reason": self.render_reason,
        }
        self.status.set(f"Отрисовка: 0 / {len(candidates):,}")
        self.after_idle(lambda: self._render_chunk(generation))

    def _render_chunk(self, generation):
        state = self.render_state
        if not state or generation != self.render_generation or state["generation"] != generation:
            return
        chunk_started = time.perf_counter(); candidates = state["candidates"]
        while state["position"] < len(candidates) and state["primitives"] < MAX_PRIMITIVES:
            item = candidates[state["position"]]; state["position"] += 1
            state["primitives"] += self._draw_object(item)
            if time.perf_counter() - chunk_started >= RENDER_BUDGET_SECONDS:
                self.status.set(f"Отрисовка: {state['position']:,} / {len(candidates):,}")
                self.after(1, lambda: self._render_chunk(generation))
                return
        limited = state["primitives"] >= MAX_PRIMITIVES and state["position"] < len(candidates)
        self._draw_overlays()
        elapsed = time.perf_counter() - state["started"]
        reason = "first_frame" if self.first_frame_pending else state["reason"]
        self.first_frame_pending = False
        self._metric(reason, elapsed, f"candidates={len(candidates)} primitives={state['primitives']}")
        self.last_render_stats = {"candidates":len(candidates),"primitives":state["primitives"],"elapsed_seconds":elapsed}
        self.render_reason = "viewport"; self.render_state = None
        suffix = f" — достигнут лимит {MAX_PRIMITIVES:,}, увеличьте масштаб" if limited else ""
        self.status.set(f"Вид: {len(candidates):,} кандидатов, {state['primitives']:,} примитивов, {elapsed*1000:.0f} мс{suffix}")

    def _draw_object(self, item):
        obj = item.section
        if not self._visible_at_level(obj, item): return 0
        object_tag = f"object-{id(obj)}"
        coords = obj.coordinates(self.level.get()); stride = self._generalization_stride(coords)
        if stride > 1 and len(coords) > 2:
            reduced = coords[::stride]; coords = reduced + ([coords[-1]] if coords[-1] != reduced[-1] else [])
        points = [self.world_to_screen(lat, lon) for lat, lon in coords]
        if not points: return 0
        primitives = 0; selected = obj in self.selected; kind = obj.name.upper()
        if kind in {"POI", "RGN10", "RGN20"}:
            x, y = points[0]; self.canvas.create_oval(x-4, y-4, x+4, y+4, fill="#5b6573", outline="#1769aa" if selected else "#30343a", width=3 if selected else 1, tags=("map",object_tag)); primitives += 1
        elif kind in {"POLYGON", "RGN80"} and len(points) >= 2:
            flat = [v for p in points for v in p]; fill = "" if self.view_vars["transparent_polygons"].get() else "#b9c5b3"; outline = "#1769aa" if selected else ("#6d7868" if self.view_vars["polygon_outlines"].get() else fill)
            self.canvas.create_polygon(*flat, fill=fill, outline=outline, width=3 if selected else 1, tags=("map",object_tag)); primitives += 1
        elif len(points) >= 2:
            flat = [v for p in points for v in p]; self.canvas.create_line(*flat, fill="#1769aa" if selected else "#60666d", width=4 if selected else 2, tags=("map",object_tag)); primitives += 1
        if self.view_vars["labels"].get() and obj.get("Label") and self.zoom >= .2:
            x, y = points[0]; self.canvas.create_text(x+5, y-7, text=obj.get("Label"), anchor="sw", fill="#202124", tags=("map",object_tag)); primitives += 1
        return primitives

    def _draw_overlays(self):
        if self.pending:
            points=[self.world_to_screen(*point) for point in self.pending]
            if len(points)>1:self.canvas.create_line(*[value for point in points for value in point],fill="#e67e22",dash=(4,2),width=2,tags=("overlay",))
            for x,y in points:self.canvas.create_oval(x-3,y-3,x+3,y+3,fill="#ffffff",outline="#e67e22",tags=("overlay",))
        if self.goto_marker:
            x, y = self.world_to_screen(*self.goto_marker); self.canvas.create_line(x-10, y, x+10, y, fill="#d12d2d", width=2, tags=("overlay",)); self.canvas.create_line(x, y-10, x, y+10, fill="#d12d2d", width=2, tags=("overlay",))
        if self.mode == "nodes" and len(self.selected) == 1:
            active = self._active_data_level(self.selected[0])
            for data_level, coords in self.selected[0].coordinate_groups():
                if data_level != active: continue
                for node_index, (lat, lon) in enumerate(coords):
                    x, y = self.world_to_screen(lat, lon)
                    self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="#ffffff", outline="#1769aa", tags=("overlay", f"node-{data_level}-{node_index}"))

    def _cancel_active_render(self):
        self.render_generation += 1; self.render_state = None

    def schedule_render(self, delay=80, reason="viewport"):
        self._cancel_active_render()
        if self.render_after: self.after_cancel(self.render_after)
        self.render_reason=reason
        self.render_after = self.after(delay, self.render_viewport)

    def _visible_at_level(self, obj, item):
        raw = obj.get("EndLevel") or obj.get("Levels")
        try:
            if raw and self.level.get() > int(raw.split(",")[0]): return False
        except ValueError: pass
        x0, y0 = self.world_to_screen(item.bbox[1], item.bbox[0]); x1, y1 = self.world_to_screen(item.bbox[3], item.bbox[2])
        pixels = max(abs(x1-x0), abs(y1-y0))
        return pixels >= (1.5 if obj.name.upper() not in {"POI", "RGN10", "RGN20"} else 0)

    def _generalization_stride(self, coords):
        if len(coords) < 500: return 1
        return max(1, min(64, int(len(coords) / max(250, self.canvas.winfo_width()))))

    def world_to_screen(self, lat, lon):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()); scale = 120 * self.zoom
        return w/2 + (float(lon)-self.center[1])*scale, h/2 - (float(lat)-self.center[0])*scale

    def screen_to_world(self, x, y):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height()); scale = 120*self.zoom
        return self.center[0]-(y-h/2)/scale, self.center[1]+(x-w/2)/scale

    def zoom_all(self):
        bounds = self.index.bounds
        if not bounds: self.center=[0,0]; self.zoom=1; self.render_viewport(); return
        self.center=[(bounds[1]+bounds[3])/2, (bounds[0]+bounds[2])/2]
        width=max(1,self.canvas.winfo_width()); height=max(1,self.canvas.winfo_height()); lon_span=max(bounds[2]-bounds[0],1e-8); lat_span=max(bounds[3]-bounds[1],1e-8)
        self.zoom=max(.001,min(1e6,min(width/(lon_span*144),height/(lat_span*144)))); self._sync_scale(); self.render_viewport()

    def change_zoom(self, factor, anchor=None):
        if anchor is None: anchor=(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2)
        before=self.screen_to_world(*anchor); self.zoom=max(.001,min(1e7,self.zoom*factor)); after=self.screen_to_world(*anchor); self.center[0]+=before[0]-after[0]; self.center[1]+=before[1]-after[1]; self._sync_scale(); self.schedule_render(reason="zoom")

    def on_wheel(self, event):
        if event.state & 0x0004:
            self.change_zoom(math.pow(1.15, event.delta/120), (event.x,event.y)); return "break"
        horizontal=bool(event.state & 0x0001); amount=-(event.delta/120)*max(35,self.canvas.winfo_height()*.08); dx=amount if horizontal else 0; dy=0 if horizontal else amount
        self._pan_pixels(dx,dy); self.schedule_render(90,"pan"); return "break"

    def _pan_pixels(self, dx, dy):
        self.canvas.move("map", -dx, -dy); scale=120*self.zoom; self.center[0]+=dy/scale; self.center[1]+=dx/scale

    def _on_resize(self, event):
        if self.resize_after: self.after_cancel(self.resize_after)
        self._cancel_active_render(); self.resize_after=self.after(100,self.render_viewport)

    # ----- interaction ----------------------------------------------
    def on_press(self,event):
        self.canvas.focus_set(); self.drag_start=(event.x,event.y,*self.center); self.drag_preview=(0,0)
        self._cancel_active_render()
        if self.mode=="pan": self.drag_kind="pan"; self.canvas.configure(cursor="fleur"); return
        if self.mode in {"POI","POLYLINE","POLYGON"}:
            self.pending.append(self.screen_to_world(event.x,event.y));
            if self.mode=="POI": self.finish_drawing()
            else:self.render_viewport()
            return
        if self.mode == "nodes":
            node = self._hit_node(event.x, event.y)
            self.drag_kind = "node" if node else None; self.drag_node = node
            return
        hit=self.hit_test(event.x,event.y)
        if hit:
            if event.state & 0x0004:
                self.selected = [x for x in self.selected if x is not hit] if hit in self.selected else [*self.selected,hit]
            elif event.state & 0x0001:
                if hit not in self.selected: self.selected.append(hit)
            elif hit not in self.selected: self.selected=[hit]
            self.drag_kind="objects"; self.refresh_properties(); self.render_viewport()
        else:
            self.drag_kind="box"; self.canvas.create_rectangle(event.x,event.y,event.x,event.y,outline="#1769aa",dash=(4,2),fill="#b8d8f0",stipple="gray25",tags=("selection-box","overlay"))

    def on_drag(self,event):
        if not self.drag_start:return
        x,y,lat,lon=self.drag_start; dx,dy=event.x-x,event.y-y
        if self.drag_kind=="pan": self.canvas.move("map",dx-self.drag_preview[0],dy-self.drag_preview[1]); self.drag_preview=(dx,dy)
        elif self.drag_kind=="box": self.canvas.coords("selection-box",x,y,event.x,event.y)
        elif self.drag_kind=="objects" and abs(dx)+abs(dy)>=DRAG_THRESHOLD:
            for obj in self.selected:self.canvas.move(f"object-{id(obj)}",dx-self.drag_preview[0],dy-self.drag_preview[1])
            self.drag_preview=(dx,dy)
        elif self.drag_kind=="node":
            self.canvas.move("overlay",dx-self.drag_preview[0],dy-self.drag_preview[1]);self.drag_preview=(dx,dy)

    def on_release(self,event):
        if not self.drag_start:return
        x,y,lat,lon=self.drag_start; dx,dy=event.x-x,event.y-y
        if self.drag_kind=="pan": self.center=[lat+dy/(120*self.zoom),lon-dx/(120*self.zoom)]; self.schedule_render(30,"pan")
        elif self.drag_kind=="box":
            self.canvas.delete("selection-box")
            if abs(dx)+abs(dy)<DRAG_THRESHOLD:
                if not(event.state&0x0005):self.selected=[]
            else:
                a=self.screen_to_world(x,y); b=self.screen_to_world(event.x,event.y); bbox=(min(a[1],b[1]),min(a[0],b[0]),max(a[1],b[1]),max(a[0],b[0])); found=[i.section for i in self.index.query(bbox) if intersects(i.bbox,bbox)]
                if event.state&0x0004:
                    for obj in found: self.selected.remove(obj) if obj in self.selected else self.selected.append(obj)
                elif event.state&0x0001:
                    self.selected=list(dict.fromkeys([*self.selected,*found]))
                else:self.selected=found
            self.refresh_properties();self.render_viewport()
        elif self.drag_kind=="objects" and abs(dx)+abs(dy)>=DRAG_THRESHOLD:
            self.push_undo(); dlat=Decimal(str(-dy/(120*self.zoom)));dlon=Decimal(str(dx/(120*self.zoom)))
            for obj in self.selected:obj.translate(dlat,dlon)
            self.doc.dirty=True;self.rebuild_index();self.render_viewport()
        elif self.drag_kind=="node" and abs(dx)+abs(dy)>=DRAG_THRESHOLD:
            self.push_undo();data_level,node_index=self.drag_node;new_lat,new_lon=self.screen_to_world(event.x,event.y)
            self.selected[0].move_node(data_level,node_index,Decimal(str(new_lat)),Decimal(str(new_lon)))
            self.doc.dirty=True;self.rebuild_index();self.render_viewport()
        self.drag_start=None;self.drag_kind=None;self.drag_preview=(0,0);self.canvas.configure(cursor="arrow" if self.mode=="select" else "hand2")

    def hit_test(self,x,y):
        lat,lon=self.screen_to_world(x,y); radius=8/(120*self.zoom); candidates=self.index.query((lon-radius,lat-radius,lon+radius,lat+radius)); ranked=[]
        for item in candidates:
            distance=self._screen_distance(item.section,x,y)
            if distance<=9:ranked.append((distance,item.section))
        ranked.sort(key=lambda p:p[0])
        if not ranked:
            self.last_hit_point=None;self.last_hit_ids=();self.hit_cycle=0;return None
        hit_ids=tuple(id(section) for _,section in ranked)
        same_point=self.last_hit_point and math.hypot(x-self.last_hit_point[0],y-self.last_hit_point[1])<=4
        if same_point and hit_ids==self.last_hit_ids:self.hit_cycle=(self.hit_cycle+1)%len(ranked)
        else:self.hit_cycle=0
        self.last_hit_point=(x,y);self.last_hit_ids=hit_ids
        return ranked[self.hit_cycle][1]

    def _screen_distance(self,obj,x,y):
        points=[self.world_to_screen(a,b) for a,b in obj.coordinates(self.level.get())]
        if not points:return math.inf
        if len(points)==1:return math.hypot(points[0][0]-x,points[0][1]-y)
        return min(self._segment_distance(x,y,*a,*b) for a,b in zip(points,points[1:]))

    @staticmethod
    def _segment_distance(px,py,x1,y1,x2,y2):
        dx,dy=x2-x1,y2-y1
        if dx==dy==0:return math.hypot(px-x1,py-y1)
        t=max(0,min(1,((px-x1)*dx+(py-y1)*dy)/(dx*dx+dy*dy)));return math.hypot(px-(x1+t*dx),py-(y1+t*dy))

    def cancel_interaction(self):
        if self.drag_start and self.drag_kind=="pan":self.canvas.move("map",-self.drag_preview[0],-self.drag_preview[1])
        elif self.drag_start and self.drag_kind=="objects":
            for obj in self.selected:self.canvas.move(f"object-{id(obj)}",-self.drag_preview[0],-self.drag_preview[1])
        elif self.drag_start and self.drag_kind=="node":self.canvas.move("overlay",-self.drag_preview[0],-self.drag_preview[1])
        self.drag_start=None;self.drag_kind=None;self.drag_preview=(0,0);self.pending=[];self.canvas.delete("selection-box");self.render_viewport()

    def on_double_click(self,event):
        if self.mode in {"POLYLINE","POLYGON"}:
            if len(self.pending)>=2 and self.pending[-1]==self.pending[-2]:self.pending.pop()
            self.finish_drawing()

    def on_motion(self,event):self.last_cursor_coordinate=self.screen_to_world(event.x,event.y)

    def _active_data_level(self,obj):
        groups=obj.coordinate_groups();eligible=[number for number,_ in groups if number<=self.level.get()]
        return max(eligible) if eligible else (groups[0][0] if groups else 0)

    def _hit_node(self,x,y):
        if len(self.selected)!=1:return None
        active=self._active_data_level(self.selected[0])
        for data_level,coords in self.selected[0].coordinate_groups():
            if data_level!=active:continue
            for node_index,(lat,lon) in enumerate(coords):
                px,py=self.world_to_screen(lat,lon)
                if math.hypot(px-x,py-y)<=8:return data_level,node_index
        return None

    # ----- context/location -----------------------------------------
    def on_context(self,event):
        self.context_coordinate=self.screen_to_world(event.x,event.y)
        menu=tk.Menu(self,tearoff=False);location=tk.Menu(menu,tearoff=False)
        location.add_command(label="Вставить здесь",command=self.paste_here,state="normal" if self.clipboard_objects else "disabled")
        templates=tk.Menu(location,tearoff=False);templates.add_command(label="Нет шаблонов",state="disabled");location.add_cascade(label="Вставить шаблон полигона",menu=templates,state="disabled");location.add_command(label="Удалить шаблон полигона…",state="disabled");location.add_separator();location.add_command(label="Копировать координаты",command=self.copy_context_coordinates);location.add_separator()
        browse=tk.Menu(location,tearoff=False);browse.add_command(label="Карты Google",command=lambda:self.browse_context("https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}"));browse.add_command(label="Bing Maps",command=lambda:self.browse_context("https://www.bing.com/maps?cp={lat}~{lon}&lvl={zoom}"));location.add_cascade(label="Обзор в",menu=browse)
        menu.add_cascade(label="Местоположение",menu=location);menu.tk_popup(event.x_root,event.y_root)

    def copy_context_coordinates(self):
        value=format_coordinates(*self.context_coordinate,self.view_options.get("coordinate_format","DD"));self.clipboard_clear();self.clipboard_append(value);self.status.set(f"Скопировано: {value}")

    def browse_context(self,template):
        lat,lon=self.context_coordinate;url=template.format(lat=f"{lat:.8f}",lon=f"{lon:.8f}",zoom=max(1,min(20,int(math.log2(max(self.zoom,1e-6)))+10)),scale=self.physical_scale());webbrowser.open(url)

    def paste_here(self):self._paste_at(*self.context_coordinate)

    # ----- document/editing ----------------------------------------
    def new_file(self):
        if not self._can_discard_changes():return
        self.doc=MpDocument([],[]);self.index.clear();self.selected=[];self.title("PolishMapAI — Без имени");self.render_viewport();self._update_commands()
    def close_file(self):self.new_file()
    def save_file(self):
        if self.doc.path is None:return self.save_as()
        try:self.doc.save();self.status.set("Сохранено");return True
        except Exception as exc:messagebox.showerror("Сохранение",str(exc));return False
    def save_as(self):
        path=filedialog.asksaveasfilename(defaultextension=".mp",filetypes=[("Polish map","*.mp")])
        if not path:return False
        try:self.doc.save(path);self.title(f"PolishMapAI — {Path(path).name}");self.status.set("Сохранено");return True
        except Exception as exc:messagebox.showerror("Сохранение",str(exc));return False
    def _can_discard_changes(self):
        if not self.doc.dirty:return True
        choice=messagebox.askyesnocancel("Несохранённые изменения","Сохранить изменения карты?")
        if choice is None:return False
        return self.save_file() if choice else True
    def request_exit(self):
        if self._can_discard_changes():self.destroy()
    def push_undo(self):self.undo_stack.append(self.doc.snapshot());self.redo_stack.clear();self._update_commands()
    def undo(self):
        if not self.undo_stack:return
        self.redo_stack.append(self.doc.snapshot());self.doc.restore(self.undo_stack.pop());self.selected=[];self.rebuild_index();self.refresh_properties();self.render_viewport();self._update_commands()
    def redo(self):
        if not self.redo_stack:return
        self.undo_stack.append(self.doc.snapshot());self.doc.restore(self.redo_stack.pop());self.selected=[];self.rebuild_index();self.refresh_properties();self.render_viewport();self._update_commands()
    def copy(self):self.clipboard_objects=[self._clone_section(x) for x in self.selected];self._update_commands()
    def cut(self):self.copy();self.delete_selected()
    def paste(self):
        if self.clipboard_objects:self._paste_at(*self.center)
    def _paste_at(self,lat,lon):
        if not self.clipboard_objects:return
        all_coords=[p for obj in self.clipboard_objects for p in obj.coordinates()]
        if not all_coords:return
        anchor_lat=sum(p[0] for p in all_coords)/len(all_coords);anchor_lon=sum(p[1] for p in all_coords)/len(all_coords);self.push_undo();new=[]
        for source in self.clipboard_objects:
            obj=self._clone_section(source);obj.translate(Decimal(str(lat))-anchor_lat,Decimal(str(lon))-anchor_lon);self.doc.sections.append(obj);new.append(obj)
        self.doc.dirty=True;self.selected=new;self.rebuild_index();self.refresh_properties();self.render_viewport()
    @staticmethod
    def _clone_section(section):
        import copy
        return copy.deepcopy(section)
    def delete_selected(self):
        if not self.selected:return
        self.push_undo()
        for obj in list(self.selected):self.doc.delete(obj)
        self.selected=[];self.rebuild_index();self.refresh_properties();self.render_viewport()
    def select_all(self,kind=None):
        def matches(obj):
            name=obj.name.upper()
            if kind is None:return True
            if kind=="POINT":return name in {"POI","RGN10","RGN20"}
            if kind=="LINE":return name in {"POLYLINE","RGN40"}
            if kind=="POLYGON":return name in {"POLYGON","RGN80"}
            return bool(obj.get("RoadID") or obj.get("RouteParam"))
        self.selected=[item.section for item in self.index.items if matches(item.section)];self.refresh_properties();self.render_viewport()
    def clear_selection(self):self.selected=[];self.refresh_properties();self.render_viewport()
    def invert_selection(self):
        chosen=set(id(x) for x in self.selected);self.selected=[x.section for x in self.index.items if id(x.section) not in chosen];self.refresh_properties();self.render_viewport()
    def rebuild_index(self):self.index.build(self.doc.objects())
    def set_mode(self,mode):self.mode=mode;self.pending=[];self.canvas.configure(cursor="hand2" if mode=="pan" else "crosshair" if mode in {"POI","POLYLINE","POLYGON"} else "arrow");self.status.set(f"Режим: {mode}");self.render_viewport()
    def finish_drawing(self):
        if not self.pending:return
        if self.mode=="POLYGON" and len(self.pending)>=3:self.pending.append(self.pending[0])
        if self.mode=="POLYLINE" and len(self.pending)<2:return
        if self.mode=="POLYGON" and len(self.pending)<4:return
        self.push_undo();obj=self.doc.add_object(self.mode,self.pending);self.index.insert(obj);self.selected=[obj];self.pending=[];self.set_mode("select");self.refresh_properties();self.render_viewport()
    def refresh_properties(self):
        self.prop_tree.delete(*self.prop_tree.get_children());self.selection_label.configure(text=f"Выбрано: {len(self.selected)}")
        if not self.selected:return
        common={k.strip():v for k,v,_ in self.selected[0].pairs()}
        for obj in self.selected[1:]:
            values={k.strip():v for k,v,_ in obj.pairs()};common={k:v for k,v in common.items() if values.get(k)==v}
        for key,value in common.items():self.prop_tree.insert("","end",text=key,values=(value,))
        self._update_commands()
    def edit_property(self,event):
        item=self.prop_tree.identify_row(event.y)
        if not item or not self.selected:return
        key=self.prop_tree.item(item,"text");old=self.prop_tree.item(item,"values")[0];value=simpledialog.askstring("Изменить свойство",key,initialvalue=old,parent=self)
        if value is not None:
            self.push_undo()
            for obj in self.selected:obj.set(key,value,self.doc.newline)
            self.doc.dirty=True
            if key.strip().lower() in {"nodeid","roadid"}:self.rebuild_index()
            self.refresh_properties();self.render_viewport()

    # ----- dialogs/commands ----------------------------------------
    def goto_coordinates(self):
        win=tk.Toplevel(self);win.title("Координаты");win.transient(self);win.grab_set();value=tk.StringVar(value=format_coordinates(*(self.last_cursor_coordinate or self.center)));valid=tk.StringVar(value="")
        ttk.Label(win,text="Координаты:").grid(row=0,column=0,padx=10,pady=10);entry=ttk.Entry(win,textvariable=value,width=48);entry.grid(row=0,column=1,padx=10,pady=10)
        ttk.Label(win,textvariable=valid,foreground="#315d31").grid(row=1,column=1,sticky="w",padx=10);ttk.Label(win,text="Допустимы DD, DDM и DMS, например: N55°37.076' E38°07.804'",wraplength=420).grid(row=2,column=0,columnspan=2,padx=10,pady=8)
        buttons=ttk.Frame(win);buttons.grid(row=3,column=0,columnspan=2,sticky="e",padx=10,pady=10);ok=ttk.Button(buttons,text="ОК",state="disabled");ok.pack(side="left",padx=4);ttk.Button(buttons,text="Отмена",command=win.destroy).pack(side="left")
        def validate(*_):
            try:lat,lon=parse_coordinates(value.get());valid.set(format_coordinates(lat,lon));ok.configure(state="normal")
            except ValueError as exc:valid.set(str(exc));ok.configure(state="disabled")
        def accept(*_):
            lat,lon=parse_coordinates(value.get());self.center=[lat,lon];self.goto_marker=(lat,lon);self.render_viewport();self.status.set(format_coordinates(lat,lon));win.destroy()
        value.trace_add("write",validate);ok.configure(command=accept);win.bind("<Return>",accept);win.bind("<Escape>",lambda e:win.destroy());entry.focus_set();entry.selection_range(0,"end");validate()
    def find_object(self):
        query=simpledialog.askstring("Найти","Label, NodeID, RoadID или свойство:",parent=self)
        if not query:return
        q=query.lower();found=[];seen=set()
        for obj in [*self.index.find_node_id(query),*self.index.find_road_id(query)]:
            if id(obj) not in seen:found.append(obj);seen.add(id(obj))
        for item in self.index.items:
            obj=item.section
            if id(obj) in seen:continue
            if q in obj.get("Label").lower() or q in obj.render().lower():found.append(obj);seen.add(id(obj))
        if not found:messagebox.showinfo("Найти","Совпадений нет");return
        self.selected=found[:100];bbox=section_bbox(found[0]);self.center=[(bbox[1]+bbox[3])/2,(bbox[0]+bbox[2])/2];self.refresh_properties();self.render_viewport();self.status.set(f"Найдено: {len(found)}")
    def map_properties(self):messagebox.showinfo("Свойства карты",f"Файл: {self.doc.path or 'Без имени'}\nОбъектов: {len(self.index.items):,}\nКодировка: Windows-1251\nИзменена: {'да' if self.doc.dirty else 'нет'}")
    def show_log(self):messagebox.showinfo("Журнал сообщений","\n".join(self.metrics[-100:]) or "Журнал пуст")
    def check_geometry(self):
        issues=geometry_issues(self.doc);messagebox.showinfo("Проверка геометрии","Ошибок нет" if not issues else "\n".join(issues[:100]))
    def import_shapefile(self):
        path=filedialog.askopenfilename(filetypes=[("ESRI Shapefile","*.shp")])
        if path:self.push_undo();count=import_objects(path,self.doc);self.rebuild_index();self.zoom_all();self.status.set(f"Импортировано: {count}")
    def export_shapefile(self):
        kind=simpledialog.askstring("Экспорт","Тип: POI, POLYLINE или POLYGON",initialvalue="POLYGON")
        if not kind:return
        path=filedialog.asksaveasfilename(defaultextension=".shp",filetypes=[("ESRI Shapefile","*.shp")])
        if path:export_objects(path,self.doc,kind.upper())
    def add_favorite(self):
        favorites=self.view_options.setdefault("favorites",[]);favorites.append({"center":self.center[:],"zoom":self.zoom});self._save_view_options();self.status.set("Текущий вид добавлен в избранное")
    def show_favorites(self):messagebox.showinfo("Избранное",f"Сохранено видов: {len(self.view_options.get('favorites',[]))}")
    def neural_info(self):messagebox.showinfo("Нейросеть","Настройка REST-провайдера доступна в следующих очередях. Пункт не выполняет скрытых сетевых запросов.")

    # ----- settings/helpers ----------------------------------------
    def _update_commands(self):
        # Tk menus remain responsive; state mirrors document/selection/history.
        for label,state in [("Отменить","normal" if self.undo_stack else "disabled"),("Вернуть","normal" if self.redo_stack else "disabled"),("Вырезать","normal" if self.selected else "disabled"),("Копировать","normal" if self.selected else "disabled"),("Вставить","normal" if self.clipboard_objects else "disabled"),("Удалить","normal" if self.selected else "disabled")]:
            try:self.edit_menu.entryconfigure(label,state=state)
            except tk.TclError:pass
    def _metric(self,name,elapsed,details=""):
        line=f"{time.strftime('%H:%M:%S')} {name}: {elapsed*1000:.1f} ms {details}";self.metrics.append(line);LOGGER.info(line)
    def _load_view_options(self):
        defaults={"grid":True,"labels":True,"label_outline":False,"polygon_outlines":True,"transparent_polygons":False,"road_classes":False,"addresses":False,"coverage":False,"coordinate_format":"DD","favorites":[]}
        try:
            path=Path(os.getenv("APPDATA",Path.home()))/"PolishMapAI"/"settings.json";defaults.update(json.loads(path.read_text("utf-8")))
        except Exception:pass
        return defaults
    def _save_view_options(self):
        for key,var in self.view_vars.items():self.view_options[key]=var.get()
        path=Path(os.getenv("APPDATA",Path.home()))/"PolishMapAI"/"settings.json";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(self.view_options,ensure_ascii=False,indent=2),"utf-8")
    def _view_changed(self):self._save_view_options();self.render_viewport()
    def physical_scale(self):return int(max(1,100_000/max(self.zoom,.001)))
    def _sync_scale(self):self.scale_text.set(self._format_scale(self.physical_scale()))
    def _scale_selected(self,event=None):
        value=self.scale_text.get().replace(" ","").lower();scale=float(value[:-2].replace(",","."))*(1000 if value.endswith("км") else 1);self.set_physical_scale(scale)
    def set_physical_scale(self,scale):self.zoom=100_000/max(1,scale);self._sync_scale();self.schedule_render()
    @staticmethod
    def _format_scale(scale):return f"{scale/1000:g} км".replace(".",",") if scale>=1000 else f"{scale:g} м"


def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(name)s %(message)s")
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "--smoke-test":
            _run_gui_smoke(Path(sys.argv[2]))
        else:
            Editor().mainloop()
    except Exception:
        # Windowed PyInstaller builds have no stderr. Keep a deterministic
        # startup diagnostic beside the executable for CI and users.
        if getattr(sys, "frozen", False):
            Path(sys.executable).with_name("PolishMapAI-startup-error.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
        raise


def _run_gui_smoke(path: Path):
    """Exercise load and progressive rendering in the packaged GUI."""
    app = Editor(); started = time.perf_counter(); deadline = started + 45
    heartbeat = {"last": started, "max_gap": 0.0, "count": 0, "error": ""}

    def finish(error=""):
        heartbeat["error"] = error
        report = {
            "ok": not error, "error": error, "objects": len(app.index.items),
            "elapsed_seconds": time.perf_counter() - started,
            "heartbeat_count": heartbeat["count"],
            "max_heartbeat_gap_ms": heartbeat["max_gap"] * 1000,
            "render": app.last_render_stats,
            "metrics": app.metrics,
        }
        report_path = Path(os.getenv("POLISHMAPAI_SMOKE_REPORT", "PolishMapAI-smoke.json"))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        app.after(1, app.destroy)

    def tick():
        now = time.perf_counter(); heartbeat["count"] += 1
        heartbeat["max_gap"] = max(heartbeat["max_gap"], now-heartbeat["last"]); heartbeat["last"] = now
        if now >= deadline: finish("Timed out while loading or rendering the map"); return
        if app.doc.path and not app.first_frame_pending and app.render_state is None:
            finish(); return
        app.after(25, tick)

    app.after(100, lambda: app.open_path(path))
    app.after(25, tick); app.mainloop()
    if heartbeat["error"]:
        raise RuntimeError(heartbeat["error"])
