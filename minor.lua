-- minor: carve rooms and custom designs with a CC: Tweaked turtle
--
--   minor box <length> <width> <height>   dig a plain room (max 64 each)
--   minor <design>                        dig a design made with designer.py
--   minor <url>                           dig a design straight from a link
--   minor update                          download the newest minor
--   add "notorch" to skip placing torches
--
-- Box rooms: the turtle sits in the FRONT-LEFT-BOTTOM corner and digs
-- forward, right and up. Designs: the turtle sits where the design's
-- start marker is, facing "up" on the designer's grid.
-- Put a CHEST directly BEHIND the turtle. Put fuel and torches in the turtle.

local REPO   = "yetimafia/minor"   -- GitHub "user/repo"
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

if args[1] == "update" then
  local ok, err = download("minor.lua", shell.getRunningProgram())
  print(ok and "minor updated!" or ("Update failed: " .. tostring(err)))
  return
end

---------------------------------------------------------------- the world
-- x = forward, z = right, y = up
-- st values: 0 leave alone, 1 needs digging, 2 open, 3 torch placed, 4 chest
local L, W, H
local st, torchAt = {}, {}
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
    elseif line:match("^layer ") then
      y = tonumber(line:match("^layer (%d+)")); x = 0
    elseif y >= 0 and x < L and line ~= "" then
      local z = 0
      for count, ch in line:gmatch("(%d+)([%.#T])") do
        for _ = 1, tonumber(count) do
          if z < W then
            if ch ~= "." then
              st[id(x, y, z)] = 1
              if ch == "T" then torchAt[id(x, y, z)] = true end
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
if inb(sx - 1, sy, sz) then
  if st[id(sx - 1, sy, sz)] == 1 then
    print("Note: the chest spot is part of the design - I'll leave it.")
  end
  st[id(sx - 1, sy, sz)] = 4
end
for i = 1, L * W * H do
  if st[i] == 1 then todo = todo + 1 end
  if st[i] ~= 1 and st[i] ~= 2 then torchAt[i] = nil end
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
  elseif st[i] == 0 then tunnels = tunnels + 1 end
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
        if not prev[ni] and (s == 2 or (allow and s == 3) or (allow == true and (s == 0 or s == 1))) then
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

local function isTorch(i)
  local d = turtle.getItemDetail(i)
  return d and d.name:find("torch") ~= nil
end

local function refuelFromInventory()
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and not isTorch(i) then
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

local function torchSlot()
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and isTorch(i) then return i end
  end
end

local function unload()
  face(2)
  for i = 1, 16 do
    if turtle.getItemCount(i) > 0 and not isTorch(i) then
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

local function tripHome(needTorches)
  local bx, by, bz, bd = x, y, z, dir
  local dist = math.abs(bx - sx) + math.abs(by - sy) + math.abs(bz - sz)
  goHome()
  unload()
  refuelFromInventory()
  while fuel() < dist * 3 + 100 do
    waitForUser("I need fuel! Put coal in my inventory.")
    refuelFromInventory()
  end
  while needTorches and not torchSlot() do
    waitForUser("I need torches! Put some in my inventory.")
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
local torchCount = 0
for _ in pairs(torchAt) do torchCount = torchCount + 1 end
print(("Size %d x %d x %d, %d blocks to dig"):format(L, W, H, todo))
if torchCount > 0 then print(torchCount .. " torches will be placed at the end") end
if fuel() ~= math.huge then
  print(("Fuel: %d   Rough need: %d"):format(fuel(), math.floor(todo / 2.5) + L + W + H))
end
print("Chest goes BEHIND me.")
waitForUser("Ready?")
term.clear()

---------------------------------------------------------------- dig
local function hasTodoNeighbour(cx, cy, cz)
  for _, n in ipairs(NB) do
    if get(cx + n[1], cy + n[2], cz + n[3]) == 1 then return true end
  end
  return false
end

while todo > 0 do
  checkup()
  progress("Digging")
  -- stand in the middle of each 3-high band so up/down get dug for free
  if y % 3 ~= 1 and get(x, y + 1, z) == 1 then
    up()
  else
    digAbove()
    digBelow()
    -- walk into an undug neighbour: forward, right, left, back
    local moved = false
    for _, turn in ipairs({ 0, 1, 3, 2 }) do
      local d = (dir + turn) % 4
      if get(x + DX[d], y, z + DZ[d]) == 1 then
        face(d); forward(); moved = true
        break
      end
    end
    if not moved and todo > 0 then
      local path = findPath(hasTodoNeighbour)
      if path then
        walk(path)
      else
        -- part of the design isn't connected: tunnel to it
        path = findPath(function(a, b, c) return get(a, b, c) == 1 end, true)
        if not path then break end
        walk(path)
      end
    end
  end
end

---------------------------------------------------------------- torches
local function torchSpot(cx, cy, cz)
  -- standing here, can I place a torch? returns how
  if get(cx, cy - 1, cz) == 2 and torchAt[id(cx, cy - 1, cz)] then return "down" end
  for d = 0, 3 do
    local tx, tz = cx + DX[d], cz + DZ[d]
    if get(tx, cy, tz) == 2 and torchAt[id(tx, cy, tz)]
       and not (tx == sx and cy == sy and tz == sz) then
      return d
    end
  end
end

local placed, remainingTorches = 0, 0
for _ in pairs(torchAt) do remainingTorches = remainingTorches + 1 end

while remainingTorches > 0 do
  local path = findPath(function(a, b, c) return torchSpot(a, b, c) ~= nil end)
  if not path then break end
  walk(path)
  if not torchSlot() then tripHome(true) end
  local how = torchSpot(x, y, z)
  turtle.select(torchSlot() or 1)
  local ti
  if how == "down" then
    ti = id(x, y - 1, z)
    if turtle.placeDown() then placed = placed + 1 end
  else
    face(how)
    ti = id(x + DX[how], y, z + DZ[how])
    if turtle.place() then placed = placed + 1 end
  end
  torchAt[ti] = nil
  st[ti] = 3
  remainingTorches = remainingTorches - 1
  turtle.select(1)
  term.setCursorPos(1, 1); term.clearLine()
  write("Torches placed: " .. placed)
end

---------------------------------------------------------------- finish
goHome()
unload()
face(0)
term.clear(); term.setCursorPos(1, 1)
print(("Done! Dug %d x %d x %d."):format(L, W, H))
if placed > 0 then print("Placed " .. placed .. " torches.") end
if tunnels > 0 then
  print("Note: dug " .. tunnels .. " extra blocks to reach parts")
  print("of the design that weren't connected.")
end
