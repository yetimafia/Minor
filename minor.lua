-- minor: carve rooms and custom designs with a CC: Tweaked turtle
--
--   minor box <length> <width> <height>   dig a plain room (max 64 each)
--   minor <design>                        dig a design made with designer.py
--   minor <url>                           dig a design straight from a link
--   minor update                          download the newest minor
--   minor test                            check version, items and trapdoor opening
--   add "notorch" to skip placing torches
--
-- Order of work: light the room (torches), dig everything, then place
-- trapdoors and finally water buckets.
--
-- Box rooms: the turtle sits in the FRONT-LEFT-BOTTOM corner and digs
-- forward, right and up. Designs: the turtle sits where the design's
-- start marker is, facing "up" on the designer's grid.
-- Put a CHEST directly BEHIND the turtle. Put fuel and torches in the turtle.

local REPO   = "yetimafia/Minor"   -- GitHub "user/repo"
local BRANCH = "main"
local BASE   = "https://raw.githubusercontent.com/" .. REPO .. "/" .. BRANCH .. "/"
local MAX    = 64
local TORCH_SPACING = 8

---------------------------------------------------------------- helpers
local yieldCount = 0
local function maybeYield()
  yieldCount = yieldCount + 1
  if yieldCount >= 4000 then
    yieldCount = 0
    os.queueEvent("minor_yield")
    os.pullEvent("minor_yield")
  end
end

local function waitForUser(msg)
  print(msg)
  print("Press any key to continue...")
  os.pullEvent("key")
end

local function download(path, dest, isUrl)
  if not http then return false, "HTTP is turned off in the server config" end
  local url = isUrl and path or (BASE .. path .. "?t=" .. os.epoch("utc"))
  local h, err = http.get(url)
  if not h then return false, err or "not found" end
  local data = h.readAll()
  h.close()
  local f = fs.open(dest, "w")
  f.write(data)
  f.close()
  return true
end

local function valid(n) return n and n >= 1 and n <= MAX and n == math.floor(n) end

local function askNumber(name)
  while true do
    write(name .. " (1-" .. MAX .. "): ")
    local n = tonumber(read())
    if valid(n) then return n end
    print("Please enter a whole number from 1 to " .. MAX .. ".")
  end
end

