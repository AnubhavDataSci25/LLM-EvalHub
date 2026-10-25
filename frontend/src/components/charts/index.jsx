/**
 * Chart components.
 *
 * All of them read colours from the CSS theme variables at render time, so
 * charts follow light/dark without a second palette definition. Every chart
 * renders an explicit empty state rather than an axis with no data.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { NA, titleCase } from '../../lib/format'

/** Series colours — olive-led, with earthy accents that stay distinguishable. */
export const SERIES_COLOURS = [
  '#7C8C46', // olive-500
  '#B4633F', // clay-500
  '#4A562C', // olive-700
  '#9C8862', // sand-600
  '#5C7A8C', // slate blue
  '#97A75E', // olive-400
  '#8C5E7C', // muted plum
  '#B8A47C', // sand-500
]

const axisProps = {
  stroke: 'rgb(var(--faint))',
  fontSize: 11,
  tickLine: false,
  axisLine: { stroke: 'rgb(var(--line))' },
}

function ChartFrame({ children, height = 280, empty, emptyLabel = 'No data yet.' }) {
  if (empty) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center rounded-xl border border-dashed border-line bg-overlay/30 text-sm text-faint"
      >
        {emptyLabel}
      </div>
    )
  }
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  )
}

function TooltipBox({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-elevated px-3 py-2 shadow-lift">
      {label ? <p className="mb-1.5 text-xs font-semibold text-ink">{label}</p> : null}
      <div className="space-y-1">
        {payload.map((entry) => (
          <div key={entry.dataKey || entry.name} className="flex items-center gap-2 text-xs">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: entry.color || entry.fill }}
            />
            <span className="text-muted">{titleCase(entry.name || entry.dataKey)}</span>
            <span className="mono ml-auto font-semibold text-ink">
              {formatter
                ? formatter(entry.value)
                : entry.value === null || entry.value === undefined
                  ? NA
                  : typeof entry.value === 'number'
                    ? entry.value.toFixed(entry.value < 10 ? 3 : 0)
                    : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */

/** Grouped bars comparing models across one or more metrics. */
export function ModelComparisonChart({ rows = [], metrics = [], height = 300 }) {
  const data = rows.map((row) => {
    const point = { name: row.label || row.key }
    metrics.forEach((metric) => {
      const value = row.metrics?.[metric]?.mean ?? row[metric]
      if (value !== null && value !== undefined) point[metric] = Number(value.toFixed(4))
    })
    return point
  })
  const active = metrics.filter((m) => data.some((d) => d[m] !== undefined))

  return (
    <ChartFrame height={height} empty={!data.length || !active.length} emptyLabel="No scored metrics to compare.">
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 4 }} barGap={3}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" vertical={false} />
        <XAxis dataKey="name" {...axisProps} interval={0} angle={data.length > 3 ? -12 : 0} dy={6} />
        <YAxis domain={[0, 1]} {...axisProps} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: 'rgb(var(--overlay))', opacity: 0.5 }} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(value) => <span className="text-muted">{titleCase(value)}</span>}
        />
        {active.map((metric, index) => (
          <Bar
            key={metric}
            dataKey={metric}
            fill={SERIES_COLOURS[index % SERIES_COLOURS.length]}
            radius={[4, 4, 0, 0]}
            maxBarSize={44}
          />
        ))}
      </BarChart>
    </ChartFrame>
  )
}

