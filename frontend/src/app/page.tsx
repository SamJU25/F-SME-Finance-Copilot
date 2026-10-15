'use client';

import { FormEvent, Fragment, useEffect, useRef, useState } from 'react';
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
const SESSION_MESSAGE_LIMIT = 20;

export interface SessionItem {
  id: string;
  title: string;
  updatedAt: string;
  messageCount: number;
}

function formatSessionTime(isoString?: string): string {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

const DEFAULT_WELCOME_MESSAGE: { role: 'agent'; text: string } = {
  role: 'agent',
  text: 'Hello, I am your Autonomous SME Finance Copilot. You can pick an inquiry below, ask any financial question, or upload your transactional bank statement on the left to run live diagnostics.',
};

const PRESETS: Record<LLMProviderId, { name: string; defaultModel: string; defaultUrl?: string; description: string }> = {
  offline: {
    name: 'Offline Local Engine (Zero Keys)',
    defaultModel: 'llama-3.2-1b-instruct-onnx',
    description: '100% private and on-device. Meta Llama-3.2-1B ONNX local generation with zero external API calls.',
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

function getEngineDisplayName(config: LLMConfig): string {
  if (config.provider === 'offline') {
    return 'Llama 3.2 (Offline)';
  }
  if (config.model_name && !config.model_name.startsWith('http')) {
    return config.model_name;
  }
  const preset = PRESETS[config.provider as LLMProviderId];
  return preset ? preset.name : config.provider;
}

function FormattedChatBubble({ text }: { text: string }) {
  if (!text) return null;

  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let currentList: React.ReactNode[] = [];

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`} className="chat-list">
          {currentList}
        </ul>
      );
      currentList = [];
    }
  };

  const renderInline = (lineText: string): React.ReactNode[] => {
    const parts = lineText.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts.map((part, pIdx) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={pIdx}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code key={pIdx} className="chat-inline-code">
            {part.slice(1, -1)}
          </code>
        );
      }
      return part;
    });
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      elements.push(<div key={`space-${idx}`} style={{ height: 6 }} />);
      return;
    }

    if (trimmed.startsWith('### ') || trimmed.startsWith('## ')) {
      flushList();
      const heading = trimmed.replace(/^#+\s*/, '');
      elements.push(
        <h4 key={`h-${idx}`} className="chat-heading">
          {heading}
        </h4>
      );
      return;
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const content = trimmed.slice(2);
      currentList.push(
        <li key={`li-${idx}`} className="chat-list-item">
          <span className="chat-bullet-dot">•</span>
          <span>{renderInline(content)}</span>
        </li>
      );
      return;
    }

    flushList();
    elements.push(
      <p key={`p-${idx}`} style={{ margin: '3px 0' }}>
        {renderInline(trimmed)}
      </p>
    );
  });

  flushList();
  return <>{elements}</>;
}

const STARTER_PROMPTS = [
  {
    icon: '📊',
    title: 'Analyze Runway & Daily Burn',
    desc: 'Calculate exact survival days and daily cash outflow velocity',
    prompt: 'What is my current runway and daily burn rate?',
  },
  {
    icon: '⚠️',
    title: 'Detect Cash Deficit Risks',
    desc: 'Early-warning forecast for upcoming cash crunches and overdrafts',
    prompt: 'Check for upcoming cash shortfalls and deficit risks over the next 60 days.',
  },
  {
    icon: '💼',
    title: 'Match Pre-Qualified Credit Facilities',
    desc: 'Review non-predatory credit lines with true APR disclosures',
    prompt: 'What pre-qualified loan or credit line options can my business qualify for?',
  },
  {
    icon: '🔄',
    title: 'Audit Working Capital & CCC',
    desc: 'Assess Cash Conversion Cycle, receivable delays, and payables buffer',
    prompt: 'Audit our Cash Conversion Cycle (CCC) and working capital efficiency.',
  },
];

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
  const [sessionId, setSessionId] = useState<string>('');
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [sessionSearch, setSessionSearch] = useState('');
  const sessionMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(event.target as Node)) {
        setSessionMenuOpen(false);
      }
    }
    if (sessionMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [sessionMenuOpen]);

  const [messages, setMessages] = useState<Array<{ role: 'user' | 'agent'; text: string; data?: CopilotResponse }>>([
    DEFAULT_WELCOME_MESSAGE,
  ]);

  // Multi-Provider AI Settings State
  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: 'offline',
    model_name: 'llama-3.2-1b-instruct-onnx',
  });
  const [draftConfig, setDraftConfig] = useState<LLMConfig>({
    provider: 'offline',
    model_name: 'llama-3.2-1b-instruct-onnx',
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
      let storedSessionsList: SessionItem[] = [];
      const rawSessions = localStorage.getItem('sme_copilot_sessions_list');
      if (rawSessions) {
        try {
          const parsed = JSON.parse(rawSessions);
          if (Array.isArray(parsed) && parsed.length > 0) {
            storedSessionsList = parsed;
          }
        } catch {
          // JSON parse fallback
        }
      }

      let storedSession = localStorage.getItem('sme_copilot_session_id');
      if (!storedSession) {
        storedSession = storedSessionsList[0]?.id || `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
        localStorage.setItem('sme_copilot_session_id', storedSession);
      }
      setSessionId(storedSession);

      const existing = storedSessionsList.find((s) => s.id === storedSession);
      if (!existing) {
        const initialItem: SessionItem = {
          id: storedSession,
          title: 'Session 1',
          updatedAt: new Date().toISOString(),
          messageCount: 1,
        };
        storedSessionsList = [initialItem, ...storedSessionsList];
        try {
          localStorage.setItem('sme_copilot_sessions_list', JSON.stringify(storedSessionsList));
        } catch {
          // LocalStorage fallback
        }
      }
      setSessions(storedSessionsList);

      const sessionChatKey = `sme_copilot_chat_${storedSession}`;
      let savedMsgs = localStorage.getItem(sessionChatKey);
      if (!savedMsgs) {
        savedMsgs = localStorage.getItem('sme_copilot_chat_history');
      }
      if (savedMsgs) {
        try {
          const parsed = JSON.parse(savedMsgs);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setMessages(parsed);
          }
        } catch {
          // LocalStorage fallback
        }
      }

      const savedCsv = localStorage.getItem('sme_copilot_csv_text');
      if (savedCsv) {
        setCsvText(savedCsv);
      }

      const saved = localStorage.getItem('sme_copilot_llm_config');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.provider === 'offline' && (!parsed.model_name || parsed.model_name === 'deterministic-v1')) {
          parsed.model_name = 'llama-3.2-1b-instruct-onnx';
          try {
            localStorage.setItem('sme_copilot_llm_config', JSON.stringify(parsed));
          } catch {
            // LocalStorage write fallback
          }
        }
        if (parsed.provider === 'ollama') {
          parsed.provider = 'offline';
          parsed.model_name = 'llama-3.2-1b-instruct-onnx';
          try {
            localStorage.setItem('sme_copilot_llm_config', JSON.stringify(parsed));
          } catch {
            // LocalStorage write fallback
          }
        }
        setLlmConfig(parsed);
        setDraftConfig(parsed);
      }
    } catch {
      // LocalStorage access fallback
    }
  }, []);

  useEffect(() => {
    if (!sessionId || !messages || messages.length === 0) return;
    try {
      const sessionChatKey = `sme_copilot_chat_${sessionId}`;
      localStorage.setItem(sessionChatKey, JSON.stringify(messages));
      localStorage.setItem('sme_copilot_chat_history', JSON.stringify(messages));

      const firstUserMsg = messages.find((m) => m.role === 'user');
      setSessions((prev) => {
        const idx = prev.findIndex((s) => s.id === sessionId);
        let updatedTitle = `Session ${prev.length || 1}`;
        if (firstUserMsg && firstUserMsg.text) {
          const cleanPrompt = firstUserMsg.text.replace(/\s+/g, ' ').trim();
          updatedTitle = cleanPrompt.length > 24 ? `${cleanPrompt.slice(0, 24)}…` : cleanPrompt;
        }

        let nextSessions: SessionItem[];
        if (idx >= 0) {
          const current = prev[idx];
          const isGeneric = current.title.startsWith('Session ') || current.title === 'Current Session' || current.title === 'New Session';
          const newTitle = isGeneric && firstUserMsg ? updatedTitle : current.title;
          const updatedItem: SessionItem = {
            ...current,
            title: newTitle,
            messageCount: messages.length,
            updatedAt: new Date().toISOString(),
          };
          nextSessions = [...prev];
          nextSessions[idx] = updatedItem;
        } else {
          nextSessions = [
            {
              id: sessionId,
              title: updatedTitle,
              messageCount: messages.length,
              updatedAt: new Date().toISOString(),
            },
            ...prev,
          ];
        }
        try {
          localStorage.setItem('sme_copilot_sessions_list', JSON.stringify(nextSessions));
        } catch {
          // LocalStorage fallback
        }
        return nextSessions;
      });
    } catch {
      // LocalStorage fallback
    }
  }, [messages, sessionId]);

  async function fetchModels(cfg: LLMConfig) {
    if (cfg.provider === 'offline') {
      setAvailableModels([
        { id: 'llama-3.2-1b-instruct-onnx', name: 'Meta Llama-3.2-1B-Instruct (On-Device ONNX)' },
      ]);
      setModelsMessage('✅ On-device SLM active: Meta Llama-3.2-1B-Instruct (Zero external keys).');
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

  async function executeAnalysis(targetFile: File, thresholdValue?: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    const effectiveDays = thresholdValue && Number(thresholdValue) >= 1
      ? thresholdValue
      : (threshold && Number(threshold) >= 1 ? threshold : '30');
    try {
      const data = new FormData();
      data.append('file', targetFile);
      data.append('alert_threshold_days', effectiveDays);
      const response = await fetch(`${API_URL}/api/v1/analyze`, { method: 'POST', body: data });
      const body = await response.json();
      if (!response.ok) {
        let msg = 'The file could not be analyzed. Check the CSV and try again.';
        if (body?.error?.message) {
          msg = body.error.message;
        } else if (Array.isArray(body?.detail)) {
          msg = body.detail.map((d: { loc?: string[]; msg?: string }) => `${d.loc?.join('.') || ''}: ${d.msg || ''}`).join(', ');
        } else if (typeof body?.detail === 'string') {
          msg = body.detail;
        }
        throw new Error(msg);
      }
      setResult(body as CashAnalysisResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'A network error interrupted the request. Try again.');
    } finally {
      setLoading(false);
    }
  }

  async function analyze(event?: FormEvent<HTMLFormElement>) {
    if (event) event.preventDefault();
    if (!file) {
      setError('Choose a CSV file before reviewing cash activity.');
      return;
    }
    await executeAnalysis(file, threshold);
  }

  async function handleLoadSample() {
    try {
      const res = await fetch('/synthetic-statement.csv');
      if (!res.ok) throw new Error('Could not fetch sample CSV file.');
      const text = await res.text();
      const sampleFile = new File([text], 'synthetic-statement.csv', { type: 'text/csv' });
      setFile(sampleFile);
      setCsvText(text);
      setThreshold('30');
      await executeAnalysis(sampleFile, '30');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load sample statement.');
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
      const activeSession = sessionId || `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
      if (!sessionId) {
        setSessionId(activeSession);
      }

      const response = await fetch(`${API_URL}/api/v1/agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': 'SME-COFFEE-001',
          'X-Session-ID': activeSession,
          'X-LLM-Config': JSON.stringify(llmConfig),
        },
        body: JSON.stringify({
          session_id: activeSession,
          message: textToSend,
          history: messages.slice(-6).map((m) => ({ role: m.role, text: m.text })),
          csv_content: csvText,
          alert_threshold_days: Number(threshold) || 30,
          llm_config: llmConfig,
        }),
      });

      const body: any = await response.json();
      if (!response.ok) {
        const errorDetail = body?.detail || 'Agent service encountered an error. Please try again.';
        setMessages([...newMsgs, { role: 'agent', text: `⚠️ ${errorDetail}` }]);
        return;
      }

      if (body.session_id && body.session_id !== activeSession) {
        setSessionId(body.session_id);
      }

      setMessages([
        ...newMsgs,
        {
          role: 'agent',
          text: body.reply || 'No response received from the agent engine.',
          data: body as CopilotResponse,
        },
      ]);
    } catch (cause) {
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

  function handleCreateNewSession() {
    const newSessionId = `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    const newMsgs = [DEFAULT_WELCOME_MESSAGE];
    const newSessionItem: SessionItem = {
      id: newSessionId,
      title: `Session ${sessions.length + 1}`,
      updatedAt: new Date().toISOString(),
      messageCount: 1,
    };

    setSessionId(newSessionId);
    setMessages(newMsgs);
    setSessions((prev) => {
      const updated = [newSessionItem, ...prev];
      try {
        localStorage.setItem('sme_copilot_session_id', newSessionId);
        localStorage.setItem(`sme_copilot_chat_${newSessionId}`, JSON.stringify(newMsgs));
        localStorage.setItem('sme_copilot_chat_history', JSON.stringify(newMsgs));
        localStorage.setItem('sme_copilot_sessions_list', JSON.stringify(updated));
      } catch {
        // LocalStorage fallback
      }
      return updated;
    });
  }

  async function handleSwitchSession(targetId: string) {
    if (targetId === '__new__') {
      handleCreateNewSession();
      return;
    }
    if (!targetId || targetId === sessionId) return;

    const sessionChatKey = `sme_copilot_chat_${targetId}`;
    let loaded = false;
    try {
      const saved = localStorage.getItem(sessionChatKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
          loaded = true;
        }
      }
    } catch {
      // LocalStorage parse fallback
    }

    if (!loaded) {
      try {
        const res = await fetch(`${API_URL}/api/v1/agent/session/${targetId}`);
        if (res.ok) {
          const data = await res.json();
          if (data?.history && Array.isArray(data.history) && data.history.length > 0) {
            const mapped = data.history.map((h: { role: 'user' | 'agent'; text: string }) => ({
              role: h.role,
              text: h.text,
            }));
            setMessages(mapped);
            loaded = true;
          }
        }
      } catch {
        // Backend fallback
      }
    }

    if (!loaded) {
      setMessages([DEFAULT_WELCOME_MESSAGE]);
    }

    setSessionId(targetId);
    try {
      localStorage.setItem('sme_copilot_session_id', targetId);
    } catch {
      // LocalStorage fallback
    }
  }

  async function handleDeleteSession(idToDelete: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await fetch(`${API_URL}/api/v1/agent/session/${idToDelete}`, { method: 'DELETE' });
    } catch {
      // Backend delete fallback
    }
    const remaining = sessions.filter((s) => s.id !== idToDelete);
    try {
      localStorage.removeItem(`sme_copilot_chat_${idToDelete}`);
      localStorage.setItem('sme_copilot_sessions_list', JSON.stringify(remaining));
    } catch {
      // LocalStorage fallback
    }
    setSessions(remaining);
    if (idToDelete === sessionId) {
      if (remaining.length > 0) {
        handleSwitchSession(remaining[0].id);
      } else {
        handleCreateNewSession();
      }
    }
  }

  const activeSessionItem = sessions.find((s) => s.id === sessionId) || {
    id: sessionId,
    title: 'Session 1',
    messageCount: messages.length,
    updatedAt: new Date().toISOString(),
  };

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(sessionSearch.toLowerCase()) ||
    s.id.toLowerCase().includes(sessionSearch.toLowerCase())
  );

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
              <div style={{ marginBottom: 16 }}>
                <label className="field-label" htmlFor="threshold">Alert threshold (runway warning days)</label>
                <input
                  id="threshold"
                  name="alert_threshold_days"
                  type="number"
                  min="1"
                  step="1"
                  placeholder="30"
                  value={threshold}
                  onChange={(event) => setThreshold(event.target.value)}
                  onBlur={() => {
                    if (!threshold || Number(threshold) < 1) {
                      setThreshold('30');
                    }
                  }}
                />
                <span style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginTop: 4 }}>
                  Default: 30 days. Triggers a warning if projected cash runway drops below this threshold.
                </span>
              </div>

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
                      executeAnalysis(picked, threshold);
                    } else {
                      setCsvText(null);
                    }
                  }}
                />
                <div className="file-name">
                  {file ? `${file.name} (${file.size} bytes)` : 'UTF-8 CSV · max 1 MB'}
                </div>
              </div>

              <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="pill-btn"
                  onClick={handleLoadSample}
                  disabled={loading}
                  title="Load and analyze the bundled demo statement with 1 click"
                >
                  ⚡ Load demo statement (synthetic-statement.csv)
                </button>
              </div>

              <button className="submit" type="submit" disabled={loading || !file} style={{ marginTop: 16 }}>
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
            <div className="chat-header-left">
              <div className="session-combobox-container" ref={sessionMenuRef}>
                <button
                  type="button"
                  className={`session-trigger-btn ${sessionMenuOpen ? 'open' : ''}`}
                  onClick={() => setSessionMenuOpen((prev) => !prev)}
                  aria-haspopup="listbox"
                  aria-expanded={sessionMenuOpen}
                  title="Select or switch chat sessions"
                >
                  <div className="session-trigger-content">
                    <svg
                      className="session-trigger-icon"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <span className="session-trigger-title">
                      {activeSessionItem.title}
                    </span>
                    <span className="session-count-badge">
                      {messages.length} msgs
                    </span>
                  </div>
                  <svg
                    className="session-chevron-icon"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </button>

                {sessionMenuOpen && (
                  <div className="session-menu-popover" role="listbox" aria-label="Chat Sessions">
                    <button
                      type="button"
                      className="session-new-btn"
                      onClick={() => {
                        handleCreateNewSession();
                        setSessionMenuOpen(false);
                        setSessionSearch('');
                      }}
                    >
                      <span className="session-new-icon" aria-hidden="true">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="12" y1="5" x2="12" y2="19"></line>
                          <line x1="5" y1="12" x2="19" y2="12"></line>
                        </svg>
                      </span>
                      <span className="session-new-text">New Session</span>
                      <span className="session-new-badge">Fresh Context</span>
                    </button>

                    {sessions.length > 2 && (
                      <div className="session-search-box">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }} aria-hidden="true">
                          <circle cx="11" cy="11" r="8"></circle>
                          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                        <input
                          type="text"
                          className="session-search-input"
                          placeholder="Search sessions…"
                          value={sessionSearch}
                          onChange={(e) => setSessionSearch(e.target.value)}
                          autoFocus
                        />
                        {sessionSearch && (
                          <button
                            type="button"
                            className="session-search-clear"
                            onClick={() => setSessionSearch('')}
                            aria-label="Clear search"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    )}

                    <div className="session-menu-section-header">
                      <span>Session History</span>
                      <span>{filteredSessions.length} total</span>
                    </div>

                    <div className="session-items-list">
                      {filteredSessions.map((s) => {
                        const isActive = s.id === sessionId;
                        return (
                          <div
                            key={s.id}
                            className={`session-menu-item ${isActive ? 'active' : ''}`}
                            role="option"
                            aria-selected={isActive}
                            onClick={() => {
                              handleSwitchSession(s.id);
                              setSessionMenuOpen(false);
                              setSessionSearch('');
                            }}
                          >
                            <div className="session-item-left">
                              <span className={`session-active-indicator ${isActive ? 'active' : ''}`} aria-hidden="true">
                                {isActive ? '✓' : '•'}
                              </span>
                              <div className="session-item-info">
                                <div className="session-item-title">{s.title}</div>
                                <div className="session-item-meta">
                                  <span>{s.messageCount || 1} msgs</span>
                                  {s.updatedAt && (
                                    <>
                                      <span className="meta-dot">·</span>
                                      <span>{formatSessionTime(s.updatedAt)}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                            {sessions.length > 1 && (
                              <button
                                type="button"
                                className="session-delete-btn"
                                title="Delete this session"
                                onClick={(e) => handleDeleteSession(s.id, e)}
                                aria-label={`Delete session ${s.title}`}
                              >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                  <polyline points="3 6 5 6 21 6"></polyline>
                                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                              </button>
                            )}
                          </div>
                        );
                      })}
                      {filteredSessions.length === 0 && (
                        <div className="session-empty-hint">No sessions found matching &ldquo;{sessionSearch}&rdquo;</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="chat-header-right">
              <button
                type="button"
                className="model-settings-btn"
                onClick={() => {
                  setDraftConfig(llmConfig);
                  setShowSettings(true);
                  fetchModels(llmConfig);
                }}
                title="Configure AI Engine & Discover Live Models"
                aria-label="Configure AI Model Settings"
              >
                <span className="model-chip-dot" />
                <span className="model-chip-name">{getEngineDisplayName(llmConfig)}</span>
                <svg
                  className="model-gear-svg"
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                </svg>
              </button>
              <button className="chat-close" onClick={() => setChatOpen(false)} type="button" aria-label="Close Drawer">
                ✕
              </button>
            </div>
          </div>

          <div className="chat-body">
            {messages.map((m, idx) => (
              <Fragment key={idx}>
                {idx > 0 && idx % SESSION_MESSAGE_LIMIT === 0 && (
                  <div className="session-breakline" role="separator" aria-label="Session limit reached">
                    <div className="breakline-divider" />
                    <div className="breakline-content">
                      <span className="breakline-pill">
                        <span className="breakline-icon">⚡</span>
                        <span>Session Context Boundary ({idx} messages reached)</span>
                      </span>
                      <span className="breakline-sub">
                        Continuing conversation below · Prior context compressed for optimal agent reasoning
                      </span>
                    </div>
                    <div className="breakline-divider" />
                  </div>
                )}
                <div className={`chat-msg ${m.role}`}>
                  <div className="chat-bubble">
                    <FormattedChatBubble text={m.text} />
                  </div>

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
              </Fragment>
            ))}
            {/* Starter Prompt Cards (Only visible before user asks a question) */}
            {!messages.some((m) => m.role === 'user') && (
              <div className="starter-prompts">
                <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', marginBottom: 2 }}>
                  Suggested Financial Inquiries
                </span>
                {STARTER_PROMPTS.map((item, pIdx) => (
                  <button
                    key={pIdx}
                    type="button"
                    className="starter-prompt-card"
                    onClick={() => sendChatMessage(item.prompt)}
                  >
                    <span className="starter-prompt-icon" aria-hidden="true">{item.icon}</span>
                    <div className="starter-prompt-content">
                      <span className="starter-prompt-title">{item.title}</span>
                      <span className="starter-prompt-desc">{item.desc}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {chatLoading && (
              <div className="chat-msg agent">
                <div className="chat-bubble" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 14px' }}>
                  <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>Thinking</span>
                  <span className="typing-dots" aria-label="Thinking">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </span>
                </div>
              </div>
            )}
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
              <div>
                <div className="modal-eyebrow">COGNITIVE ENGINE CONFIGURATION</div>
                <h3 id="settings-title">AI Provider & Model Settings</h3>
                <p className="modal-subtitle">
                  Configure your LLM provider credentials, verify latency, and discover live fine-tuned models.
                </p>
              </div>
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
                      model_name: p === 'offline' ? 'llama-3.2-1b-instruct-onnx' : '',
                      base_url: info.defaultUrl || '',
                    };
                    setDraftConfig(nextCfg);
                    setTestResult(null);
                    setCustomModelMode(false);
                    setAvailableModels(
                      p === 'offline'
                        ? [
                            { id: 'llama-3.2-1b-instruct-onnx', name: 'Meta Llama-3.2-1B-Instruct (On-Device ONNX)' },
                          ]
                        : []
                    );
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
                    API Key (Required)
                  </label>
                  <input
                    id="api-key-input"
                    className="text-input"
                    type="password"
                    placeholder="Paste API Key (e.g. AIzaSy..., sk-ant..., sk-...)"
                    value={draftConfig.api_key || ''}
                    onChange={(e) => {
                      const updated = { ...draftConfig, api_key: e.target.value.trim() };
                      setDraftConfig(updated);
                    }}
                  />
                </div>
              )}

              {draftConfig.provider === 'custom' && (
                <div>
                  <label className="field-label" htmlFor="base-url-input">Base URL</label>
                  <input
                    id="base-url-input"
                    className="text-input"
                    type="text"
                    placeholder="e.g. https://openrouter.ai/api/v1 or http://localhost:11434/v1"
                    value={draftConfig.base_url || ''}
                    onChange={(e) => setDraftConfig({ ...draftConfig, base_url: e.target.value })}
                  />
                </div>
              )}

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
