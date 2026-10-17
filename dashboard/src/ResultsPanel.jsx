import { useEffect, useState } from 'react'

const W = 260
const H = 120
const PAD = 28

// One small line chart: every series shares the y range of its own data. Numbers are in the table below.
function Chart({ title, epochs, series }) {
  const all = series.flatMap((s) => s.values)
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const x = (i) => PAD + (i * (W - PAD - 6)) / (epochs.length - 1)
  const y = (v) => 8 + ((hi - v) * (H - 8 - 20)) / (hi - lo || 1)
  return (
    <figure className="chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        <text x="0" y="12" className="axis">{hi.toFixed(4)}</text>
        <text x="0" y={H - 20} className="axis">{lo.toFixed(4)}</text>
        {epochs.map((e, i) => (
          <text key={e} x={x(i)} y={H - 4} className="axis" textAnchor="middle">{e}</text>
        ))}
        {series.map((s, k) => (
          <polyline
            key={s.label}
            className={`line line${k}`}
            fill="none"
            points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}
          />
        ))}
      </svg>
      <div className="legend">
        {series.map((s, k) => (
          <span key={s.label} className={`key key${k}`}>{s.label}</span>
        ))}
        <span>x: epoch</span>
      </div>
      <p className="axis-note">y-axis runs from {lo.toFixed(4)} to {hi.toFixed(4)}, not from 0</p>
    </figure>
  )
}

function Confusion({ classes, matrix }) {
  return (
    <table className="results-table cm">
      <thead>
        <tr>
          <th>true \ predicted</th>
          {classes.map((c) => <th key={c}>{c}</th>)}
        </tr>
      </thead>
      <tbody>
        {matrix.map((row, i) => {
          const total = row.reduce((a, b) => a + b, 0)
          return (
            <tr key={classes[i]}>
              <th>{classes[i]}</th>
              {row.map((n, j) => (
                <td
                  key={classes[j]}
                  style={{ background: `color-mix(in srgb, var(--accent) ${Math.round((100 * n) / total)}%, transparent)` }}
                >
                  {n}
                </td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Router5({ r }) {
  const epochs = r.curve.map((c) => c.epoch)
  return (
    <section>
      <h2>Earlier 5-class model (models/router_distilbert)</h2>
      <p className="warn">
        The curve and confusion matrix below belong to this earlier 5-class model (MASSIVE data only). They are
        NOT the 6-class model Friday runs (models/router_v2, next section).
      </p>
      <div className="charts">
        <Chart title="Train loss" epochs={epochs} series={[{ label: 'train loss', values: r.curve.map((c) => c.train_loss) }]} />
        <Chart
          title="Dev accuracy and macro-F1"
          epochs={epochs}
          series={[
            { label: 'dev acc', values: r.curve.map((c) => c.dev_acc) },
            { label: 'dev macro-F1', values: r.curve.map((c) => c.dev_macro_f1) },
          ]}
        />
      </div>
      <table className="results-table">
        <thead>
          <tr><th>epoch</th><th>train loss</th><th>dev acc</th><th>dev macro-F1</th><th>seconds</th></tr>
        </thead>
        <tbody>
          {r.curve.map((c) => (
            <tr key={c.epoch}>
              <td>{c.epoch}</td><td>{c.train_loss}</td><td>{c.dev_acc}</td><td>{c.dev_macro_f1}</td><td>{c.seconds}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Checkpoint: best dev macro-F1 at epoch {r.best_epoch}. Test accuracy {r.test_accuracy}, macro-F1{' '}
        {r.test_macro_f1} ({r.confusion_total} test rows, one run, one seed).
      </p>
      <h3>Confusion matrix (test, {r.confusion_total} rows; shading = share of the true-class row)</h3>
      <Confusion classes={r.classes} matrix={r.confusion} />
    </section>
  )
}

function Router6({ r }) {
  const b = r.runs.find((x) => x.run.startsWith(r.deployed_run))
  return (
    <section>
      <h2>Deployed 6-class model (models/router_v2)</h2>
      <p>
        Run {r.deployed_run} is the model Friday runs: {b.correct}/{b.total} correct on the held-out own lines
        (accuracy {b.own_accuracy}, macro-F1 {b.own_macro_f1}).
      </p>
      <p className="warn">
        One seed per run, {b.total} held-out lines, typed lowercase text (not Whisper output). A per-epoch curve
        and a confusion matrix for these 6-class runs were not saved: the raw Kaggle output is not in the repo,
        so none is shown.
      </p>
      <table className="results-table">
        <thead>
          <tr><th>run</th><th>own accuracy</th><th>own macro-F1</th><th>doc_qa</th><th>MASSIVE test acc (5 classes)</th></tr>
        </thead>
        <tbody>
          {r.runs.map((x) => (
            <tr key={x.run} className={x.run.startsWith(r.deployed_run) ? 'deployed' : ''}>
              <td>{x.run}</td>
              <td>{x.own_accuracy} ({x.correct}/{x.total})</td>
              <td>{x.own_macro_f1}</td>
              <td>{x.doc_qa_correct}/{x.doc_qa_total}</td>
              <td>{x.massive_test_acc}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Run {r.deployed_run} per class</h3>
      <table className="results-table">
        <thead>
          <tr><th>class</th><th>correct</th><th>precision</th><th>recall</th><th>F1</th></tr>
        </thead>
        <tbody>
          {r.run_b_per_class.map((c) => (
            <tr key={c.class}>
              <td>{c.class}</td><td>{c.correct}/{c.support}</td><td>{c.precision}</td><td>{c.recall}</td><td>{c.f1}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export default function ResultsPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/results/router_results.json')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then(setData)
      .catch((err) => setError(`Could not load the results file: ${err.message}`))
  }, [])

  if (error) return <div className="empty">{error}</div>
  if (!data) return <div className="empty">Loading...</div>
  return (
    <main className="results">
      <p className="meta">
        Numbers are copied from training/*.md by scripts/p705_extract.py. The raw Kaggle output files were not saved.
      </p>
      <Router5 r={data.router5} />
      <Router6 r={data.router6} />
    </main>
  )
}
