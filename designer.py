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
import tkinter as tk
from collections import deque
from tkinter import filedialog, messagebox, ttk

MAX = 64
KEEP, DIG, TORCH = 0, 1, 2
HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN_DIR = os.path.join(HERE, "designs")

COLORS = {
    KEEP: "#3b3b3b",
    DIG: "#e9dcb5",
    TORCH: "#ffa200",
    "ghost": "#565663",   # kept here, but dug on the layer below
    "start": "#3fbf5a",
    "chest": "#8a5a2b",
    "line": "#2a2a2a",
}


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
        self.ghost = tk.BooleanVar(value=True)

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

        body = ttk.Frame(self.root, padding=6)
        body.pack(fill="both", expand=True)

        side = ttk.Frame(body)
        side.pack(side="left", fill="y", padx=(0, 8))

        lay = ttk.LabelFrame(side, text="Layer", padding=6)
        lay.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(lay)
        row.pack()
        ttk.Button(row, text="▼", width=3, command=lambda: self.change_layer(-1)).pack(side="left")
        self.layer_label = ttk.Label(row, text="", width=10, anchor="center")
        self.layer_label.pack(side="left")
        ttk.Button(row, text="▲", width=3, command=lambda: self.change_layer(1)).pack(side="left")
        ttk.Checkbutton(lay, text="Show layer below", variable=self.ghost,
                        command=self.redraw).pack(anchor="w", pady=(4, 0))

        tools = ttk.LabelFrame(side, text="Tool (left mouse)", padding=6)
        tools.pack(fill="x", pady=(0, 6))
        for value, text in (("dig", "Dig pen"), ("keep", "Keep pen (eraser)"),
                            ("torch", "Torch pen"), ("rect", "Dig rectangle"),
                            ("rectkeep", "Keep rectangle"), ("start", "Set turtle start")):
            ttk.Radiobutton(tools, text=text, value=value, variable=self.tool).pack(anchor="w")
        ttk.Label(tools, text="Right mouse = eraser", foreground="#777").pack(anchor="w", pady=(4, 0))

        lay_ops = ttk.LabelFrame(side, text="This layer", padding=6)
        lay_ops.pack(fill="x", pady=(0, 6))
        ttk.Button(lay_ops, text="Fill layer", command=lambda: self.fill_layer(DIG)).pack(fill="x")
        ttk.Button(lay_ops, text="Clear layer", command=lambda: self.fill_layer(KEEP)).pack(fill="x")
        ttk.Button(lay_ops, text="Copy to layer above", command=self.copy_up).pack(fill="x")
        ttk.Button(lay_ops, text="Copy to ALL layers above", command=self.copy_all_up).pack(fill="x")

        shapes = ttk.LabelFrame(side, text="Whole design", padding=6)
        shapes.pack(fill="x", pady=(0, 6))
        for text, fn in (("Box (fill all)", self.shape_box), ("Sphere", self.shape_sphere),
                         ("Dome", self.shape_dome), ("Cylinder", self.shape_cylinder),
                         ("Tunnel (arch)", self.shape_arch), ("Clear all", self.shape_clear)):
            ttk.Button(shapes, text=text, command=fn).pack(fill="x")

        tor = ttk.LabelFrame(side, text="Torches", padding=6)
        tor.pack(fill="x", pady=(0, 6))
        r = ttk.Frame(tor)
        r.pack(fill="x")
        ttk.Label(r, text="Every").pack(side="left")
        ttk.Spinbox(r, from_=2, to=32, textvariable=self.spacing, width=4).pack(side="left", padx=3)
        ttk.Label(r, text="blocks").pack(side="left")
        ttk.Button(tor, text="Auto place torches", command=self.auto_torches).pack(fill="x", pady=(4, 0))
        ttk.Button(tor, text="Remove all torches", command=self.clear_torches).pack(fill="x")

        ttk.Button(side, text="Undo  (Ctrl+Z)", command=self.undo).pack(fill="x", pady=(0, 6))

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
        self.root.bind("<Prior>", lambda e: self.change_layer(1))
        self.root.bind("<Next>", lambda e: self.change_layer(-1))

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")
        self.stats = ttk.Label(bottom, text="")
        self.stats.pack(side="left")
        ttk.Button(bottom, text="Save + Upload to GitHub", command=self.save_upload).pack(side="right")
        ttk.Button(bottom, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(bottom, text="Open...", command=self.open).pack(side="right")

    # ---- grid drawing -------------------------------------------------
    def rebuild_grid(self):
        d = self.d
        self.cell = max(8, min(28, 720 // max(d.L, d.W)))
        c = self.cell
        self.canvas.delete("all")
        self.canvas.config(width=d.W * c + 1, height=(d.L + 1) * c + 1)
        self.rects = {}
        for x in range(d.L):
            for z in range(d.W):
                sy = (d.L - 1 - x) * c
                sx = z * c
                self.rects[(x, z)] = self.canvas.create_rectangle(
                    sx, sy, sx + c, sy + c, outline=COLORS["line"])
        self.redraw()

    def redraw(self):
        d, y = self.d, self.layer
        self.canvas.delete("marker")
        for (x, z), item in self.rects.items():
            v = d.grid[y][x][z]
            color = COLORS[v]
            if v == KEEP and self.ghost.get() and y > 0 and d.grid[y - 1][x][z]:
                color = COLORS["ghost"]
            self.canvas.itemconfig(item, fill=color)
        c = self.cell
        sx, sy, sz = d.start
        if sy == y:
            self.mark(sx, sz, "S", COLORS["start"])
            if sx - 1 >= 0:
                self.mark(sx - 1, sz, "C", COLORS["chest"])
            else:  # chest sits just outside the grid
                px, py = sz * c, d.L * c
                self.canvas.create_rectangle(px, py, px + c, py + c, fill=COLORS["chest"],
                                             outline="", tags="marker")
                self.canvas.create_text(px + c / 2, py + c / 2, text="C", fill="white",
                                        tags="marker", font=("TkDefaultFont", max(7, c // 2)))
        self.layer_label.config(text=f"{y + 1} of {d.H}")
        self.update_stats()

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
        self.d.grid[self.layer][x][z] = value
        v = value
        color = COLORS[v]
        if v == KEEP and self.ghost.get() and self.layer > 0 and self.d.grid[self.layer - 1][x][z]:
            color = COLORS["ghost"]
        self.canvas.itemconfig(self.rects[(x, z)], fill=color)

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
        if tool == "start" and not erase:
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
            messagebox.showinfo("Saved", f"Saved to {path}\n\nOn the turtle: minor {name}\n"
                                         "(upload it to GitHub first, or copy the file over)")
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

    def save_upload(self):
        path = self.save(quiet=True)
        if not path:
            return
        name = self.name.get()

        def git(*args):
            return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)

        try:
            if git("rev-parse", "--is-inside-work-tree").returncode != 0:
                messagebox.showerror("Upload", "This folder isn't a git repository.\n\n"
                                               "Download it with:  git clone <your repo url>\n"
                                               "and run designer.py from inside it.")
                return
        except FileNotFoundError:
            messagebox.showerror("Upload", "Git isn't installed. Get it from git-scm.com")
            return

        git("add", path)
        commit = git("commit", "-m", f"Update design {name}")
        git("pull", "--rebase")
        push = git("push")
        if push.returncode != 0:
            messagebox.showerror("Upload", "Push failed:\n\n" + (push.stderr or commit.stdout)[-800:])
            return
        messagebox.showinfo("Uploaded", f"Uploaded!\n\nOn the turtle type:\n    minor {name}\n\n"
                                        "(GitHub can take a minute to show the new version.)")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
