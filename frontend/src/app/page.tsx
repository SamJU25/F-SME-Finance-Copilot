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

const RUNWAY_HORIZON_PRESETS = [
  { days: '30', label: '30d', sub: '1 mo' },
  { days: '60', label: '60d', sub: '2 mo' },
  { days: '90', label: '90d', sub: '1 qtr' },
  { days: '180', label: '180d', sub: '6 mo' },
];

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

function deriveSessionTitle(firstPrompt?: string, fileName?: string): string {
  if (fileName) {
    const cleanName = fileName
      .replace(/\.[^/.]+$/, '')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (cleanName) {
      return cleanName
        .split(' ')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ')
        .slice(0, 32);
    }
  }

  if (!firstPrompt || !firstPrompt.trim()) {
    return 'New Conversation';
  }

  const lower = firstPrompt.toLowerCase();

  if (lower.includes('runway') || lower.includes('burn')) return 'Runway & Daily Burn';
  if (lower.includes('deficit') || lower.includes('shortfall') || lower.includes('overdraft')) return 'Deficit Risk Forecast';
  if (lower.includes('amortization') || lower.includes('monthly payment')) return 'Loan Amortization';
  if (lower.includes('factor') || lower.includes('advance rate')) return 'Invoice Factoring';
  if (lower.includes('loan') || lower.includes('credit') || lower.includes('borrow')) return 'Credit Facility Matching';
  if (lower.includes('break-even') || lower.includes('breakeven')) return 'Break-Even Analysis';
  if (lower.includes('dscr') || lower.includes('debt service')) return 'DSCR Debt Analysis';
  if (lower.includes('fccr') || lower.includes('fixed charge')) return 'FCCR Covenant Audit';
  if (lower.includes('ccc') || lower.includes('working capital') || lower.includes('dso') || lower.includes('dpo')) return 'Working Capital & CCC';
  if (lower.includes('concentration') || lower.includes('hhi')) return 'Revenue Concentration';
  if (lower.includes('churn') || lower.includes('attrition')) return 'Customer Attrition Stress';
  if (lower.includes('hash') || lower.includes('blockchain')) return 'Invoice Verification';
  if (lower.includes('balance')) return 'Cash Balance Inquiry';

  const cleaned = firstPrompt
    .replace(/^(?:can you|could you|please|what is|what are|how do i|how much|tell me about|check|analyze|evaluate)\s+/i, '')
    .replace(/[?!.]+$/, '')
    .replace(/\s+/g, ' ')
    .trim();

  const source = cleaned || firstPrompt.trim();
  const words = source.split(' ');
  const selectedWords: string[] = [];
  let currentLen = 0;
  for (const word of words) {
    if (currentLen + word.length > 28 && selectedWords.length >= 2) break;
    selectedWords.push(word.charAt(0).toUpperCase() + word.slice(1));
    currentLen += word.length + 1;
    if (selectedWords.length >= 5) break;
  }

  return selectedWords.join(' ') || 'Financial Diagnostic';
}

const DEFAULT_WELCOME_MESSAGE: { role: 'agent'; text: string } = {
  role: 'agent',
  text: 'How can I help with your business finances today?',
};

const CASH_STATUS_LABELS: Record<string, string> = {
  WATCH: 'Adequate Runway',
  LOW_RUNWAY: 'Low Runway Alert',
  NO_BURN: 'Cash Flow Positive',
  CASH_NONPOSITIVE: 'Critical Deficit',
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
    prompt: 'What is my current runway and daily burn rate?',
  },
  {
    icon: '⚠️',
    title: 'Detect Cash Deficit Risks',
    prompt: 'Check for upcoming cash shortfalls and deficit risks over the next 60 days.',
  },
  {
    icon: '💼',
    title: 'Match Pre-Qualified Credit Facilities',
    prompt: 'What pre-qualified loan or credit line options can my business qualify for?',
  },
  {
    icon: '🔄',
    title: 'Audit Working Capital & CCC',
    prompt: 'Audit our Cash Conversion Cycle (CCC) and working capital efficiency.',
  },
];

