function render_gcode_complete_path_matlab(gcodeFileName, userConfig)
%RENDER_GCODE_COMPLETE_PATH_MATLAB Render complete G-code toolpath previews.
%
% 用法：
%   1. 把本文件放在 .gcode 文件的同一个目录。
%   2. 在 MATLAB 中打开并运行本文件。
%   3. 如果当前目录有多个 G-code 文件，默认选择体积最大的一个文件。
%
% 指定文件名运行：
%   render_gcode_complete_path_matlab('叶轮完整(1).gcode')
%
% 指定配置运行：
%   cfg = struct('render3DPreview', true, 'plotTravelMoves', true);
%   render_gcode_complete_path_matlab('叶轮完整.gcode', cfg)
%
% 输出文件：
%   gcode_complete_path_c_unwrapped_top_matlab.png  C 轴反向展开后的顶视图
%   gcode_complete_path_machine_xy_matlab.png       原始机床 X/Y 坐标顶视图
%   gcode_complete_path_ac_inverse_3d_matlab.fig    AC 轴反算回 XYZ 后的 3D 预览
%   gcode_complete_path_ac_inverse_3d_matlab.png    AC 轴反算 3D 预览快照
%   gcode_toolpath_render_stats_matlab.txt          解析统计
%
% 说明：
%   - 解析 G0/G1 的 X/Y/Z/A/C/E/F 字段，支持 G90/G91、M82/M83、G20/G21、G92。
%   - 正挤出段按 Z 高度着色；非挤出和空走路径用浅灰色绘制。
%   - C 轴展开采用 [x',y'] = Rz(-C) * [x,y]，适合作为带 C 轴旋转路径的顶视图代理。
%   - 3D FIG 采用 P_part = Rz(-C) * Rx(-A) * P_machine，将 A/C 轴位反算回 XYZ。

    if nargin < 1
        gcodeFileName = '';
    end
    if nargin < 2
        userConfig = struct();
    end

    cfg = mergeConfig(defaultRenderConfig(), userConfig);

    scriptPath = mfilename('fullpath');
    if isempty(scriptPath)
        scriptDir = pwd;
    else
        scriptDir = fileparts(scriptPath);
        if isempty(scriptDir)
            scriptDir = pwd;
        end
    end

    gcodePath = resolveGcodePath(scriptDir, gcodeFileName);
    fprintf('Input G-code: %s\n', gcodePath);

    data = parseGcodeFile(gcodePath, cfg);

    [ux0, uy0] = rotateXYMinusC(data.sx, data.sy, data.sc);
    [ux1, uy1] = rotateXYMinusC(data.ex, data.ey, data.ec);
    [kx0, ky0, kz0] = inverseRotaryACToXYZ(data.sx, data.sy, data.sz, data.sa, data.sc, cfg);
    [kx1, ky1, kz1] = inverseRotaryACToXYZ(data.ex, data.ey, data.ez, data.ea, data.ec, cfg);
    data.stats.acInverseXBounds = axisBounds(kx0, kx1);
    data.stats.acInverseYBounds = axisBounds(ky0, ky1);
    data.stats.acInverseZBounds = axisBounds(kz0, kz1);

    outputs = struct();
    outputs.cUnwrappedTopPng = fullfile(scriptDir, 'gcode_complete_path_c_unwrapped_top_matlab.png');
    outputs.machineXYPng = fullfile(scriptDir, 'gcode_complete_path_machine_xy_matlab.png');
    outputs.acInverse3DFig = fullfile(scriptDir, 'gcode_complete_path_ac_inverse_3d_matlab.fig');
    outputs.acInverse3DPng = fullfile(scriptDir, 'gcode_complete_path_ac_inverse_3d_matlab.png');
    outputs.stats = fullfile(scriptDir, 'gcode_toolpath_render_stats_matlab.txt');

    subtitleC = sprintf('C-unwrapped top view, positive extrusion colored by Z; segments %s, extrusion %s, travel/non-extrusion %s', ...
        formatCount(data.stats.movementSegments), ...
        formatCount(data.stats.printSegments), ...
        formatCount(data.stats.travelSegments));

    renderToolpath2DFigure( ...
        ux0, uy0, ux1, uy1, data.sz, data.ez, data.printMask, ...
        outputs.cUnwrappedTopPng, ...
        'G-code complete toolpath, C-axis unwrapped top view', ...
        subtitleC, cfg);

    if cfg.render3DPreview
        subtitle3D = sprintf('AC inverse 3D preview, positive extrusion colored by reconstructed Z; segments %s, extrusion %s, travel/non-extrusion %s', ...
            formatCount(data.stats.movementSegments), ...
            formatCount(data.stats.printSegments), ...
            formatCount(data.stats.travelSegments));

        renderToolpath3DFigure( ...
            kx0, ky0, kx1, ky1, kz0, kz1, data.printMask, ...
            outputs.acInverse3DFig, outputs.acInverse3DPng, ...
            'G-code complete toolpath, AC inverse 3D preview', ...
            subtitle3D, cfg);
    end

    if cfg.alsoPlotMachineXY
        subtitleXY = sprintf('Raw machine X/Y top view, positive extrusion colored by Z; segments %s, extrusion %s, travel/non-extrusion %s', ...
            formatCount(data.stats.movementSegments), ...
            formatCount(data.stats.printSegments), ...
            formatCount(data.stats.travelSegments));

        renderToolpath2DFigure( ...
            data.sx, data.sy, data.ex, data.ey, data.sz, data.ez, data.printMask, ...
            outputs.machineXYPng, ...
            'G-code complete toolpath, raw machine X/Y view', ...
            subtitleXY, cfg);
    end

    writeStatsFile(outputs.stats, gcodePath, data, cfg, outputs);

    fprintf('\nDone.\n');
    fprintf('Saved: %s\n', outputs.cUnwrappedTopPng);
    if cfg.render3DPreview
        fprintf('Saved: %s\n', outputs.acInverse3DFig);
        if cfg.export3DPng
            fprintf('Saved: %s\n', outputs.acInverse3DPng);
        end
    end
    if cfg.alsoPlotMachineXY
        fprintf('Saved: %s\n', outputs.machineXYPng);
    end
    fprintf('Saved: %s\n', outputs.stats);