/** Metric movement across successive runs. */
export function MetricTrendChart({ points = [], metrics = ['correctness', 'faithfulness'], height = 280 }) {
  const active = metrics.filter((m) => points.some((p) => p[m] !== null && p[m] !== undefined))
  return (
    <ChartFrame
      height={height}
      empty={points.length < 2 || !active.length}
      emptyLabel="At least two completed runs are needed to show a trend."
    >
      <LineChart data={points} margin={{ top: 8, right: 12, left: -18, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" vertical={false} />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis domain={[0, 1]} {...axisProps} />
        <Tooltip content={<TooltipBox />} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(value) => <span className="text-muted">{titleCase(value)}</span>}
        />
        {active.map((metric, index) => (
          <Line
            key={metric}
            type="monotone"
            dataKey={metric}
            stroke={SERIES_COLOURS[index % SERIES_COLOURS.length]}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: SERIES_COLOURS[index % SERIES_COLOURS.length] }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ChartFrame>
  )
}

/** Horizontal bars for the failure taxonomy. */
export function FailureDistributionChart({ items = [], height = 280 }) {
  const data = items.map((item) => ({
    name: item.label || titleCase(item.failure_type),
    count: item.count,
  }))
  return (
    <ChartFrame height={height} empty={!data.length} emptyLabel="No failures recorded.">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, left: 12, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" horizontal={false} />
        <XAxis type="number" {...axisProps} allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={130} {...axisProps} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: 'rgb(var(--overlay))', opacity: 0.5 }} />
        <Bar dataKey="count" radius={[0, 5, 5, 0]} maxBarSize={22}>
          {data.map((_, index) => (
            <Cell key={index} fill={SERIES_COLOURS[index % SERIES_COLOURS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  )
}

/** Latency or score histogram. */
export function DistributionChart({ data = [], dataKey = 'count', labelKey = 'bucket', height = 220, colour }) {
  const hasValues = data.some((d) => d[dataKey] > 0)
  return (
    <ChartFrame height={height} empty={!hasValues} emptyLabel="Nothing measured yet.">
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" vertical={false} />
        <XAxis dataKey={labelKey} {...axisProps} />
        <YAxis {...axisProps} allowDecimals={false} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: 'rgb(var(--overlay))', opacity: 0.5 }} />
        <Bar dataKey={dataKey} fill={colour || SERIES_COLOURS[0]} radius={[4, 4, 0, 0]} maxBarSize={46} />
      </BarChart>
    </ChartFrame>
  )
}

/** Latency per model — separate from quality so the trade-off is visible. */
export function LatencyChart({ rows = [], height = 260 }) {
  const data = rows
    .filter((row) => row.avg_latency_ms !== null && row.avg_latency_ms !== undefined)
    .map((row) => ({
      name: row.label || row.key,
      average: Math.round(row.avg_latency_ms),
      p95: row.p95_latency_ms ? Math.round(row.p95_latency_ms) : null,
    }))
  return (
    <ChartFrame height={height} empty={!data.length} emptyLabel="No latency was recorded.">
      <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 4 }} barGap={3}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" vertical={false} />
        <XAxis dataKey="name" {...axisProps} />
        <YAxis {...axisProps} unit=" ms" width={62} />
        <Tooltip content={<TooltipBox formatter={(v) => (v === null ? NA : `${v} ms`)} />} cursor={{ fill: 'rgb(var(--overlay))', opacity: 0.5 }} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(value) => <span className="text-muted">{titleCase(value)}</span>}
        />
        <Bar dataKey="average" name="Average" fill={SERIES_COLOURS[0]} radius={[4, 4, 0, 0]} maxBarSize={38} />
        <Bar dataKey="p95" name="p95" fill={SERIES_COLOURS[3]} radius={[4, 4, 0, 0]} maxBarSize={38} />
      </BarChart>
    </ChartFrame>
  )
}

/** Radar profile across metrics — useful when comparing 2-4 models. */
export function MetricRadarChart({ rows = [], metrics = [], height = 300 }) {
  const data = metrics.map((metric) => {
    const point = { metric: titleCase(metric) }
    rows.forEach((row) => {
      const value = row.metrics?.[metric]?.mean ?? row[metric]
      if (value !== null && value !== undefined) point[row.label || row.key] = Number(value.toFixed(4))
    })
    return point
  })
  const usable = data.filter((point) => Object.keys(point).length > 1)

  return (
    <ChartFrame
      height={height}
      empty={usable.length < 3 || !rows.length}
      emptyLabel="A radar needs at least three shared metrics."
    >
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="rgb(var(--line))" />
        <PolarAngleAxis dataKey="metric" tick={{ fill: 'rgb(var(--muted))', fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 1]} tick={{ fill: 'rgb(var(--faint))', fontSize: 10 }} />
        <Tooltip content={<TooltipBox />} />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(value) => <span className="text-muted">{value}</span>}
        />
        {rows.map((row, index) => (
          <Radar
            key={row.key}
            name={row.label || row.key}
            dataKey={row.label || row.key}
            stroke={SERIES_COLOURS[index % SERIES_COLOURS.length]}
            fill={SERIES_COLOURS[index % SERIES_COLOURS.length]}
            fillOpacity={0.16}
            strokeWidth={2}
          />
        ))}
      </RadarChart>
    </ChartFrame>
  )
}