interface StagedIntentItem {
  id: string;
  tenant_id: string;
  action_type: string;
  amount_cents: number;
  target_identifier: string;
  status: 'STAGED_PENDING_HITL' | 'EXECUTED' | 'REJECTED';
  staged_at: string;
  facility_name: string;
  apr_percent?: string;
}

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [csvText, setCsvText] = useState<string | null>(null);
  const [threshold, setThreshold] = useState('30');
  const [result, setResult] = useState<CashAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Staged Action Proposals State
  const [stagedIntents, setStagedIntents] = useState<StagedIntentItem[]>([]);

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
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && chatOpen) {
        setChatOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [chatOpen]);

  // Lock background homepage scrolling when drawer is open
  useEffect(() => {
    if (chatOpen) {
      const originalOverflow = document.body.style.overflow;
      const originalPaddingRight = document.body.style.paddingRight;
      const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
      document.body.style.overflow = 'hidden';
      if (scrollbarWidth > 0) {
        document.body.style.paddingRight = `${scrollbarWidth}px`;
      }
      return () => {
        document.body.style.overflow = originalOverflow;
        document.body.style.paddingRight = originalPaddingRight;
      };
    }
  }, [chatOpen]);

  useEffect(() => {
    async function syncStagingLedger() {
      try {
        const res = await fetch(`${API_URL}/api/v1/actions`);
        if (res.ok) {
          const remoteIntents = await res.json();
          if (Array.isArray(remoteIntents)) {
            const pendingOnly = remoteIntents.filter((r: { status: string }) => r.status === 'STAGED_PENDING_HITL');
            const mapped: StagedIntentItem[] = pendingOnly.map((r: { id: string; tenant_id: string; action_type: string; amount_cents: number; target_identifier: string; status: string; staged_at?: string; apr_percent?: string }) => ({
              id: r.id,
              tenant_id: r.tenant_id,
              action_type: r.action_type,
              amount_cents: r.amount_cents,
              target_identifier: r.target_identifier,
              status: r.status as 'STAGED_PENDING_HITL' | 'EXECUTED' | 'REJECTED',
              staged_at: r.staged_at ? new Date(r.staged_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Pending',
              facility_name: r.action_type === 'FACTOR_INVOICE' ? 'Invoice Factoring' : r.action_type === 'DRAW_CREDIT_LINE' ? 'Credit Line Draw' : r.action_type,
              apr_percent: r.apr_percent ? `${r.apr_percent}% True APR` : undefined,
            }));
            setStagedIntents(mapped);
          }
        }
      } catch {
        // Local fallback
      }
    }
    syncStagingLedger();
  }, []);

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

  const [messages, setMessages] = useState<Array<{ role: 'user' | 'agent'; text: string; data?: CopilotResponse }>>([]);

  const conversationMessages = messages.filter(
    (m) => m.text !== DEFAULT_WELCOME_MESSAGE.text
  );
  const hasUserMessages = conversationMessages.some((m) => m.role === 'user');

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
            storedSessionsList = parsed.map((item: SessionItem) => {
              if (item.title && (item.title.startsWith('Session ') || item.title === 'Current Session')) {
                try {
                  const msgsStr = localStorage.getItem(`sme_copilot_chat_${item.id}`);
                  if (msgsStr) {
                    const parsedMsgs = JSON.parse(msgsStr);
                    const firstUser = parsedMsgs.find((m: any) => m.role === 'user');
                    if (firstUser?.text) {
                      return { ...item, title: deriveSessionTitle(firstUser.text) };
                    }
                  }
                } catch {
                  // Fallback
                }
                return { ...item, title: 'New Conversation' };
              }
              return item;
            });
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
          title: 'New Conversation',
          updatedAt: new Date().toISOString(),
          messageCount: 0,
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
        const updatedTitle = deriveSessionTitle(firstUserMsg?.text, file?.name);

        let nextSessions: SessionItem[];
        if (idx >= 0) {
          const current = prev[idx];
          const isGeneric = current.title.startsWith('Session ') || current.title === 'Current Session' || current.title === 'New Session' || current.title === 'New Conversation';
          const newTitle = isGeneric && (firstUserMsg || file) ? updatedTitle : current.title;
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

  function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files?.[0] ?? null;
    setFile(picked);
    setResult(null);
    setError(null);
    if (picked) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = (e.target?.result as string) || '';
        setCsvText(content);
        try {
          localStorage.setItem(`sme_copilot_csv_${sessionId}`, content);
          localStorage.setItem('sme_copilot_csv_text', content);
        } catch {
          // LocalStorage fallback
        }
      };
      reader.readAsText(picked);
      executeAnalysis(picked, threshold);
      const fileTitle = deriveSessionTitle(undefined, picked.name);
      setSessions((prev) => {
        const idx = prev.findIndex((s) => s.id === sessionId);
        if (idx >= 0) {
          const current = prev[idx];
          const isGeneric = current.title.startsWith('Session ') || current.title === 'Current Session' || current.title === 'New Session' || current.title === 'New Conversation';
          if (isGeneric) {
            const next = [...prev];
            next[idx] = { ...current, title: fileTitle, updatedAt: new Date().toISOString() };
            try {
              localStorage.setItem('sme_copilot_sessions_list', JSON.stringify(next));
            } catch {
              // LocalStorage fallback
            }
            return next;
          }
        }
        return prev;
      });
    } else {
      setCsvText(null);
    }
  }

  async function handleRemoveCsv() {
    setFile(null);
    setCsvText(null);
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    try {
      localStorage.removeItem(`sme_copilot_csv_${sessionId}`);
      localStorage.removeItem('sme_copilot_csv_text');
    } catch {
      // LocalStorage fallback
    }
    try {
      await fetch(`${API_URL}/api/v1/agent/session/${encodeURIComponent(sessionId)}/statement`, {
        method: 'DELETE',
        headers: {
          'X-Tenant-ID': 'SME-COFFEE-001',
          'X-Session-ID': sessionId,
        },
      });
    } catch {
      // Offline fallback
    }
  }

  function handleChangeCsv() {
    fileInputRef.current?.click();
  }

  async function analyze(event?: FormEvent<HTMLFormElement>) {
    if (event) event.preventDefault();
    if (!file && !csvText) {
      setError('Choose a CSV file before reviewing cash activity.');
      return;
    }
    const targetFile = file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' });
    await executeAnalysis(targetFile, threshold);
  }

  async function sendChatMessage(promptText?: string) {
    const textToSend = promptText || chatInput;
    if (!textToSend.trim()) return;

    const newMsgs = [...conversationMessages, { role: 'user' as const, text: textToSend }];
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
          history: conversationMessages.slice(-6).map((m) => ({ role: m.role, text: m.text })),
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
    const newMsgs: Array<{ role: 'user' | 'agent'; text: string; data?: CopilotResponse }> = [];
    const newSessionItem: SessionItem = {
      id: newSessionId,
      title: 'New Conversation',
      updatedAt: new Date().toISOString(),
      messageCount: 0,
    };

    setSessionId(newSessionId);
    setMessages(newMsgs);
    setChatInput('');
    setCsvText(null);
    setFile(null);
    setResult(null);
    setError(null);
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

    setChatInput('');
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

    try {
      const savedCsv = localStorage.getItem(`sme_copilot_csv_${targetId}`);
      if (savedCsv) {
        setCsvText(savedCsv);
      }
    } catch {
      // LocalStorage fallback
    }

    if (!loaded) {
      try {
        const res = await fetch(`${API_URL}/api/v1/agent/session/${targetId}`);
        if (res.ok) {
          const data = await res.json();
          const msgsList = data?.messages || data?.history;
          if (Array.isArray(msgsList) && msgsList.length > 0) {
            const mapped = msgsList.map((h: { role: 'user' | 'agent'; text: string }) => ({
              role: h.role,
              text: h.text,
            }));
            setMessages(mapped);
            loaded = true;
            try {
              localStorage.setItem(sessionChatKey, JSON.stringify(mapped));
            } catch {
              // LocalStorage fallback
            }
          }
          if (data?.csv_content) {
            setCsvText(data.csv_content);
            try {
              localStorage.setItem(`sme_copilot_csv_${targetId}`, data.csv_content);
            } catch {
              // LocalStorage fallback
            }
          }
        }
      } catch {
        // Backend fallback
      }
    }

    if (!loaded) {
      setMessages([]);
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
      localStorage.removeItem(`sme_copilot_csv_${idToDelete}`);
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
    title: 'New Conversation',
    messageCount: messages.length,
    updatedAt: new Date().toISOString(),
  };

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(sessionSearch.toLowerCase()) ||
    s.id.toLowerCase().includes(sessionSearch.toLowerCase())
  );

  async function executeAction(intentId: string) {
    try {
      await fetch(`${API_URL}/api/v1/actions/${intentId}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ biometric_signature: 'approved_founder_session' }),
      });
      setExecutedIntents((prev) => ({ ...prev, [intentId]: true }));
      setStagedIntents((prev) =>
        prev.map((item) =>
          item.id === intentId
            ? { ...item, status: 'EXECUTED' as const }
            : item
        )
      );
    } catch (err) {
      console.error('Execution error:', err);
      setExecutedIntents((prev) => ({ ...prev, [intentId]: true }));
      setStagedIntents((prev) =>
        prev.map((item) =>
          item.id === intentId
            ? { ...item, status: 'EXECUTED' as const }
            : item
        )
      );
    }
  }

  async function rejectAction(intentId: string) {
    try {
      await fetch(`${API_URL}/api/v1/actions/${intentId}/reject`, {
        method: 'POST',
      });
      setStagedIntents((prev) =>
        prev.map((item) =>
          item.id === intentId
            ? { ...item, status: 'REJECTED' as const }
            : item
        )
      );
    } catch (err) {
      console.error('Rejection error:', err);
      setStagedIntents((prev) =>
        prev.map((item) =>
          item.id === intentId
            ? { ...item, status: 'REJECTED' as const }
            : item
        )
      );
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">$</span>
          <span>SME Finance Copilot</span>
        </div>
        <div className="topbar-actions">
          {/* Live AI Engine Selector Pill */}
          <button
            className="topbar-engine-btn"
            onClick={() => {
              setDraftConfig(llmConfig);
              setShowSettings(true);
              fetchModels(llmConfig);
            }}
            type="button"
            title="Configure AI model provider and credentials"
            aria-label="Configure AI Model Settings"
          >
            <span className="topbar-dot" aria-hidden="true" />
            <span className="topbar-engine-label">Engine:</span>
            <span className="topbar-engine-name">{getEngineDisplayName(llmConfig)}</span>
            <svg
              className="topbar-gear-svg"
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

          {/* Copilot Chat Toggle Button */}
          <button
            className={`topbar-chat-btn ${chatOpen ? 'active' : ''}`}
            onClick={() => setChatOpen((prev) => !prev)}
            type="button"
            title={chatOpen ? 'Close Copilot Drawer' : 'Open Autonomous Copilot Drawer'}
            aria-expanded={chatOpen}
          >
            <svg
              className="topbar-chat-icon"
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
            <span>Copilot</span>
            <span className="topbar-chat-badge">{conversationMessages.length}</span>
          </button>

        </div>
      </header>

      <main>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 'clamp(28px, 4vw, 40px)', letterSpacing: '-0.03em', margin: '0 0 8px' }}>
            Cash Runway & Liquidity
          </h1>
          <p style={{ margin: 0, color: 'var(--muted)', fontSize: 15 }}>
            Upload a bank statement CSV to compute burn velocity, project runway, and detect cash deficit risks.
          </p>
        </div>

        {/* Staged Action Proposals */}
        {result && stagedIntents.length > 0 && (
          <div className="staged-queue-panel" style={{ marginBottom: 24 }}>
            <div className="staged-queue-head">
              <h3 className="staged-queue-title">Action Proposals</h3>
            </div>

            <div className="staged-table-wrapper">
              <table className="staged-items-table">
                <thead>
                  <tr>
                    <th>Proposal</th>
                    <th>Target Identifier</th>
                    <th>Amount</th>
                    <th>Timestamp</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {stagedIntents.map((item) => {
                    const isExecuted = item.status === 'EXECUTED' || executedIntents[item.id];
                    const isRejected = item.status === 'REJECTED';
                    return (
                      <tr key={item.id}>
                        <td>
                          <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{item.facility_name}</div>
                          <div className="staged-meta-sub">{item.apr_percent ? `${item.action_type} · ${item.apr_percent}` : item.action_type}</div>
                        </td>
                        <td>
                          <div className="staged-intent-id">{item.target_identifier}</div>
                        </td>
                        <td>
                          <div className="staged-amount">
                            ${(item.amount_cents / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </td>
                        <td>
                          <div className="staged-meta-sub">{item.staged_at}</div>
                        </td>
                        <td>
                          <span className={`staged-badge ${isExecuted ? 'executed' : isRejected ? 'pending' : 'pending'}`}>
                            {isExecuted ? 'Approved' : isRejected ? 'Rejected' : 'Pending Review'}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {isExecuted ? (
                            <span className="staged-executed-badge">✓ Approved</span>
                          ) : isRejected ? (
                            <span style={{ fontSize: 11, color: 'var(--muted)' }}>Dismissed</span>
                          ) : (
                            <div style={{ display: 'inline-flex', gap: 6 }}>
                              <button
                                type="button"
                                className="approve-btn"
                                onClick={() => executeAction(item.id)}
                              >
                                Approve
                              </button>
                              <button
                                type="button"
                                className="reject-btn"
                                onClick={() => rejectAction(item.id)}
                              >
                                Reject
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="content-grid">
          <section className="panel" aria-labelledby="upload-title">
            <h2 id="upload-title">Statement Ingestion</h2>
            <p className="panel-intro">Processed in local memory · Ephemeral session</p>
            <form onSubmit={analyze}>
              <div className="threshold-group">
                <label className="field-label" htmlFor="threshold">Alert threshold (runway warning days)</label>
                <div className="threshold-container">
                  <div className="threshold-pills" role="radiogroup" aria-label="Runway alert horizon presets">
                    {RUNWAY_HORIZON_PRESETS.map((preset) => {
                      const isSelected = threshold === preset.days;
                      return (
                        <button
                          key={preset.days}
                          type="button"
                          role="radio"
                          aria-checked={isSelected}
                          className={`threshold-pill ${isSelected ? 'active' : ''}`}
                          onClick={() => {
                            setThreshold(preset.days);
                            if (file || csvText) {
                              const target = file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' });
                              executeAnalysis(target, preset.days);
                            }
                          }}
                        >
                          <span className="threshold-pill-days">{preset.label}</span>
                          <span className="threshold-pill-sub">({preset.sub})</span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="threshold-custom-wrap">
                    <span className="threshold-custom-prefix">Custom:</span>
                    <input
                      id="threshold"
                      name="alert_threshold_days"
                      type="number"
                      min="1"
                      max="365"
                      step="1"
                      aria-label="Custom runway alert days"
                      className="threshold-custom-input"
                      placeholder="30"
                      value={threshold}
                      onChange={(event) => setThreshold(event.target.value)}
                      onBlur={() => {
                        const num = Number(threshold);
                        if (!threshold || isNaN(num) || num < 1) {
                          setThreshold('30');
                        } else if (file || csvText) {
                          const target = file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' });
                          executeAnalysis(target, threshold);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          if (file || csvText) {
                            const target = file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' });
                            executeAnalysis(target, threshold);
                          }
                        }
                      }}
                    />
                    <span className="threshold-custom-suffix">days</span>
                  </div>
                </div>
                <div className="threshold-helper">
                  Triggers warning if burn velocity depletes cash balance within{' '}
                  <strong>{threshold || '30'} days</strong>.
                </div>
              </div>

              {file || csvText ? (
                <>
                  <input
                    ref={fileInputRef}
                    id="csv-file"
                    className="file-input"
                    aria-label="Choose bank statement CSV file"
                    type="file"
                    accept=".csv,text/csv"
                    style={{ display: 'none' }}
                    onChange={handleFileInputChange}
                  />
                  <div className="uploaded-file-card" role="region" aria-label="Active uploaded bank statement">
                    <div className="uploaded-file-info">
                      <span className="uploaded-file-icon" aria-hidden="true">📄</span>
                      <div className="uploaded-file-meta">
                        <span className="uploaded-file-name">
                          {file ? file.name : 'Active_Statement.csv'}
                        </span>
                        <span className="uploaded-file-size">
                          {file
                            ? `${(file.size / 1024).toFixed(1)} KB · Active in Session`
                            : csvText
                            ? `${(csvText.length / 1024).toFixed(1)} KB · Active in Session`
                            : 'Statement Loaded'}
                        </span>
                      </div>
                    </div>
                    <div className="uploaded-file-actions">
                      <button
                        type="button"
                        className="change-csv-btn"
                        onClick={handleChangeCsv}
                        title="Replace with another CSV statement"
                      >
                        Change
                      </button>
                      <button
                        type="button"
                        className="remove-csv-btn"
                        onClick={handleRemoveCsv}
                        title="Remove statement from active session"
                      >
                        <span aria-hidden="true">✕</span> Remove
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="dropzone">
                  <span className="upload-icon" aria-hidden="true">↑</span>
                  <label className="field-label" htmlFor="csv-file">Choose a CSV file</label>
                  <input
                    ref={fileInputRef}
                    id="csv-file"
                    className="file-input"
                    aria-label="Choose bank statement CSV file"
                    type="file"
                    accept=".csv,text/csv"
                    onChange={handleFileInputChange}
                  />
                  <div className="file-name">UTF-8 CSV · max 1 MB</div>
                </div>
              )}

              <div style={{ marginTop: 8, fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
                Format: <code>{CSV_HEADER}</code>
              </div>

              <button className="submit" type="submit" disabled={loading || (!file && !csvText)} style={{ marginTop: 16 }}>
                {loading ? 'Analyzing statement…' : 'Analyze cash activity'}
              </button>
            </form>
            {loading && <div className="notice loading" role="status" aria-live="polite">Reading statement and calculating cash metrics…</div>}
            {error && <div className="notice error" role="alert">{error}</div>}
          </section>

          <section className="panel" aria-labelledby="result-title">
            <div className="result-head">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <h2 id="result-title">Cash Summary</h2>
                  {result?.analysis_mode && (
                    <span
                      className={`mode-badge ${result.analysis_mode === 'HISTORICAL_AUDIT' ? 'audit' : 'live'}`}
                      role="status"
                      title={
                        result.analysis_mode === 'HISTORICAL_AUDIT'
                          ? `Statement closed ${result.statement_age_days} days ago. Metrics and projections evaluate historical liquidity from that closing baseline.`
                          : `Statement is current (closed ${result.statement_age_days ?? 0} days ago).`
                      }
                    >
                      <span className="mode-dot" aria-hidden="true" />
                      {result.analysis_mode === 'HISTORICAL_AUDIT'
                        ? `Historical Audit · Closed ${result.statement_age_days}d ago`
                        : 'Live Operating'}
                    </span>
                  )}
                </div>
                {result?.end_date && (
                  <p className="result-as-of">
                    As of statement close: <time dateTime={result.end_date}>{result.end_date}</time>
                    {result.start_date && (
                      <span className="result-span"> · {result.start_date} to {result.end_date}</span>
                    )}
                  </p>
                )}
              </div>
              {result && (
                <span
                  className={`status ${result.cash_status}`}
                  role="status"
                  aria-label={`Liquidity status: ${CASH_STATUS_LABELS[result.cash_status] || result.cash_status}`}
                >
                  <span className="status-dot" aria-hidden="true" />
                  {CASH_STATUS_LABELS[result.cash_status] || result.cash_status.replaceAll('_', ' ')}
                </span>
              )}
            </div>

            {result ? (
              <div className="result" aria-live="polite">
                {result.analysis_mode === 'HISTORICAL_AUDIT' && (
                  <div className="audit-mode-banner" role="note">
                    <span className="audit-icon" aria-hidden="true">🏛️</span>
                    <div>
                      <strong>Historical Diagnostic Mode:</strong> This statement closed{' '}
                      <span className="tabular-num">{result.statement_age_days}</span> days ago ({result.end_date}). Metrics evaluate performance over the reviewed window. Runway and deficit projections benchmark liquidity from that closing baseline.
                    </div>
                  </div>
                )}
                <div className="metrics">
                  <Metric label="Current balance" value={money(result.current_balance, result.currency)} />
                  <Metric label="Historical net change" value={money(result.net_period_change, result.currency)} />
                  <Metric label="Average daily burn" value={money(result.average_daily_burn, result.currency)} />
                  <Metric
                    label={result.analysis_mode === 'HISTORICAL_AUDIT' ? 'Historical runway from close' : 'Estimated runway'}
                    value={result.runway_days === null ? 'No burn' : `${result.runway_days} days`}
                  />
                  <Metric label="Period reviewed" value={`${result.period_days} days`} />
                  <Metric label="Rows accepted" value={`${result.accepted_count}`} />
                </div>
                {result.rejected_rows.length > 0 && (
                  <div className="rejections">
                    <h3>Rows not included ({result.rejected_rows.length})</h3>
                    <ul>{result.rejected_rows.map((row) => <li key={`${row.row_number}-${row.reason_code}`}>Row {row.row_number}: {row.reason_code.replaceAll('_', ' ').toLowerCase()}</li>)}</ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="empty-results-box">
                <div className="empty-results-icon">📊</div>
                <h3>No Statement Analyzed</h3>
                <p>Upload a CSV file to view cash runway, burn rate, and liquidity status.</p>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* Interactive Copilot Chat Sidecar Drawer */}
      {chatOpen && (
        <>
          <div
            className="chat-backdrop"
            onClick={() => setChatOpen(false)}
            onWheel={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onTouchMove={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            aria-hidden="true"
          />
          <div
            className="chat-drawer"
            role="complementary"
            aria-label="Autonomous AI Copilot Sidecar"
            onWheel={(e) => {
              e.stopPropagation();
            }}
          >
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
                      {conversationMessages.length} msgs
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
                        <svg className="session-search-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <circle cx="11" cy="11" r="8"></circle>
                          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                        <input
                          type="text"
                          className="session-search-input"
                          placeholder="Search sessions…"
                          value={sessionSearch}
                          onChange={(e) => setSessionSearch(e.target.value)}
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
                            <button
                              type="button"
                              className="session-delete-btn"
                              title="Delete this session chat"
                              onClick={(e) => handleDeleteSession(s.id, e)}
                              aria-label={`Delete session ${s.title}`}
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                              </svg>
                            </button>
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
              <button className="chat-close" onClick={() => setChatOpen(false)} type="button" aria-label="Close Drawer">
                ✕
              </button>
            </div>
          </div>

          <div className="chat-body">
            {!hasUserMessages ? (
              <div className="chat-empty-state">
                <div className="chat-empty-greeting">
                  <h3>How can I help with your business finances today?</h3>
                  <p>Ask about cash runway, deficit forecasts, or select a suggested inquiry below.</p>
                </div>
                <div className="starter-prompts">
                  <span className="starter-prompts-label">Suggested Financial Inquiries</span>
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
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              conversationMessages.map((m, idx) => (
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
                    {m.data?.metrics && (m.data.metrics.current_balance || m.data.metrics.average_daily_burn || m.data.metrics.runway_days !== undefined || m.data.metrics.daily_average_balance || m.data.metrics.risk_tier) && (
                      <div className="chat-card">
                        <strong>Calculated Cash Metrics</strong>
                        {m.data.metrics.current_balance && <div>Balance: ${m.data.metrics.current_balance}</div>}
                        {m.data.metrics.average_daily_burn && <div>Burn: ${m.data.metrics.average_daily_burn}/day</div>}
                        {m.data.metrics.runway_days !== undefined && <div>Runway: {m.data.metrics.runway_days} days</div>}
                        {m.data.metrics.daily_average_balance && <div>Daily Avg Balance: ${m.data.metrics.daily_average_balance}</div>}
                        {m.data.metrics.risk_tier && <div>Risk Rating: {m.data.metrics.risk_tier}</div>}
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

                    {/* Action Proposal Card */}
                    {m.data?.staged_action && (
                      <div className={`chat-card ${executedIntents[m.data.staged_action.intent_id] ? 'executed' : ''}`}>
                        <strong>
                          {executedIntents[m.data.staged_action.intent_id]
                            ? '✓ Proposal Approved'
                            : 'Action Proposal Awaiting Review'}
                        </strong>
                        <div style={{ marginTop: 4 }}>
                          Action: {m.data.staged_action.action_type} · Amount: ${(m.data.staged_action.amount_cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' })}
                        </div>
                        {!executedIntents[m.data.staged_action.intent_id] && (
                          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                            <button
                              className="approve-btn"
                              type="button"
                              onClick={() => executeAction(m.data!.staged_action!.intent_id)}
                            >
                              Approve
                            </button>
                            <button
                              className="reject-btn"
                              type="button"
                              onClick={() => rejectAction(m.data!.staged_action!.intent_id)}
                            >
                              Dismiss
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </Fragment>
              ))
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
      </>
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
