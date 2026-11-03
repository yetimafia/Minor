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

```
git clone https://github.com/yetimafia/minor
cd minor
python designer.py
```

You only need Python 3. On Windows, get it from python.org; tkinter is included.

- You see one layer at a time from above. ▲/▼ (or Page Up/Down) changes layers.
- **Light** squares get dug, **dark** squares are left alone, and **orange** squares get dug and get a torch.
- Tools: dig pen, eraser (right-click always erases), torch pen, rectangles, and *Set turtle start*.
- Shape buttons: box, sphere, dome, cylinder, and arch tunnel. *Copy to ALL layers above* turns a floor plan into a 3D room.
- *Auto place torches* puts torches on the floor every N blocks. The room needs to be at least 2 tall there.
- The bottom bar shows block count, fuel needed, and a warning if part of the design isn't connected to the start. If a part isn't connected, the turtle digs a small tunnel to reach it.
- **Save + Upload to GitHub** saves `designs/<name>.txt` and pushes it. Then on the turtle, type `minor <name>`.

Upload needs Git installed and signed in to GitHub (git-scm.com). If you don't use Git, upload the `.txt` file into the `designs` folder on github.com instead.

## Design file format

```
minor-design 1
size <length> <width> <height>
start <x> <y> <z>
layer 0
<one line per row, run-length: 3.10#1T>   . keep   # dig   T dig + torch
```
