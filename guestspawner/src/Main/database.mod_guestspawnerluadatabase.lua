-- Mod_GuestSpawner: test helper. A button in the park ("+500 guests") brings 500 more guests into the park,
-- quickly, even when the park has no rides yet (normally the park rating decides how many guests come).
-- The park needs an entrance that is connected to the road (as always).
local global = _G
local api = global.api
local table = global.table
local require = global.require
local pcall = global.pcall
local pairs = global.pairs
local type = global.type
local math = global.math
local string = global.string
local tostring = global.tostring

-- ---------------------------------------------------------------- settings
local PER_CLICK = 500          -- guests per click
local SPAWN_RATE = 10.0        -- guests per second while the goal is not reached (the game uses at most 5)
local STAY_LENGTH = 9000.0     -- seconds a guest stays (the game's maximum)

local DB = {}
local S = { goal = nil, hud = nil, clock = 0.0, pending = 0 }

local function trace(s) pcall(api.debug.Trace, "[GuestSpawner] " .. tostring(s)) end

local function guests_api()
    local ok, w = pcall(api.world.GetWorldAPIs)
    return ok and type(w) == "table" and w.guests or nil
end

local function num_guests()
    local g = guests_api()
    local ok, n = pcall(function() return g:GetNumGuests() end)
    return (ok and type(n) == "number") and n or nil
end

-- our numbers on top of what the park rating calculated (only while a click is being worked off)
local function apply(guestsAPI, nIdeal, nStay, nCap)
    if S.goal == nil then return false end
    if type(guestsAPI) ~= "table" or type(guestsAPI.SetGuestSpawnData) ~= "function" then return false end
    local ideal = math.max(nIdeal or 0, S.goal)
    local stay = math.max(nStay or 0, STAY_LENGTH)
    local cap = nCap
    if cap ~= nil then cap = math.max(cap, S.goal) end
    return pcall(guestsAPI.SetGuestSpawnData, guestsAPI, ideal, SPAWN_RATE, stay, cap)
end

function DB.AddContentToCall(_tContentToCall)
    table.insert(_tContentToCall, require("Database.Mod_GuestSpawnerLuaDatabase"))
end

-- ---------------------------------------------------------------- button in the HUD
local function find_hud()
    local found = nil
    pcall(function()
        local st = api.forgeutils and api.forgeutils.uiHookManagerState
        local wr = st and st.wrappers
        if type(wr) ~= "table" then return end
        for w, name in pairs(wr) do
            if name == "HUD" and w.view ~= nil then found = w end
        end
    end)
    return found
end

local function send(txt)
    if S.hud then pcall(S.hud.TriggerEventAtNextAdvance, S.hud, "GS_State", txt) end
end

local function connect()
    local hud = find_hud()
    if hud == nil or hud == S.hud then return end
    S.hud = hud
    pcall(hud.AddEventListener, hud, "GS_Spawn500", 0, function() S.pending = S.pending + 1 end, DB)
    pcall(hud.AddEventListener, hud, "GS_Hello", 0, function() S.hello = true end, DB)
    trace("button connected")
end

local function status()
    local n = num_guests()
    if S.goal == nil or n == nil then return nil end
    if n >= S.goal then return nil end
    return string.format("%d/%d", n, S.goal)
end

-- every frame (driven by the day/night cycle, which runs in every park)
local function tick(dt)
    connect()
    while S.pending > 0 do
        S.pending = S.pending - 1
        local n = num_guests() or 0
        S.goal = math.max(S.goal or 0, n) + PER_CLICK
        trace("goal " .. S.goal)
        local g = guests_api()
        if g then apply(g, S.goal, STAY_LENGTH, nil) end
        send(status())
    end
    S.clock = S.clock + (dt or 0)
    if S.clock < 2.0 then return end
    S.clock = 0.0
    if S.goal ~= nil then
        local n = num_guests()
        if n ~= nil and n >= S.goal then
            S.goal = nil        -- done: the park rating decides again
            send(string.format("done:%d", n))
            return
        end
        local g = guests_api()
        if g then apply(g, S.goal, STAY_LENGTH, nil) end
    end
    send(status())
end

-- the park rating sets its own spawn data every few seconds: overwrite it right after (while a click runs)
local bHooked = false
local function install_hook()
    if bHooked then return end
    local ok, hookManager = pcall(require, "forgeutils.hookmanager")
    if not ok or type(hookManager) ~= "table" then return end
    bHooked = hookManager:AddHook("Managers.ParkRatingManager", "ParkRatingManagerAdvancer_Advance",
        function(original, self, _timeStep, ...)
            local before = self.nTimeToRecalculate
            local r = original(self, _timeStep, ...)
            if S.goal ~= nil and (before == nil or self.nTimeToRecalculate == nil or self.nTimeToRecalculate > before) then
                local cap, applies = nil, false
                pcall(function() cap, applies = self:GetGuestCap() end)
                apply(self.guestsAPI, self.nIdealNumberOfGuests, self.nCappedGuestStayLength, applies and cap or nil)
            end
            return r
        end) and true or false
    trace("hook " .. (bHooked and "installed" or "failed"))
end

local bTick = false
local function install_tick()
    if bTick then return end
    local ok, DNC = pcall(require, "lighting.daynightcycle")
    if not ok or type(DNC) ~= "table" then return end
    local inner = global.rawget(DNC, "Advance")
    global.rawset(DNC, "Advance", nil)
    local wrapper = function(self, dt, ...)
        local r = inner and inner(self, dt, ...)
        pcall(tick, dt)
        return r
    end
    local oldmt = global.getmetatable(DNC)
    local oldIndex = oldmt and oldmt.__index
    local oldNew = oldmt and oldmt.__newindex
    local mt = {}
    if oldmt then for k, v in pairs(oldmt) do mt[k] = v end end
    mt.__index = function(t, k)
        if k == "Advance" then return wrapper end
        if type(oldIndex) == "function" then return oldIndex(t, k) end
        if type(oldIndex) == "table" then return oldIndex[k] end
        return nil
    end
    mt.__newindex = function(t, k, v)
        if k == "Advance" then inner = v return end
        if type(oldNew) == "function" then return oldNew(t, k, v) end
        global.rawset(t, k, v)
    end
    global.setmetatable(DNC, mt)
    bTick = true
    trace("tick installed")
end

function DB.Init()
    pcall(api.ui2.MapResources, "GuestSpawner")
    pcall(function()
        local hooks = require("forgeutils.uihookmanager")
        hooks:AddImportHook("HUD", "/js/guestspawner/button.js")
    end)
    install_hook()
    install_tick()
end

function DB.Setup()
    install_hook()
    install_tick()
end

function DB.Shutdown()
    pcall(api.ui2.UnmapResources, "GuestSpawner")
end

return DB
