-- Installs (or updates) "minor" on a turtle, then optionally runs it.
--   wget run https://raw.githubusercontent.com/yetimafia/Minor/main/install.lua
--   wget run https://raw.githubusercontent.com/yetimafia/Minor/main/install.lua <design or url>
-- The designer's "Copy turtle command" button gives you the second form.
local URL = "https://raw.githubusercontent.com/yetimafia/Minor/main/minor.lua"
local args = { ... }

if not http then
  print("HTTP is turned off on this server, so I can't download.")
  return
end

write("Getting latest minor... ")
local h, err = http.get(URL .. "?t=" .. os.epoch("utc"))
if h then
  local code = h.readAll()
  h.close()
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
end
