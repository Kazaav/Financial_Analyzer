/* Financial Analyzer · ECharts renderer · v20260526 */
(function () {
  'use strict';
  if (typeof echarts === 'undefined') return;

  // Format number based on hint
  function fmt(value, hint) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    var v = Number(value);
    var abs = Math.abs(v);
    if (hint === 'percent') return (v * 100).toFixed(1) + '%';
    if (hint === 'ratio') return v.toFixed(2) + 'x';
    if (hint === 'people') return v.toLocaleString() + ' 人';
    if (hint === 'money_per_person') return v.toFixed(1) + ' 百万円/人';
    // money: 兆 / 億 / 百万
    if (abs >= 1000000) return (v / 1000000).toFixed(2) + '兆円';
    if (abs >= 100) return Math.round(v / 100).toLocaleString() + '億円';
    return Math.round(v).toLocaleString() + '百万円';
  }

  // Theme tokens read live from CSS custom properties, so charts follow the
  // active light/dark theme. Recomputed on 'fa-themechange'. Palette stays fixed
  // (series identity) but is theme-agnostic enough to read on both backgrounds.
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fallback;
  }
  function getTheme() {
    return {
      text: cssVar('--t3', '#7d8fa8'),
      textBright: cssVar('--t1', '#e8edf6'),
      grid: cssVar('--chart-grid', '#1b2538'),
      bd: cssVar('--chart-axis', '#2b3851'),
      accent: cssVar('--accent', '#6aaaff'),
      elev: cssVar('--bg-elev-2', '#141c2b'),
      palette: ['#4e8ee8', '#2faa6f', '#d4893a', '#d4564c', '#9472d4', '#1aa9b8', '#c2682f', '#7c5fc0'],
    };
  }
  var theme = getTheme();

  function baseOption() {
    return {
      backgroundColor: 'transparent',
      grid: { left: 8, right: 8, top: 24, bottom: 36, containLabel: true },
      textStyle: { color: theme.text, fontFamily: 'Inter, "Noto Sans JP", sans-serif' },
      tooltip: {
        trigger: 'item',
        backgroundColor: theme.elev,
        borderColor: theme.bd,
        borderWidth: 1,
        textStyle: { color: theme.textBright, fontSize: 12 },
        padding: [8, 12],
        extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,.28); border-radius: 6px;',
      },
    };
  }

  function lineOption(payload) {
    var opt = baseOption();
    opt.tooltip.trigger = 'axis';
    opt.tooltip.axisPointer = { type: 'line', lineStyle: { color: theme.bd } };
    opt.xAxis = {
      type: 'category',
      data: payload.categories,
      axisLine: { lineStyle: { color: theme.bd } },
      axisTick: { show: false },
      axisLabel: { color: theme.text, fontSize: 11, fontFamily: 'JetBrains Mono, monospace' },
    };
    opt.yAxis = {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: {
        color: theme.text, fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
        formatter: function (v) { return fmt(v, payload.format); },
      },
    };
    opt.tooltip.formatter = function (params) {
      var lines = [params[0].axisValue + '年度'];
      params.forEach(function (p) {
        lines.push(
          '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + p.color + ';margin-right:6px"></span>' +
          p.seriesName + '<span style="float:right;margin-left:18px;font-family:JetBrains Mono">' + fmt(p.value, payload.format) + '</span>'
        );
      });
      return lines.join('<br>');
    };
    opt.series = payload.series.map(function (s) {
      return {
        name: s.name, type: 'line', smooth: false,
        data: s.data, color: s.color,
        symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2 },
        emphasis: { focus: 'series' },
      };
    });
    if (payload.series.length > 1) {
      opt.legend = {
        data: payload.series.map(function (s) { return s.name; }),
        textStyle: { color: theme.text, fontSize: 11 },
        top: 4, right: 4, icon: 'circle', itemHeight: 8,
      };
      opt.grid.top = 38;
    }
    return opt;
  }

  function barOption(payload) {
    var opt = baseOption();
    opt.xAxis = {
      type: 'category',
      data: payload.categories,
      axisLine: { lineStyle: { color: theme.bd } },
      axisTick: { show: false },
      axisLabel: {
        color: theme.text, fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
        interval: 0,
        formatter: function (v) {
          if (!v) return '';
          return v.length > 8 ? v.slice(0, 8) + '..' : v;
        },
      },
    };
    opt.yAxis = {
      type: 'value', scale: true,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: {
        color: theme.text, fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
        formatter: function (v) { return fmt(v, payload.format); },
      },
    };
    opt.tooltip.formatter = function (p) {
      var year = payload.years[p.dataIndex] || '';
      return '<strong style="font-weight:600">' + p.name + '</strong>' +
        (year ? ' / ' + year + '年度' : '') + '<br>' +
        '<span style="font-family:JetBrains Mono">' + fmt(p.value, payload.format) + '</span>';
    };
    opt.series = [{
      type: 'bar',
      data: payload.values.map(function (v, i) {
        return { value: v, itemStyle: { color: payload.colors[i] || theme.accent, borderRadius: [3, 3, 0, 0] } };
      }),
      barMaxWidth: 36,
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(110,168,255,.5)' } },
    }];
    return opt;
  }

  function scatterOption(payload) {
    var opt = baseOption();
    opt.tooltip.trigger = 'item';
    opt.xAxis = {
      type: 'category',
      data: payload.points.map(function (p, i) { return p.label; }),
      axisLine: { lineStyle: { color: theme.bd } },
      axisTick: { show: false },
      axisLabel: { show: false },
    };
    opt.yAxis = {
      type: 'value', scale: true,
      axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: theme.grid, type: 'dashed' } },
      axisLabel: {
        color: theme.text, fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
        formatter: function (v) { return fmt(v, payload.format); },
      },
    };
    opt.tooltip.formatter = function (p) {
      var pt = payload.points[p.dataIndex];
      return '<strong style="font-weight:600">' + pt.label + '</strong>' +
        (pt.year ? ' / ' + pt.year + '年度' : '') + '<br>' +
        '<span style="font-family:JetBrains Mono">' + fmt(pt.value, payload.format) + '</span>';
    };
    opt.series = [{
      type: 'scatter', symbolSize: 14,
      data: payload.points.map(function (p, i) {
        return { value: [i, p.value], itemStyle: { color: p.color || theme.accent } };
      }),
      emphasis: { itemStyle: { shadowBlur: 12, shadowColor: 'rgba(110,168,255,.7)' } },
    }];
    return opt;
  }

  function renderChart(host) {
    var raw = host.getAttribute('data-echarts');
    if (!raw) return;
    var payload;
    try { payload = JSON.parse(raw); } catch (e) { return; }
    var chart = echarts.init(host, null, { renderer: 'svg' });
    var opt;
    if (payload.type === 'line') opt = lineOption(payload);
    else if (payload.type === 'bar') opt = barOption(payload);
    else if (payload.type === 'scatter') opt = scatterOption(payload);
    else return;
    chart.setOption(opt);
    return chart;
  }

  var resizeQueue = [];

  function initAll() {
    var hosts = document.querySelectorAll('.echart-host');
    hosts.forEach(function (host) {
      // Defer hidden charts (tab not active or panel hidden) until visible
      if (host.offsetParent === null) {
        // Use IntersectionObserver to render when visible
        var obs = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting && !host.dataset.rendered) {
              host.dataset.rendered = '1';
              var inst = renderChart(host);
              if (inst) resizeQueue.push(inst);
              obs.disconnect();
            }
          });
        }, { threshold: 0.05 });
        obs.observe(host);
      } else {
        host.dataset.rendered = '1';
        var inst = renderChart(host);
        if (inst) resizeQueue.push(inst);
      }
    });

    // Also re-init when a hidden panel becomes visible (tab switch / category switch)
    document.addEventListener('click', function () {
      setTimeout(function () {
        document.querySelectorAll('.echart-host').forEach(function (host) {
          if (!host.dataset.rendered && host.offsetParent !== null) {
            host.dataset.rendered = '1';
            var inst = renderChart(host);
            if (inst) resizeQueue.push(inst);
          } else if (host.dataset.rendered && host.offsetParent !== null) {
            var inst = echarts.getInstanceByDom(host);
            if (inst) inst.resize();
          }
        });
      }, 80);
    }, true);

    window.addEventListener('resize', function () {
      resizeQueue.forEach(function (c) { try { c.resize(); } catch (e) {} });
    });

    // Re-theme rendered charts when the user toggles light/dark.
    document.addEventListener('fa-themechange', function () {
      theme = getTheme();
      document.querySelectorAll('.echart-host').forEach(function (host) {
        if (!host.dataset.rendered) return;
        var inst = echarts.getInstanceByDom(host);
        if (!inst) return;
        var raw = host.getAttribute('data-echarts');
        if (!raw) return;
        var payload;
        try { payload = JSON.parse(raw); } catch (e) { return; }
        var opt = payload.type === 'line' ? lineOption(payload)
          : payload.type === 'bar' ? barOption(payload)
          : payload.type === 'scatter' ? scatterOption(payload) : null;
        if (opt) inst.setOption(opt, true);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
