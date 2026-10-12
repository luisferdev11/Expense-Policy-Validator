import type { VariantStats } from "../lib/evaluation";

/** Accuracy with its 95 % interval, one row per model. Axis from 0.8 to 1 keeps the gaps readable. */
export function ForestPlot({ variants, highlight }: { variants: VariantStats[]; highlight: string }) {
  const min = 0.8;
  const W = 640;
  const left = 150;
  const right = 20;
  const rowH = 32;
  const H = variants.length * rowH + 40;
  const x = (v: number) => left + ((Math.max(min, v) - min) / (1 - min)) * (W - left - right);
  const ticks = [0.8, 0.85, 0.9, 0.95, 1];
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Category accuracy with 95 percent intervals for each model"
      className="chart"
      style={{ width: "100%", height: "auto" }}
    >
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={8} y2={H - 28} stroke="var(--border)" strokeWidth={1} />
          <text x={x(t)} y={H - 10} textAnchor="middle" fontSize={11} fill="var(--ink-muted)" fontFamily="var(--font-mono)">
            {Math.round(t * 100)} %
          </text>
        </g>
      ))}
      {variants.map((v, i) => {
        const y = 24 + i * rowH;
        const on = v.variant === highlight;
        return (
          <g key={v.variant}>
            <text x={left - 10} y={y + 4} textAnchor="end" fontSize={12} fill="var(--ink)" fontFamily="var(--font-mono)" fontWeight={on ? 600 : 400}>
              {v.variant}
            </text>
            <line x1={x(v.accuracy.interval[0])} x2={x(v.accuracy.interval[1])} y1={y} y2={y} stroke={on ? "var(--accent)" : "var(--ink-muted)"} strokeWidth={3} strokeLinecap="round" />
            <circle cx={x(v.accuracy.value)} cy={y} r={5} fill={on ? "var(--accent)" : "var(--surface)"} stroke={on ? "var(--accent)" : "var(--ink-muted)"} strokeWidth={2} />
            <title>{`${v.variant}: ${v.accuracy.k} of ${v.accuracy.n}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

/** A 3×3 disposition matrix; shade follows the count. Rows are the answer, columns the proposal. */
export function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const max = Math.max(1, ...matrix.flat());
  return (
    <table className="confusion" aria-label="Disposition confusion matrix">
      <thead>
        <tr>
          <th scope="col" className="muted">
            answer ↓ · proposed →
          </th>
          {labels.map((l) => (
            <th key={l} scope="col">
              {l}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.map((row, i) => (
          <tr key={labels[i]}>
            <th scope="row">{labels[i]}</th>
            {row.map((n, j) => (
              <td
                key={labels[j]}
                className={i === j ? "is-diag" : ""}
                style={{ background: n === 0 ? "transparent" : `color-mix(in srgb, ${i === j ? "var(--accent)" : "var(--high)"} ${Math.round(15 + (n / max) * 55)}%, var(--surface))` }}
              >
                <span className="ll-num">{n}</span>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Accuracy of the lines kept as the EXC-03 confidence threshold rises (E7), with the chosen one. */
export function CoverageCurve({
  curve,
  threshold,
}: {
  curve: { threshold: number; coverage: number; accuracy: number }[];
  threshold: number;
}) {
  const W = 640;
  const H = 220;
  const l = 44;
  const r = 16;
  const t = 12;
  const b = 34;
  const ymin = 0.9;
  const px = (cov: number) => l + cov * (W - l - r);
  const py = (acc: number) => t + (1 - (Math.max(ymin, acc) - ymin) / (1 - ymin)) * (H - t - b);
  const pts = curve.map((c) => `${px(c.coverage).toFixed(1)},${py(c.accuracy).toFixed(1)}`).join(" ");
  const chosen = [...curve].reverse().find((c) => c.threshold >= threshold) ?? curve[0];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Accuracy against share of items kept as the confidence threshold rises" className="chart" style={{ width: "100%", height: "auto" }}>
      {[0.9, 0.95, 1].map((v) => (
        <g key={v}>
          <line x1={l} x2={W - r} y1={py(v)} y2={py(v)} stroke="var(--border)" />
          <text x={l - 6} y={py(v) + 4} textAnchor="end" fontSize={11} fill="var(--ink-muted)" fontFamily="var(--font-mono)">
            {Math.round(v * 100)} %
          </text>
        </g>
      ))}
      {[0, 0.5, 1].map((v) => (
        <text key={v} x={px(v)} y={H - 12} textAnchor="middle" fontSize={11} fill="var(--ink-muted)" fontFamily="var(--font-mono)">
          {Math.round(v * 100)} %
        </text>
      ))}
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2} />
      <circle cx={px(chosen.coverage)} cy={py(chosen.accuracy)} r={5} fill="var(--high)" stroke="var(--surface)" strokeWidth={2} />
      <text x={px(chosen.coverage) - 8} y={py(chosen.accuracy) + 18} textAnchor="end" fontSize={11} fill="var(--ink)">
        threshold {threshold}
      </text>
      <text x={W / 2} y={H - 1} textAnchor="middle" fontSize={11} fill="var(--ink-muted)">
        share of items kept (coverage)
      </text>
    </svg>
  );
}