end

function cfg = defaultRenderConfig()
    cfg = struct();
    cfg.defaultExtrusionRelative = true;    % 若文件开头没有 M82/M83，则按相对挤出 E 处理。
    cfg.numColors = 160;                    % Z 高度色带数量；数值越大颜色越细，绘图略慢。
    cfg.figurePixels = [2800, 2800];         % 二维 PNG 输出画布像素。
    cfg.figure3DPixels = [2400, 1800];       % 三维预览输出画布像素。
    cfg.resolutionDPI = 300;                 % PNG 导出分辨率。
    cfg.plotTravelMoves = true;              % 是否绘制非挤出/空走路径。
    cfg.alsoPlotMachineXY = true;            % 是否额外输出原始机床 X/Y 坐标图。
    cfg.render3DPreview = true;              % 是否保存 AC 轴反算后的 3D FIG。
    cfg.export3DPng = true;                  % 是否同步导出 3D PNG 快照。
    cfg.acInverseOrder = 'RzMinusC_after_RxMinusA'; % 默认 P = Rz(-C) * Rx(-A) * P_machine。
    cfg.motionLineWidth = 0.25;
    cfg.travelLineWidth = 0.15;
    cfg.motionLineWidth3D = 0.35;
    cfg.travelLineWidth3D = 0.18;
    cfg.view3DAzimuth = -42;
    cfg.view3DElevation = 28;
end

function cfg = mergeConfig(cfg, userConfig)
    if isempty(userConfig)
        return;
    end
    if ~isstruct(userConfig)
        error('userConfig 必须是 struct。');
    end

    names = fieldnames(userConfig);
    for i = 1:numel(names)
        name = names{i};
        if ~isfield(cfg, name)
            error('未知配置项：%s', name);
        end
        cfg.(name) = userConfig.(name);
    end
end

