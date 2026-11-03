-- Installs "minor" on a turtle.
-- wget run https://raw.githubusercontent.com/yetimafia/minor/main/install.lua
local URL = "https://raw.githubusercontent.com/yetimafia/minor/main/minor.lua"

if not http then
  print("HTTP is turned off on this server, so I can't download.")
  return
end

write("Downloading minor... ")
local h, err = http.get(URL .. "?t=" .. os.epoch("utc"))
if not h then
  print("failed: " .. tostring(err))
  return
end
local code = h.readAll()
h.close()

local f = fs.open("minor", "w")
f.write(code)
f.close()
print("done!")
print("")
print("Try:  minor box 16 16 5")
print("  or: minor <design name>")
print("Later, update with:  minor update")
