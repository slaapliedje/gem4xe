-- shrdump.lua -- MAME apple2gs autoboot script for the GSlayer gates.
--
-- Waits for the program under test to write "GSDONE" at $E1:9DF0, then
-- writes the whole Super Hi-Res area, $E1:2000-$E1:9FFF (pixels, SCBs and
-- palettes), to $GS_OUT and exits.  Gives up after $GS_LIMIT emulated
-- seconds (default 120) and writes GS_OUT..".timeout" instead, so the
-- gate can tell "never finished" from "never started".
local out   = os.getenv("GS_OUT") or "shr.bin"
local limit = tonumber(os.getenv("GS_LIMIT") or "120")
local sig   = "GSDONE"

local function space()
  return manager.machine.devices[":maincpu"].spaces["program"]
end

local function signalled(sp)
  for i = 1, #sig do
    if sp:read_u8(0xE19DF0 + i - 1) ~= sig:byte(i) then return false end
  end
  return true
end

local function dump(path, sp)
  local t = {}
  for a = 0xE12000, 0xE19FFF do t[#t + 1] = string.char(sp:read_u8(a)) end
  local f = assert(io.open(path, "wb"))
  f:write(table.concat(t))
  f:close()
end

local settle = nil
emu.register_frame_done(function()
  local sp = space()
  local now = manager.machine.time.seconds
  if signalled(sp) then
    -- One more second after the signal, so nothing still in flight
    -- (a VBL task, the cursor) is caught half-drawn.
    settle = settle or now + 1
    if now >= settle then
      dump(out, sp)
      manager.machine:exit()
    end
  elseif now >= limit then
    local f = io.open(out .. ".timeout", "w")
    if f then f:write(string.format("no GSDONE after %d s\n", limit)); f:close() end
    manager.machine:exit()
  end
end)