function gcodePath = resolveGcodePath(scriptDir, gcodeFileName)
    if isempty(gcodeFileName)
        patterns = {'*.gcode', '*.gco', '*.nc', '*.ngc', '*.tap'};
        files = [];
        for i = 1:numel(patterns)
            files = [files; dir(fullfile(scriptDir, patterns{i}))]; %#ok<AGROW>
        end
        if isempty(files)
            error('当前脚本目录没有找到 .gcode/.gco/.nc/.ngc/.tap 文件：%s', scriptDir);
        end
        [~, idx] = max([files.bytes]);
        gcodePath = fullfile(files(idx).folder, files(idx).name);
        return;
    end

    if exist(gcodeFileName, 'file') == 2
        gcodePath = gcodeFileName;
    else
        gcodePath = fullfile(scriptDir, gcodeFileName);
    end

    if exist(gcodePath, 'file') ~= 2
        error('找不到指定 G-code 文件：%s', gcodePath);
    end
end

function data = parseGcodeFile(gcodePath, cfg)
    fid = fopen(gcodePath, 'r');
    if fid < 0
        error('无法打开 G-code 文件：%s', gcodePath);
    end
    fileCleanup = onCleanup(@() fclose(fid));

    tokenPattern = '([A-Za-z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)';

    chunk = 1100000;
    nAlloc = chunk;
    nSeg = 0;

    sx = zeros(nAlloc, 1, 'single');
    sy = zeros(nAlloc, 1, 'single');
    sz = zeros(nAlloc, 1, 'single');
    sa = zeros(nAlloc, 1, 'single');
    sc = zeros(nAlloc, 1, 'single');
    ex = zeros(nAlloc, 1, 'single');
    ey = zeros(nAlloc, 1, 'single');
    ez = zeros(nAlloc, 1, 'single');
    ea = zeros(nAlloc, 1, 'single');
    ec = zeros(nAlloc, 1, 'single');
    deltaE = zeros(nAlloc, 1, 'single');
    printMask = false(nAlloc, 1);
    motionCode = zeros(nAlloc, 1, 'uint8');

    posX = 0; posY = 0; posZ = 0; posA = 0; posC = 0; posE = 0;
    coordAbs = true;
    extrRel = cfg.defaultExtrusionRelative;
    units = 1.0;
    motion = NaN;

    lineCount = 0;
    g0Count = 0;
    g1Count = 0;
    tStart = tic;

    while true
        rawLine = fgetl(fid);
        if ~ischar(rawLine)
            break;
        end
        lineCount = lineCount + 1;

        semiPos = find(rawLine == ';', 1, 'first');
        if ~isempty(semiPos)
            rawLine = rawLine(1:semiPos-1);
        end
        rawLine = regexprep(rawLine, '\([^)]*\)', '');
        codeLine = strtrim(rawLine);
        if isempty(codeLine)
            continue;
        end

        tokens = regexp(codeLine, tokenPattern, 'tokens');
        if isempty(tokens)
            continue;
        end

        hasX = false; hasY = false; hasZ = false; hasA = false; hasC = false; hasE = false;
        valX = 0; valY = 0; valZ = 0; valA = 0; valC = 0; valE = 0;
        gList = zeros(1, 6);
        mList = zeros(1, 6);
        nG = 0;
        nM = 0;

        for it = 1:numel(tokens)
            letter = upper(tokens{it}{1});
            val = str2double(tokens{it}{2});
            switch letter
                case 'G'
                    gi = round(val);
                    if abs(val - gi) < 1e-9
                        nG = nG + 1;
                        if nG > numel(gList)
                            gList(end+6) = 0; %#ok<AGROW>
                        end
                        gList(nG) = gi;
                    end
                case 'M'
                    mi = round(val);
                    if abs(val - mi) < 1e-9
                        nM = nM + 1;
                        if nM > numel(mList)
                            mList(end+6) = 0; %#ok<AGROW>
                        end
                        mList(nM) = mi;
                    end
                case 'X'
                    hasX = true; valX = val;
                case 'Y'
                    hasY = true; valY = val;
                case 'Z'
                    hasZ = true; valZ = val;
                case 'A'
                    hasA = true; valA = val;
                case 'C'
                    hasC = true; valC = val;
                case 'E'
                    hasE = true; valE = val;
                otherwise
                    % F、S、T、I、J、K、R 等字段在本顶视图渲染中不参与几何计算。
            end
        end

        hasMotionThisLine = false;
        hasG92 = false;
        for ig = 1:nG
            g = gList(ig);
            switch g
                case 90
                    coordAbs = true;
                case 91
                    coordAbs = false;
                case 0
                    motion = 0;
                    hasMotionThisLine = true;
                case 1
                    motion = 1;
                    hasMotionThisLine = true;
                case 20
                    units = 25.4;
                case 21
                    units = 1.0;
                case 92
                    hasG92 = true;
                otherwise
                    % 其他 G 指令不改变本解析器需要的线性路径状态。
            end
        end

        for im = 1:nM
            m = mList(im);
            switch m
                case 82
                    extrRel = false;
                case 83
                    extrRel = true;
                otherwise
                    % 其他 M 指令不参与路径几何计算。
            end
        end

        if hasG92
            if hasX, posX = valX * units; end
            if hasY, posY = valY * units; end
            if hasZ, posZ = valZ * units; end
            if hasA, posA = valA; end
            if hasC, posC = valC; end
            if hasE, posE = valE; end
            if ~hasMotionThisLine
                continue;
            end
        end

        if ~(motion == 0 || motion == 1)
            continue;
        end

        hasSpatialAxis = hasX || hasY || hasZ || hasA || hasC;
        if ~hasSpatialAxis
            if hasE
                if extrRel
                    posE = posE + valE;
                else
                    posE = valE;
                end
            end
            continue;
        end

        oldX = posX; oldY = posY; oldZ = posZ; oldA = posA; oldC = posC; oldE = posE;
        newX = oldX; newY = oldY; newZ = oldZ; newA = oldA; newC = oldC; newE = oldE;

        if hasX
            v = valX * units;
            if coordAbs, newX = v; else, newX = newX + v; end
        end
        if hasY
            v = valY * units;
            if coordAbs, newY = v; else, newY = newY + v; end
        end
        if hasZ
            v = valZ * units;
            if coordAbs, newZ = v; else, newZ = newZ + v; end
        end
        if hasA
            if coordAbs, newA = valA; else, newA = newA + valA; end
        end
        if hasC
            if coordAbs, newC = valC; else, newC = newC + valC; end
        end

        dE = 0;
        if hasE
            if extrRel
                dE = valE;
                newE = oldE + valE;
            else
                dE = valE - oldE;
                newE = valE;
            end
        end

        nSeg = nSeg + 1;
        if nSeg > nAlloc
            nAlloc = nAlloc + chunk;
            sx(nAlloc, 1) = single(0); sy(nAlloc, 1) = single(0); sz(nAlloc, 1) = single(0);
            sa(nAlloc, 1) = single(0); sc(nAlloc, 1) = single(0);
            ex(nAlloc, 1) = single(0); ey(nAlloc, 1) = single(0); ez(nAlloc, 1) = single(0);
            ea(nAlloc, 1) = single(0); ec(nAlloc, 1) = single(0);
            deltaE(nAlloc, 1) = single(0);
            printMask(nAlloc, 1) = false;
            motionCode(nAlloc, 1) = uint8(0);
        end

        sx(nSeg) = single(oldX); sy(nSeg) = single(oldY); sz(nSeg) = single(oldZ);
        sa(nSeg) = single(oldA); sc(nSeg) = single(oldC);
        ex(nSeg) = single(newX); ey(nSeg) = single(newY); ez(nSeg) = single(newZ);
        ea(nSeg) = single(newA); ec(nSeg) = single(newC);
        deltaE(nSeg) = single(dE);
        printMask(nSeg) = dE > 1e-9;
        motionCode(nSeg) = uint8(motion);

        if motion == 0
            g0Count = g0Count + 1;
        else
            g1Count = g1Count + 1;
        end

        posX = newX; posY = newY; posZ = newZ; posA = newA; posC = newC; posE = newE;

        if mod(lineCount, 250000) == 0
            fprintf('Parsed %s lines, %s motion segments...\n', formatCount(lineCount), formatCount(nSeg));
        end
    end

    if nSeg == 0
        error('没有解析到 G0/G1 空间运动段。');
    end

    data = struct();
    data.sx = sx(1:nSeg); data.sy = sy(1:nSeg); data.sz = sz(1:nSeg);
    data.sa = sa(1:nSeg); data.sc = sc(1:nSeg);
    data.ex = ex(1:nSeg); data.ey = ey(1:nSeg); data.ez = ez(1:nSeg);
    data.ea = ea(1:nSeg); data.ec = ec(1:nSeg);
    data.deltaE = deltaE(1:nSeg);
    data.printMask = printMask(1:nSeg);
    data.motionCode = motionCode(1:nSeg);

    data.stats = struct();
    data.stats.lineCount = lineCount;
    data.stats.movementSegments = nSeg;
    data.stats.printSegments = nnz(data.printMask);
    data.stats.travelSegments = nSeg - data.stats.printSegments;
    data.stats.g0Segments = g0Count;
    data.stats.g1Segments = g1Count;
    data.stats.parseSeconds = toc(tStart);
    data.stats.totalPositiveE = sum(double(data.deltaE(data.deltaE > 0)));
    data.stats.xBounds = [min(min(double(data.sx)), min(double(data.ex))), max(max(double(data.sx)), max(double(data.ex)))];
    data.stats.yBounds = [min(min(double(data.sy)), min(double(data.ey))), max(max(double(data.sy)), max(double(data.ey)))];
    data.stats.zBounds = [min(min(double(data.sz)), min(double(data.ez))), max(max(double(data.sz)), max(double(data.ez)))];
    data.stats.aBounds = [min(min(double(data.sa)), min(double(data.ea))), max(max(double(data.sa)), max(double(data.ea)))];
    data.stats.cBounds = [min(min(double(data.sc)), min(double(data.ec))), max(max(double(data.sc)), max(double(data.ec)))];

    fprintf('Parse complete: %s segments, %s extrusion segments. Parse time %.2f s.\n', ...
        formatCount(data.stats.movementSegments), formatCount(data.stats.printSegments), data.stats.parseSeconds);
