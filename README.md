# minor

A turtle program for CC: Tweaked (ComputerCraft) that digs out rooms and custom shapes up to **64 × 64 × 64** and places torches. It comes with a Python designer you run on your PC to draw what to dig.

## Install on a turtle

```
wget run https://raw.githubusercontent.com/yetimafia/Minor/main/install.lua
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
- If your design has **trapdoors** or **water**, put trapdoors and water buckets in the turtle (one bucket per water spot). They're placed **at the very end**, after everything is dug: trapdoors first, then water. The turtle never burns or unloads them, and comes home to ask if it runs out.
- The turtle digs **bottom up**: it finishes each 3-block-high band of layers completely before moving up, so there are no dark half-dug spaces left below it.
- Put **torches** in the turtle. It **lights the room first**: it digs a path to each torch spot and places the torch, then digs out everything else, so mobs can't spawn while it works. It keeps torches when it empties into the chest, and comes home to ask for more if it runs out. Add `notorch` to skip torches: `minor box 20 20 5 notorch`.

## Opening trapdoors (datapack)

When **Open them after placing** is checked in the designer (it's on by default), the turtle clicks each trapdoor open with a **stick** right after placing it. Put 1 stick in the turtle.

Plain CC: Tweaked doesn't let turtles click trapdoors, so the world needs a tiny datapack that adds wooden trapdoors to CC's list of blocks turtles may use:

1. Download [`datapack/minor_trapdoors.zip`](datapack/minor_trapdoors.zip).
2. Put the zip, without unzipping it, in your world's `datapacks` folder:
   - Singleplayer: `.minecraft/saves/<your world>/datapacks/`
   - Server: `<server>/world/datapacks/`
3. Run `/reload`, or reopen the world.

Without the datapack, the turtle notices the trapdoor didn't open, leaves the rest closed, and tells you at the end. Iron trapdoors can't be opened by clicking, even by players.

## The designer (on your PC)

Download the designer straight from this link (right-click, then *Save link as*):

**https://raw.githubusercontent.com/yetimafia/Minor/main/designer.py**

Or clone the repo. Then run:

```
python designer.py
```

You only need Python 3. On Windows, get it from python.org; tkinter is included.

### Tabs (auto-saved)

The designer has **5 tabs** across the top, and each one holds its own design. Everything is saved automatically a couple of seconds after each change, when you switch tabs, and when you close the designer. All 5 tabs come back next time you open it, and after **Update designer**. *New in this tab* starts a blank design in the current tab. The tabs are stored in `designs/_tabs/` on your PC; they don't get uploaded.

### Opening designs from a link

**Open from URL...** (next to *Open...*) loads a design from the web into the current tab. You can paste:
- a raw link (`https://raw.githubusercontent.com/.../designs/name.txt`)
- a normal GitHub file link (`https://github.com/.../blob/main/designs/name.txt`)
- the whole turtle command from *Copy turtle command*

It also lists every design in your repo, so you can double-click one to open it. If you copied a link before opening the window, it's filled in for you.

### Drawing

- You see one layer at a time from above. ▲/▼ (or Page Up/Down) changes layers.
- **Show neighbour layer** (or press **G**) switches between seeing what's dug on the layer below (blue), the layer above (red), or neither.
- **Light** squares get dug, **dark** squares are left alone, and **orange** squares get dug and get a torch.
- Tools: dig pen, eraser (right-click always erases), torch pen, **trapdoor pen**, **water bucket pen**, rectangles, and *Set turtle start*. Trapdoor and water squares get dug like normal, then get their item placed at the end. The green **S** is the start and the brown **C** is the chest.
- Shape buttons: box, sphere, dome, cylinder, and arch tunnel. *Copy to ALL layers above* turns a floor plan into a 3D room.
- **★ Shape through layers** stamps a rectangle, circle, ring, walls, diamond or plus across a range of layers. Give it a size for the first and last layer and it grows or shrinks in between, so you can make cones, pyramids, round towers and funnels. It can also *leave solid*, which cuts a pillar out of a room.
- **Show water flow** previews where each water bucket will spread, using Minecraft's rules: up to 7 blocks out, shallower each block, falling down holes and heading toward a nearby drop. Walls and closed trapdoors stop it. The bottom bar warns you if water would wash away torches. The preview assumes everything outside your design is solid; real cave openings can let water escape.
- *Auto place torches* puts torches on the floor every N blocks.
- **Move the turtle:** drag the green **S**, or use the arrows in *Turtle start*. ▲▼◀▶ move it forward, back, left and right, and *Up*/*Down* move it between layers. The chest always goes right behind it.
- The bottom bar shows block count, fuel needed, and warnings.

### 3D view

Click **3D view** in the top bar (or press **Ctrl+D**). Your design opens in a Chrome tab as a 3D model, made with three.js r149.

- **Hollowed out:** solid rock with your mined space carved out. Cave walls are lighter, so the shape stands out, and it opens cut in half so you can see inside.
- **Blocks to mine:** only the blocks the turtle will dig.
- **Show up to layer** and **Slice from turtle side** cut the model open. **See-through** shows torches inside.
- Left-drag rotates, right-drag moves, and scrolling zooms. *Top* view matches the designer grid.

It needs an internet connection to load three.js. If Chrome isn't installed, it opens in your default browser.

### Updating the designer

Click **⟳ Update designer**. It downloads the newest version, closes, and reopens with your current design still open. The old version is kept as `designer.py.bak`.

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
<one line per row, run-length: 3.10#1T>   . keep   # dig   T torch   D trapdoor   W water
```
