#!/usr/bin/env python3
"""
Minor Designer - draw what your ComputerCraft turtle should dig.

Run:  python designer.py
Needs only Python 3 (tkinter comes with it on Windows and Mac).

How the grid works
  * You look DOWN at one layer at a time. Layer 1 is the bottom.
  * The top of the grid is the direction the turtle FACES.
  * Light squares get dug. Dark squares are left alone.
  * Orange squares get dug AND get a torch on the floor.
  * The green "S" square is where the turtle starts. The brown "C" square
    behind it is where the chest goes.

Save writes designs/<name>.txt next to this script. "Save + Upload" also
runs git add / commit / push, so on the turtle you can then just type:
    minor <name>
"""

import os
import subprocess
import sys
import base64
import html as htmllib
import pathlib
import shutil
import webbrowser
import json
import ssl
import urllib.error
import urllib.request
import tkinter as tk
from collections import deque
from tkinter import filedialog, messagebox, ttk

MAX = 64
KEEP, DIG, TORCH, WATER, TRAP = 0, 1, 2, 3, 4  # WATER/TRAP: dug, then placed at the end
HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(HERE, "designs")
SETTINGS_FILE = os.path.join(HERE, "minor_settings.json")
TABS_DIR = os.path.join(DESIGN_DIR, "_tabs")   # the 5 auto-saved tabs live here
TAB_COUNT = 5
DEFAULT_SETTINGS = {"repo": "yetimafia/Minor", "branch": "main", "token": ""}
UPDATE_REPO = "yetimafia/Minor"  # where the designer and minor.lua live


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


def github(method, url, token, body=None):
    """Tiny GitHub API helper. Returns (status, json)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "minor-designer"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        ctx = ssl.create_default_context()
        try:
            import certifi  # helps on some Macs
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}

def open_in_chrome(url):
    """Open url in Google Chrome if we can find it. Returns True on success."""
    candidates = []
    if os.name == "nt":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for exe in candidates:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe, url], close_fds=True)
                return True
            except OSError:
                pass
    return False


COLORS = {
    "start": "#3fbf5a",
    "chest": "#8a5a2b",
    "line": "#1e1f23",
}

# tile looks: (base, highlight, shadow)
STYLE = {
    DIG:     ("#e6cf98", "#fff3d2", "#b38f52"),   # dug - warm sandy tile
    WATER:   ("#3f7fd6", "#7fb0f0", "#2a5aa0"),   # water bucket goes here
    TRAP:    ("#e6cf98", "#fff3d2", "#b38f52"),   # trapdoor goes here (icon drawn on top)
    TORCH:   ("#efd492", "#fff6d8", "#b8904c"),
    KEEP:    ("#3e4046", "#4b4e55", "#303237"),   # left alone - dark stone
    "below": ("#3c5779", "#4d6a90", "#2e4460"),   # dug on the layer below (blue)
    "above": ("#7a4545", "#935656", "#5e3434"),   # dug on the layer above (red)
}


def shade(color, amount):
    """Lighten (+) or darken (-) a #rrggbb colour."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (max(0, min(255, v + amount)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def blend(a, b, t):
    """Mix colour a toward colour b by t (0..1)."""
    ra, ga, ba = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    rb, gb, bb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t), round(ba + (bb - ba) * t))


def jitter(x, y, z):
    """Small fixed per-block colour variation so tiles look textured."""
    h = (x * 73856093) ^ (z * 19349663) ^ (y * 83492791)
    return (h % 7 - 3) * 4


class Design:
    def __init__(self, length=16, width=16, height=6):
        self.L, self.W, self.H = length, width, height
        self.grid = [[[KEEP] * width for _ in range(length)] for _ in range(height)]
        self.start = (0, 0, 0)  # x (forward), y (up), z (right)
        self.open_traps = True  # turtle clicks trapdoors open after placing them

    def resize(self, length, width, height):
        old = self.grid
        new = [[[KEEP] * width for _ in range(length)] for _ in range(height)]
        for y in range(min(height, self.H)):
            for x in range(min(length, self.L)):
                for z in range(min(width, self.W)):
                    new[y][x][z] = old[y][x][z]
        self.L, self.W, self.H, self.grid = length, width, height, new
        sx, sy, sz = self.start
        self.start = (min(sx, length - 1), min(sy, height - 1), min(sz, width - 1))

    def water_flow(self):
        """Where the water buckets will end up flowing, Minecraft style.

        Returns {(x, y, z): (level, falling)} for every block water reaches,
        not counting the bucket spots themselves. level 1..7 = how far from
        the source (7 is the thin edge), falling = a full column pouring down.
        Assumes everything outside the dug area is solid rock, closed
        trapdoors block water, and the turtle is parked on its start block.
        """
        import heapq
        L, W, H = self.L, self.W, self.H
        sx, sy, sz = self.start
        grid = self.grid

        def open_(x, y, z):
            if not (0 <= x < L and 0 <= y < H and 0 <= z < W):
                return False
            if (x, y, z) == (sx, sy, sz) or (x, y, z) == (sx - 1, sy, sz):
                return False  # turtle parks here / chest
            return grid[y][x][z] not in (KEEP, TRAP)

        def hole_below(x, y, z):
            return open_(x, y - 1, z)

        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))

        def slope_distance(x, y, z, came_from):
            """Steps (1-4) to the nearest drop going this way, or None."""
            seen = {(x, z), came_from}
            frontier = [(x, z)]
            for dist in range(1, 5):
                nxt = []
                for (cx, cz) in frontier:
                    if hole_below(cx, y, cz):
                        return dist
                    for dx, dz in dirs:
                        n = (cx + dx, cz + dz)
                        if n not in seen and open_(n[0], y, n[1]):
                            seen.add(n)
                            nxt.append(n)
                frontier = nxt
                if not frontier:
                    break
            return None

        level, falling, heap = {}, set(), []
        sources = set()
        for y in range(H):
            for x in range(L):
                for z in range(W):
                    if grid[y][x][z] == WATER and open_(x, y, z):
                        sources.add((x, y, z))
                        level[(x, y, z)] = 0
                        heap.append((0, x, y, z))
        heapq.heapify(heap)
        while heap:
            l, x, y, z = heapq.heappop(heap)
            if level.get((x, y, z), 99) < l:
                continue
            if open_(x, y - 1, z):  # water pours straight down first
                b = (x, y - 1, z)
                if level.get(b, 99) > 0:
                    level[b] = 0
                    falling.add(b)
                    heapq.heappush(heap, (0, x, y - 1, z))
                continue
            if l >= 7:
                continue
            # flows only toward the closest drop within 4 blocks, if there is one
            options = []
            for dx, dz in dirs:
                nx, nz = x + dx, z + dz
                if open_(nx, y, nz):
                    options.append((slope_distance(nx, y, nz, (x, z)), nx, nz))
            dists = [o[0] for o in options if o[0] is not None]
            best = min(dists) if dists else None
            for dist, nx, nz in options:
                if best is not None and dist != best:
                    continue
                if level.get((nx, y, nz), 99) > l + 1:
                    level[(nx, y, nz)] = l + 1
                    heapq.heappush(heap, (l + 1, nx, y, nz))
        return {c: (lv, c in falling) for c, lv in level.items() if c not in sources}

    def count_items(self):
        water = traps = 0
        for layer in self.grid:
            for row in layer:
                for v in row:
                    if v == WATER:
                        water += 1
                    elif v == TRAP:
                        traps += 1
        return water, traps

    def count(self):
        dig = torches = 0
        for layer in self.grid:
            for row in layer:
                for v in row:
                    if v:
                        dig += 1
                    if v == TORCH:
                        torches += 1
        return dig, torches

    def unreachable(self):
        """How many dig squares can't be reached from the start without
        tunnelling through kept blocks."""
        sx, sy, sz = self.start
        seen = {(sx, sy, sz)}
        q = deque([(sx, sy, sz)])
        while q:
            x, y, z = q.popleft()
            for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                nx, ny, nz = x + dx, y + dy, z + dz
                if (0 <= nx < self.L and 0 <= ny < self.H and 0 <= nz < self.W
                        and (nx, ny, nz) not in seen and self.grid[ny][nx][nz]):
                    seen.add((nx, ny, nz))
                    q.append((nx, ny, nz))
        dig, _ = self.count()
        reached = len(seen) - (0 if self.grid[sy][sx][sz] else 1)
        return dig - reached

    # ---- file format -------------------------------------------------
    def to_text(self):
        out = ["minor-design 1",
               f"size {self.L} {self.W} {self.H}",
               "start {} {} {}".format(*self.start)]
        if self.open_traps:
            out.append("trapdoors open")
        chars = {KEEP: ".", DIG: "#", TORCH: "T", WATER: "W", TRAP: "D"}
        for y in range(self.H):
            out.append(f"layer {y}")
            for x in range(self.L):
                row = self.grid[y][x]
                parts, i = [], 0
                while i < self.W:
                    j = i
                    while j < self.W and row[j] == row[i]:
                        j += 1
                    parts.append(f"{j - i}{chars[row[i]]}")
                    i = j
                out.append("".join(parts))
        return "\n".join(out) + "\n"

    @classmethod
    def from_text(cls, text):
        import re
        d = None
        y, x = -1, 0
        values = {".": KEEP, "#": DIG, "T": TORCH, "W": WATER, "D": TRAP}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("size "):
                L, W, H = map(int, line.split()[1:4])
                d = cls(L, W, H)
            elif line.startswith("start ") and d:
                sx, sy, sz = map(int, line.split()[1:4])
                d.start = (sx, sy, sz)
                d.open_traps = False  # only on if the file says so
            elif line.startswith("trapdoors open") and d:
                d.open_traps = True
            elif line.startswith("layer ") and d:
                y, x = int(line.split()[1]), 0
            elif d and y >= 0 and x < d.L and line:
                z = 0
                for count, ch in re.findall(r"(\d+)([.#TWD])", line):
                    for _ in range(int(count)):
                        if z < d.W:
                            d.grid[y][x][z] = values[ch]
                            z += 1
                x += 1
        if d is None:
            raise ValueError("Not a minor design file")
        return d


