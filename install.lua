-- Installs (or updates) "minor" on a turtle, then optionally runs it.
--   wget run https://raw.githubusercontent.com/yetimafia/Minor/main/install.lua
--   wget run https://raw.githubusercontent.com/yetimafia/Minor/main/install.lua <design or url>
-- The designer's "Copy turtle command" button gives you the second form.
local REPO, BRANCH = "yetimafia/Minor", "main"
local args = { ... }

if not http then
  print("HTTP is turned off on this server, so I can't download.")
  return
end

local function fetch(url, headers)
  local h, err = http.get(url, headers)
  if not h then return nil, err end
  local data = h.readAll()
  h.close()
  return data
end

write("Getting latest minor... ")
-- GitHub's API always has the newest version (raw links can be ~5 minutes old)
local code, err = fetch("https://api.github.com/repos/" .. REPO .. "/contents/minor.lua?ref=" .. BRANCH,
                        { ["Accept"] = "application/vnd.github.raw", ["User-Agent"] = "minor-turtle" })
if not code then
  code, err = fetch("https://raw.githubusercontent.com/" .. REPO .. "/" .. BRANCH .. "/minor.lua?t=" .. os.epoch("utc"))
end

if code then
  local f = fs.open("minor", "w")
  f.write(code)
  f.close()
  print("done!")
elseif fs.exists("minor") then
  print("failed, using the copy I have.")
else
  print("failed: " .. tostring(err))
  return
end

if #args > 0 then
  shell.run("minor", table.unpack(args))
else
  print("")
  print("Try:  minor box 16 16 5")
  print("  or: minor <design name>")
  print("  or: minor test")
end
