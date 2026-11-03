# minor

A turtle program for CC: Tweaked (ComputerCraft) that digs out rooms and custom shapes up to **64 × 64 × 64** and places torches. It comes with a Python designer you run on your PC to draw what to dig.

## Install on a turtle

```
wget run https://raw.githubusercontent.com/yetimafia/minor/main/install.lua
```

Update later with `minor update`.

## Dig a plain room

```
minor box <length> <width> <height>
minor box 20 15 6
```

Put the turtle in the **front-left-bottom corner** of the room. It digs forward, to the right, and up.

## Dig a design

```
minor dome
minor tunnel
minor <your design name>
```

The turtle downloads the newest version of the design from this repo each time. Put it where the design's green **S** is, facing the way the designer grid points (up).

## Before you start

- Put a **chest directly behind** the turtle. When the turtle fills up, it comes back and empties into it.
- Put **fuel** (coal, charcoal, lava buckets…) in the turtle. If it runs low it burns coal it has dug up. If that's not enough, it comes home and asks for more.
- Put **torches** in the turtle. It places them after digging and keeps them when it empties into the chest. Add `notorch` to skip torches: `minor box 20 20 5 notorch`.

## The designer (on your PC)

Download `designer.py`, or clone the repo, and run:

```
python designer.py
```

You only need Python 3. On Windows, get it from python.org; tkinter is included.

### Drawing

- You see one layer at a time from above. ▲/▼ (or Page Up/Down) changes layers.
- **Light** squares get dug, **dark** squares are left alone, and **orange** squares get dug and get a torch.
- Tools: dig pen, eraser (right-click always erases), torch pen, rectangles, and *Set turtle start*. The green **S** is the start and the brown **C** is the chest.
- Shape buttons: box, sphere, dome, cylinder, and arch tunnel. *Copy to ALL layers above* turns a floor plan into a 3D room.
- *Auto place torches* puts torches on the floor every N blocks.
- The bottom bar shows block count, fuel needed, and warnings.

### Sending it to the turtle

1. Click **1. Upload to GitHub**. The first time, it asks for a GitHub token:
   - Go to **github.com/settings/personal-access-tokens/new**.
   - *Repository access*: Only select repositories → `minor`.
   - *Permissions → Repository permissions → Contents*: **Read and write**.
   - Generate the token and paste it in. It's saved in `minor_settings.json` on your PC only and is never uploaded.
2. Click **2. Copy turtle command**.
3. Click the turtle's screen, press **Ctrl+V**, then **Enter**. It installs or updates `minor` and digs your design. It works on a brand-new turtle too.

## Design file format

```
minor-design 1
size <length> <width> <height>
start <x> <y> <z>
layer 0
<one line per row, run-length: 3.10#1T>   . keep   # dig   T dig + torch
```
