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
import json
import ssl
import urllib.error
import urllib.request
import tkinter as tk
from collections import deque
from tkinter import filedialog, messagebox, ttk

MAX = 64
KEEP, DIG, TORCH = 0, 1, 2
HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(HERE, "designs")
SETTINGS_FILE = os.path.join(HERE, "minor_settings.json")
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

COLORS = {
    "start": "#3fbf5a",
    "chest": "#8a5a2b",
    "line": "#1e1f23",
}

# tile looks: (base, highlight, shadow)
STYLE = {
    DIG:     ("#e6cf98", "#fff3d2", "#b38f52"),   # dug - warm sandy tile
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


def jitter(x, y, z):
    """Small fixed per-block colour variation so tiles look textured."""
    h = (x * 73856093) ^ (z * 19349663) ^ (y * 83492791)
    return (h % 7 - 3) * 4


class Design:
    def __init__(self, length=16, width=16, height=6):
        self.L, self.W, self.H = length, width, height
        self.grid = [[[KEEP] * width for _ in range(length)] for _ in range(height)]
        self.start = (0, 0, 0)  # x (forward), y (up), z (right)

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
        chars = {KEEP: ".", DIG: "#", TORCH: "T"}
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
        values = {".": KEEP, "#": DIG, "T": TORCH}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("size "):
                L, W, H = map(int, line.split()[1:4])
                d = cls(L, W, H)
            elif line.startswith("start ") and d:
                sx, sy, sz = map(int, line.split()[1:4])
                d.start = (sx, sy, sz)
            elif line.startswith("layer ") and d:
                y, x = int(line.split()[1]), 0
            elif d and y >= 0 and x < d.L and line:
                z = 0
                for count, ch in re.findall(r"(\d+)([.#T])", line):
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
        self.settings = load_settings()
        self.uploaded = {}  # design name -> commit sha of last upload
        self.command = tk.StringVar(value="")

        self.build_ui()
        self.rebuild_grid()

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

        tools = ttk.LabelFrame(side_a, text="Tool (left mouse)", padding=6)
        tools.pack(fill="x", pady=(0, 6))
        for value, text in (("dig", "Dig pen"), ("keep", "Keep pen (eraser)"),
                            ("torch", "Torch pen"), ("rect", "Dig rectangle"),
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
        self.root.bind("<g>", lambda e: self.cycle_ghost())
        self.root.bind("<G>", lambda e: self.cycle_ghost())
        self.root.bind("<Prior>", lambda e: self.change_layer(1))
        self.root.bind("<Next>", lambda e: self.change_layer(-1))

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")
        self.stats = ttk.Label(bottom, text="")
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
        text = f"{dig} blocks to dig   |   {torches} torches   |   ~{fuel} fuel (~{fuel // 80 + 1} coal)"
        bad = self.d.unreachable()
        if bad:
            text += f"   |   ⚠ {bad} blocks not connected to the start (turtle will tunnel to them)"
        d = self.d
        stuck = sum(1 for y in range(d.H) for x in range(d.L) for z in range(d.W)
                    if d.grid[y][x][z] == TORCH and not (y + 1 < d.H and d.grid[y + 1][x][z]))
        if stuck:
            text += f"   |   ⚠ {stuck} torches have no dug space above (turtle places from above - they'll be skipped)"
        sx, sy, sz = self.d.start
        if sx - 1 >= 0 and self.d.grid[sy][sx - 1][sz]:
            text += "   |   ⚠ chest spot is marked to dig (it'll be skipped)"
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
        self.d.grid[self.layer][x][z] = value
        self.draw_cell(x, z)

    def pen_value(self, erase):
        if erase:
            return KEEP
        return {"dig": DIG, "keep": KEEP, "torch": TORCH}.get(self.tool.get())

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
        d = self.d
        self.history.append((d.L, d.W, d.H, [[row[:] for row in layer] for layer in d.grid], d.start))
        self.history = self.history[-40:]

    def undo(self):
        if not self.history:
            return
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
                    if d.grid[y][x][z] and floor and room_above and (x, y, z) != d.start:
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

        # save what's open so the new version can load it
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