end

function [xr, yr] = rotateXYMinusC(x, y, cDeg)
    theta = -double(cDeg) * pi / 180;
    co = cos(theta);
    si = sin(theta);
    xd = double(x);
    yd = double(y);
    xr = xd .* co - yd .* si;
    yr = xd .* si + yd .* co;
end

function [xr, yr, zr] = inverseRotaryACToXYZ(x, y, z, aDeg, cDeg, cfg)
    xd = double(x(:));
    yd = double(y(:));
    zd = double(z(:));
    ad = -double(aDeg(:)) * pi / 180;
    cd = -double(cDeg(:)) * pi / 180;

    order = lower(char(cfg.acInverseOrder));
    switch order
        case lower('RzMinusC_after_RxMinusA')
            [x1, y1, z1] = rotateXVector(xd, yd, zd, ad);
            [xr, yr, zr] = rotateZVector(x1, y1, z1, cd);
        case lower('RxMinusA_after_RzMinusC')
            [x1, y1, z1] = rotateZVector(xd, yd, zd, cd);
            [xr, yr, zr] = rotateXVector(x1, y1, z1, ad);
        otherwise
            error('未知 AC 反算顺序：%s', cfg.acInverseOrder);
    end
end

function [xr, yr, zr] = rotateXVector(x, y, z, angleRad)
    co = cos(angleRad);
    si = sin(angleRad);
    xr = x;
    yr = y .* co - z .* si;
    zr = y .* si + z .* co;
