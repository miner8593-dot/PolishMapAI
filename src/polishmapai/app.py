from __future__ import annotations

import json
import math
import tkinter as tk
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .ai import AiSettings, request_features
from .credentials import get_api_key, set_api_key
from .mp import MpDocument, MpSection, geometry_issues
from .shapefile_io import export_objects, import_objects


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PolishMapAI — untitled")
        self.geometry("1280x800")
        self.minsize(900, 560)
        self.doc = MpDocument([], [])
        self.selected: MpSection | None = None
        self.mode = "select"
        self.pending: list[tuple[float, float]] = []
        self.zoom = 1.0
        self.center = [0.0, 0.0]
        self.drag_start = None
        self.undo_stack = []
        self.redo_stack = []
        self.level = tk.IntVar(value=0)
        self.status = tk.StringVar(value="Ready")
        self.ai_settings = AiSettings()
        self.ai_candidates: list[dict] = []
        self.audit_log: list[dict] = []
        self._build_menu()
        self._build_ui()
        self._bind_keys()

    def _build_menu(self):
        bar = tk.Menu(self)
        file_menu = tk.Menu(bar, tearoff=False)
        for label, command, accelerator in [
            ("New", self.new_file, "Ctrl+N"), ("Open…", self.open_file, "Ctrl+O"),
            ("Save", self.save_file, "Ctrl+S"), ("Save As…", self.save_as, "Ctrl+Shift+S")]:
            file_menu.add_command(label=label, command=command, accelerator=accelerator)
        file_menu.add_separator()
        file_menu.add_command(label="Import Shapefile…", command=self.import_shapefile)
        file_menu.add_command(label="Export selected type…", command=self.export_shapefile)
        file_menu.add_separator(); file_menu.add_command(label="Exit", command=self.destroy)
        edit = tk.Menu(bar, tearoff=False)
        edit.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit.add_separator(); edit.add_command(label="Delete", command=self.delete_selected, accelerator="Del")
        edit.add_command(label="Find…", command=self.find_object, accelerator="Ctrl+F")
        view = tk.Menu(bar, tearoff=False)
        view.add_command(label="Zoom In", command=lambda: self.change_zoom(1.25), accelerator="+")
        view.add_command(label="Zoom Out", command=lambda: self.change_zoom(0.8), accelerator="-")
        view.add_command(label="Zoom All", command=self.zoom_all, accelerator="Home")
        tools = tk.Menu(bar, tearoff=False)
        tools.add_command(label="Select / Move", command=lambda: self.set_mode("select"))
        tools.add_command(label="Create POI", command=lambda: self.set_mode("POI"))
        tools.add_command(label="Create Polyline", command=lambda: self.set_mode("POLYLINE"))
        tools.add_command(label="Create Polygon", command=lambda: self.set_mode("POLYGON"))
        tools.add_separator(); tools.add_command(label="Close polygon", command=self.close_polygon)
        tools.add_command(label="Check geometry", command=self.check_geometry)
        neural = tk.Menu(bar, tearoff=False)
        neural.add_command(label="Settings…", command=self.ai_settings_dialog)
        neural.add_command(label="Analyze visible area…", command=self.ai_analyze)
        neural.add_command(label="Preview / accept…", command=self.ai_preview)
        neural.add_command(label="Audit log…", command=self.show_audit)
        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "PolishMapAI 0.1\nIndependent clean-room cartographic editor"))
        for label, menu in [("Файл", file_menu), ("Правка", edit), ("Вид", view), ("Инструменты", tools), ("Нейросеть", neural), ("Справка", help_menu)]:
            bar.add_cascade(label=label, menu=menu)
        self.config(menu=bar)

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=3); toolbar.pack(fill="x")
        for text, mode in [("↖ Select", "select"), ("● POI", "POI"), ("╱ Line", "POLYLINE"), ("▱ Polygon", "POLYGON"), ("✋ Pan", "pan")]:
            ttk.Button(toolbar, text=text, command=lambda m=mode: self.set_mode(m)).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.change_zoom(1.25)).pack(side="left")
        ttk.Button(toolbar, text="−", width=3, command=lambda: self.change_zoom(0.8)).pack(side="left")
        ttk.Label(toolbar, text=" Detail level:").pack(side="left")
        ttk.Spinbox(toolbar, from_=0, to=24, width=4, textvariable=self.level, command=self.redraw).pack(side="left")
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True)
        map_frame = ttk.Frame(pane); prop_frame = ttk.Frame(pane, padding=6)
        pane.add(map_frame, weight=4); pane.add(prop_frame, weight=1)
        self.canvas = tk.Canvas(map_frame, background="#f4f2e9", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self.on_click); self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<B1-Motion>", self.on_drag); self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", lambda e: self.change_zoom(1.2 if e.delta > 0 else 0.833))
        ttk.Label(prop_frame, text="Object properties", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.prop_tree = ttk.Treeview(prop_frame, columns=("value",), show="tree headings")
        self.prop_tree.heading("#0", text="Field"); self.prop_tree.heading("value", text="Value")
        self.prop_tree.column("#0", width=110); self.prop_tree.column("value", width=190)
        self.prop_tree.pack(fill="both", expand=True, pady=5)
        self.prop_tree.bind("<Double-1>", self.edit_property)
        ttk.Label(prop_frame, text="Double-click a value to edit. Unknown fields are preserved.", wraplength=280).pack(anchor="w")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=3).pack(fill="x")

    def _bind_keys(self):
        self.bind("<Control-o>", lambda e: self.open_file()); self.bind("<Control-s>", lambda e: self.save_file())
        self.bind("<Control-z>", lambda e: self.undo()); self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-f>", lambda e: self.find_object()); self.bind("<Delete>", lambda e: self.delete_selected())
        self.bind("<Escape>", lambda e: self.cancel_pending()); self.bind("<Home>", lambda e: self.zoom_all())

    def new_file(self):
        self.doc = MpDocument([], []); self.selected = None; self.redraw(); self.refresh_properties()

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Polish map", "*.mp"), ("All files", "*.*")])
        if not path: return
        try:
            self.doc = MpDocument.load(path); self.selected = None; self.title(f"PolishMapAI — {Path(path).name}")
            self.zoom_all(); self.status.set(f"Loaded {len(self.doc.objects())} objects — Windows-1251 lossless mode")
        except Exception as exc: messagebox.showerror("Open failed", str(exc))

    def save_file(self):
        if self.doc.path is None: return self.save_as()
        try: self.doc.save(); self.status.set("Saved")
        except Exception as exc: messagebox.showerror("Save failed", str(exc))

    def save_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".mp", filetypes=[("Polish map", "*.mp")])
        if path:
            self.doc.save(path); self.title(f"PolishMapAI — {Path(path).name}")

    def push_undo(self):
        self.undo_stack.append(self.doc.snapshot()); self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack: return
        self.redo_stack.append(self.doc.snapshot()); self.doc.restore(self.undo_stack.pop()); self.selected = None; self.redraw(); self.refresh_properties()

    def redo(self):
        if not self.redo_stack: return
        self.undo_stack.append(self.doc.snapshot()); self.doc.restore(self.redo_stack.pop()); self.selected = None; self.redraw(); self.refresh_properties()

    def set_mode(self, mode):
        self.mode = mode; self.pending.clear(); self.status.set(f"Mode: {mode}")

    def world_to_screen(self, lat, lon):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = 120 * self.zoom
        return w / 2 + (float(lon) - self.center[1]) * scale, h / 2 - (float(lat) - self.center[0]) * scale

    def screen_to_world(self, x, y):
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = 120 * self.zoom
        return self.center[0] - (y - h / 2) / scale, self.center[1] + (x - w / 2) / scale

    def redraw(self):
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        for x in range(0, w, 100): self.canvas.create_line(x, 0, x, h, fill="#dedbd0")
        for y in range(0, h, 100): self.canvas.create_line(0, y, w, y, fill="#dedbd0")
        for obj in self.doc.objects():
            end_level = obj.get("EndLevel") or obj.get("Levels")
            try:
                if end_level and self.level.get() > int(end_level.split(",")[0]): continue
            except ValueError: pass
            coords = obj.coordinates(); points = [self.world_to_screen(lat, lon) for lat, lon in coords]
            selected = obj is self.selected
            if obj.name.upper() in {"POI", "RGN10", "RGN20"} and points:
                x, y = points[0]; item = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill="#e9322e", outline="#1956a3" if selected else "#76110f", width=3 if selected else 1)
            elif obj.name.upper() in {"POLYGON", "RGN80"} and len(points) >= 2:
                flat = [v for pair in points for v in pair]; item = self.canvas.create_polygon(*flat, fill="#8dcf9a", stipple="gray50", outline="#1956a3" if selected else "#26783b", width=3 if selected else 1)
            elif len(points) >= 2:
                flat = [v for pair in points for v in pair]; item = self.canvas.create_line(*flat, fill="#1956a3" if selected else "#555", width=4 if selected else 2)
            else: continue
            self.canvas.tag_bind(item, "<Button-1>", lambda e, o=obj: self.select_object(o))
            if selected:
                for x, y in points: self.canvas.create_rectangle(x-3, y-3, x+3, y+3, fill="white", outline="#1956a3")
        if self.pending:
            pts = [self.world_to_screen(*p) for p in self.pending]
            if len(pts) > 1: self.canvas.create_line(*[v for p in pts for v in p], fill="#e67e22", dash=(4, 2), width=2)

    def select_object(self, obj):
        self.selected = obj; self.refresh_properties(); self.redraw(); self.status.set(obj.get("Label") or obj.name)

    def on_click(self, event):
        if self.mode in {"POI", "POLYLINE", "POLYGON"}:
            point = self.screen_to_world(event.x, event.y); self.pending.append(point)
            if self.mode == "POI": self.finish_drawing()
            else: self.redraw()
        elif self.mode == "pan": self.drag_start = (event.x, event.y, *self.center)
        else: self.drag_start = (event.x, event.y)

    def on_double_click(self, event):
        if self.mode in {"POLYLINE", "POLYGON"}: self.finish_drawing()

    def on_drag(self, event):
        if self.mode == "pan" and self.drag_start:
            x, y, lat, lon = self.drag_start; scale = 120 * self.zoom
            self.center = [lat + (event.y-y)/scale, lon - (event.x-x)/scale]; self.redraw()

    def on_release(self, event):
        if self.mode == "select" and self.selected and self.drag_start:
            dx, dy = event.x-self.drag_start[0], event.y-self.drag_start[1]
            if abs(dx)+abs(dy) > 3:
                self.push_undo(); scale = 120*self.zoom
                coords = [(float(a)-dy/scale, float(b)+dx/scale) for a,b in self.selected.coordinates()]
                self.selected.set("Data0", ",".join(f"({a:.8f},{b:.8f})" for a,b in coords), self.doc.newline)
                self.doc.dirty = True; self.redraw()
        self.drag_start = None

    def finish_drawing(self):
        if not self.pending: return
        if self.mode == "POLYGON" and len(self.pending) >= 3 and self.pending[0] != self.pending[-1]: self.pending.append(self.pending[0])
        if self.mode != "POI" and len(self.pending) < 2: return
        self.push_undo(); self.selected = self.doc.add_object(self.mode, self.pending); self.pending = []; self.mode = "select"; self.refresh_properties(); self.redraw()

    def cancel_pending(self): self.pending.clear(); self.mode = "select"; self.redraw()

    def close_polygon(self):
        if self.selected and self.selected.name.upper() in {"POLYGON", "RGN80"}:
            coords = self.selected.coordinates()
            if coords and coords[0] != coords[-1]:
                self.push_undo(); coords.append(coords[0]); self.selected.set("Data0", ",".join(f"({a},{b})" for a,b in coords), self.doc.newline); self.doc.dirty=True; self.redraw()

    def delete_selected(self):
        if self.selected: self.push_undo(); self.doc.delete(self.selected); self.selected=None; self.refresh_properties(); self.redraw()

    def refresh_properties(self):
        self.prop_tree.delete(*self.prop_tree.get_children())
        if not self.selected: return
        shown = set()
        preferred = ["Type", "Label", "Levels", "EndLevel", "CityName", "StreetDesc", "HouseNumber", "RouteParam"]
        pairs = self.selected.pairs()
        for key in preferred:
            value = self.selected.get(key)
            self.prop_tree.insert("", "end", iid=f"p:{key}", text=key, values=(value,)); shown.add(key.lower())
        for key, value, index in pairs:
            if key.strip().lower() not in shown:
                self.prop_tree.insert("", "end", iid=f"i:{index}", text=key, values=(value,))

    def edit_property(self, event):
        item = self.prop_tree.identify_row(event.y)
        if not item or not self.selected: return
        key = self.prop_tree.item(item, "text"); old = self.prop_tree.item(item, "values")[0]
        value = simpledialog.askstring("Edit property", key, initialvalue=old, parent=self)
        if value is not None:
            self.push_undo(); self.selected.set(key, value, self.doc.newline); self.doc.dirty=True; self.refresh_properties(); self.redraw()

    def change_zoom(self, factor): self.zoom = min(1e6, max(0.01, self.zoom*factor)); self.redraw(); self.status.set(f"Zoom {self.zoom:.2f}x")

    def zoom_all(self):
        coords = [p for obj in self.doc.objects() for p in obj.coordinates()]
        if not coords: self.center=[0,0]; self.zoom=1; self.redraw(); return
        lats=[float(p[0]) for p in coords]; lons=[float(p[1]) for p in coords]
        self.center=[(min(lats)+max(lats))/2,(min(lons)+max(lons))/2]
        span=max(max(lats)-min(lats),max(lons)-min(lons),1e-5); self.zoom=max(.01,5/span); self.redraw()

    def find_object(self):
        query = simpledialog.askstring("Find", "Label, type or property text:", parent=self)
        if not query: return
        q=query.lower()
        for obj in self.doc.objects():
            if q in obj.render().lower(): self.select_object(obj); return
        messagebox.showinfo("Find", "No matching object")

    def check_geometry(self):
        issues=geometry_issues(self.doc); messagebox.showinfo("Geometry check", "No issues found." if not issues else "\n".join(issues[:100]))

    def import_shapefile(self):
        path=filedialog.askopenfilename(filetypes=[("ESRI Shapefile","*.shp")])
        if path:
            try: self.push_undo(); count=import_objects(path,self.doc); self.zoom_all(); messagebox.showinfo("Import",f"Imported {count} objects")
            except Exception as exc: messagebox.showerror("Import failed",str(exc))

    def export_shapefile(self):
        kind=simpledialog.askstring("Export","Object type: POI, POLYLINE or POLYGON",initialvalue="POLYGON")
        if not kind: return
        path=filedialog.asksaveasfilename(defaultextension=".shp",filetypes=[("ESRI Shapefile","*.shp")])
        if path:
            try: export_objects(path,self.doc,kind.upper())
            except Exception as exc: messagebox.showerror("Export failed",str(exc))

    def ai_settings_dialog(self):
        win=tk.Toplevel(self); win.title("Neural Network settings"); win.transient(self); win.grab_set()
        values={"Base URL":tk.StringVar(value=self.ai_settings.base_url),"Model":tk.StringVar(value=self.ai_settings.model),"Timeout":tk.StringVar(value=str(self.ai_settings.timeout)),"API key":tk.StringVar(value=get_api_key())}
        for row,(label,var) in enumerate(values.items()): ttk.Label(win,text=label).grid(row=row,column=0,sticky="w",padx=8,pady=5); ttk.Entry(win,textvariable=var,width=60,show="*" if label=="API key" else "").grid(row=row,column=1,padx=8,pady=5)
        ttk.Label(win,text="System instruction").grid(row=4,column=0,sticky="nw",padx=8,pady=5); prompt=tk.Text(win,width=60,height=6); prompt.insert("1.0",self.ai_settings.system_prompt); prompt.grid(row=4,column=1,padx=8,pady=5)
        def save():
            self.ai_settings=AiSettings(values["Base URL"].get(),values["Model"].get(),int(values["Timeout"].get()),prompt.get("1.0","end").strip()); set_api_key(values["API key"].get()); win.destroy()
        ttk.Button(win,text="Save",command=save).grid(row=5,column=1,sticky="e",padx=8,pady=8)

    def ai_analyze(self):
        task=simpledialog.askstring("Neural Network","Describe objects to recognize in the visible area:",parent=self)
        if not task:return
        context={"bbox":self.visible_bbox(),"objects":[{"type":o.name,"properties":dict((k,v) for k,v,_ in o.pairs()),"coordinates":[[float(b),float(a)] for a,b in o.coordinates()]} for o in self.doc.objects()]}
        try:
            geo,audit=request_features(self.ai_settings,get_api_key(),task,context); self.ai_candidates=geo["features"]; self.audit_log.append(audit); self.ai_preview()
        except Exception as exc: messagebox.showerror("AI request failed",str(exc))

    def visible_bbox(self):
        a=self.screen_to_world(0,self.canvas.winfo_height()); b=self.screen_to_world(self.canvas.winfo_width(),0); return [a[1],a[0],b[1],b[0]]

    def ai_preview(self):
        if not self.ai_candidates: messagebox.showinfo("AI preview","No proposed objects"); return
        win=tk.Toplevel(self); win.title("AI proposed objects")
        tree=ttk.Treeview(win,columns=("kind","label","confidence"),show="headings",selectmode="extended")
        for col in ("kind","label","confidence"): tree.heading(col,text=col.title())
        for i,f in enumerate(self.ai_candidates): tree.insert("","end",iid=str(i),values=(f["geometry"]["type"],f.get("properties",{}).get("label",""),f.get("properties",{}).get("confidence",0)))
        tree.pack(fill="both",expand=True,padx=8,pady=8)
        def accept():
            self.push_undo()
            for iid in tree.selection():
                f=self.ai_candidates[int(iid)]; g=f["geometry"]; p=f.get("properties",{}); coords=g["coordinates"]
                if g["type"]=="Point": kind="POI"; points=[(coords[1],coords[0])]
                elif g["type"]=="LineString": kind="POLYLINE"; points=[(x[1],x[0]) for x in coords]
                else: kind="POLYGON"; points=[(x[1],x[0]) for x in coords[0]]
                self.doc.add_object(kind,points,Type=str(p.get("mp_type","0x0")),Label=str(p.get("label","")),AIConfidence=str(p.get("confidence",0)))
            self.audit_log.append({"action":"accepted","indexes":list(tree.selection())}); self.redraw(); win.destroy()
        ttk.Button(win,text="Accept selected",command=accept).pack(side="left",padx=8,pady=8); ttk.Button(win,text="Reject / close",command=win.destroy).pack(side="right",padx=8,pady=8)

    def show_audit(self): messagebox.showinfo("AI audit log",json.dumps(self.audit_log,ensure_ascii=False,indent=2) or "No entries")


def main():
    Editor().mainloop()