---------------------------------------------------------------- arguments
local args, useTorches = {}, true
for _, a in ipairs({ ... }) do
  if a:lower() == "notorch" or a:lower() == "notorches" then useTorches = false
  else args[#args + 1] = a end
end

if args[1] == "test" then
  term.clear(); term.setCursorPos(1, 1)
  print("== minor test ==")
  local host = tostring(_HOST)
  print(host)
  local maj, mnr = host:match("ComputerCraft (%d+)%.(%d+)")
  local newEnough = maj and (tonumber(maj) > 1 or tonumber(mnr) >= 104)
  print("HTTP: " .. (http and "on" or "OFF (ask the server owner)"))
  print("Fuel: " .. tostring(turtle.getFuelLevel()))
  local trap, stick = nil, nil
  local items = {}
  for i = 1, 16 do
    local d = turtle.getItemDetail(i)
    if d then
      items[#items + 1] = d.name:gsub("^minecraft:", "") .. " x" .. d.count
      if d.name:find("trapdoor") and not trap then trap = i end
      if d.name == "minecraft:stick" and not stick then stick = i end
    end
  end
  print("Items: " .. (#items > 0 and table.concat(items, ", ") or "none"))
  if maj and not newEnough then
    print("")
    print("This CC: Tweaked is older than 1.104,")
    print("so turtles can't open trapdoors at all.")
    print("Trapdoors will be placed closed.")
    return
  end
  if not (trap and stick) then
    print("")
    print("For a trapdoor test, give me 1 trapdoor")
    print("and 1 stick, with an empty space in front.")
    return
  end
  if turtle.detect() then
    print("")
    print("Clear the block in front of me to test.")
    return
  end
  turtle.select(trap)
  local ok, err = turtle.place()
  if not ok then
    print("Couldn't place the test trapdoor: " .. tostring(err))
    turtle.select(1)
    return
  end
  turtle.select(stick)
  local _, useErr = turtle.place()
  local seen, data = turtle.inspect()
  local isOpen = seen and data.state and data.state.open
  if isOpen then
    print("Trapdoor test: OPENED - all good!")
  else
    print("Trapdoor test: did NOT open (" .. tostring(useErr) .. ")")
    print("-> Put minor_trapdoors.zip in the world's")
    print("   datapacks folder and run /reload.")
    print("   Check it with /datapack list")
  end
  turtle.select(trap)
  turtle.dig() -- take the test trapdoor back
  turtle.select(1)
  return
end

if args[1] == "update" then
  local ok, err = download("minor.lua", shell.getRunningProgram())
  print(ok and "minor updated!" or ("Update failed: " .. tostring(err)))
  return
end

---------------------------------------------------------------- the world
-- x = forward, z = right, y = up
-- st values: 0 leave alone, 1 needs digging, 2 open, 3 torch placed, 4 chest
local L, W, H
local st, torchAt, waterAt, trapAt = {}, {}, {}, {}
local openTraps = false -- older design files: "trapdoors open" = open every trapdoor
local sx, sy, sz = 0, 0, 0 -- start position
local todo, tunnels = 0, 0

local function id(x, y, z) return x + L * (z + W * y) + 1 end
local function inb(x, y, z)
  return x >= 0 and x < L and y >= 0 and y < H and z >= 0 and z < W
end
local function get(x, y, z)
  if not inb(x, y, z) then return -1 end
  return st[id(x, y, z)]
end
local function decode(i)
  i = i - 1
  local x = i % L; i = math.floor(i / L)
  local z = i % W
  return x, math.floor(i / W), z
end

local function makeBox(l, w, h)
  L, W, H = l, w, h
  for i = 1, L * W * H do st[i] = 1 end
  -- automatic torches on the floor, only if the room is 2+ tall
  if H >= 2 then
    local ox = math.floor(((L - 1) % TORCH_SPACING) / 2)
    local oz = math.floor(((W - 1) % TORCH_SPACING) / 2)
    for x = ox, L - 1, TORCH_SPACING do
      for z = oz, W - 1, TORCH_SPACING do torchAt[id(x, 0, z)] = true end
    end
  end
end

local function loadDesign(path)
  local f = fs.open(path, "r")
  if not f then error("Can't open " .. path) end
  local header = f.readLine()
  if not header or not header:find("^minor%-design") then
    f.close(); error(path .. " is not a minor design file")
  end
  local y = -1
  local x = 0
  while true do
    local line = f.readLine()
    if not line then break end
    local a, b, c = line:match("^size (%d+) (%d+) (%d+)")
    if a then
      L, W, H = tonumber(a), tonumber(b), tonumber(c)
      for i = 1, L * W * H do st[i] = 0 end
    elseif line:match("^start ") then
      local p, q, r = line:match("^start (%d+) (%d+) (%d+)")
      sx, sy, sz = tonumber(p), tonumber(q), tonumber(r)
    elseif line:match("^trapdoors open") then
      openTraps = true
    elseif line:match("^layer ") then
      y = tonumber(line:match("^layer (%d+)")); x = 0
    elseif y >= 0 and x < L and line ~= "" then
      local z = 0
      for count, ch in line:gmatch("(%d+)([%.#TWDO])") do
        for _ = 1, tonumber(count) do
          if z < W then
            if ch ~= "." then
              local i = id(x, y, z)
              st[i] = 1
              if ch == "T" then torchAt[i] = true
              elseif ch == "W" then waterAt[i] = true
              elseif ch == "D" then trapAt[i] = "closed"
              elseif ch == "O" then trapAt[i] = "open" end
            end
            z = z + 1
          end
        end
      end
      x = x + 1
      maybeYield()
    end
  end
  f.close()
  if not L then error("Design has no size line") end
end

-- figure out what to dig
term.clear(); term.setCursorPos(1, 1)
print("== Minor ==")
local mode = args[1]
if not mode then
  write("Design name (or 'box'): ")
  mode = read()
end

if mode == "box" then
  makeBox(valid(tonumber(args[2])) and tonumber(args[2]) or askNumber("Length (forward)"),
          valid(tonumber(args[3])) and tonumber(args[3]) or askNumber("Width (right)"),
          valid(tonumber(args[4])) and tonumber(args[4]) or askNumber("Height (up)"))
else
  local ok, err, localPath
  if mode:find("^https?://") then
    local name = mode:match("([^/]+)%.txt$") or "download"
    localPath = "designs/" .. name .. ".txt"
    write("Downloading design '" .. name .. "'... ")
    ok, err = download(mode, localPath, true)
    if ok then print("done.")
    elseif fs.exists(localPath) then print("failed, using saved copy.")
    else error("Couldn't download the design: " .. tostring(err)) end
  else
    local name = mode:gsub("%.txt$", "")
    localPath = "designs/" .. name .. ".txt"
    write("Getting design '" .. name .. "'... ")
    ok, err = download("designs/" .. name .. ".txt", localPath)
    if ok then print("downloaded.")
    elseif fs.exists(localPath) then print("using saved copy.")
    elseif fs.exists(name) then localPath = name; print("using local file.")
    else error("Couldn't find design '" .. name .. "': " .. tostring(err)) end
  end
  loadDesign(localPath)
end

-- the start cell is always open; the chest cell is never touched
if not inb(sx, sy, sz) then error("Design start is outside the design") end
st[id(sx, sy, sz)] = 2
torchAt[id(sx, sy, sz)] = nil
waterAt[id(sx, sy, sz)] = nil
trapAt[id(sx, sy, sz)] = nil
if inb(sx - 1, sy, sz) then
  if st[id(sx - 1, sy, sz)] == 1 then
    print("Note: the chest spot is part of the design - I'll leave it.")
  end
  st[id(sx - 1, sy, sz)] = 4
end
for i = 1, L * W * H do
  if st[i] == 1 then todo = todo + 1 end
  if st[i] ~= 1 and st[i] ~= 2 then torchAt[i] = nil; waterAt[i] = nil; trapAt[i] = nil end
end
if not useTorches then torchAt = {} end

---------------------------------------------------------------- moving
-- dir: 0=forward(+x) 1=right(+z) 2=back(-x) 3=left(-z)
local x, y, z, dir = sx, sy, sz, 0
local DX = { [0] = 1, 0, -1, 0 }
local DZ = { [0] = 0, 1, 0, -1 }
local total = todo

local function turnRight() turtle.turnRight(); dir = (dir + 1) % 4 end
local function turnLeft()  turtle.turnLeft();  dir = (dir + 3) % 4 end
local function face(d)
  local diff = (d - dir) % 4
  if diff == 1 then turnRight()
  elseif diff == 2 then turnRight(); turnRight()
  elseif diff == 3 then turnLeft() end
end

local function opened(i)
  if st[i] == 1 then todo = todo - 1
  elseif st[i] == 0 then tunnels = tunnels + 1
  elseif st[i] == 3 then torchAt[i] = true end -- walked through a torch: put it back later
  st[i] = 2
end

local function move(moveFn, detectFn, digFn, attackFn)
  local tries = 0
  while not moveFn() do
    if detectFn() then
      if not digFn() then tries = tries + 10 end
    else
      attackFn()
    end
    tries = tries + 1
    if tries > 300 then
      waitForUser("I'm stuck (bedrock or a protected block?). Clear the way.")
      tries = 0
    end
  end
end

local function arrive()
  if inb(x, y, z) then opened(id(x, y, z)) end
end

local function forward()
  move(turtle.forward, turtle.detect, turtle.dig, turtle.attack)
  x = x + DX[dir]; z = z + DZ[dir]; arrive()
end
local function up()
  move(turtle.up, turtle.detectUp, turtle.digUp, turtle.attackUp)
  y = y + 1; arrive()
end
local function down()
  move(turtle.down, turtle.detectDown, turtle.digDown, turtle.attackDown)
  y = y - 1; arrive()
end

local function stepTo(nx, ny, nz)
  if ny > y then up()
  elseif ny < y then down()
  else
    local d
    if nx > x then d = 0 elseif nz > z then d = 1 elseif nx < x then d = 2 else d = 3 end
    face(d); forward()
  end
end

-- dig neighbours without moving (only if the design says so)
local function digAbove()
  if get(x, y + 1, z) ~= 1 then return end
  local n = 0
  while turtle.detectUp() and n < 64 do
    if not turtle.digUp() then break end
    n = n + 1
  end
  opened(id(x, y + 1, z))
end
local function digBelow()
  if get(x, y - 1, z) ~= 1 then return end
  if turtle.detectDown() then turtle.digDown() end
  opened(id(x, y - 1, z))
end

-- breadth-first search from the turtle. Returns a list of cells to walk.
-- allow: nil = open cells only, "torch" = may walk through placed torches,
-- "marked" = may dig through blocks the design says to dig (not torch spots),
-- true = may also tunnel through blocks the design says to keep.
local NB = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 0, 1 }, { 0, 0, -1 }, { 0, 1, 0 }, { 0, -1, 0 } }
local function findPath(isGoal, allow)
  if not inb(x, y, z) then return nil end
  local start = id(x, y, z)
  local prev = { [start] = 0 }
  local queue, head = { start }, 1
  while head <= #queue do
    local ci = queue[head]; head = head + 1
    local cx, cy, cz = decode(ci)
    if isGoal(cx, cy, cz) then
      local path = {}
      while ci ~= start do
        table.insert(path, 1, ci)
        ci = prev[ci]
      end
      return path
    end
    for _, n in ipairs(NB) do
      local nx, ny, nz = cx + n[1], cy + n[2], cz + n[3]
      if inb(nx, ny, nz) then
        local ni = id(nx, ny, nz)
        local s = st[ni]
        local ok = s == 2
          or (allow == "torch" and s == 3)
          or (allow == "marked" and s == 1 and not torchAt[ni])
          or (allow == true and (s == 0 or s == 1))
        if not prev[ni] and ok then
          prev[ni] = ci
          queue[#queue + 1] = ni
        end
      end
    end
    maybeYield()
  end
  return nil
end

local function walk(path)
  for _, ci in ipairs(path) do stepTo(decode(ci)) end
end

---------------------------------------------------------------- items & fuel
local function fuel()
  local f = turtle.getFuelLevel()
  if f == "unlimited" then return math.huge end
  return f
end

-- items the turtle keeps (never burns or drops in the chest)
local KINDS = {
  torch    = function(n) return n:find("torch") ~= nil end,
  water    = function(n) return n:find("water_bucket") ~= nil end,
  trapdoor = function(n) return n:find("trapdoor") ~= nil end,
  stick    = function(n) return n == "minecraft:stick" end, -- used to click trapdoors open
}
local KIND_NAMES = { torch = "torches", water = "water buckets", trapdoor = "trapdoors", stick = "sticks" }

local function kindOf(i)
  local d = turtle.getItemDetail(i)
  if not d then return nil end
  for k, test in pairs(KINDS) do
    if test(d.name) then return k end
  end
end

local function isTorch(i) return kindOf(i) == "torch" end
local function isKept(i) return kindOf(i) ~= nil end

local function itemSlot(kind)
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and kindOf(i) == kind then return i end
  end
end

local function refuelFromInventory()
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and not isKept(i) then  -- never burn wooden trapdoors
      turtle.select(i)
      if turtle.refuel(0) then turtle.refuel() end
    end
  end
  turtle.select(1)
end

local function hasEmptySlot()
  for i = 1, 16 do
    if turtle.getItemCount(i) == 0 then return true end
  end
  return false
end

local function torchSlot() return itemSlot("torch") end

local function unload()
  face(2)
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and not isKept(i) then
      turtle.select(i)
      while turtle.getItemCount(i) > 0 do
        if not turtle.detect() then
          waitForUser("No chest behind me! Place one.")
        elseif not turtle.drop() then
          waitForUser("The chest is full! Empty it.")
        end
      end
    end
  end
  turtle.select(1)
end

local function goHome()
  local home = function(a, b, c) return a == sx and b == sy and c == sz end
  walk(findPath(home) or findPath(home, "torch") or findPath(home, true) or {})
end

local function goBack(tx, ty, tz, td)
  local there = function(a, b, c) return a == tx and b == ty and c == tz end
  walk(findPath(there) or findPath(there, "torch") or {})
  face(td)
end

-- need: nil/false, true (= torches), or "torch" / "water" / "trapdoor"
local function tripHome(need)
  if need == true then need = "torch" end
  local bx, by, bz, bd = x, y, z, dir
  local dist = math.abs(bx - sx) + math.abs(by - sy) + math.abs(bz - sz)
  goHome()
  unload()
  refuelFromInventory()
  while fuel() < dist * 3 + 100 do
    waitForUser("I need fuel! Put coal in my inventory.")
    refuelFromInventory()
  end
  while need and not itemSlot(need) do
    waitForUser("I need " .. KIND_NAMES[need] .. "! Put some in my inventory.")
  end
  goBack(bx, by, bz, bd)
end

local function checkup()
  local dist = math.abs(x - sx) + math.abs(y - sy) + math.abs(z - sz)
  if fuel() < dist * 2 + 100 then
    refuelFromInventory()
    if fuel() < dist * 2 + 100 then tripHome(false); return end
  end
  if not hasEmptySlot() then tripHome(false) end
end

local lastShown = -1
local function progress(label)
  local pct = total > 0 and math.floor((total - todo) / total * 100) or 100
  if pct == lastShown then return end
  lastShown = pct
  term.setCursorPos(1, 1); term.clearLine()
  write(("%s %d%%  fuel:%s"):format(label, pct,
    fuel() == math.huge and "inf" or tostring(fuel())))
end

---------------------------------------------------------------- start
turtle.select(1)
refuelFromInventory()
local torchCount, noRoom = 0, 0
for i in pairs(torchAt) do
  local tx, ty, tz = decode(i)
  local above = get(tx, ty + 1, tz)
  if above == 1 or above == 2 then
    torchCount = torchCount + 1
  else
    torchAt[i] = nil -- nowhere to stand above it
    noRoom = noRoom + 1
  end
end
if noRoom > 0 then
  print(noRoom .. " torch spots have no space above - skipping those")
end
local waterCount, trapCount = 0, 0
for _ in pairs(waterAt) do waterCount = waterCount + 1 end
for _ in pairs(trapAt) do trapCount = trapCount + 1 end
if waterCount + trapCount > 0 then
  print(("At the end: %d trapdoors, %d water buckets"):format(trapCount, waterCount))
end
local openCount = 0
for _, how in pairs(trapAt) do
  if how == "open" or openTraps then openCount = openCount + 1 end
end
if openCount > 0 then
  print(openCount .. " trapdoors get opened: put 1 stick in me")
end
print(("Size %d x %d x %d, %d blocks to dig"):format(L, W, H, todo))
if torchCount > 0 then print(torchCount .. " torches - I'll light the room first") end
if fuel() ~= math.huge then
  print(("Fuel: %d   Rough need: %d"):format(fuel(), math.floor(todo / 2.5) + L + W + H))
end
print("Chest goes BEHIND me.")
waitForUser("Ready?")
if torchCount > 0 and not torchSlot() then
  waitForUser("I have no torches! Put some in me, or I'll skip them.")
  if not torchSlot() then
    print("No torches - skipping them.")
    torchAt = {}
    torchCount = 0
    sleep(1)
  end
end
term.clear()

---------------------------------------------------------------- light first
-- Dig a path to each torch spot and place the torch before digging the rest,
-- so the room is lit while the turtle works.
local function solidBelow(cx, cy, cz)
  local s = get(cx, cy - 1, cz)
  return s == 0 or s == -1 or s == 4
end

local function canLight(i)
  return torchAt[i] and (st[i] == 1 or st[i] == 2)
end

-- Torches are only ever placed from DIRECTLY ABOVE (placeDown), so they
-- always stand on the floor. Placing sideways would stick them on a wall.
-- Standing at (cx,cy,cz): is the block under me a torch spot with floor under it?
local function lightSpot(cx, cy, cz)
  if inb(cx, cy - 1, cz) and canLight(id(cx, cy - 1, cz)) and solidBelow(cx, cy - 1, cz) then
    return "down"
  end
end

local function placeTorchFrom()
  if not torchSlot() then tripHome(true) end
  local ti = id(x, y - 1, z)
  if st[ti] == 1 then
    local n = 0
    while turtle.detectDown() and n < 64 do
      if not turtle.digDown() then break end
      n = n + 1
    end
    opened(ti)
  end
  turtle.select(torchSlot() or 1)
  local ok = turtle.placeDown()
  turtle.select(1)
  torchAt[ti] = nil
  if ok then st[ti] = 3 end
  return ok
end

local lit = 0
while torchCount > 0 do
  checkup()
  local path = findPath(function(a, b, c) return lightSpot(a, b, c) ~= nil end, "marked")
  if not path then break end
  walk(path)
  if not lightSpot(x, y, z) then break end
  if placeTorchFrom() then lit = lit + 1 end
  term.setCursorPos(1, 1); term.clearLine()
  write(("Lighting: %d of %d torches"):format(lit, torchCount))
end

---------------------------------------------------------------- dig
-- Bottom up: the design is split into 3-high bands (layers 1-3, 4-6, ...).
-- Each band is finished completely before the turtle moves up to the next,
-- so it never leaves dark, half-dug spaces below it.
local band = nil                       -- band being dug (nil = anything left)
local bandTodo = {}
local function bandOf(cy) return math.floor(cy / 3) end
for i = 1, L * W * H do
  if st[i] == 1 then
    local _, cy = decode(i)
    local b = bandOf(cy)
    bandTodo[b] = (bandTodo[b] or 0) + 1
  end
end

-- keep the band counts right whenever any block gets dug
local plainOpened = opened
opened = function(i)
  if st[i] == 1 then
    local _, cy = decode(i)
    local b = bandOf(cy)
    bandTodo[b] = bandTodo[b] - 1
  end
  plainOpened(i)
end

local function want(cx, cy, cz)
  return get(cx, cy, cz) == 1 and (band == nil or bandOf(cy) == band)
end

local function hasWantNeighbour(cx, cy, cz)
  for _, n in ipairs(NB) do
    if want(cx + n[1], cy + n[2], cz + n[3]) then return true end
  end
  return false
end

local function remaining()
  if band then return bandTodo[band] or 0 end
  return todo
end

local function digLoop(label)
  while remaining() > 0 do
    checkup()
    progress(label)
    -- stand in the middle of each 3-high band so up/down get dug for free
    if y % 3 ~= 1 and want(x, y + 1, z) then
      up()
    else
      if want(x, y + 1, z) then digAbove() end
      if want(x, y - 1, z) then digBelow() end
      -- walk into an undug neighbour: forward, right, left, back
      local moved = false
      for _, turn in ipairs({ 0, 1, 3, 2 }) do
        local d = (dir + turn) % 4
        if want(x + DX[d], y, z + DZ[d]) then
          face(d); forward(); moved = true
          break
        end
      end
      if not moved and remaining() > 0 then
        local path = findPath(hasWantNeighbour)
          or findPath(hasWantNeighbour, "marked")
          or findPath(hasWantNeighbour, "torch")
        if path then
          walk(path)
        elseif band then
          return -- rest of this band can't be reached yet; picked up at the end
        else
          -- part of the design isn't connected: tunnel to it
          path = findPath(function(a, b, c) return get(a, b, c) == 1 end, true)
          if not path then return end
          walk(path)
        end
      end
    end
  end
end

local bands = math.floor((H - 1) / 3) + 1
for b = 0, bands - 1 do
  if (bandTodo[b] or 0) > 0 then
    band = b
    local top = math.min(H, b * 3 + 3)
    digLoop(("Layers %d-%d"):format(b * 3 + 1, top))
  end
end
band = nil
digLoop("Finishing")

---------------------------------------------------------------- torches
local function torchSpot(cx, cy, cz)
  -- any torches still missing (knocked off, etc.) get placed now - from above only
  if get(cx, cy - 1, cz) == 2 and torchAt[id(cx, cy - 1, cz)] and solidBelow(cx, cy - 1, cz) then
    return "down"
  end
end

local placed, remainingTorches = 0, 0
for _ in pairs(torchAt) do remainingTorches = remainingTorches + 1 end

while remainingTorches > 0 do
  local path = findPath(function(a, b, c) return torchSpot(a, b, c) ~= nil end)
  if not path then break end
  walk(path)
  if not torchSlot() then tripHome(true) end
  local ti = id(x, y - 1, z)
  turtle.select(torchSlot() or 1)
  if turtle.placeDown() then placed = placed + 1; st[ti] = 3 end
  turtle.select(1)
  torchAt[ti] = nil
  remainingTorches = remainingTorches - 1
  term.setCursorPos(1, 1); term.clearLine()
  write("Torches placed: " .. placed)
end

---------------------------------------------------------------- trapdoors & water
-- Placed last, once everything is dug: trapdoors first, then water (so
-- flowing water can't get in the way). The turtle stands next to the spot
-- (above it if it can) and places into it.
-- Opening trapdoors: the turtle "clicks" the trapdoor with a stick. Plain
-- CC: Tweaked doesn't allow turtles to click trapdoors, so this only works
-- with the minor datapack installed (see README). We check it really opened.
local openWorks = nil            -- nil = not tried yet, false = turtles can't open them here
local trapsOpened, noStick, openErr = 0, false, nil

local function tryOpen(how)
  if openWorks == false then return end
  local s = itemSlot("stick")
  if not s then noStick = true; return end
  turtle.select(s)
  local look
  local _, err
  if how == "down" then _, err = turtle.placeDown(); look = turtle.inspectDown
  elseif how == "up" then _, err = turtle.placeUp(); look = turtle.inspectUp
  else _, err = turtle.place(); look = turtle.inspect end -- already facing it
  turtle.select(1)
  local ok, data = look()
  if ok and data.state and data.state.open then
    trapsOpened = trapsOpened + 1
    openWorks = true
  elseif openWorks == nil then
    openWorks = false
    openErr = err
  end
end

local function placeItems(spots, kind)
  local total = 0
  for _ in pairs(spots) do total = total + 1 end
  local done, left = 0, total

  local function how(cx, cy, cz)
    if get(cx, cy - 1, cz) == 2 and spots[id(cx, cy - 1, cz)] then return "down", id(cx, cy - 1, cz) end
    for d = 0, 3 do
      local tx, tz = cx + DX[d], cz + DZ[d]
      if get(tx, cy, tz) == 2 and spots[id(tx, cy, tz)] then return d, id(tx, cy, tz) end
    end
    if get(cx, cy + 1, cz) == 2 and spots[id(cx, cy + 1, cz)] then return "up", id(cx, cy + 1, cz) end
  end
  -- prefer standing somewhere that isn't itself a spot
  local clear = function(a, b, c) return not spots[id(a, b, c)] and how(a, b, c) ~= nil end
  local any = function(a, b, c) return how(a, b, c) ~= nil end

  while left > 0 do
    checkup()
    local path = findPath(clear) or findPath(any)
    if not path then break end
    walk(path)
    local h, si = how(x, y, z)
    if not h then break end
    local wantOpen = kind == "trapdoor" and (spots[si] == "open" or openTraps)
    if not itemSlot(kind) then tripHome(kind) end
    turtle.select(itemSlot(kind) or 1)
    local ok
    if h == "down" then ok = turtle.placeDown()
    elseif h == "up" then ok = turtle.placeUp()
    else face(h); ok = turtle.place() end
    turtle.select(1)
    spots[si] = nil
    left = left - 1
    if ok then
      done = done + 1
      if kind == "trapdoor" then
        st[si] = 5 -- solid now: walk around it
        if wantOpen then tryOpen(h) end
      end
    end
    term.setCursorPos(1, 1); term.clearLine()
    write(("Placing %s: %d of %d"):format(KIND_NAMES[kind], done, total))
  end
  return done, left
end

local trapsPlaced, trapsLeft = 0, 0
local waterPlaced, waterLeft = 0, 0
if trapCount > 0 then trapsPlaced, trapsLeft = placeItems(trapAt, "trapdoor") end
if waterCount > 0 then waterPlaced, waterLeft = placeItems(waterAt, "water") end

---------------------------------------------------------------- finish
goHome()
unload()
face(0)
term.clear(); term.setCursorPos(1, 1)
print(("Done! Dug %d x %d x %d."):format(L, W, H))
local torchesTotal = lit + placed
if torchesTotal > 0 then print("Placed " .. torchesTotal .. " torches.") end
if trapsPlaced > 0 then print("Placed " .. trapsPlaced .. " trapdoors.") end
if waterPlaced > 0 then print("Placed " .. waterPlaced .. " water buckets.") end
if openCount > 0 and trapsPlaced > 0 then
  if trapsOpened > 0 then print("Opened " .. trapsOpened .. " trapdoors.")
  elseif noStick then print("No stick, so trapdoors were left closed.")
  elseif openWorks == false then
    local maj, mnr = tostring(_HOST):match("ComputerCraft (%d+)%.(%d+)")
    if maj and tonumber(maj) == 1 and tonumber(mnr) < 104 then
      print("Couldn't open trapdoors: CC: Tweaked is")
      print("older than 1.104, which can't do it.")
    else
      print("Couldn't open trapdoors (" .. tostring(openErr) .. ").")
      print("Add the minor datapack, run /reload,")
      print("then 'minor test' to check.")
    end
  end
end
if trapsLeft + waterLeft > 0 then
  print(("Couldn't reach %d trapdoor/water spots."):format(trapsLeft + waterLeft))
end
if tunnels > 0 then
  print("Note: dug " .. tunnels .. " extra blocks to reach parts")
  print("of the design that weren't connected.")
end