end

function [xr, yr, zr] = rotateZVector(x, y, z, angleRad)
    co = cos(angleRad);
    si = sin(angleRad);
    xr = x .* co - y .* si;
    yr = x .* si + y .* co;
    zr = z;
end

function bounds = axisBounds(startValues, endValues)
    bounds = [min(min(double(startValues)), min(double(endValues))), ...
        max(max(double(startValues)), max(double(endValues)))];
end

function renderToolpath2DFigure(x0, y0, x1, y1, z0, z1, printMask, outPath, titleText, subtitleText, cfg)
    x0 = double(x0(:)); y0 = double(y0(:)); x1 = double(x1(:)); y1 = double(y1(:));
    z0 = double(z0(:)); z1 = double(z1(:)); printMask = logical(printMask(:));

    finiteMask = isfinite(x0) & isfinite(y0) & isfinite(x1) & isfinite(y1) & isfinite(z0) & isfinite(z1);
    x0 = x0(finiteMask); y0 = y0(finiteMask); x1 = x1(finiteMask); y1 = y1(finiteMask);
    z0 = z0(finiteMask); z1 = z1(finiteMask); printMask = printMask(finiteMask);

    zMid = 0.5 * (z0 + z1);
    zMin = min([z0; z1]);
    zMax = max([z0; z1]);

    xMin = min(min(x0), min(x1));
    xMax = max(max(x0), max(x1));
    yMin = min(min(y0), min(y1));
    yMax = max(max(y0), max(y1));
    span = max(xMax - xMin, yMax - yMin);
    if span <= 0
        span = 1;
    end
    pad = 0.045 * span;

    fig = figure('Visible', 'off', 'Color', 'w', 'Units', 'pixels', ...
        'Position', [80, 80, cfg.figurePixels(1), cfg.figurePixels(2)]);
    ax = axes('Parent', fig);
    hold(ax, 'on');
    axis(ax, 'equal');
    grid(ax, 'on');
    box(ax, 'on');
    set(ax, 'Layer', 'top');
    xlim(ax, [xMin - pad, xMax + pad]);
    ylim(ax, [yMin - pad, yMax + pad]);
    xlabel(ax, 'X / mm');
    ylabel(ax, 'Y / mm');
    title(ax, {titleText, subtitleText}, 'Interpreter', 'none');

    nColors = cfg.numColors;
    cmap = parula(nColors);
    colormap(ax, cmap);

    if zMax > zMin
        zNorm = (zMid - zMin) ./ (zMax - zMin);
        bins = 1 + floor(zNorm * (nColors - 1));
        bins = max(1, min(nColors, bins));
    else
        bins = ones(size(zMid));
    end

    if cfg.plotTravelMoves
        travelMask = ~printMask;
        if any(travelMask)
            plotSegments(ax, x0(travelMask), y0(travelMask), x1(travelMask), y1(travelMask), ...
                [0.78, 0.78, 0.78], cfg.travelLineWidth);
        end
    end

    for k = 1:nColors
        idx = printMask & (bins == k);
        if any(idx)
            plotSegments(ax, x0(idx), y0(idx), x1(idx), y1(idx), cmap(k, :), cfg.motionLineWidth);
        end
    end

    caxis(ax, [zMin, zMax]);
    cb = colorbar(ax);
    ylabel(cb, 'Z / mm');

    infoText = sprintf('Z range %.4g to %.4g mm', zMin, zMax);
    text(ax, xMin - pad * 0.65, yMin - pad * 0.55, infoText, ...
        'Color', [0.2, 0.2, 0.2], 'FontSize', 10, 'Interpreter', 'none');

    drawnow;
    try
        exportgraphics(fig, outPath, 'Resolution', cfg.resolutionDPI);
    catch
        print(fig, outPath, '-dpng', sprintf('-r%d', cfg.resolutionDPI));
    end
    close(fig);
    fprintf('Rendered: %s\n', outPath);