class App:
    def __init__(self, root):
        self.root = root
        root.title("Minor Designer")
        self.d = Design()
        self.layer = 0
        self.cell = 12
        self.rects = {}
        self.drag_start = None
        self.drag_rect = None
        self.history = []

        self.name = tk.StringVar(value="myroom")
        self.vL = tk.IntVar(value=self.d.L)
        self.vW = tk.IntVar(value=self.d.W)
        self.vH = tk.IntVar(value=self.d.H)
        self.tool = tk.StringVar(value="dig")
        self.spacing = tk.IntVar(value=8)
        self.ghost = tk.StringVar(value="below")
        self.show_flow = tk.BooleanVar(value=True)
        self.flow = {}
        self.settings = load_settings()
        self.uploaded = {}  # design name -> commit sha of last upload
        self.command = tk.StringVar(value="")

        # 5 tabs, each its own design, saved automatically
        self.slots = [None] * TAB_COUNT
        self.cur_slot = 0
        self.slot_var = tk.IntVar(value=0)
        self.dirty = False
        self.load_tabs()

        self.build_ui()
        self.rebuild_grid()
        self.update_tab_labels()
        self.name.trace_add("write", lambda *a: self.on_name_change())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(2000, self.autosave_tick)

    # ---- layout --------------------------------------------------------
    def build_ui(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Name").pack(side="left")
        ttk.Entry(top, textvariable=self.name, width=14).pack(side="left", padx=(2, 12))
        for label, var in (("Length (forward)", self.vL), ("Width (right)", self.vW), ("Height", self.vH)):
            ttk.Label(top, text=label).pack(side="left")
            ttk.Spinbox(top, from_=1, to=MAX, textvariable=var, width=4).pack(side="left", padx=(2, 8))
        ttk.Button(top, text="Apply size", command=self.apply_size).pack(side="left")
        ttk.Button(top, text="⟳ Update designer", command=self.update_designer).pack(side="right")
        ttk.Button(top, text="3D view", command=self.view_3d).pack(side="right", padx=6)

        tabs = ttk.Frame(self.root, padding=(6, 0, 6, 0))
        tabs.pack(fill="x")
        ttk.Label(tabs, text="Tabs:").pack(side="left", padx=(0, 4))
        self.tab_buttons = []
        for i in range(TAB_COUNT):
            b = tk.Radiobutton(tabs, text=str(i + 1), variable=self.slot_var, value=i, indicatoron=False,
                               command=self.switch_tab, width=15, padx=6, pady=3, selectcolor="#e6cf98",
                               anchor="w")
            b.pack(side="left", padx=2)
            self.tab_buttons.append(b)
        ttk.Button(tabs, text="New in this tab", command=self.new_in_tab).pack(side="left", padx=(8, 0))
        self.autosave_label = ttk.Label(tabs, text="", foreground="#3a7")
        self.autosave_label.pack(side="right")

        body = ttk.Frame(self.root, padding=6)
        body.pack(fill="both", expand=True)

        side_a = ttk.Frame(body)
        side_a.pack(side="left", fill="y", padx=(0, 6))
        side_b = ttk.Frame(body)
        side_b.pack(side="left", fill="y", padx=(0, 8))

        lay = ttk.LabelFrame(side_a, text="Layer", padding=6)
        lay.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(lay)
        row.pack()
        ttk.Button(row, text="▼", width=3, command=lambda: self.change_layer(-1)).pack(side="left")
        self.layer_label = ttk.Label(row, text="", width=10, anchor="center")
        self.layer_label.pack(side="left")
        ttk.Button(row, text="▲", width=3, command=lambda: self.change_layer(1)).pack(side="left")
        ttk.Label(lay, text="Show neighbour layer:").pack(anchor="w", pady=(6, 0))
        gr = ttk.Frame(lay)
        gr.pack(anchor="w")
        for value, text in (("off", "Off"), ("below", "Below"), ("above", "Above")):
            ttk.Radiobutton(gr, text=text, value=value, variable=self.ghost,
                            command=self.redraw).pack(side="left")
        self.ghost_hint = ttk.Label(lay, text="", foreground="#777")
        self.ghost_hint.pack(anchor="w")
        ttk.Label(lay, text="(G key switches)", foreground="#999").pack(anchor="w")
        ttk.Checkbutton(lay, text="Show water flow", variable=self.show_flow,
                        command=self.redraw).pack(anchor="w", pady=(4, 0))

        tools = ttk.LabelFrame(side_a, text="Tool (left mouse)", padding=6)
        tools.pack(fill="x", pady=(0, 6))
        for value, text in (("dig", "Dig pen"), ("keep", "Keep pen (eraser)"),
                            ("torch", "Torch pen"), ("trap", "Trapdoor pen (placed last)"),
                            ("water", "Water bucket pen (placed last)"), ("rect", "Dig rectangle"),
                            ("rectkeep", "Keep rectangle"), ("start", "Set turtle start")):
            ttk.Radiobutton(tools, text=text, value=value, variable=self.tool).pack(anchor="w")
        ttk.Label(tools, text="Right mouse = eraser", foreground="#777").pack(anchor="w", pady=(4, 0))

        lay_ops = ttk.LabelFrame(side_a, text="This layer", padding=6)
        lay_ops.pack(fill="x", pady=(0, 6))
        ttk.Button(lay_ops, text="Fill layer", command=lambda: self.fill_layer(DIG)).pack(fill="x")
        ttk.Button(lay_ops, text="Clear layer", command=lambda: self.fill_layer(KEEP)).pack(fill="x")
        ttk.Button(lay_ops, text="Copy to layer above", command=self.copy_up).pack(fill="x")
        ttk.Button(lay_ops, text="Copy to ALL layers above", command=self.copy_all_up).pack(fill="x")

        shapes = ttk.LabelFrame(side_b, text="Shapes", padding=6)
        shapes.pack(fill="x", pady=(0, 6))
        ttk.Button(shapes, text="★ Shape through layers...", command=self.layer_shape_dialog).pack(fill="x", pady=(0, 4))
        ttk.Label(shapes, text="Whole design:", foreground="#777").pack(anchor="w")
        for text, fn in (("Box (fill all)", self.shape_box), ("Sphere", self.shape_sphere),
                         ("Dome", self.shape_dome), ("Cylinder", self.shape_cylinder),
                         ("Tunnel (arch)", self.shape_arch), ("Clear all", self.shape_clear)):
            ttk.Button(shapes, text=text, command=fn).pack(fill="x")

        tor = ttk.LabelFrame(side_b, text="Torches", padding=6)
        tor.pack(fill="x", pady=(0, 6))
        r = ttk.Frame(tor)
        r.pack(fill="x")
        ttk.Label(r, text="Every").pack(side="left")
        ttk.Spinbox(r, from_=2, to=32, textvariable=self.spacing, width=4).pack(side="left", padx=3)
        ttk.Label(r, text="blocks").pack(side="left")
        ttk.Button(tor, text="Auto place torches", command=self.auto_torches).pack(fill="x", pady=(4, 0))
        ttk.Button(tor, text="Remove all torches", command=self.clear_torches).pack(fill="x")

        trp = ttk.LabelFrame(side_b, text="Trapdoors", padding=6)
        trp.pack(fill="x", pady=(0, 6))
        self.open_traps = tk.BooleanVar(value=True)
        ttk.Checkbutton(trp, text="Open them after placing", variable=self.open_traps,
                        command=self.set_open_traps).pack(anchor="w")
        ttk.Label(trp, text="Needs 1 stick in the turtle and\nthe datapack (see README)",
                  foreground="#777", justify="left").pack(anchor="w")

        ttk.Button(side_b, text="Undo  (Ctrl+Z)", command=self.undo).pack(fill="x", pady=(0, 6))

        tp = ttk.LabelFrame(side_a, text="Turtle start (drag the S)", padding=6)
        tp.pack(fill="x", pady=(0, 6))
        pad = ttk.Frame(tp)
        pad.pack()
        arrows = (("▲", 0, 1, (1, 0, 0)), ("◀", 1, 0, (0, 0, -1)), ("▶", 1, 2, (0, 0, 1)),
                  ("▼", 2, 1, (-1, 0, 0)))
        for text, r, c, delta in arrows:
            ttk.Button(pad, text=text, width=3,
                       command=lambda d=delta: self.move_start(*d)).grid(row=r, column=c)
        ttk.Button(pad, text="Up", width=6, command=lambda: self.move_start(0, 1, 0)).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(pad, text="Down", width=6, command=lambda: self.move_start(0, -1, 0)).grid(row=2, column=3, padx=(8, 0))
        self.start_label = ttk.Label(tp, text="", foreground="#777")
        self.start_label.pack(pady=(4, 0))
        ttk.Button(tp, text="Go to turtle's layer", command=self.goto_start_layer).pack(fill="x")

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="▲ turtle faces this way ▲", foreground="#777").pack()
        self.canvas = tk.Canvas(right, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", lambda e: self.on_press(e, False))
        self.canvas.bind("<B1-Motion>", lambda e: self.on_drag(e, False))
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.on_release(e, False))
        self.canvas.bind("<Button-3>", lambda e: self.on_press(e, True))
        self.canvas.bind("<B3-Motion>", lambda e: self.on_drag(e, True))
        self.canvas.bind("<ButtonRelease-3>", lambda e: self.on_release(e, True))
        self.canvas.bind("<Button-2>", lambda e: self.on_press(e, True))  # Mac right-click
        self.canvas.bind("<B2-Motion>", lambda e: self.on_drag(e, True))
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-d>", lambda e: self.view_3d())
        self.root.bind("<g>", lambda e: self.cycle_ghost())
        self.root.bind("<G>", lambda e: self.cycle_ghost())
        self.root.bind("<Prior>", lambda e: self.change_layer(1))
        self.root.bind("<Next>", lambda e: self.change_layer(-1))

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")
        self.stats = ttk.Label(bottom, text="", wraplength=560, justify="left")
        self.stats.pack(side="left")
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(bottom, text="Open...", command=self.open).pack(side="right")

        gh = ttk.LabelFrame(self.root, text="Send to turtle", padding=6)
        gh.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(gh, text="1. Upload to GitHub", command=self.upload).pack(side="left")
        ttk.Button(gh, text="2. Copy turtle command", command=self.copy_command).pack(side="left", padx=6)
        ttk.Entry(gh, textvariable=self.command, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(gh, text="GitHub settings", command=self.settings_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(gh, text="⟳ Update designer", command=self.update_designer).pack(side="left", padx=(6, 0))
        self.status = ttk.Label(self.root, text="", foreground="#3a7", padding=(8, 0, 8, 6))
        self.status.pack(fill="x")
        self.name.trace_add("write", lambda *a: self.refresh_command())
        self.refresh_command()

    # ---- grid drawing -------------------------------------------------
    def rebuild_grid(self):
        self.sync_from_design()
        d = self.d
        self.cell = max(8, min(28, 720 // max(d.L, d.W)))
        c = self.cell
        self.canvas.delete("all")
        self.canvas.config(width=d.W * c + 1, height=(d.L + 1) * c + 1)
        self.rects = {}
        self.bevels = {}
        self.torch_items = {}
        bw = max(1, c // 9)
        for x in range(d.L):
            for z in range(d.W):
                py = (d.L - 1 - x) * c
                px = z * c
                self.rects[(x, z)] = self.canvas.create_rectangle(
                    px, py, px + c, py + c, outline=COLORS["line"])
                o = bw / 2 + 1
                hi = self.canvas.create_line(px + o, py + c - o, px + o, py + o, px + c - o, py + o,
                                             width=bw, capstyle="projecting")
                lo = self.canvas.create_line(px + c - o, py + o, px + c - o, py + c - o, px + o, py + c - o,
                                             width=bw, capstyle="projecting")
                self.bevels[(x, z)] = (hi, lo)
        self.redraw()

    def tile_style(self, x, z):
        d, y = self.d, self.layer
        v = d.grid[y][x][z]
        key = v
        if v == KEEP:
            g = self.ghost.get()
            if g == "below" and y > 0 and d.grid[y - 1][x][z]:
                key = "below"
            elif g == "above" and y + 1 < d.H and d.grid[y + 1][x][z]:
                key = "above"
        base, hi, lo = STYLE[key]
        j = jitter(x, y, z)
        flow = self.flow.get((x, y, z)) if self.show_flow.get() else None
        if flow and v != WATER:
            lvl, falling = flow
            depth = 1.0 if falling else (8 - lvl) / 8.0      # full near the bucket, thin at the edge
            mix = 0.25 + 0.5 * depth
            base, hi, lo = (blend(c, "#3f7fd6", mix) for c in (base, hi, lo))
        return shade(base, j), shade(hi, j // 2), shade(lo, j // 2), v

    def draw_cell(self, x, z):
        base, hi, lo, v = self.tile_style(x, z)
        self.canvas.itemconfig(self.rects[(x, z)], fill=base)
        h, l = self.bevels[(x, z)]
        self.canvas.itemconfig(h, fill=hi)
        self.canvas.itemconfig(l, fill=lo)
        old = self.torch_items.pop((x, z), None)
        if old:
            for item in old:
                self.canvas.delete(item)
        if v == TORCH:
            self.torch_items[(x, z)] = self.draw_torch(x, z)
        elif v == WATER:
            self.torch_items[(x, z)] = self.draw_water(x, z)
        elif v == TRAP:
            self.torch_items[(x, z)] = self.draw_trapdoor(x, z)

    def draw_water(self, x, z):
        """Water: little light-blue waves on a blue tile."""
        c = self.cell
        px, py = z * c, (self.d.L - 1 - x) * c
        u = c / 8.0
        items = []
        for row, shift in ((2.4, 0), (4.4, 0.8), (6.2, 0)):
            pts = []
            for k in range(5):
                pts += [px + (1.2 + shift + k * 1.3) * u, py + (row + (0.5 if k % 2 else -0.4)) * u]
            items.append(self.canvas.create_line(*pts, fill="#cfe4ff", width=max(1, c // 12),
                                                 smooth=True, tags="torch"))
        return items

    def draw_trapdoor(self, x, z):
        """Trapdoor: a wooden hatch with a frame and four little windows."""
        c = self.cell
        px, py = z * c, (self.d.L - 1 - x) * c
        u = c / 8.0

        def box(x0, y0, x1, y1, color):
            return self.canvas.create_rectangle(px + x0 * u, py + y0 * u, px + x1 * u, py + y1 * u,
                                                fill=color, outline="", tags="torch")
        items = [box(1.2, 1.2, 6.8, 6.8, "#9c6b38")]          # wood
        for (a, b) in ((2.0, 2.0), (4.2, 2.0), (2.0, 4.2), (4.2, 4.2)):
            items.append(box(a, b, a + 1.8, b + 1.8, "#4a3018"))  # holes
        items.append(box(1.2, 1.2, 6.8, 1.7, "#b9864c"))       # top edge highlight
        return items

    def draw_torch(self, x, z):
        """A little pixel-art torch: wooden stick with a glowing flame."""
        c = self.cell
        px, py = z * c, (self.d.L - 1 - x) * c
        u = c / 8.0

        def box(x0, y0, x1, y1, color):
            return self.canvas.create_rectangle(px + x0 * u, py + y0 * u, px + x1 * u, py + y1 * u,
                                                fill=color, outline="", tags="torch")
        return [
            box(2.4, 1.0, 5.6, 4.4, "#fbe3a0"),   # warm glow on the tile
            box(3.3, 3.6, 4.7, 7.3, "#8b5a2b"),   # stick
            box(4.0, 3.6, 4.7, 7.3, "#6b4220"),   # stick shadow
            box(3.3, 3.6, 4.7, 4.1, "#3a2614"),   # charred top
            box(2.9, 1.9, 5.1, 3.6, "#ff8c1a"),   # flame
            box(3.3, 1.1, 4.7, 1.9, "#ffb627"),   # flame tip
            box(3.5, 2.2, 4.5, 3.4, "#ffe45c"),   # hot core
            box(3.75, 0.7, 4.25, 1.1, "#fff2a8"),  # spark
        ]

    def redraw(self):
        d, y = self.d, self.layer
        self.flow = d.water_flow() if self.show_flow.get() else {}
        self.canvas.delete("marker")
        for (x, z) in self.rects:
            self.draw_cell(x, z)
        c = self.cell
        sx, sy, sz = d.start
        if sy == y:
            self.mark(sx, sz, "S", COLORS["start"])
            if sx - 1 >= 0:
                self.mark(sx - 1, sz, "C", COLORS["chest"])
            else:  # chest sits just outside the grid
                px, py = sz * c, d.L * c
                self.canvas.create_rectangle(px + 1, py + 1, px + c - 1, py + c - 1, fill=COLORS["chest"],
                                             outline="", tags="marker")
                self.canvas.create_text(px + c / 2, py + c / 2, text="C", fill="white",
                                        tags="marker", font=("TkDefaultFont", max(7, c // 2), "bold"))
        self.layer_label.config(text=f"{y + 1} of {d.H}")
        if hasattr(self, "start_label"):
            self.start_label.config(text=f"forward {sx}, right {sz}, layer {sy + 1}")
        if hasattr(self, "ghost_hint"):
            self.ghost_hint.config(text={"off": "", "below": "Blue = dug on the layer below",
                                         "above": "Red = dug on the layer above"}[self.ghost.get()])
        self.update_stats()

    def cycle_ghost(self):
        order = ["off", "below", "above"]
        self.ghost.set(order[(order.index(self.ghost.get()) + 1) % 3])
        self.redraw()

    def mark(self, x, z, text, color):
        c = self.cell
        px, py = z * c, (self.d.L - 1 - x) * c
        self.canvas.create_rectangle(px + 1, py + 1, px + c - 1, py + c - 1, fill=color,
                                     outline="", tags="marker")
        self.canvas.create_text(px + c / 2, py + c / 2, text=text, fill="white", tags="marker",
                                font=("TkDefaultFont", max(7, c // 2), "bold"))

    def update_stats(self):
        dig, torches = self.d.count()
        fuel = int(dig / 2.5) + self.d.L + self.d.W + self.d.H
        water, traps = self.d.count_items()
        text = f"{dig} blocks to dig  |  {torches} torches  |  ~{fuel} fuel (~{fuel // 80 + 1} coal)"
        if water or traps:
            text += f"  |  at the end: {traps} trapdoors, {water} water buckets"
        if water and self.show_flow.get():
            d = self.d
            text += f"  |  water spreads to {len(self.flow)} more blocks"
            washed = sum(1 for (x, y, z) in self.flow if d.grid[y][x][z] == TORCH)
            if washed:
                text += f"  |  ⚠ water will wash away {washed} torches"
        bad = self.d.unreachable()
        if bad:
            text += f"  |  ⚠ {bad} blocks not connected to the start (turtle will tunnel to them)"
        d = self.d
        stuck = sum(1 for y in range(d.H) for x in range(d.L) for z in range(d.W)
                    if d.grid[y][x][z] == TORCH and not (y + 1 < d.H and d.grid[y + 1][x][z]))
        if stuck:
            text += f"  |  ⚠ {stuck} torches have no dug space above (turtle places from above - they'll be skipped)"
        sx, sy, sz = self.d.start
        if sx - 1 >= 0 and self.d.grid[sy][sx - 1][sz]:
            text += "  |  ⚠ chest spot is marked to dig (it'll be skipped)"
        self.stats.config(text=text)

    # ---- mouse --------------------------------------------------------
    def cell_at(self, e):
        z = int(e.x // self.cell)
        x = self.d.L - 1 - int(e.y // self.cell)
        if 0 <= x < self.d.L and 0 <= z < self.d.W:
            return x, z
        return None

    def paint(self, x, z, value):
        if self.d.grid[self.layer][x][z] == value:
            return
        self.dirty = True
        self.d.grid[self.layer][x][z] = value
        self.draw_cell(x, z)

    def pen_value(self, erase):
        if erase:
            return KEEP
        return {"dig": DIG, "keep": KEEP, "torch": TORCH, "water": WATER, "trap": TRAP}.get(self.tool.get())

    def on_press(self, e, erase):
        p = self.cell_at(e)
        if not p:
            return
        self.snapshot()
        tool = self.tool.get()
        sx, sy, sz = self.d.start
        if not erase and (tool == "start" or (sy == self.layer and p == (sx, sz))):
            self.dragging_start = True
            self.d.start = (p[0], self.layer, p[1])
            self.redraw()
            return
        if tool in ("rect", "rectkeep") and not erase:
            self.drag_start = p
            return
        self.paint(*p, self.pen_value(erase))

    def on_drag(self, e, erase):
        p = self.cell_at(e)
        if not p:
            return
        tool = self.tool.get()
        if getattr(self, "dragging_start", False) and not erase:
            if (p[0], self.layer, p[1]) != self.d.start:
                self.d.start = (p[0], self.layer, p[1])
                self.redraw()
            return
        if tool in ("rect", "rectkeep") and not erase and self.drag_start:
            c = self.cell
            (x0, z0), (x1, z1) = self.drag_start, p
            self.canvas.delete("drag")
            self.canvas.create_rectangle(min(z0, z1) * c, (self.d.L - 1 - max(x0, x1)) * c,
                                         (max(z0, z1) + 1) * c, (self.d.L - min(x0, x1)) * c,
                                         outline="#4fa3ff", width=2, tags="drag")
            return
        if tool == "start" and not erase:
            return
        self.paint(*p, self.pen_value(erase))

    def on_release(self, e, erase):
        if getattr(self, "dragging_start", False):
            self.dragging_start = False
            self.redraw()
            return
        tool = self.tool.get()
        if tool in ("rect", "rectkeep") and not erase and self.drag_start:
            p = self.cell_at(e) or self.drag_start
            (x0, z0), (x1, z1) = self.drag_start, p
            v = DIG if tool == "rect" else KEEP
            for x in range(min(x0, x1), max(x0, x1) + 1):
                for z in range(min(z0, z1), max(z0, z1) + 1):
                    self.d.grid[self.layer][x][z] = v
            self.drag_start = None
            self.canvas.delete("drag")
        self.redraw()

    # ---- undo ---------------------------------------------------------
    def snapshot(self):
        self.dirty = True
        d = self.d
        self.history.append((d.L, d.W, d.H, [[row[:] for row in layer] for layer in d.grid], d.start))
        self.history = self.history[-40:]

    def undo(self):
        if not self.history:
            return
        self.dirty = True
        L, W, H, grid, start = self.history.pop()
        size_changed = (L, W, H) != (self.d.L, self.d.W, self.d.H)
        self.d.L, self.d.W, self.d.H, self.d.grid, self.d.start = L, W, H, grid, start
        self.vL.set(L); self.vW.set(W); self.vH.set(H)
        self.layer = min(self.layer, H - 1)
        self.rebuild_grid() if size_changed else self.redraw()

    # ---- buttons ------------------------------------------------------
    def apply_size(self):
        try:
            L, W, H = (max(1, min(MAX, int(v.get()))) for v in (self.vL, self.vW, self.vH))
        except (tk.TclError, ValueError):
            messagebox.showerror("Size", "Sizes must be whole numbers from 1 to 64.")
            return
        self.snapshot()
        self.vL.set(L); self.vW.set(W); self.vH.set(H)
        self.d.resize(L, W, H)
        self.layer = min(self.layer, H - 1)
        self.rebuild_grid()

    def change_layer(self, delta):
        self.layer = max(0, min(self.d.H - 1, self.layer + delta))
        self.redraw()

    def fill_layer(self, v):
        self.snapshot()
        for row in self.d.grid[self.layer]:
            for z in range(len(row)):
                row[z] = v
        self.redraw()

    def copy_up(self):
        if self.layer + 1 >= self.d.H:
            return
        self.snapshot()
        self.d.grid[self.layer + 1] = [[DIG if v else KEEP for v in row] for row in self.d.grid[self.layer]]
        self.layer += 1
        self.redraw()

    def copy_all_up(self):
        self.snapshot()
        for y in range(self.layer + 1, self.d.H):
            self.d.grid[y] = [[DIG if v else KEEP for v in row] for row in self.d.grid[self.layer]]
        self.redraw()

    def shape(self, inside):
        self.snapshot()
        d = self.d
        for y in range(d.H):
            for x in range(d.L):
                for z in range(d.W):
                    # normalised -1..1 coordinates of the block centre
                    nx = (x + 0.5) / d.L * 2 - 1
                    ny = (y + 0.5) / d.H
                    nz = (z + 0.5) / d.W * 2 - 1
                    d.grid[y][x][z] = DIG if inside(nx, ny, nz) else KEEP
        self.center_start()
        self.redraw()

    def center_start(self):
        """Put the turtle start on the lowest dug square in the middle-back."""
        d = self.d
        z = d.W // 2
        for y in range(d.H):
            for x in range(d.L):
                if d.grid[y][x][z]:
                    d.start = (x, y, z)
                    return

    def shape_box(self):
        self.shape(lambda x, y, z: True)
        self.d.start = (0, 0, 0)
        self.redraw()

    def shape_sphere(self):
        self.shape(lambda x, y, z: x * x + (y * 2 - 1) ** 2 + z * z <= 1)

    def shape_dome(self):
        self.shape(lambda x, y, z: x * x + y * y + z * z <= 1)

    def shape_cylinder(self):
        self.shape(lambda x, y, z: x * x + z * z <= 1)

    def shape_arch(self):
        # a tunnel running forward: flat floor, round roof
        self.shape(lambda x, y, z: z * z + y * y <= 1)

    def shape_clear(self):
        self.shape(lambda x, y, z: False)

    def auto_torches(self):
        self.snapshot()
        self.clear_torches(snapshot=False)
        d = self.d
        try:
            sp = max(2, int(self.spacing.get()))
        except (tk.TclError, ValueError):
            sp = 8
        count = 0
        ox = ((d.L - 1) % sp) // 2   # centre the torch grid in the room
        oz = ((d.W - 1) % sp) // 2
        for y in range(d.H):
            for x in range(ox, d.L, sp):
                for z in range(oz, d.W, sp):
                    floor = y == 0 or not d.grid[y - 1][x][z]
                    room_above = y + 1 < d.H and d.grid[y + 1][x][z]
                    if d.grid[y][x][z] == DIG and floor and room_above and (x, y, z) != d.start:
                        d.grid[y][x][z] = TORCH
                        count += 1
        self.redraw()
        if count == 0:
            messagebox.showinfo("Torches", "No good floor spots found. Torches need a room at "
                                           "least 2 tall, or try a smaller spacing.")

    def clear_torches(self, snapshot=True):
        if snapshot:
            self.snapshot()
        for layer in self.d.grid:
            for row in layer:
                for z, v in enumerate(row):
                    if v == TORCH:
                        row[z] = DIG
        self.redraw()

    # ---- files --------------------------------------------------------
    def clean_name(self):
        name = "".join(ch for ch in self.name.get().strip() if ch.isalnum() or ch in "-_")
        if not name:
            messagebox.showerror("Name", "Give the design a name (letters, numbers, - or _).")
            return None
        self.name.set(name)
        return name

    def save(self, quiet=False):
        name = self.clean_name()
        if not name:
            return None
        os.makedirs(DESIGN_DIR, exist_ok=True)
        path = os.path.join(DESIGN_DIR, name + ".txt")
        with open(path, "w", newline="\n") as f:
            f.write(self.d.to_text())
        if not quiet:
            self.status.config(text=f"Saved {path}. Upload it to send it to the turtle.", foreground="#3a7")
        return path

    def open(self):
        path = filedialog.askopenfilename(initialdir=DESIGN_DIR if os.path.isdir(DESIGN_DIR) else HERE,
                                          filetypes=[("Minor designs", "*.txt"), ("All files", "*")])
        if not path:
            return
        try:
            with open(path) as f:
                d = Design.from_text(f.read())
        except Exception as ex:
            messagebox.showerror("Open", f"Couldn't read that file:\n{ex}")
            return
        self.snapshot()
        self.d = d
        self.vL.set(d.L); self.vW.set(d.W); self.vH.set(d.H)
        self.name.set(os.path.splitext(os.path.basename(path))[0])
        self.layer = 0
        self.rebuild_grid()

    # ---- shapes through layers -----------------------------------------
    LAYER_SHAPES = ["Rectangle", "Circle / oval", "Ring (hollow circle)", "Walls (hollow rectangle)",
                    "Diamond", "Plus / cross"]

    def layer_shape_dialog(self):
        d = self.d
        if getattr(self, "shape_win", None) and self.shape_win.winfo_exists():
            self.shape_win.lift()
            return
        win = self.shape_win = tk.Toplevel(self.root)
        win.title("Shape through layers")
        win.transient(self.root)
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both")

        v = {
            "shape": tk.StringVar(value=self.LAYER_SHAPES[1]),
            "len0": tk.IntVar(value=d.L), "wid0": tk.IntVar(value=d.W),
            "len1": tk.IntVar(value=d.L), "wid1": tk.IntVar(value=d.W),
            "cx": tk.IntVar(value=(d.L - 1) // 2), "cz": tk.IntVar(value=(d.W - 1) // 2),
            "from": tk.IntVar(value=self.layer + 1), "to": tk.IntVar(value=d.H),
            "thick": tk.IntVar(value=1), "mode": tk.StringVar(value="dig"),
        }
        row = 0

        def label(text, r, c=0, **kw):
            ttk.Label(f, text=text, **kw).grid(row=r, column=c, sticky="w", pady=2, padx=(0, 6))

        def spin(var, r, c, hi=MAX):
            ttk.Spinbox(f, from_=0, to=hi, textvariable=var, width=5).grid(row=r, column=c, sticky="w", pady=2)

        label("Shape", row)
        ttk.Combobox(f, textvariable=v["shape"], values=self.LAYER_SHAPES, state="readonly",
                     width=26).grid(row=row, column=1, columnspan=3, sticky="w")
        row += 1
        label("", row)
        label("Length (fwd)", row, 1, foreground="#777")
        label("Width (right)", row, 2, foreground="#777")
        row += 1
        label("Size on FIRST layer", row); spin(v["len0"], row, 1); spin(v["wid0"], row, 2)
        row += 1
        label("Size on LAST layer", row); spin(v["len1"], row, 1); spin(v["wid1"], row, 2)
        row += 1
        label("Centre block", row); spin(v["cx"], row, 1); spin(v["cz"], row, 2)
        ttk.Button(f, text="Middle", command=lambda: (v["cx"].set((self.d.L - 1) // 2),
                                                       v["cz"].set((self.d.W - 1) // 2))).grid(row=row, column=3)
        row += 1
        label("Layers from / to", row); spin(v["from"], row, 1); spin(v["to"], row, 2)
        ttk.Button(f, text="All", command=lambda: (v["from"].set(1), v["to"].set(self.d.H))).grid(row=row, column=3)
        row += 1
        label("Wall thickness", row); spin(v["thick"], row, 1, 32)
        label("(ring, walls, plus)", row, 2, foreground="#777")
        row += 1
        label("Mode", row)
        mf = ttk.Frame(f)
        mf.grid(row=row, column=1, columnspan=3, sticky="w")
        ttk.Radiobutton(mf, text="Dig it out", value="dig", variable=v["mode"]).pack(side="left")
        ttk.Radiobutton(mf, text="Leave it solid", value="keep", variable=v["mode"]).pack(side="left", padx=6)
        row += 1

        def preset(kind):
            L0, W0 = v["len0"].get(), v["wid0"].get()
            if kind == "straight":
                v["len1"].set(L0); v["wid1"].set(W0)
            elif kind == "shrink":
                v["len1"].set(1); v["wid1"].set(1)
            elif kind == "grow":
                v["len1"].set(L0); v["wid1"].set(W0)
                v["len0"].set(1); v["wid0"].set(1)

        label("Quick sizes", row)
        pf = ttk.Frame(f)
        pf.grid(row=row, column=1, columnspan=3, sticky="w")
        ttk.Button(pf, text="Straight up", command=lambda: preset("straight")).pack(side="left")
        ttk.Button(pf, text="Pyramid / cone", command=lambda: preset("shrink")).pack(side="left", padx=4)
        ttk.Button(pf, text="Upside down", command=lambda: preset("grow")).pack(side="left")
        row += 1

        ttk.Label(f, foreground="#777", justify="left", text=(
            "Tip: Circle + Pyramid/cone = a cone. Rectangle + Pyramid = a pyramid.\n"
            "Ring with the same size top and bottom = a round tower.")).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
        row += 1

        bf = ttk.Frame(f)
        bf.grid(row=row, column=0, columnspan=4, sticky="e", pady=(10, 0))

        def apply():
            try:
                vals = {k: var.get() for k, var in v.items()}
            except (tk.TclError, ValueError):
                messagebox.showerror("Shape", "Please use whole numbers.", parent=win)
                return
            self.snapshot()
            n = self.apply_layer_shape(vals)
            self.redraw()
            self.status.config(text=f"Shape applied: {n} blocks changed. (Ctrl+Z to undo)", foreground="#3a7")

        ttk.Button(bf, text="Undo", command=self.undo).pack(side="left")
        ttk.Button(bf, text="Apply", command=apply).pack(side="left", padx=6)
        ttk.Button(bf, text="Close", command=win.destroy).pack(side="left")

    def apply_layer_shape(self, o):
        """Stamp a 2D shape onto a range of layers, resizing it between the
        first and last layer. Returns how many blocks changed."""
        d = self.d
        y0 = max(1, min(d.H, int(o["from"]))) - 1
        y1 = max(1, min(d.H, int(o["to"]))) - 1
        if y1 < y0:
            y0, y1 = y1, y0
        shape = o["shape"]
        t = max(1, int(o["thick"]))
        dig = o["mode"] == "dig"
        changed = 0
        for y in range(y0, y1 + 1):
            f = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
            ln = max(1, round(o["len0"] + (o["len1"] - o["len0"]) * f))
            wd = max(1, round(o["wid0"] + (o["wid1"] - o["wid0"]) * f))
            x0 = int(o["cx"]) - (ln - 1) // 2
            z0 = int(o["cz"]) - (wd - 1) // 2
            x1, z1 = x0 + ln - 1, z0 + wd - 1
            mx, mz = (x0 + x1 + 1) / 2.0, (z0 + z1 + 1) / 2.0
            a, b = ln / 2.0, wd / 2.0
            for x in range(max(0, x0), min(d.L - 1, x1) + 1):
                for z in range(max(0, z0), min(d.W - 1, z1) + 1):
                    u = (x + 0.5 - mx) / a
                    w = (z + 0.5 - mz) / b
                    if shape.startswith("Rectangle"):
                        inside = True
                    elif shape.startswith("Circle"):
                        inside = u * u + w * w <= 1.0
                    elif shape.startswith("Ring"):
                        ia, ib = a - t, b - t
                        inner = ia > 0 and ib > 0 and ((x + 0.5 - mx) / ia) ** 2 + ((z + 0.5 - mz) / ib) ** 2 < 1.0
                        inside = u * u + w * w <= 1.0 and not inner
                    elif shape.startswith("Walls"):
                        inside = x < x0 + t or x > x1 - t or z < z0 + t or z > z1 - t
                    elif shape.startswith("Diamond"):
                        inside = abs(u) + abs(w) <= 1.0
                    else:  # plus / cross
                        inside = abs(x + 0.5 - mx) <= t / 2.0 or abs(z + 0.5 - mz) <= t / 2.0
                    if not inside:
                        continue
                    cur = d.grid[y][x][z]
                    if dig and cur == KEEP:
                        d.grid[y][x][z] = DIG
                        changed += 1
                    elif not dig and cur != KEEP:
                        d.grid[y][x][z] = KEEP
                        changed += 1
        return changed

    def set_open_traps(self):
        self.d.open_traps = bool(self.open_traps.get())
        self.dirty = True

    # ---- tabs (auto-saved) --------------------------------------------
    def tab_path(self, i):
        return os.path.join(TABS_DIR, f"tab{i + 1}.txt")

    def load_tabs(self):
        """Bring back all 5 tabs from last time."""
        try:
            with open(os.path.join(TABS_DIR, "tabs.json")) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
        infos = meta.get("tabs", [])
        for i in range(TAB_COUNT):
            info = infos[i] if i < len(infos) and isinstance(infos[i], dict) else {}
            d = None
            try:
                with open(self.tab_path(i)) as f:
                    d = Design.from_text(f.read())
            except (OSError, ValueError):
                pass
            self.slots[i] = {"d": d, "name": info.get("name", "myroom" if i == 0 else f"design{i + 1}"),
                             "layer": int(info.get("layer", 0)), "history": []}
        cur = meta.get("current", 0)
        self.cur_slot = cur if isinstance(cur, int) and 0 <= cur < TAB_COUNT else 0
        self.slot_var.set(self.cur_slot)
        self.apply_tab(self.cur_slot, rebuild=False)

    def store_tab(self):
        self.slots[self.cur_slot] = {"d": self.d, "name": self.name.get(), "layer": self.layer,
                                     "history": self.history}

    def apply_tab(self, i, rebuild=True):
        s = self.slots[i]
        if s["d"] is None:
            s["d"] = Design()
        self.d = s["d"]
        self.history = s["history"]
        self.layer = max(0, min(self.d.H - 1, s["layer"]))
        self.name.set(s["name"])
        self.vL.set(self.d.L); self.vW.set(self.d.W); self.vH.set(self.d.H)
        if rebuild:
            self.rebuild_grid()

    def save_tabs(self, which=None):
        """Write tab files (just the current one by default) plus the tab list."""
        try:
            os.makedirs(TABS_DIR, exist_ok=True)
            for i in ([self.cur_slot] if which is None else which):
                s = self.slots[i]
                if s and s["d"] is not None:
                    tmp = self.tab_path(i) + ".tmp"
                    with open(tmp, "w", newline="\n") as f:
                        f.write(s["d"].to_text())
                    os.replace(tmp, self.tab_path(i))  # never leaves a half-written file
            meta = {"current": self.cur_slot,
                    "tabs": [{"name": s["name"], "layer": s["layer"]} for s in self.slots]}
            with open(os.path.join(TABS_DIR, "tabs.json"), "w") as f:
                json.dump(meta, f, indent=1)
            return True
        except OSError as ex:
            self.status.config(text=f"Couldn't auto-save: {ex}", foreground="#c33")
            return False

    def autosave_tick(self):
        if self.dirty:
            self.dirty = False
            self.store_tab()
            if self.save_tabs():
                self.autosave_label.config(text=f"Tab {self.cur_slot + 1} saved ✓")
                self.root.after(1500, lambda: self.autosave_label.config(text=""))
        self.root.after(2000, self.autosave_tick)

    def switch_tab(self):
        i = self.slot_var.get()
        if i == self.cur_slot:
            return
        self.store_tab()
        self.save_tabs()          # save the tab we're leaving
        self.dirty = False
        self.cur_slot = i
        self.apply_tab(i)
        self.save_tabs([])        # remember which tab is open
        self.update_tab_labels()

    def new_in_tab(self):
        if not messagebox.askyesno("New design", f"Start a new blank design in tab {self.cur_slot + 1}?\n\n"
                                                 "What's in this tab now will be replaced. (Undo can bring "
                                                 "it back until you close the designer.)"):
            return
        self.snapshot()
        self.d = Design()
        self.layer = 0
        self.name.set(f"design{self.cur_slot + 1}")
        self.vL.set(self.d.L); self.vW.set(self.d.W); self.vH.set(self.d.H)
        self.rebuild_grid()

    def on_name_change(self):
        self.dirty = True
        if self.slots[self.cur_slot] is not None:
            self.slots[self.cur_slot]["name"] = self.name.get()
        self.update_tab_labels()

    def update_tab_labels(self):
        if not hasattr(self, "tab_buttons"):
            return
        for i, b in enumerate(self.tab_buttons):
            s = self.slots[i]
            name = self.name.get() if i == self.cur_slot else (s["name"] if s and s["d"] is not None else "empty")
            b.config(text=f"{i + 1}: {name[:12]}")

    def on_close(self):
        self.store_tab()
        self.save_tabs()
        self.root.destroy()

    def sync_from_design(self):
        """Update checkboxes after a different design was loaded."""
        if hasattr(self, "open_traps"):
            self.open_traps.set(self.d.open_traps)

    # ---- 3D view --------------------------------------------------------
    def view_3d(self):
        """Write a three.js page for this design and open it in Chrome."""
        name = self.name.get().strip() or "design"
        page = (VIEWER_HTML
                .replace("__DESIGN__", json.dumps(self.d.to_text()).replace("</", "<\\/"))
                .replace("__FLOW__", json.dumps([[x, y, z, lv, int(f)] for (x, y, z), (lv, f)
                                                 in self.d.water_flow().items()]))
                .replace("__NAME__", htmllib.escape(name)))
        os.makedirs(DESIGN_DIR, exist_ok=True)
        path = os.path.join(DESIGN_DIR, "_3d_view.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        url = pathlib.Path(path).resolve().as_uri()
        if open_in_chrome(url):
            self.status.config(text="Opened the 3D view in Chrome.", foreground="#3a7")
        else:
            webbrowser.open(url)
            self.status.config(text="Chrome not found - opened the 3D view in your default browser.",
                               foreground="#c80")

    # ---- turtle start -------------------------------------------------
    def move_start(self, dx, dy, dz):
        d = self.d
        sx, sy, sz = d.start
        nx, ny, nz = sx + dx, sy + dy, sz + dz
        if not (0 <= nx < d.L and 0 <= ny < d.H and 0 <= nz < d.W):
            self.status.config(text="The turtle has to start inside the design. Make the design "
                                    "bigger to move it further.", foreground="#c80")
            return
        self.snapshot()
        d.start = (nx, ny, nz)
        self.layer = ny  # follow the turtle between layers
        self.status.config(text="", foreground="#777")
        self.redraw()

    def goto_start_layer(self):
        self.layer = self.d.start[1]
        self.redraw()

    # ---- self update --------------------------------------------------
    def update_designer(self):
        # Always update from the official repo, with no token (it's public),
        # so a wrong repo setting or an expired token can't break updating.
        repo = UPDATE_REPO
        sources = [
            (f"https://api.github.com/repos/{repo}/contents/designer.py?ref=main",
             {"Accept": "application/vnd.github.raw", "User-Agent": "minor-designer"}),
            (f"https://raw.githubusercontent.com/{repo}/main/designer.py",
             {"User-Agent": "minor-designer", "Cache-Control": "no-cache"}),
        ]
        self.status.config(text="Checking for updates...", foreground="#777")
        self.root.update()
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        new_code, errors = None, []
        for url, headers in sources:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                    code = r.read().decode("utf-8")
                compile(code, "designer.py", "exec")  # make sure it's real Python
                new_code = code
                break
            except Exception as ex:
                errors.append(f"{url.split('/')[2]}: {ex}")
        if new_code is None:
            self.status.config(text="Update failed.", foreground="#c33")
            hint = ""
            if any("CERTIFICATE" in e.upper() for e in errors):
                hint = ("\n\nOn a Mac, run 'Install Certificates.command' from your Python folder "
                        "(Applications > Python 3.x), then try again.")
            messagebox.showerror("Update", "Couldn't download the update:\n\n" + "\n".join(errors) + hint)
            return

        me = os.path.abspath(__file__)
        with open(me, encoding="utf-8") as f:
            old_code = f.read()
        if new_code.replace("\r\n", "\n") == old_code.replace("\r\n", "\n"):
            self.status.config(text="You already have the newest designer.", foreground="#3a7")
            return
        if not messagebox.askyesno("Update", "A new version is ready. Restart the designer now?\n\n"
                                             "Your current design will be kept open."):
            self.status.config(text="", foreground="#777")
            return

        # keep a backup, then swap in the new file
        with open(me + ".bak", "w", encoding="utf-8", newline="") as f:
            f.write(old_code)
        with open(me, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_code)

        # save all tabs + what's open so the new version can load it
        self.store_tab()
        self.save_tabs()
        os.makedirs(DESIGN_DIR, exist_ok=True)
        resume = os.path.join(DESIGN_DIR, "_resume.txt")
        with open(resume, "w", newline="\n") as f:
            f.write(self.d.to_text())
        meta = json.dumps({"name": self.name.get(), "layer": self.layer})

        try:
            exe = sys.executable or "python"
            flags = 0
            if os.name == "nt":
                # start the new window on its own so closing this one can't take it down
                flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                if os.path.exists(pyw):
                    exe = pyw
            subprocess.Popen([exe, me, "--resume", resume, meta], cwd=HERE, creationflags=flags,
                             close_fds=True)
        except Exception as ex:
            messagebox.showinfo("Update", f"Updated! Please close and reopen the designer yourself.\n\n({ex})")
            return
        self.root.destroy()

    def resume_from(self, path, meta):
        try:
            with open(path) as f:
                d = Design.from_text(f.read())
            info = json.loads(meta) if meta else {}
        except Exception:
            return
        self.d = d
        self.vL.set(d.L); self.vW.set(d.W); self.vH.set(d.H)
        self.name.set(info.get("name", "myroom"))
        self.layer = max(0, min(d.H - 1, int(info.get("layer", 0))))
        self.rebuild_grid()
        self.status.config(text="Updated to the newest designer!", foreground="#3a7")
        try:
            os.remove(path)
        except OSError:
            pass

    # ---- GitHub -------------------------------------------------------
    def raw_url(self, path, ref=None):
        st = self.settings
        return f"https://raw.githubusercontent.com/{st['repo']}/{ref or st['branch']}/{path}"

    def refresh_command(self):
        name = "".join(ch for ch in self.name.get().strip() if ch.isalnum() or ch in "-_")
        if not name:
            self.command.set("")
            return
        # point at the exact upload, so the turtle never gets an old cached copy
        design = self.raw_url(f"designs/{name}.txt", self.uploaded.get(name))
        self.command.set(f"wget run {self.raw_url('install.lua')} {design}")

    def copy_command(self):
        name = self.clean_name()
        if not name:
            return
        self.refresh_command()
        self.root.clipboard_clear()
        self.root.clipboard_append(self.command.get())
        self.root.update()
        if name in self.uploaded:
            self.status.config(text="Copied! Click the turtle's screen and press Ctrl+V, then Enter.",
                               foreground="#3a7")
        else:
            self.status.config(text="Copied - but this design hasn't been uploaded yet this session. "
                                    "Upload it first if you changed it.", foreground="#c80")

    def settings_dialog(self, first_time=False):
        win = tk.Toplevel(self.root)
        win.title("GitHub settings")
        win.transient(self.root)
        win.grab_set()
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both")
        repo = tk.StringVar(value=self.settings["repo"])
        branch = tk.StringVar(value=self.settings["branch"])
        token = tk.StringVar(value=self.settings["token"])
        if first_time:
            ttk.Label(frm, justify="left", text=(
                "To upload, the designer needs a GitHub token (one time only).\n\n"
                "1. Go to github.com/settings/personal-access-tokens/new\n"
                "2. Repository access: Only select repositories -> your minor repo\n"
                "3. Permissions -> Repository permissions -> Contents: Read and write\n"
                "4. Generate token, copy it, paste it below.\n\n"
                "It's saved in minor_settings.json on this PC only - never upload that file.")
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for r, (label, var, show) in enumerate((("Repo (user/name)", repo, ""), ("Branch", branch, ""),
                                                 ("Token", token, "•")), start=1):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(frm, textvariable=var, width=46, show=show).grid(row=r, column=1, pady=2)
        ttk.Button(frm, text="Use default repo", command=lambda: repo.set(DEFAULT_SETTINGS["repo"])).grid(
            row=4, column=0, sticky="w", pady=(10, 0))
        result = {"ok": False}

        def ok():
            r = repo.get().strip().strip("/")
            for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
                if r.lower().startswith(prefix):
                    r = r[len(prefix):]
            if r.endswith(".git"):
                r = r[:-4]
            if "/" not in r:  # just the repo name -> assume the same owner
                r = DEFAULT_SETTINGS["repo"].split("/")[0] + "/" + r
            # make sure the repo really exists before saving it
            try:
                code, info = github("GET", f"https://api.github.com/repos/{r}", token.get().strip())
                if code == 401:  # bad token - check the repo without it
                    code, info = github("GET", f"https://api.github.com/repos/{r}", "")
            except Exception:
                code, info = 0, {}
            if code in (403, 404):
                messagebox.showerror("GitHub settings", f"Can't find the repo '{r}' on GitHub.\n\n"
                                     f"It should look like {DEFAULT_SETTINGS['repo']}", parent=win)
                return
            if code == 200 and isinstance(info, dict) and info.get("full_name"):
                r = info["full_name"]  # fixes capital letters / renamed repos
            if code == 200 and isinstance(info, dict) and info.get("private"):
                messagebox.showwarning("GitHub settings", "That repo is private. Turtles can only download "
                                       "from public repos - make it public in the repo's Settings.", parent=win)
            repo.set(r)
            self.settings.update(repo=r, branch=branch.get().strip() or "main",
                                 token=token.get().strip())
            save_settings(self.settings)
            self.refresh_command()
            result["ok"] = True
            win.destroy()

        ttk.Button(frm, text="Save", command=ok).grid(row=4, column=1, sticky="e", pady=(10, 0))
        self.root.wait_window(win)
        return result["ok"]

    def upload(self):
        path = self.save(quiet=True)
        if not path:
            return
        name = self.name.get()
        if not self.settings.get("token"):
            if not self.settings_dialog(first_time=True) or not self.settings.get("token"):
                return
        st = self.settings
        api = f"https://api.github.com/repos/{st['repo']}/contents/designs/{name}.txt"
        self.status.config(text="Uploading...", foreground="#777")
        self.root.update()
        try:
            code, info = github("GET", api + f"?ref={st['branch']}", st["token"])
            body = {
                "message": f"Update design {name}",
                "content": base64.b64encode(self.d.to_text().encode()).decode(),
                "branch": st["branch"],
            }
            if code == 200 and isinstance(info, dict) and info.get("sha"):
                body["sha"] = info["sha"]
            code, info = github("PUT", api, st["token"], body)
        except Exception as ex:  # network problems
            self.status.config(text="", foreground="#777")
            messagebox.showerror("Upload", f"Couldn't reach GitHub:\n{ex}")
            return
        if code not in (200, 201):
            msg = info.get("message", "") if isinstance(info, dict) else ""
            hint = ""
            if code in (401, 403):
                hint = "\n\nThe token is wrong, expired, or doesn't have Contents: Read and write."
            elif code == 404:
                hint = "\n\nCheck the repo name in GitHub settings, and that the token can see that repo."
            self.status.config(text="Upload failed.", foreground="#c33")
            messagebox.showerror("Upload", f"GitHub said: {code} {msg}{hint}")
            return
        self.uploaded[name] = info.get("commit", {}).get("sha") or st["branch"]
        self.refresh_command()
        self.status.config(text=f"Uploaded '{name}'! Now click '2. Copy turtle command' and paste it "
                                "into the turtle.", foreground="#3a7")


# 3D viewer page (three.js r149). __NAME__ and __DESIGN__ get filled in.
VIEWER_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__NAME__ – Minor 3D</title>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #17181c;
               font: 13px "Segoe UI", system-ui, sans-serif; color: #e8e6e1; }
  #c { display: block; width: 100vw; height: 100vh; }
  #ui { position: absolute; top: 12px; left: 12px; width: 250px; padding: 14px 16px 12px;
        background: rgba(24, 25, 30, .88); border: 1px solid #2c2e35; border-radius: 10px;
        box-shadow: 0 6px 24px rgba(0,0,0,.35); }
  h1 { margin: 0 0 2px; font-size: 16px; font-weight: 600; }
  .sub { color: #9a988f; margin-bottom: 12px; }
  .seg { display: flex; background: #101114; border-radius: 7px; padding: 3px; margin-bottom: 12px; }
  .seg button { flex: 1; border: 0; background: transparent; color: #b7b4ab; padding: 7px 4px;
                border-radius: 5px; cursor: pointer; font: inherit; }
  .seg button.on { background: #e6cf98; color: #1d1a12; font-weight: 600; }
  label.row { display: block; margin: 9px 0 3px; color: #c9c6bd; }
  label.row span { float: right; color: #e6cf98; font-variant-numeric: tabular-nums; }
  input[type=range] { width: 100%; accent-color: #e6cf98; }
  .checks { margin-top: 10px; display: grid; gap: 4px; }
  .checks label { cursor: pointer; color: #c9c6bd; }
  .btns { display: flex; gap: 6px; margin-top: 12px; }
  .btns button { flex: 1; background: #2a2c33; color: #e8e6e1; border: 1px solid #3a3d46;
                 border-radius: 6px; padding: 6px 4px; cursor: pointer; font: inherit; }
  .btns button:hover { background: #343741; }
  #stats { margin-top: 12px; padding-top: 10px; border-top: 1px solid #2c2e35; color: #9a988f; line-height: 1.6; }
  .key { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
  #help { position: absolute; bottom: 12px; left: 12px; color: #7d7b74; font-size: 12px; }
  #err { position: absolute; inset: 0; display: none; place-items: center; text-align: center; color: #e8e6e1; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="ui">
  <h1>__NAME__</h1>
  <div class="sub" id="size"></div>
  <div class="seg">
    <button id="mHollow" class="on">Hollowed out</button>
    <button id="mMine">Blocks to mine</button>
  </div>
  <label class="row">Show up to layer <span id="topV"></span></label>
  <input type="range" id="top" min="1" step="1">
  <label class="row">Slice from turtle side <span id="sliceV"></span></label>
  <input type="range" id="slice" min="0" step="1">
  <div class="checks">
    <label><input type="checkbox" id="xray"> See-through</label>
    <label><input type="checkbox" id="torches" checked> Torches</label>
    <label><input type="checkbox" id="items" checked> Trapdoors &amp; water</label>
    <label><input type="checkbox" id="flow" checked> Water flow</label>
    <label><input type="checkbox" id="turtle" checked> Turtle &amp; chest</label>
    <label><input type="checkbox" id="grid" checked> Ground grid</label>
  </div>
  <div class="btns">
    <button id="vReset">Reset view</button>
    <button id="vTop">Top</button>
    <button id="vSide">Side</button>
  </div>
  <div id="stats"></div>
</div>
<div id="help">Left drag: rotate &nbsp;·&nbsp; Right drag: move &nbsp;·&nbsp; Scroll: zoom</div>
<div id="err"><div><h2>Couldn't load three.js</h2><p>This page needs an internet connection the first time it loads.</p></div></div>

<script type="importmap">
{ "imports": {
    "three": "https://unpkg.com/three@0.149.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.149.0/examples/jsm/"
} }
</script>
<script>
  // shown only if the module below never starts (offline, blocked CDN)
  setTimeout(() => { if (!window.__minorStarted) document.getElementById('err').style.display = 'grid'; }, 8000);
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
window.__minorStarted = true;

const DESIGN = __DESIGN__;
const FLOW = __FLOW__;   // [x, y, z, level 1-7, falling]

// ---------------------------------------------------------------- parse
const KEEP = 0, DIG = 1, TORCH = 2, WATER = 3, TRAP = 4;
let L = 1, W = 1, H = 1, start = [0, 0, 0], grid;
(function parse() {
  let y = -1, x = 0;
  for (const raw of DESIGN.split('\n')) {
    const line = raw.trim();
    if (line.startsWith('size ')) {
      [L, W, H] = line.split(/\s+/).slice(1, 4).map(Number);
      grid = new Uint8Array(L * W * H);
    } else if (line.startsWith('start ')) {
      start = line.split(/\s+/).slice(1, 4).map(Number);
    } else if (line.startsWith('layer ')) {
      y = Number(line.split(/\s+/)[1]); x = 0;
    } else if (grid && y >= 0 && x < L && line && !line.startsWith('minor')) {
      let z = 0;
      for (const m of line.matchAll(/(\d+)([.#TWD])/g)) {
        const v = { '#': DIG, 'T': TORCH, 'W': WATER, 'D': TRAP }[m[2]] ?? KEEP;
        for (let n = 0; n < +m[1] && z < W; n++, z++) grid[x + L * (z + W * y)] = v;
      }
      x++;
    }
  }
})();
const [SX, SY, SZ] = start;
const at = (x, y, z) => (x < 0 || y < 0 || z < 0 || x >= L || y >= H || z >= W) ? -1 : grid[x + L * (z + W * y)];
const isChest = (x, y, z) => x === SX - 1 && y === SY && z === SZ;
const isStart = (x, y, z) => x === SX && y === SY && z === SZ;

// design (x fwd, y up, z right) -> world. Turtle faces -Z (into the screen).
const toWorld = (x, y, z, v = new THREE.Vector3()) => v.set(z + 0.5 - W / 2, y + 0.5, L / 2 - (x + 0.5));

// ---------------------------------------------------------------- scene
const canvas = document.getElementById('c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x17181c);
scene.fog = new THREE.Fog(0x17181c, 200, 600);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

scene.add(new THREE.HemisphereLight(0xdfe6f5, 0x3a3226, 0.75));
const sun = new THREE.DirectionalLight(0xfff1dc, 0.85);
sun.position.set(0.6, 1.0, 0.45);
scene.add(sun);
const fill = new THREE.DirectionalLight(0x9db4ff, 0.25);
fill.position.set(-0.7, 0.3, -0.6);
scene.add(fill);

const maxDim = Math.max(L, W, H);
const gridHelper = new THREE.GridHelper(Math.ceil(maxDim * 1.6 / 2) * 2 + 8, Math.ceil(maxDim * 1.6 / 2) * 2 + 8, 0x3a3d46, 0x26282e);
gridHelper.position.y = -0.002 - 1; // under the padding layer
scene.add(gridHelper);

// "forward" arrow on the ground
const fwdArrow = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, -0.95, L / 2 + 3),
                                       3, 0x3fbf5a, 0.9, 0.6);
scene.add(fwdArrow);

const cube = new THREE.BoxGeometry(1, 1, 1);
const blockMat = new THREE.MeshLambertMaterial({ transparent: false });
let blocks = null;

// torches: stick + glowing flame
const stickGeo = new THREE.BoxGeometry(0.14, 0.58, 0.14);
const flameGeo = new THREE.BoxGeometry(0.24, 0.24, 0.24);
const stickMat = new THREE.MeshLambertMaterial({ color: 0x8b5a2b });
const flameMat = new THREE.MeshBasicMaterial({ color: 0xffb02e });
const coreGeo = new THREE.BoxGeometry(0.13, 0.13, 0.13);
const coreMat = new THREE.MeshBasicMaterial({ color: 0xfff1a0 });
let torchGroup = new THREE.Group();
scene.add(torchGroup);

// water (see-through blue) and trapdoors (thin wooden slab on the floor)
const waterGeo = new THREE.BoxGeometry(0.98, 0.9, 0.98);
const waterMat = new THREE.MeshLambertMaterial({ color: 0x3f7fd6, transparent: true, opacity: 0.55, depthWrite: false });
const trapGeo = new THREE.BoxGeometry(0.96, 0.19, 0.96);
const trapMat = new THREE.MeshLambertMaterial({ color: 0x9c6b38 });
let itemGroup = new THREE.Group();
scene.add(itemGroup);
const flowMat = new THREE.MeshLambertMaterial({ color: 0x5c98ea, transparent: true, opacity: 0.42, depthWrite: false });
const unitBox = new THREE.BoxGeometry(1, 1, 1);
let flowMesh = null;

// turtle + chest
const turtleGroup = new THREE.Group();
scene.add(turtleGroup);
{
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.82, 0.82),
                              new THREE.MeshLambertMaterial({ color: 0x3fbf5a }));
  const face = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.32, 0.04),
                              new THREE.MeshBasicMaterial({ color: 0x17181c }));
  face.position.set(0, 0.08, -0.43);
  const eye = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.05), new THREE.MeshBasicMaterial({ color: 0xdcffe2 }));
  eye.position.set(-0.12, 0.1, -0.45);
  const t = new THREE.Group();
  t.add(body, face, eye);
  t.name = 'turtle';
  toWorld(SX, SY, SZ, t.position);
  const chest = new THREE.Mesh(new THREE.BoxGeometry(0.86, 0.8, 0.86),
                               new THREE.MeshLambertMaterial({ color: 0x8a5a2b }));
  const lid = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.08, 0.9), new THREE.MeshLambertMaterial({ color: 0x6b4220 }));
  lid.position.y = 0.12;
  const lock = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.18, 0.05), new THREE.MeshLambertMaterial({ color: 0xc9c9c9 }));
  lock.position.set(0, 0.08, 0.44);
  const c = new THREE.Group();
  c.add(chest, lid, lock);
  toWorld(SX - 1, SY, SZ, c.position);
  c.position.y -= 0.1;
  turtleGroup.add(t, c);
}

// ---------------------------------------------------------------- build
const state = { mode: 'hollow', top: H, slice: 0, xray: false };
const PAD = 1; // rock around the design in hollow mode

function jitter(x, y, z) {
  let h = (x * 73856093) ^ (z * 19349663) ^ (y * 83492791);
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h >>> 0) % 1000) / 1000 - 0.5;
}

function visibleCut(x, y) { return y < state.top && x >= state.slice; }

function filled(x, y, z) {
  if (!visibleCut(x, y)) return false;
  const v = at(x, y, z);
  if (state.mode === 'mine') {
    return (v === DIG) && !isStart(x, y, z);
  }
  // hollow: rock = anything inside the padded box that isn't dug
  if (x < -PAD || y < -PAD || z < -PAD || x >= L + PAD || y >= H + PAD || z >= W + PAD) return false;
  if (isChest(x, y, z) || isStart(x, y, z)) return false;
  return v === KEEP || v === -1;
}

function touchesDug(x, y, z) {
  return at(x + 1, y, z) > 0 || at(x - 1, y, z) > 0 || at(x, y + 1, z) > 0 ||
         at(x, y - 1, z) > 0 || at(x, y, z + 1) > 0 || at(x, y, z - 1) > 0;
}

const tmpM = new THREE.Matrix4(), tmpV = new THREE.Vector3(), tmpC = new THREE.Color();
let blockCount = 0;

function rebuild() {
  if (blocks) { scene.remove(blocks); blocks.dispose(); }
  const p = state.mode === 'hollow' ? PAD : 0;
  const cells = [];
  for (let y = -p; y < H + p; y++)
    for (let x = -p; x < L + p; x++)
      for (let z = -p; z < W + p; z++) {
        if (!filled(x, y, z)) continue;
        // only draw blocks you could see (something open next to them)
        if (filled(x + 1, y, z) && filled(x - 1, y, z) && filled(x, y + 1, z) &&
            filled(x, y - 1, z) && filled(x, y, z + 1) && filled(x, y, z - 1)) continue;
        cells.push(x, y, z);
      }
  const n = cells.length / 3;
  blockCount = n;
  blocks = new THREE.InstancedMesh(cube, blockMat, Math.max(1, n));
  blocks.count = n;
  for (let i = 0; i < n; i++) {
    const x = cells[i * 3], y = cells[i * 3 + 1], z = cells[i * 3 + 2];
    toWorld(x, y, z, tmpV);
    tmpM.makeTranslation(tmpV.x, tmpV.y, tmpV.z);
    blocks.setMatrixAt(i, tmpM);
    const j = jitter(x, y, z);
    if (state.mode === 'mine') {
      // warm sand, a little darker near the bottom
      const k = 0.82 + 0.18 * (H > 1 ? y / (H - 1) : 1) + j * 0.08;
      tmpC.setRGB(0.92 * k, 0.80 * k, 0.56 * k);
    } else if (touchesDug(x, y, z)) {
      const k = 0.95 + j * 0.10;      // cave walls: lighter stone so the shape pops
      tmpC.setRGB(0.66 * k, 0.64 * k, 0.60 * k);
    } else {
      const k = 0.90 + j * 0.14;      // plain rock
      tmpC.setRGB(0.40 * k, 0.41 * k, 0.44 * k);
    }
    blocks.setColorAt(i, tmpC);
  }
  if (blocks.instanceColor) blocks.instanceColor.needsUpdate = true;
  blocks.instanceMatrix.needsUpdate = true;
  scene.add(blocks);

  // torches
  scene.remove(torchGroup);
  torchGroup = new THREE.Group();
  const spots = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < L; x++) for (let z = 0; z < W; z++)
    if (at(x, y, z) === TORCH && visibleCut(x, y)) spots.push([x, y, z]);
  if (spots.length) {
    const sticks = new THREE.InstancedMesh(stickGeo, stickMat, spots.length);
    const flames = new THREE.InstancedMesh(flameGeo, flameMat, spots.length);
    const cores = new THREE.InstancedMesh(coreGeo, coreMat, spots.length);
    spots.forEach(([x, y, z], i) => {
      toWorld(x, y, z, tmpV);
      tmpM.makeTranslation(tmpV.x, tmpV.y - 0.5 + 0.29, tmpV.z); sticks.setMatrixAt(i, tmpM);
      tmpM.makeTranslation(tmpV.x, tmpV.y - 0.5 + 0.68, tmpV.z); flames.setMatrixAt(i, tmpM);
      tmpM.makeTranslation(tmpV.x, tmpV.y - 0.5 + 0.70, tmpV.z); cores.setMatrixAt(i, tmpM);
    });
    torchGroup.add(sticks, flames, cores);
  }
  torchGroup.visible = document.getElementById('torches').checked;
  scene.add(torchGroup);

  scene.remove(itemGroup);
  itemGroup = new THREE.Group();
  const water = [], traps = [];
  for (let y = 0; y < H; y++) for (let x = 0; x < L; x++) for (let z = 0; z < W; z++) {
    if (!visibleCut(x, y)) continue;
    const v = at(x, y, z);
    if (v === WATER) water.push([x, y, z]); else if (v === TRAP) traps.push([x, y, z]);
  }
  const addInst = (list, geo, mat, dy) => {
    if (!list.length) return;
    const m = new THREE.InstancedMesh(geo, mat, list.length);
    list.forEach(([x, y, z], i) => {
      toWorld(x, y, z, tmpV);
      tmpM.makeTranslation(tmpV.x, tmpV.y + dy, tmpV.z);
      m.setMatrixAt(i, tmpM);
    });
    itemGroup.add(m);
  };
  addInst(traps, trapGeo, trapMat, -0.5 + 0.095);
  addInst(water, waterGeo, waterMat, -0.05);
  itemGroup.visible = document.getElementById('items').checked;
  scene.add(itemGroup);

  // flowing water: taller near the bucket, a thin film at the edge
  if (flowMesh) { scene.remove(flowMesh); flowMesh.dispose(); flowMesh = null; }
  const shown = FLOW.filter(([x, y]) => visibleCut(x, y));
  if (shown.length) {
    flowMesh = new THREE.InstancedMesh(unitBox, flowMat, shown.length);
    const sc = new THREE.Vector3();
    shown.forEach(([x, y, z, lvl, falling], i) => {
      const h = falling ? 1.0 : Math.max(0.1, (8 - lvl) / 9);
      toWorld(x, y, z, tmpV);
      sc.set(0.98, h, 0.98);
      tmpM.makeScale(sc.x, sc.y, sc.z);
      tmpM.setPosition(tmpV.x, tmpV.y - 0.5 + h / 2, tmpV.z);
      flowMesh.setMatrixAt(i, tmpM);
    });
    flowMesh.visible = document.getElementById('flow').checked;
    scene.add(flowMesh);
  }

  turtleGroup.visible = document.getElementById('turtle').checked && visibleCut(SX, SY);
  applyXray();
  updateStats(spots.length);
}

function applyXray() {
  blockMat.transparent = state.xray;
  blockMat.opacity = state.xray ? 0.28 : 1;
  blockMat.depthWrite = !state.xray;
  blockMat.needsUpdate = true;
}

// ---------------------------------------------------------------- UI
let digCount = 0, torchTotal = 0, waterTotal = 0, trapTotal = 0;
for (let i = 0; i < grid.length; i++) {
  if (grid[i]) digCount++;
  if (grid[i] === TORCH) torchTotal++;
  if (grid[i] === WATER) waterTotal++;
  if (grid[i] === TRAP) trapTotal++;
}
document.getElementById('size').textContent = `${L} long × ${W} wide × ${H} tall`;

function updateStats(shownTorches) {
  const sw = state.mode === 'mine'
    ? '<span class="key" style="background:#e6cf98"></span>blocks the turtle digs'
    : '<span class="key" style="background:#a8a399"></span>cave walls &nbsp;<span class="key" style="background:#686a70"></span>rock';
  document.getElementById('stats').innerHTML =
    `${digCount.toLocaleString()} blocks to mine<br>${torchTotal} torches` +
    (waterTotal + trapTotal ? `<br>${trapTotal} trapdoors, ${waterTotal} water (placed last)` : '') +
    (FLOW.length ? `<br><span class="key" style="background:#5c98ea"></span>water spreads to ${FLOW.length} blocks` : '') +
    `<br>${sw}<br><span style="color:#5d5b55">${blockCount.toLocaleString()} cubes drawn</span>`;
}

const topEl = document.getElementById('top'), sliceEl = document.getElementById('slice');
topEl.max = H; topEl.value = H;
sliceEl.max = L - 1;

function syncLabels() {
  document.getElementById('topV').textContent = `${state.top} / ${H}`;
  document.getElementById('sliceV').textContent = state.slice === 0 ? 'none' : `${state.slice} rows`;
  topEl.value = state.top; sliceEl.value = state.slice;
}

function setMode(m) {
  state.mode = m;
  document.getElementById('mHollow').classList.toggle('on', m === 'hollow');
  document.getElementById('mMine').classList.toggle('on', m === 'mine');
  // a solid lump of rock shows nothing - open it up so you can see inside
  if (m === 'hollow' && state.slice === 0 && state.top === H) state.slice = Math.floor(L / 2);
  if (m === 'mine') state.slice = 0;
  syncLabels(); rebuild();
}

let pending = 0;
function queueRebuild() { cancelAnimationFrame(pending); pending = requestAnimationFrame(rebuild); }
topEl.addEventListener('input', () => { state.top = +topEl.value; syncLabels(); queueRebuild(); });
sliceEl.addEventListener('input', () => { state.slice = +sliceEl.value; syncLabels(); queueRebuild(); });
document.getElementById('mHollow').onclick = () => setMode('hollow');
document.getElementById('mMine').onclick = () => setMode('mine');
document.getElementById('xray').onchange = e => { state.xray = e.target.checked; applyXray(); };
document.getElementById('torches').onchange = e => { torchGroup.visible = e.target.checked; };
document.getElementById('items').onchange = e => { itemGroup.visible = e.target.checked; };
document.getElementById('flow').onchange = e => { if (flowMesh) flowMesh.visible = e.target.checked; };
document.getElementById('turtle').onchange = e => { turtleGroup.visible = e.target.checked && visibleCut(SX, SY); };
document.getElementById('grid').onchange = e => { gridHelper.visible = e.target.checked; fwdArrow.visible = e.target.checked; };

const centre = new THREE.Vector3(0, H / 2, 0);
function view(kind) {
  const d = maxDim * 1.9 + 6;
  controls.target.copy(centre);
  if (kind === 'top') camera.position.set(0, H / 2 + d, 0.01); // forward = up the screen, like the designer
  else if (kind === 'side') camera.position.set(d, H / 2, 0);
  else camera.position.set(d * 0.55, H / 2 + d * 0.55, d * 0.75); // behind & above the turtle
  controls.update();
}
document.getElementById('vReset').onclick = () => view('reset');
document.getElementById('vTop').onclick = () => view('top');
document.getElementById('vSide').onclick = () => view('side');

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);

resize();
view('reset');
setMode('hollow');
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
window.__minorReady = true;
</script>
</body>
</html>
'''


def main():
    root = tk.Tk()
    app = App(root)
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--resume":
        app.resume_from(args[1], args[2] if len(args) > 2 else "")
    elif args and os.path.isfile(args[0]):
        try:
            with open(args[0]) as f:
                app.d = Design.from_text(f.read())
            app.vL.set(app.d.L); app.vW.set(app.d.W); app.vH.set(app.d.H)
            app.name.set(os.path.splitext(os.path.basename(args[0]))[0])
            app.rebuild_grid()
        except Exception:
            pass
    root.mainloop()


if __name__ == "__main__":
    main()
