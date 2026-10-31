-- ------------------------------------------------------------------
-- MovesExec: экзекьютор с эффектами движений из ma2_fxgen
-- Группа выбирается при запуске (как в PosExec): одна и та же раскладка
-- эффектов ставится на любую группу, уже во время работы.
-- Каждый эффект - отдельная кью; Goto на экзекьюторе, Fade 2.
-- ------------------------------------------------------------------

-- S - амплитуда в градусах (спрашивается при запуске)
local function Cues(S)
    return {
        {name='PT Circle', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0', 100, 30}, lines={{'PAN', 2, -(S), S, '0', 100, 30}, {'TILT', 3, -(S), S, '0', 100, 30}}},
        {name='PT Circle Spread', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 30}, lines={{'PAN', 2, -(S), S, '0 Thru 360', 100, 30}, {'TILT', 3, -(S), S, '0 Thru 360', 100, 30}}},
        {name='PT Figure 8', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0', 100, 30}, lines={{'PAN', 2, -(S), S, '0', 100, 30}, {'TILT', 2, -(S*0.5), S*0.5, '0', 100, 60}}},
        {name='PT Figure 8 Spread', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 30}, lines={{'PAN', 2, -(S), S, '0 Thru 360', 100, 30}, {'TILT', 2, -(S*0.5), S*0.5, '0 Thru 360', 100, 60}}},
        {name='PT Square', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0', 100, 30}, lines={{'PAN', 13, -(S), S, '0', 50, 30}, {'TILT', 13, -(S), S, '90', 50, 30}}},
        {name='PT Tilt Wave', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 40}, lines={{'TILT', 2, -(S), S, '0 Thru 360', 100, 40}}},
        {name='PT Tilt Mirror', wings=2, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 40}, lines={{'TILT', 2, -(S), S, '0 Thru 360', 100, 40}}},
        {name='PT Tilt Lift Chase', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 60}, lines={{'TILT', 1, 0, S, '0 Thru 360', 30, 60}}},
        {name='PT Tilt Bounce', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 60}, lines={{'TILT', 6, -(S), S, '0 Thru 360', 100, 60}}},
        {name='PT Pan Fan', wings=2, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0', 100, 30}, lines={{'PAN', 2, -(S), S, '0', 100, 30}}},
        {name='PT Pan Mirror Wave', wings=2, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 30}, lines={{'PAN', 2, -(S), S, '0 Thru 360', 100, 30}}},
        {name='PT Pan Sweep', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 180', 100, 20}, lines={{'PAN', 2, -(S*2), S*2, '0 Thru 180', 100, 20}}},
        {name='PT Ballyhoo', wings=0, groups=0, blocks=0, dim={'DIM', 2, 40, 100, '0 Thru 360', 100, 45}, lines={{'PAN', 12, -(S), S, '0 Thru 360', 100, 45}, {'TILT', 12, -(S), S, '0 Thru 360', 100, 45}}},
    }
end

local SPEED_GROUP = 2   -- Speed-группа движений (SpecialMaster 3.N), nil - не задавать

local function yes(v)
    v = string.lower(v or '')
    return v == 'yes' or v == 'y' or v == 'да' or v == '1'
end

local function MovesExec()
    local execNumber = gma.textinput('Exec number', '111')
    if not execNumber then return end
    local group = gma.textinput('Group (1, 1 + 3, 1 Thru 4)', '1')
    if not group or group == '' then return end
    local execLabel = gma.textinput('Exec label', 'MOVES '..group)
    local S = tonumber(gma.textinput('Amplitude, degrees', '20')) or 20
    local withDim = yes(gma.textinput('Dimmer wave in moves?', 'yes'))

    local CUES = Cues(S)
    gma.cmd('Blind On')
    for i, c in ipairs(CUES) do
        gma.cmd('ClearAll')
        gma.cmd('Group '..group)
        gma.cmd('MAtricksReset')
        if c.wings > 0 then gma.cmd('MAtricksWings '..c.wings) end
        if c.groups > 0 then gma.cmd('MAtricksGroups '..c.groups) end
        if c.blocks > 0 then gma.cmd('MAtricksBlocks '..c.blocks) end
        local lines = c.lines
        if withDim and c.dim then
            lines = {c.dim}
            for _, l in ipairs(c.lines) do lines[#lines + 1] = l end
        end
        for _, l in ipairs(lines) do
            gma.cmd('Attribute "'..l[1]..'"')
            gma.cmd('EffectForm '..l[2])
            gma.cmd('EffectLow '..l[3])
            gma.cmd('EffectHigh '..l[4])
            gma.cmd('EffectPhase '..l[5])
            gma.cmd('EffectWidth '..l[6])
            gma.cmd('EffectBPM '..l[7])
            if SPEED_GROUP then gma.cmd('EffectSpeedGroup '..SPEED_GROUP) end
        end
        gma.cmd('Store Cue '..i..' Exec '..execNumber..' /o /nc')
        gma.cmd('Label Cue '..i..' Exec '..execNumber..' "'..c.name..'"')
    end
    gma.cmd('ClearAll')
    gma.cmd('MAtricksReset')

    gma.cmd('Assign Goto Executor '..execNumber)
    gma.cmd('Label Executor '..execNumber..' "'..execLabel..'"')
    gma.cmd('Assign Fade 2 Cue 1 Thru Executor '..execNumber)
    gma.cmd('Assign Executor '..execNumber..' /offtime=2 /ooo=off')
    gma.cmd('Assign Seq "'..execLabel..'" /track=off')
    gma.cmd('Blind Off')
    gma.feedback('MovesExec: '..#CUES..' cues -> Exec '..execNumber..', group '..group)
end

return MovesExec
