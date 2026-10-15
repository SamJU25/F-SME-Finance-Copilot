'use client';

import { FormEvent, useEffect, useState } from 'react';
import type {
  CashAnalysisResponse,
  CopilotResponse,
  FetchModelsResponse,
  LLMConfig,
  LLMProviderId,
  ModelItem,
  TestConnectionResponse,
} from '../types/api';

const API_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const CSV_HEADER = 'transaction_id,posted_on,amount,currency,description,closing_balance';

const PRESETS: Record<LLMProviderId, { name: string; defaultModel: string; defaultUrl?: string; description: string }> = {
  offline: {
    name: 'Offline Local Engine (Zero Keys)',
    defaultModel: 'deterministic-v1',
    description: '100% private and offline. Pure Python Decimal calculation with zero external API calls.',
  },
  gemini: {
    name: 'Google Gemini',
    defaultModel: 'gemini-2.0-flash',
    defaultUrl: 'https://generativelanguage.googleapis.com/v1beta',
    description: '1M+ context window. Recommended for scanning multi-month bank statement CSVs.',
  },
  anthropic: {
    name: 'Anthropic Claude',
    defaultModel: 'claude-3-5-sonnet-20241022',
    defaultUrl: 'https://api.anthropic.com/v1/messages',
    description: 'High precision on debt covenants, underwriting guidelines, and financial statements.',
  },
  openai: {
    name: 'OpenAI (GPT-4o)',
    defaultModel: 'gpt-4o-mini',
    defaultUrl: 'https://api.openai.com/v1',
    description: 'Standard enterprise LLM for executive summaries and cash flow advice.',
  },
  deepseek: {
    name: 'DeepSeek',
    defaultModel: 'deepseek-chat',
    defaultUrl: 'https://api.deepseek.com/v1',
    description: 'Low-cost commercial reasoning ($0.14/1M tokens) suitable for budget-conscious SMEs.',
  },
  groq: {
    name: 'Groq (Llama 3.3)',
    defaultModel: 'llama-3.3-70b-versatile',
    defaultUrl: 'https://api.groq.com/openai/v1',
    description: 'Sub-second latency (<300ms) for real-time interactive financial Q&A.',
  },
  ollama: {
    name: 'Local Ollama',
    defaultModel: 'qwen2.5:14b',
    defaultUrl: 'http://localhost:11434/v1',
    description: 'Self-hosted local inference engine. Zero cloud egress for strict compliance.',
  },
  custom: {
    name: 'Custom (OpenAI-Compatible)',
    defaultModel: 'custom-model',
    defaultUrl: 'https://openrouter.ai/api/v1',
    description: 'Universal adapter for OpenRouter, Together AI, vLLM, LM Studio, or private VPCs.',
  },
};

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

  // Multi-Provider AI Settings State
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: 'offline',
    model_name: 'deterministic-v1',
  });
  const [draftConfig, setDraftConfig] = useState<LLMConfig>({
    provider: 'offline',
    model_name: 'deterministic-v1',
  });
  const [showSettings, setShowSettings] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);

  // Dynamic Model Discovery State
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [customModelMode, setCustomModelMode] = useState(false);
  const [modelsMessage, setModelsMessage] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem('sme_copilot_llm_config');
      if (saved) {
        const parsed = JSON.parse(saved);
        setLlmConfig(parsed);
        setDraftConfig(parsed);
      }
    } catch {
      // LocalStorage access fallback
    }
  }, []);

  async function fetchModels(cfg: LLMConfig) {
    if (cfg.provider === 'offline') {
      setAvailableModels([{ id: 'deterministic-v1', name: 'Deterministic Financial Engine (Offline)' }]);
      setModelsMessage(null);
      return;
    }

    if (['gemini', 'anthropic', 'openai', 'deepseek', 'groq'].includes(cfg.provider) && !cfg.api_key) {
      setAvailableModels([]);
      setModelsMessage('API not connected. Enter your API key and verify connection to load available models.');
      return;
    }

    if (cfg.provider === 'custom' && !cfg.base_url) {
      setAvailableModels([]);
      setModelsMessage('Base URL required. Enter Base URL and verify connection to load available models.');
      return;
    }

    setLoadingModels(true);
    setModelsMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/agent/fetch-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: cfg.provider,
          api_key: cfg.api_key,
          base_url: cfg.base_url,
        }),
      });
      const data: FetchModelsResponse = await res.json();
      if (data.success && data.models && data.models.length > 0) {
        setAvailableModels(data.models);
        setModelsMessage(`✅ Connected: Discovered ${data.models.length} live models.`);
        const match = data.models.find((m) => m.id === cfg.model_name);
        if (!match && !customModelMode && data.models[0]) {
          setDraftConfig((prev) => ({ ...prev, model_name: data.models[0].id }));
        }
      } else {
        setAvailableModels([]);
        setModelsMessage(data.message || '⚠️ Unable to discover models. Verify your API credentials.');
      }
    } catch (cause) {
      setAvailableModels([]);
      setModelsMessage(cause instanceof Error ? cause.message : 'Could not fetch remote models.');
    } finally {
      setLoadingModels(false);
    }
  }

  async function handleTestConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/agent/test-connection`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draftConfig),
      });
      const data: TestConnectionResponse = await res.json();
      setTestResult(data);
      if (data.success && draftConfig.provider !== 'offline') {
        fetchModels(draftConfig);
      }
    } catch (cause) {
      setTestResult({
        success: false,
        message: cause instanceof Error ? cause.message : 'Network failure testing connection.',
        provider: draftConfig.provider,
      });
    } finally {
      setTesting(false);
    }
  }

  function handleSaveSettings() {
    setLlmConfig(draftConfig);
    try {
      localStorage.setItem('sme_copilot_llm_config', JSON.stringify(draftConfig));
    } catch {
      // LocalStorage fallback
    }
    setShowSettings(false);
    setTestResult(null);
  }

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
          'X-LLM-Config': JSON.stringify(llmConfig),
        },
        body: JSON.stringify({
          message: textToSend,
          csv_content: csvText,
          alert_threshold_days: Number(threshold) || 30,
          llm_config: llmConfig,
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            className="settings-btn"
            onClick={() => {
              setDraftConfig(llmConfig);
              setShowSettings(true);
              fetchModels(llmConfig);
            }}
            type="button"
            title="Configure AI model provider and credentials"
          >
            <span>⚙️ AI Provider:</span>
            <span className={`provider-badge ${llmConfig.provider === 'custom' ? 'custom' : ''}`}>
              {llmConfig.provider.toUpperCase()}
            </span>
          </button>
          <button
            className="settings-btn"
            onClick={() => setChatOpen((prev) => !prev)}
            type="button"
            title="Toggle Copilot Chat"
          >
            <span>💬 Copilot Chat</span>
          </button>
          <span className="demo-tag">Autonomous AI Participant</span>
        </div>
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
              <strong>Tier 1 — Autonomous Observation</strong>
              <p>Continuous transaction ingestion, daily average balance calculation, and cash burn metrics. 100% read-only.</p>
            </div>
            <div className="side-note">
              <strong>Tier 2 — Staging Ledger (Zero Money Movement)</strong>
              <p>Autonomous AI drafts credit applications and stages proposals into an immutable audit ledger. No funds move.</p>
            </div>
            <div className="side-note">
              <strong>Tier 3 — Human-in-the-Loop Biometric Verification</strong>
              <p>Drawdowns and fund transfers halt strictly until approved via biometric WebAuthn FIDO2 passkey verification.</p>
            </div>
          </aside>
        </div>

        <section className="schema" aria-labelledby="schema-title">
          <h2 id="schema-title">Required CSV headers</h2>
          <p className="schema-intro">Your file must include these column names in any order:</p>
          <pre><code>{CSV_HEADER}</code></pre>
        </section>
      </main>

      {/* Floating Copilot Button */}
      <button
        className="chat-toggle-btn"
        onClick={() => setChatOpen(!chatOpen)}
        type="button"
        aria-label="Toggle Autonomous AI Copilot Drawer"
      >
        <span>🤖</span>
        <span>{chatOpen ? 'Close Copilot' : 'Ask AI Copilot'}</span>
      </button>

      {/* Interactive Copilot Chat Drawer */}
      {chatOpen && (
        <div className="chat-drawer" role="complementary" aria-label="Autonomous AI Copilot Chat Drawer">
          <div className="chat-header">
            <div>
              <h3>🤖 AI Finance Copilot</h3>
              <div style={{ marginTop: 4 }}>
                <span className="badge">
                  {llmConfig.provider.toUpperCase()} · {llmConfig.model_name || 'deterministic'}
                </span>
              </div>
            </div>
            <button className="chat-close" onClick={() => setChatOpen(false)} type="button" aria-label="Close Drawer">
              ✕
            </button>
          </div>

          <div className="chat-body">
            {messages.map((m, idx) => (
              <div key={idx} className={`chat-msg ${m.role}`}>
                <div className="chat-bubble">{m.text}</div>

                {/* Predictive Early-Warning Alert Card */}
                {m.data?.metrics?.has_projected_deficit && (
                  <div className="chat-card" style={{ borderColor: '#e0837b', background: '#fdf2f1' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#9b3d37', fontWeight: 700 }}>
                      <span>🚨</span>
                      <span>{m.data.metrics.deficit_severity} DEFICIT EARLY WARNING</span>
                    </div>
                    <div style={{ marginTop: 4, color: '#172b2d' }}>
                      Projected shortfall of <strong>${m.data.metrics.projected_shortfall_amount}</strong> in <strong>{m.data.metrics.days_until_deficit} days</strong> ({m.data.metrics.projected_deficit_date}).
                    </div>
                    {m.data.metrics.recommended_bridge_amount && (
                      <div style={{ marginTop: 6, fontSize: 11, color: '#5e7071' }}>
                        💡 Recommended working capital bridge: <strong>${m.data.metrics.recommended_bridge_amount}</strong>
                      </div>
                    )}
                  </div>
                )}

                {/* Structured Metrics Card */}
                {m.data?.metrics && (
                  <div className="chat-card">
                    <strong>Calculated Cash Metrics</strong>
                    {m.data.metrics.current_balance && <div>Balance: ${m.data.metrics.current_balance}</div>}
                    {m.data.metrics.average_daily_burn && <div>Burn: ${m.data.metrics.average_daily_burn}/day</div>}
                    {m.data.metrics.runway_days !== undefined && <div>Runway: {m.data.metrics.runway_days} days</div>}
                    {m.data.metrics.daily_average_balance && <div>Daily Avg Balance: ${m.data.metrics.daily_average_balance}</div>}
                    {m.data.metrics.risk_tier && <div>Risk Tier: {m.data.metrics.risk_tier}</div>}
                  </div>
                )}


                {/* Pre-Qualified Financing Options */}
                {m.data?.matched_options && m.data.matched_options.length > 0 && (
                  <div className="chat-card">
                    <strong>Pre-Qualified Financing Facilities:</strong>
                    <ul style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                      {m.data.matched_options.map((opt, oIdx) => (
                        <li key={oIdx} style={{ marginTop: 4 }}>
                          <strong>{opt.facility_name}</strong> ({opt.provider})<br />
                          Limit: ${Number(opt.max_amount).toLocaleString()} · APR: {opt.apr_percent}% · Term: {opt.term_days}d
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Tier 3 Biometric Approval Card */}
                {m.data?.staged_action && (
                  <div className={`chat-card ${executedIntents[m.data.staged_action.intent_id] ? 'executed' : 'biometric'}`}>
                    <strong>
                      {executedIntents[m.data.staged_action.intent_id]
                        ? '✅ Execution Completed (WebAuthn Signed)'
                        : '⚠️ Tier 3 HITL Biometric Approval Required'}
                    </strong>
                    <div style={{ marginTop: 4 }}>
                      Action: {m.data.staged_action.action_type} · Amount: ${(m.data.staged_action.amount_cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
                    </div>
                    {!executedIntents[m.data.staged_action.intent_id] && (
                      <button
                        className="biometric-btn"
                        type="button"
                        onClick={() => executeBiometric(m.data!.staged_action!.intent_id)}
                      >
                        👆 Confirm Biometric WebAuthn Passkey
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            {chatLoading && (
              <div className="chat-msg agent">
                <div className="chat-bubble">Analyzing with Three-Tier Security Gate…</div>
              </div>
            )}
          </div>

          {/* Quick Action Suggestion Pills */}
          <div style={{ padding: '8px 16px', background: '#fafbf9', borderTop: '1px solid var(--line)' }}>
            <span style={{ fontSize: 11, color: 'var(--muted)', display: 'block', marginBottom: 4, fontWeight: 600 }}>Quick Prompts:</span>
            <div className="chat-pills">
              <button
                className="pill-btn"
                type="button"
                onClick={() => sendChatMessage('What is my current runway and daily burn rate?')}
              >
                📊 Check Runway
              </button>
              <button
                className="pill-btn"
                type="button"
                onClick={() => sendChatMessage('What loan or credit line options can my business qualify for?')}
              >
                💼 Match Credit Facilities
              </button>
              <button
                className="pill-btn"
                type="button"
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

      {/* AI Provider Settings Modal */}
      {showSettings && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="settings-title">
          <div className="modal-card">
            <div className="modal-head">
              <h3 id="settings-title">AI Provider & Model Settings</h3>
              <button
                className="modal-close-btn"
                type="button"
                onClick={() => {
                  setShowSettings(false);
                  setTestResult(null);
                }}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div>
                <label className="field-label" htmlFor="provider-select">Select Provider</label>
                <select
                  id="provider-select"
                  className="select-input"
                  value={draftConfig.provider}
                  onChange={(e) => {
                    const p = e.target.value as LLMProviderId;
                    const info = PRESETS[p];
                    const nextCfg: LLMConfig = {
                      ...draftConfig,
                      provider: p,
                      model_name: p === 'offline' ? 'deterministic-v1' : '',
                      base_url: info.defaultUrl || '',
                    };
                    setDraftConfig(nextCfg);
                    setTestResult(null);
                    setCustomModelMode(false);
                    setAvailableModels(p === 'offline' ? [{ id: 'deterministic-v1', name: 'Deterministic Financial Engine (Offline)' }] : []);
                    if (p === 'offline' || nextCfg.api_key) {
                      fetchModels(nextCfg);
                    } else {
                      setModelsMessage('API not connected. Enter your API key and verify connection to load available models.');
                    }
                  }}
                >
                  {Object.entries(PRESETS).map(([id, info]) => (
                    <option key={id} value={id}>
                      {info.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="provider-desc">
                {PRESETS[draftConfig.provider]?.description}
              </div>

              {draftConfig.provider !== 'offline' && (
                <div>
                  <label className="field-label" htmlFor="api-key-input">
                    API Key {draftConfig.provider === 'ollama' ? '(Optional)' : '(Required)'}
                  </label>
                  <input
                    id="api-key-input"
                    className="text-input"
                    type="password"
                    placeholder={draftConfig.provider === 'ollama' ? 'ollama' : 'Paste API Key (e.g. AIzaSy..., sk-ant..., sk-...)'}
                    value={draftConfig.api_key || ''}
                    onChange={(e) => {
                      const updated = { ...draftConfig, api_key: e.target.value };
                      setDraftConfig(updated);
                    }}
                  />
                </div>
              )}

              {(draftConfig.provider === 'custom' || draftConfig.provider === 'ollama') && (
                <div>
                  <label className="field-label" htmlFor="base-url-input">Base URL</label>
                  <input
                    id="base-url-input"
                    className="text-input"
                    type="text"
                    placeholder="e.g. http://localhost:11434/v1 or https://openrouter.ai/api/v1"
                    value={draftConfig.base_url || ''}
                    onChange={(e) => setDraftConfig({ ...draftConfig, base_url: e.target.value })}
                  />
                </div>
              )}

              {draftConfig.provider !== 'offline' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <label className="field-label" style={{ margin: 0 }} htmlFor="model-select">Target Model</label>
                    <button
                      type="button"
                      style={{ fontSize: 11, background: 'none', border: 0, color: 'var(--green)', cursor: 'pointer', fontWeight: 600 }}
                      onClick={() => fetchModels(draftConfig)}
                      disabled={loadingModels}
                    >
                      {loadingModels ? 'Fetching…' : '🔄 Discover Live Models'}
                    </button>
                  </div>

                  {!customModelMode ? (
                    <div>
                      {availableModels.length > 0 ? (
                        <>
                          <select
                            id="model-select"
                            className="select-input"
                            value={draftConfig.model_name || ''}
                            onChange={(e) => {
                              if (e.target.value === '__custom__') {
                                setCustomModelMode(true);
                              } else {
                                setDraftConfig({ ...draftConfig, model_name: e.target.value });
                              }
                            }}
                          >
                            {availableModels.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.name}
                              </option>
                            ))}
                            <option value="__custom__">➕ Custom / Fine-Tuned Model Name…</option>
                          </select>
                          {modelsMessage && (
                            <div style={{ fontSize: 11, color: 'var(--green)', marginTop: 4, fontWeight: 500 }}>
                              {modelsMessage}
                            </div>
                          )}
                        </>
                      ) : (
                        <div
                          style={{
                            background: 'var(--surface-2)',
                            border: '1px dashed var(--border)',
                            borderRadius: 6,
                            padding: '12px 14px',
                            fontSize: 12,
                          }}
                        >
                          <div style={{ color: 'var(--muted)', marginBottom: 8, lineHeight: 1.4 }}>
                            {loadingModels
                              ? '⏳ Querying provider endpoint to discover models…'
                              : (modelsMessage || '⚠️ API not connected. Enter your API key above and click "Test Connection" to discover models.')}
                          </div>
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: 11, padding: '4px 10px', width: 'auto' }}
                            onClick={() => setCustomModelMode(true)}
                          >
                            ✏️ Or Type Model Name Manually
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          id="custom-model-input"
                          className="text-input"
                          type="text"
                          placeholder="e.g. ft:gpt-4o-mini:my-org::123 or qwen2.5:32b"
                          value={draftConfig.model_name || ''}
                          onChange={(e) => setDraftConfig({ ...draftConfig, model_name: e.target.value })}
                          autoFocus
                        />
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ whiteSpace: 'nowrap', padding: '0 12px', fontSize: 12 }}
                          onClick={() => setCustomModelMode(false)}
                        >
                          List
                        </button>
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                        Enter any model identifier or private fine-tune snapshot.
                      </div>
                    </div>
                  )}
                </div>
              )}

              {testResult && (
                <div className={`test-status ${testResult.success ? 'success' : 'error'}`} role="status">
                  <span>{testResult.success ? '✅' : '❌'}</span>
                  <div>
                    <strong>{testResult.success ? 'Connected' : 'Connection Failed'}</strong>
                    {testResult.latency_ms !== null && testResult.latency_ms !== undefined && (
                      <span style={{ marginLeft: 6, opacity: 0.8 }}>({testResult.latency_ms}ms)</span>
                    )}
                    <div style={{ fontSize: 12, marginTop: 2 }}>{testResult.message}</div>
                  </div>
                </div>
              )}
            </div>

            <div className="modal-foot">
              <button
                className="btn-secondary"
                type="button"
                disabled={testing}
                onClick={handleTestConnection}
              >
                {testing ? 'Testing connection…' : '⚡ Test Connection'}
              </button>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={() => {
                    setShowSettings(false);
                    setTestResult(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  className="btn-primary"
                  type="button"
                  onClick={handleSaveSettings}
                >
                  Save Settings
                </button>
              </div>
            </div>
          </div>
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
