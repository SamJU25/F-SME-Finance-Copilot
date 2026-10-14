'use client';

import { FormEvent, useState } from 'react';
import type { CashAnalysisResponse } from '../types/api';

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const CSV_HEADER = 'transaction_id,posted_on,amount,currency,description,closing_balance';

function money(value: string, currency: string): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return `${value} ${currency}`;
  try {
    const [, sign, whole, fraction = ''] = match;
    const symbol = new Intl.NumberFormat('en', { style: 'currency', currency })
      .formatToParts(0)
      .find((part) => part.type === 'currency')?.value;
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${sign}${symbol ?? `${currency} `}${grouped}${fraction ? `.${fraction}` : ''}`;
  } catch {
    return `${value} ${currency}`;
  }
}

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [threshold, setThreshold] = useState('30');
  const [result, setResult] = useState<CashAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError('Choose a CSV file before reviewing cash activity.');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = new FormData();
      data.append('file', file);
      data.append('alert_threshold_days', threshold);
      const response = await fetch(`${API_URL}/api/v1/analyze`, { method: 'POST', body: data });
      const body = await response.json();
      if (!response.ok) {
        const detail = body?.error ?? body?.detail?.error;
        throw new Error(detail?.message ?? 'The file could not be analyzed. Check the CSV and try again.');
      }
      setResult(body as CashAnalysisResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'A network error interrupted the request. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark" aria-hidden="true">$</span><span>Cash review</span></div>
        <span className="demo-tag">Local privacy mode</span>
      </header>
      <main>
        <div className="eyebrow">Working capital · Cash Flow Review</div>
        <h1>A clearer read on your cash movement.</h1>
        <p className="lede">Import a bank statement CSV to review recent transactions, current balance, and an explainable historical-average runway indicator.</p>

        <div className="content-grid">
          <section className="panel" aria-labelledby="upload-title">
            <h2 id="upload-title">Review a statement</h2>
            <p className="panel-intro">Your file is processed for this request only. It is not stored or sent to an external service.</p>
            <form onSubmit={analyze}>
              <label className="field-label" htmlFor="threshold">Alert threshold (days)</label>
              <input id="threshold" name="alert_threshold_days" type="number" min="1" step="1" value={threshold} onChange={(event) => setThreshold(event.target.value)} required />

              <div className="dropzone">
                <span className="upload-icon" aria-hidden="true">↑</span>
                <label className="field-label" htmlFor="csv-file">Choose a CSV file</label>
                <input
                  id="csv-file"
                  className="file-input"
                  aria-label="Choose bank statement CSV file"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => {
                    setFile(event.target.files?.[0] ?? null);
                    setResult(null);
                    setError(null);
                  }}
                />
                <div className="file-name">{file ? file.name : 'UTF-8 CSV · max 1 MB'}</div>
              </div>

              <button className="submit" type="submit" disabled={loading || !threshold || Number(threshold) < 1}>
                {loading ? 'Reviewing statement…' : 'Analyze cash activity'}
              </button>
            </form>
            {loading && <div className="notice loading" role="status" aria-live="polite">Reading your statement and calculating a historical average…</div>}
            {error && <div className="notice error" role="alert">{error}</div>}
            {result && <div className="notice success" role="status">Review complete. {result.accepted_count} transaction{result.accepted_count === 1 ? '' : 's'} accepted.</div>}

            {result && (
              <section className="result" aria-labelledby="result-title" aria-live="polite">
                <div className="result-head">
                  <h2 id="result-title">Cash summary</h2>
                  <span className={`status ${result.cash_status}`}>{result.cash_status.replaceAll('_', ' ')}</span>
                </div>
                <div className="metrics">
                  <Metric label="Current balance" value={money(result.current_balance, result.currency)} />
                  <Metric label="Historical net change" value={money(result.net_period_change, result.currency)} />
                  <Metric label="Average daily burn" value={money(result.average_daily_burn, result.currency)} />
                  <Metric label="Estimated runway" value={result.runway_days === null ? 'No burn' : `${result.runway_days} days`} />
                  <Metric label="Period reviewed" value={`${result.period_days} days`} />
                  <Metric label="Rows accepted" value={`${result.accepted_count}`} />
                </div>
                <p className="caveat">This is a historical-average indicator from the uploaded rows. It is not a forecast, credit decision, or financial advice.</p>
                {result.rejected_rows.length > 0 && (
                  <div className="rejections">
                    <h3>Rows not included ({result.rejected_rows.length})</h3>
                    <ul>{result.rejected_rows.map((row) => <li key={`${row.row_number}-${row.reason_code}`}>Row {row.row_number}: {row.reason_code.replaceAll('_', ' ').toLowerCase()}</li>)}</ul>
                  </div>
                )}
              </section>
            )}
          </section>

          <aside className="panel" aria-labelledby="steps-title">
            <h2 id="steps-title">What this review does</h2>
            <p className="panel-intro">A transparent starting point. No live accounts or financial actions.</p>
            <p className="panel-intro">Try a <a href="/synthetic-statement.csv" download>sample statement CSV</a> to see accepted and rejected row handling.</p>
            <div className="side-note"><span className="note-index">01</span><div><strong>Checks the rows</strong><p>Malformed dates, amounts, duplicate IDs and mixed currencies are reported safely.</p></div></div>
            <div className="side-note"><span className="note-index">02</span><div><strong>Shows the arithmetic</strong><p>Money is parsed and calculated with exact decimal values before formatting for display.</p></div></div>
            <div className="side-note"><span className="note-index">03</span><div><strong>Uses your threshold</strong><p>Choose the number of days that defines your low-runway indicator.</p></div></div>
            <p className="caveat">Required CSV header:</p>
            <code className="file-name">{CSV_HEADER}</code>
          </aside>
        </div>
        <p className="footer">Privacy-first · files are processed locally in-memory and never persisted</p>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong></div>;
}