/** Before/after deltas per metric — the improvement-loop chart. */
export function DeltaChart({ deltas = [], height = 260 }) {
  const data = deltas
    .filter((d) => d.delta !== null && d.delta !== undefined)
    .map((d) => {
      const deltaVal = Number((d.delta * 100).toFixed(2))
      const ciLowVal =
        d.ci_low !== null && d.ci_low !== undefined ? Number((d.ci_low * 100).toFixed(2)) : null
      const ciHighVal =
        d.ci_high !== null && d.ci_high !== undefined ? Number((d.ci_high * 100).toFixed(2)) : null
      const error =
        ciLowVal !== null && ciHighVal !== null
          ? [Math.max(0, deltaVal - ciLowVal), Math.max(0, ciHighVal - deltaVal)]
          : undefined

      return {
        name: d.label || titleCase(d.metric),
        delta: deltaVal,
        ciLow: ciLowVal,
        ciHigh: ciHighVal,
        error,
        direction: d.direction,
        significance: d.significance,
      }
    })

  const colourFor = (entry) => {
    if (entry.significance === 'significant') {
      if (entry.direction === 'improved') return 'rgb(var(--ok))'
      if (entry.direction === 'regressed') return 'rgb(var(--bad))'
    }
    return 'rgb(var(--faint))'
  }

  return (
    <ChartFrame height={height} empty={!data.length} emptyLabel="No metric was measured on both sides.">
      <BarChart data={data} margin={{ top: 12, right: 12, left: -14, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 4" stroke="rgb(var(--line))" vertical={false} />
        <XAxis dataKey="name" {...axisProps} />
        <YAxis {...axisProps} unit=" pp" width={56} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const entry = payload[0].payload
            return (
              <div className="rounded-xl border border-line bg-elevated px-3 py-2 shadow-lift text-xs">
                <p className="mb-1 font-semibold text-ink">{entry.name}</p>
                <p className="mono font-semibold text-ink">
                  Delta: {entry.delta > 0 ? '+' : ''}{entry.delta} pp
                </p>
                {entry.ciLow !== null && entry.ciHigh !== null ? (
                  <p className="mono text-[0.7rem] text-muted">
                    95% CI: [{entry.ciLow > 0 ? '+' : ''}{entry.ciLow}, {entry.ciHigh > 0 ? '+' : ''}{entry.ciHigh}] pp
                  </p>
                ) : null}
                {entry.significance ? (
                  <p className="mt-1 text-[0.7rem] text-muted">
                    Significance:{' '}
                    <span className="font-medium text-ink capitalize">
                      {entry.significance.replace('_', ' ')}
                    </span>
                  </p>
                ) : null}
              </div>
            )
          }}
          cursor={{ fill: 'rgb(var(--overlay))', opacity: 0.5 }}
        />
        <Bar dataKey="delta" radius={[4, 4, 0, 0]} maxBarSize={44}>
          <ErrorBar dataKey="error" width={4} strokeWidth={1.5} stroke="rgb(var(--ink))" />
          {data.map((entry, index) => (
            <Cell key={index} fill={colourFor(entry)} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  )
}