end

function renderToolpath3DFigure(x0, y0, x1, y1, z0, z1, printMask, outFigPath, outPngPath, titleText, subtitleText, cfg)
    x0 = double(x0(:)); y0 = double(y0(:)); x1 = double(x1(:)); y1 = double(y1(:));
    z0 = double(z0(:)); z1 = double(z1(:)); printMask = logical(printMask(:));

    finiteMask = isfinite(x0) & isfinite(y0) & isfinite(z0) & isfinite(x1) & isfinite(y1) & isfinite(z1);
    x0 = x0(finiteMask); y0 = y0(finiteMask); z0 = z0(finiteMask);
    x1 = x1(finiteMask); y1 = y1(finiteMask); z1 = z1(finiteMask);
    printMask = printMask(finiteMask);

    zMid = 0.5 * (z0 + z1);
    xMin = min(min(x0), min(x1));
    xMax = max(max(x0), max(x1));
    yMin = min(min(y0), min(y1));
    yMax = max(max(y0), max(y1));
    zMin = min(min(z0), min(z1));
    zMax = max(max(z0), max(z1));

    xySpan = max(xMax - xMin, yMax - yMin);
    if xySpan <= 0
        xySpan = 1;
    end
    zSpan = zMax - zMin;
    if zSpan <= 0
        zSpan = 1;
    end
    xyPad = 0.045 * xySpan;
    zPad = 0.06 * zSpan;

    fig = figure('Visible', 'off', 'Color', 'w', 'Units', 'pixels', ...
        'Position', [80, 80, cfg.figure3DPixels(1), cfg.figure3DPixels(2)]);
    ax = axes('Parent', fig);
    hold(ax, 'on');
    grid(ax, 'on');
    box(ax, 'on');
    set(ax, 'Layer', 'top', 'Projection', 'perspective');
    daspect(ax, [1, 1, 1]);
    view(ax, cfg.view3DAzimuth, cfg.view3DElevation);
    xlim(ax, [xMin - xyPad, xMax + xyPad]);
    ylim(ax, [yMin - xyPad, yMax + xyPad]);
    zlim(ax, [zMin - zPad, zMax + zPad]);
    xlabel(ax, 'X / mm');
    ylabel(ax, 'Y / mm');
    zlabel(ax, 'Z / mm');
    title(ax, {titleText, subtitleText}, 'Interpreter', 'none');

    nColors = cfg.numColors;
    cmap = parula(nColors);
    colormap(ax, cmap);

    if zMax > zMin
        zNorm = (zMid - zMin) ./ (zMax - zMin);
        bins = 1 + floor(zNorm * (nColors - 1));
        bins = max(1, min(nColors, bins));
    else
        bins = ones(size(zMid));
    end

    if cfg.plotTravelMoves
        travelMask = ~printMask;
        if any(travelMask)
            plotSegments3D(ax, x0(travelMask), y0(travelMask), z0(travelMask), ...
                x1(travelMask), y1(travelMask), z1(travelMask), ...
                [0.78, 0.78, 0.78], cfg.travelLineWidth3D);
        end
    end

    for k = 1:nColors
        idx = printMask & (bins == k);
        if any(idx)
            plotSegments3D(ax, x0(idx), y0(idx), z0(idx), x1(idx), y1(idx), z1(idx), ...
                cmap(k, :), cfg.motionLineWidth3D);
        end
    end

    caxis(ax, [zMin, zMax]);
    cb = colorbar(ax);
    ylabel(cb, 'Z / mm');

    infoText = sprintf('X %.4g to %.4g mm, Y %.4g to %.4g mm, Z %.4g to %.4g mm', ...
        xMin, xMax, yMin, yMax, zMin, zMax);
    text(ax, xMin - xyPad * 0.65, yMin - xyPad * 0.55, zMin - zPad * 0.25, infoText, ...
        'Color', [0.2, 0.2, 0.2], 'FontSize', 10, 'Interpreter', 'none');

    drawnow;
    try
        savefig(fig, outFigPath, 'compact');
    catch
        savefig(fig, outFigPath);
    end

    if cfg.export3DPng
        try
            exportgraphics(fig, outPngPath, 'Resolution', cfg.resolutionDPI);
        catch
            print(fig, outPngPath, '-dpng', sprintf('-r%d', cfg.resolutionDPI));
        end
    end

    close(fig);
    fprintf('Rendered: %s\n', outFigPath);
    if cfg.export3DPng
        fprintf('Rendered: %s\n', outPngPath);
    end
