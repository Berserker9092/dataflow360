// Fabriques d'options ECharts : un seul endroit pour garder des graphiques cohérents et sobres.
import { fmtXof, fmtInt, fmtCompact, fmtDayShort, fmtMonth } from './format'

export const PALETTE = ['#6366F1', '#14B8A6', '#F59E0B', '#EC4899', '#3B82F6', '#8B5CF6', '#10B981', '#EF4444']
export const COLORS = { primary: '#6366F1', teal: '#14B8A6', amber: '#F59E0B', red: '#EF4444', green: '#16A34A', gray: '#9CA3AF' }

export function theme(dark) {
  return dark
    ? { text: '#9AA4B2', grid: '#243044', tipBg: '#0F172A', tipText: '#E5E7EB', tipBorder: '#334155', surface: '#111A2C' }
    : { text: '#6B7280', grid: '#EDF0F5', tipBg: '#FFFFFF', tipText: '#111827', tipBorder: '#E5E7EB', surface: '#FFFFFF' }
}

const tooltipBase = (t) => ({
  backgroundColor: t.tipBg,
  borderColor: t.tipBorder,
  textStyle: { color: t.tipText, fontSize: 12 },
  extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(15,23,42,.18);',
})

export const fmtLabel = (label, kind) => (kind === 'month' ? fmtMonth(label) : fmtDayShort(label))

// Courbes (avec comparaison en pointillés). series: [{ name, data, color?, dashed?, area? }]
export function lineOption({ labels, series, dark, money = true, labelKind = 'day' }) {
  const t = theme(dark)
  const fmt = money ? fmtXof : fmtInt
  return {
    animationDuration: 500,
    color: PALETTE,
    grid: { left: 8, right: 16, top: series.length > 1 ? 36 : 16, bottom: 4, containLabel: true },
    legend:
      series.length > 1
        ? { top: 0, right: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 4, textStyle: { color: t.text } }
        : undefined,
    tooltip: { ...tooltipBase(t), trigger: 'axis', valueFormatter: (v) => (v == null ? '–' : fmt(v)) },
    xAxis: {
      type: 'category',
      data: labels.map((l) => fmtLabel(l, labelKind)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.grid } },
      axisTick: { show: false },
      axisLabel: { color: t.text, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: t.text, formatter: (v) => fmtCompact(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: series.map((s, i) => {
      const color = s.color || (s.dashed ? COLORS.gray : PALETTE[i % PALETTE.length])
      return {
        name: s.name,
        type: 'line',
        data: s.data,
        smooth: 0.25,
        showSymbol: false,
        symbolSize: 6,
        lineStyle: { width: s.dashed ? 2 : 2.6, type: s.dashed ? 'dashed' : 'solid', color },
        itemStyle: { color },
        areaStyle:
          s.area === false || s.dashed
            ? undefined
            : {
                color: {
                  type: 'linear',
                  x: 0,
                  y: 0,
                  x2: 0,
                  y2: 1,
                  colorStops: [
                    { offset: 0, color: `${color}40` },
                    { offset: 1, color: `${color}00` },
                  ],
                },
              },
        z: s.dashed ? 1 : 2,
      }
    }),
  }
}

// Barres horizontales classées (top produits, pays...). items: [{ label, value }]
export function hbarOption({ items, dark, money = true, color = COLORS.primary }) {
  const t = theme(dark)
  const fmt = money ? fmtXof : fmtInt
  const data = [...items].reverse()
  return {
    animationDuration: 500,
    grid: { left: 8, right: 40, top: 4, bottom: 4, containLabel: true },
    tooltip: { ...tooltipBase(t), trigger: 'axis', axisPointer: { type: 'none' }, valueFormatter: (v) => fmt(v) },
    xAxis: { type: 'value', show: false },
    yAxis: {
      type: 'category',
      data: data.map((d) => d.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.text, width: 110, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        data: data.map((d) => d.value),
        barMaxWidth: 16,
        itemStyle: { color, borderRadius: [0, 6, 6, 0] },
        label: { show: true, position: 'right', color: t.text, fontSize: 11, formatter: (p) => fmtCompact(p.value) },
      },
    ],
  }
}

// Barres verticales (activité par minute...). labels + data.
export function barOption({ labels, data, dark, money = false, color = COLORS.primary, name = '' }) {
  const t = theme(dark)
  const fmt = money ? fmtXof : fmtInt
  return {
    animationDuration: 300,
    grid: { left: 8, right: 8, top: 12, bottom: 4, containLabel: true },
    tooltip: { ...tooltipBase(t), trigger: 'axis', valueFormatter: (v) => fmt(v) },
    xAxis: {
      type: 'category',
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: t.grid } },
      axisLabel: { color: t.text, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: t.text, formatter: (v) => fmtCompact(v) },
      splitLine: { lineStyle: { color: t.grid } },
    },
    series: [{ name, type: 'bar', data, barMaxWidth: 18, itemStyle: { color, borderRadius: [5, 5, 0, 0] } }],
  }
}

// Anneau avec légende. items: [{ label, value }]
export function donutOption({ items, dark, money = true }) {
  const t = theme(dark)
  const fmt = money ? fmtXof : fmtInt
  return {
    animationDuration: 500,
    color: PALETTE,
    tooltip: { ...tooltipBase(t), trigger: 'item', valueFormatter: (v) => fmt(v) },
    legend: {
      orient: 'vertical',
      right: 0,
      top: 'middle',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: t.text },
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '82%'],
        center: ['32%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: t.surface, borderWidth: 2 },
        label: { show: false },
        data: items.map((d) => ({ name: d.label, value: d.value })),
      },
    ],
  }
}

// Mini-courbe d'une carte KPI (sans axes).
export function sparkOption({ data, color = COLORS.primary }) {
  return {
    animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, boundaryGap: false, data: data.map((_, i) => i) },
    yAxis: { type: 'value', show: false, min: 'dataMin' },
    series: [
      {
        type: 'line',
        data,
        smooth: 0.3,
        showSymbol: false,
        lineStyle: { width: 2, color },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${color}33` },
              { offset: 1, color: `${color}00` },
            ],
          },
        },
      },
    ],
  }
}
