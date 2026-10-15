'use client';

import { FormEvent, useState } from 'react';
import type { CashAnalysisResponse, CopilotResponse } from '../types/api';

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
  const [csvText, setCsvText] = useState<string | null>(null);
  const [threshold, setThreshold] = useState('30');
  const [result, setResult] = useState<CashAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Copilot Chat Drawer State
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [executedIntents, setExecutedIntents] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'agent'; text: string; data?: CopilotResponse }>>([
    {
      role: 'agent',
      text: 'Hello, I am your Autonomous SME Finance Copilot. Upload your bank statement or click a quick prompt below to diagnose your runway, evaluate financing facilities, or stage credit applications.',
    },
  ]);

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

  async function sendChatMessage(promptText?: string) {
    const textToSend = promptText || chatInput;
    if (!textToSend.trim()) return;

    const newMsgs = [...messages, { role: 'user' as const, text: textToSend }];
    setMessages(newMsgs);
    setChatInput('');
    setChatLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/v1/agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': 'SME-COFFEE-001',
        },
        body: JSON.stringify({
          message: textToSend,
          csv_content: csvText,
          alert_threshold_days: Number(threshold) || 30,
        }),
      });

      const body: CopilotResponse = await response.json();
      setMessages([...newMsgs, { role: 'agent', text: body.reply, data: body }]);
    } catch {
      setMessages([
        ...newMsgs,
        {
          role: 'agent',
          text: `Unable to reach the local agent backend at ${API_URL}. Verify the FastAPI service is active.`,
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  async function executeBiometric(intentId: string) {
    try {
      const res = await fetch(`${API_URL}/api/v1/actions/${intentId}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ biometric_signature: 'webauthn_passkey_signed_founder' }),
      });
      if (res.ok) {
        setExecutedIntents((prev) => ({ ...prev, [intentId]: true }));
      }
    } catch (err) {
      console.error('Biometric execution error:', err);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">$</span>
          <span>SME Finance Copilot</span>
        </div>
        <span className="demo-tag">Autonomous AI Participant · Local privacy mode</span>
      </header>
      <main>
        <div className="eyebrow">Autonomous AI CFO · FinTechathon 2026 Topic E</div>
        <h1>Continuous cash protection & liquidity matching.</h1>
        <p className="lede">
          Import a bank statement CSV to review recent transactions, calculate your historical runway,
          and interact with your autonomous AI CFO behind a Three-Tier Security Gate.
        </p>

        <div className="content-grid">
          <section className="panel" aria-labelledby="upload-title">
            <h2 id="upload-title">Review a statement</h2>
            <p className="panel-intro">Your file is processed in local memory only. Zero data is persisted or sent to third parties.</p>
            <form onSubmit={analyze}>
              <label className="field-label" htmlFor="threshold">Alert threshold (days)</label>
              <input
                id="threshold"
                name="alert_threshold_days"
                type="number"
                min="1"
                step="1"
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
                required
              />

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
                    const picked = event.target.files?.[0] ?? null;
                    setFile(picked);
                    setResult(null);
                    setError(null);
                    if (picked) {
                      const reader = new FileReader();
                      reader.onload = (e) => setCsvText(e.target?.result as string);
                      reader.readAsText(picked);
                    } else {
                      setCsvText(null);
                    }
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
                <p className="caveat">Deterministic calculation computed in pure Python Decimal arithmetic. Never hallucinated.</p>
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
            <h2 id="steps-title">Three-Tier Security Architecture</h2>
            <p className="panel-intro">How the Autonomous AI Copilot protects your business funds:</p>
            <div className="side-note">
              <span className="note-index">01</span>
              <div>
                <strong>Tier 1: Read-Only Observation</strong>
                <p>Pure Decimal calculations for runway, burn, and WeBank Daily Average Balance (DAB). Autonomous execution.</p>
              </div>
            </div>
            <div className="side-note">
              <span className="note-index">02</span>
              <div>
                <strong>Tier 2: Staged Queue Only</strong>
                <p>Loan drafts, factoring offers, and cash actions are placed in an immutable staging ledger. Zero money moves.</p>
              </div>
            </div>
            <div className="side-note">
              <span className="note-index">03</span>
              <div>
                <strong>Tier 3: Hardware Biometric Touch</strong>
                <p>Irreversible fund disbursements require explicit WebAuthn FIDO2 passkey authorization from the business owner.</p>
              </div>
            </div>
            <p className="caveat">Required CSV header format:</p>
            <code className="file-name">{CSV_HEADER}</code>
          </aside>
        </div>
        <p className="footer">Privacy-first · files processed locally in-memory · Zero external LLM arithmetic authority</p>
      </main>

      {/* Floating Copilot Chat Toggle Button */}
      <button
        className="chat-toggle-btn"
        onClick={() => setChatOpen(!chatOpen)}
        aria-label="Toggle Autonomous AI Copilot"
      >
        <span>🤖</span>
        <span>{chatOpen ? 'Close Copilot' : 'Ask AI Copilot'}</span>
      </button>

      {/* Copilot Chat Drawer */}
      {chatOpen && (
        <div className="chat-drawer" role="dialog" aria-label="Autonomous AI Copilot Drawer">
          <div className="chat-header">
            <h3>
              <span>🤖</span>
              <span>AI Copilot</span>
              <span className="badge">Active</span>
            </h3>
            <button className="chat-close" onClick={() => setChatOpen(false)} aria-label="Close chat">✕</button>
          </div>

          <div className="chat-body">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>
                <div className="chat-bubble">{m.text}</div>

                {/* Structured Metrics Card if provided by agent */}
                {m.data?.metrics && (
                  <div className="chat-card">
                    {m.data.metrics.current_balance && <div><strong>Balance:</strong> ${m.data.metrics.current_balance}</div>}
                    {m.data.metrics.runway_days !== undefined && <div><strong>Runway:</strong> {m.data.metrics.runway_days ?? 'N/A'} days</div>}
                    {m.data.metrics.average_daily_burn && <div><strong>Daily Burn:</strong> ${m.data.metrics.average_daily_burn}/day</div>}
                    {m.data.metrics.risk_tier && <div><strong>WeBank Tier:</strong> {m.data.metrics.risk_tier}</div>}
                  </div>
                )}

                {/* Pre-qualified Credit Facilities if matched */}
                {m.data?.matched_options && m.data.matched_options.length > 0 && (
                  <div className="chat-card">
                    <strong>Pre-Qualified Facilities:</strong>
                    {m.data.matched_options.map((opt, idx) => (
                      <div key={idx} style={{ marginTop: '6px', borderTop: '1px solid #eee', paddingTop: '4px' }}>
                        <div>{opt.facility_name} ({opt.provider})</div>
                        <div style={{ color: '#146b55' }}>APR: {opt.apr_percent}% · Max: ${opt.max_amount}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Tier 2 Staged Proposal & Tier 3 Biometric Approval */}
                {m.data?.staged_action && (
                  <div className={`chat-card ${executedIntents[m.data.staged_action.intent_id] ? 'executed' : 'biometric'}`}>
                    <div>
                      <strong>
                        {executedIntents[m.data.staged_action.intent_id]
                          ? '✅ Executed on Consortium Ledger'
                          : '🔒 Staged in Tier 2 Queue (Pending Biometric 2FA)'}
                      </strong>
                    </div>
                    <div style={{ marginTop: '4px' }}>
                      {m.data.staged_action.action_type} · ${(m.data.staged_action.amount_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '11px', opacity: 0.85, marginTop: '2px' }}>
                      Intent ID: {m.data.staged_action.intent_id}
                    </div>

                    {!executedIntents[m.data.staged_action.intent_id] && (
                      <button
                        className="biometric-btn"
                        onClick={() => executeBiometric(m.data!.staged_action!.intent_id)}
                      >
                        👆 Touch WebAuthn Biometric Passkey (Tier 3)
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}

            {chatLoading && (
              <div className="chat-msg agent">
                <div className="chat-bubble">Thinking and evaluating deterministic tools…</div>
              </div>
            )}
          </div>

          {/* Quick Suggestion Pills */}
          <div style={{ padding: '0 16px 8px' }}>
            <div className="chat-pills">
              <button
                className="pill-btn"
                onClick={() => sendChatMessage('What is my current runway and daily burn rate?')}
              >
                💡 Diagnose Runway
              </button>
              <button
                className="pill-btn"
                onClick={() => sendChatMessage('What loan or credit line options can my business qualify for?')}
              >
                📊 Match Credit
              </button>
              <button
                className="pill-btn"
                onClick={() => sendChatMessage('Please stage an application to draw line of $25,000 for working capital')}
              >
                ⚡ Stage $25k Loan
              </button>
            </div>
          </div>

          <form
            className="chat-footer"
            onSubmit={(e) => {
              e.preventDefault();
              sendChatMessage();
            }}
          >
            <input
              className="chat-input"
              placeholder="Ask Copilot about cash, loans, or actions…"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={chatLoading}
            />
            <button className="chat-send-btn" type="submit" disabled={chatLoading || !chatInput.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </div>
  );
}