end

function plotSegments(ax, x0, y0, x1, y1, rgb, lineWidth)
    n = numel(x0);
    if n == 0
        return;
    end
    xx = nan(3, n);
    yy = nan(3, n);
    xx(1, :) = x0(:).';
    xx(2, :) = x1(:).';
    yy(1, :) = y0(:).';
    yy(2, :) = y1(:).';
    line(ax, xx(:), yy(:), 'Color', rgb, 'LineWidth', lineWidth);
end

function plotSegments3D(ax, x0, y0, z0, x1, y1, z1, rgb, lineWidth)
    n = numel(x0);
    if n == 0
        return;
    end
    xx = nan(3, n);
    yy = nan(3, n);
    zz = nan(3, n);
    xx(1, :) = x0(:).';
    xx(2, :) = x1(:).';
    yy(1, :) = y0(:).';
    yy(2, :) = y1(:).';
    zz(1, :) = z0(:).';
    zz(2, :) = z1(:).';
    line(ax, xx(:), yy(:), zz(:), 'Color', rgb, 'LineWidth', lineWidth);
end

function writeStatsFile(statsPath, gcodePath, data, cfg, outputs)
    fid = fopen(statsPath, 'w');
    if fid < 0
        warning('无法写入统计文件：%s', statsPath);
        return;
    end
    cleanup = onCleanup(@() fclose(fid));

    s = data.stats;
    fprintf(fid, 'G-code path render stats, MATLAB\n');
    fprintf(fid, 'file = %s\n', gcodePath);
    fprintf(fid, 'line_count = %d\n', s.lineCount);
    fprintf(fid, 'movement_segments = %d\n', s.movementSegments);
    fprintf(fid, 'print_segments_positive_E = %d\n', s.printSegments);
    fprintf(fid, 'travel_or_nonextrude_segments = %d\n', s.travelSegments);
    fprintf(fid, 'G0_segments = %d\n', s.g0Segments);
    fprintf(fid, 'G1_segments = %d\n', s.g1Segments);
    fprintf(fid, 'total_positive_E = %.12g\n', s.totalPositiveE);
    fprintf(fid, 'machine_x_bounds_mm = [%.12g, %.12g]\n', s.xBounds(1), s.xBounds(2));
    fprintf(fid, 'machine_y_bounds_mm = [%.12g, %.12g]\n', s.yBounds(1), s.yBounds(2));
    fprintf(fid, 'machine_z_bounds_mm = [%.12g, %.12g]\n', s.zBounds(1), s.zBounds(2));
    fprintf(fid, 'A_bounds_deg = [%.12g, %.12g]\n', s.aBounds(1), s.aBounds(2));
    fprintf(fid, 'C_bounds_deg = [%.12g, %.12g]\n', s.cBounds(1), s.cBounds(2));
    fprintf(fid, 'ac_inverse_x_bounds_mm = [%.12g, %.12g]\n', s.acInverseXBounds(1), s.acInverseXBounds(2));
    fprintf(fid, 'ac_inverse_y_bounds_mm = [%.12g, %.12g]\n', s.acInverseYBounds(1), s.acInverseYBounds(2));
    fprintf(fid, 'ac_inverse_z_bounds_mm = [%.12g, %.12g]\n', s.acInverseZBounds(1), s.acInverseZBounds(2));
    fprintf(fid, 'parse_seconds = %.6f\n', s.parseSeconds);
    fprintf(fid, 'defaultExtrusionRelative = %d\n', cfg.defaultExtrusionRelative);
    fprintf(fid, 'numColors = %d\n', cfg.numColors);
    fprintf(fid, 'figurePixels = [%d, %d]\n', cfg.figurePixels(1), cfg.figurePixels(2));
    fprintf(fid, 'figure3DPixels = [%d, %d]\n', cfg.figure3DPixels(1), cfg.figure3DPixels(2));
    fprintf(fid, 'plotTravelMoves = %d\n', cfg.plotTravelMoves);
    fprintf(fid, 'alsoPlotMachineXY = %d\n', cfg.alsoPlotMachineXY);
    fprintf(fid, 'render3DPreview = %d\n', cfg.render3DPreview);
    fprintf(fid, 'export3DPng = %d\n', cfg.export3DPng);
    fprintf(fid, 'acInverseOrder = %s\n', char(cfg.acInverseOrder));
    fprintf(fid, 'view3D = [%.12g, %.12g]\n', cfg.view3DAzimuth, cfg.view3DElevation);
    fprintf(fid, 'output_c_unwrapped_top_png = %s\n', outputs.cUnwrappedTopPng);
    fprintf(fid, 'output_machine_xy_png = %s\n', outputs.machineXYPng);
    fprintf(fid, 'output_ac_inverse_3d_fig = %s\n', outputs.acInverse3DFig);
    fprintf(fid, 'output_ac_inverse_3d_png = %s\n', outputs.acInverse3DPng);
end

function s = formatCount(n)
    s0 = sprintf('%d', round(double(n)));
    nGroups = ceil(length(s0) / 3);
    parts = cell(1, nGroups);
    rightIdx = length(s0);
    for i = nGroups:-1:1
        leftIdx = max(1, rightIdx - 2);
        parts{i} = s0(leftIdx:rightIdx);
        rightIdx = leftIdx - 1;
    end
    s = strjoin(parts, ',');
end
