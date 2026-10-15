'use client';

import React, { FormEvent, Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
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

export interface ChartPoint {
  date: string;
  displayDate: string;
  balance?: number;
  projection?: number;
  inflow?: number;
  outflow?: number;
  isProjection?: boolean;
}

function buildCashTrajectorySeries(
  csv: string | null,
  res: CashAnalysisResponse | null,
  thresholdDays: number
): ChartPoint[] {
  if (!res) return [];

  const points: ChartPoint[] = [];

  if (csv) {
    const lines = csv.trim().split('\n');
    const rawParsed: { date: string; amount: number; balance?: number }[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const parts = line.split(/[;,]/);
      if (parts.length >= 3) {
        const datePart = parts.find((p) =>
          /^\d{4}-\d{2}-\d{2}$|^\d{1,2}\/\d{1,2}\/\d{4}$|^\d{1,2}\.\d{1,2}\.\d{4}$/.test(p.trim())
        );
        if (datePart) {
          let normDate = datePart.trim();
          if (normDate.includes('/')) {
            const dp = normDate.split('/');
            normDate = `${dp[2]}-${dp[0].padStart(2, '0')}-${dp[1].padStart(2, '0')}`;
          } else if (normDate.includes('.')) {
            const dp = normDate.split('.');
            normDate = `${dp[2]}-${dp[1].padStart(2, '0')}-${dp[0].padStart(2, '0')}`;
          }

          const numParts = parts.filter((p) =>
            /^[+-]?\$?€?£?\s*\(?\d+([.,]\d{2})?\)?$/.test(p.trim())
          );
          if (numParts.length > 0) {
            const cleanNum = (s: string) => {
              let v = s.replace(/[\$€£\s\(\)]/g, '');
              if (v.includes(',') && !v.includes('.')) v = v.replace(',', '.');
              else if (v.includes('.') && v.includes(',')) v = v.replace('.', '').replace(',', '.');
              return parseFloat(v) || 0;
            };
            const amt = cleanNum(numParts[0]);
            const bal = numParts.length > 1 ? cleanNum(numParts[numParts.length - 1]) : undefined;
            rawParsed.push({ date: normDate, amount: amt, balance: bal });
          }
        }
      }
    }

    if (rawParsed.length > 0) {
      rawParsed.sort((a, b) => a.date.localeCompare(b.date));
      const byDate = new Map<string, { lastBal: number; inflow: number; outflow: number }>();
      let runningBal = parseFloat(res.current_balance) - parseFloat(res.net_period_change);

      for (const item of rawParsed) {
        if (item.balance !== undefined) {
          runningBal = item.balance;
        } else {
          runningBal += item.amount;
        }
        const existing = byDate.get(item.date) || { lastBal: runningBal, inflow: 0, outflow: 0 };
        existing.lastBal = runningBal;
        if (item.amount > 0) existing.inflow += item.amount;
        else existing.outflow += Math.abs(item.amount);
        byDate.set(item.date, existing);
      }

      for (const [dStr, info] of Array.from(byDate.entries())) {
        points.push({
          date: dStr,
          displayDate: dStr.slice(5),
          balance: Math.round(info.lastBal * 100) / 100,
          inflow: Math.round(info.inflow * 100) / 100,
          outflow: Math.round(info.outflow * 100) / 100,
          isProjection: false,
        });
      }
    }
  }

  // Anchor fallback if no points parsed
  if (points.length === 0) {
    const curBal = parseFloat(res.current_balance);
    const netChg = parseFloat(res.net_period_change);
    const startBal = curBal - netChg;
    if (res.start_date) {
      points.push({
        date: res.start_date,
        displayDate: res.start_date.slice(5),
        balance: Math.round(startBal * 100) / 100,
        isProjection: false,
      });
    }
    if (res.end_date) {
      points.push({
        date: res.end_date,
        displayDate: res.end_date.slice(5),
        balance: Math.round(curBal * 100) / 100,
        isProjection: false,
      });
    }
  }

  // Forward Runway Projections
  const curBal = parseFloat(res.current_balance);
  const burn = parseFloat(res.average_daily_burn);
  const lastDateStr =
    res.end_date ||
    (points.length > 0 ? points[points.length - 1].date : new Date().toISOString().slice(0, 10));

  if (curBal > 0 && burn > 0) {
    const lastDate = new Date(lastDateStr);
    const maxDays = Math.min(90, res.runway_days ? res.runway_days + 15 : 90);
    const lastPoint = points[points.length - 1];
    if (lastPoint) {
      lastPoint.projection = lastPoint.balance;
    }

    const intervals = [7, 14, 21, 30, 45, 60, 90].filter((d) => d <= maxDays);
    if (res.runway_days && !intervals.includes(res.runway_days)) {
      intervals.push(res.runway_days);
      intervals.sort((a, b) => a - b);
    }

    for (const d of intervals) {
      const projDate = new Date(lastDate.getTime() + d * 86400000);
      const iso = projDate.toISOString().slice(0, 10);
      const projBal = Math.max(0, curBal - burn * d);
      points.push({
        date: iso,
        displayDate: `${iso.slice(5)} (+${d}d)`,
        projection: Math.round(projBal * 100) / 100,
        isProjection: true,
      });
    }
  }

  return points;
}

function CustomChartTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean;
  payload?: any[];
  currency: string;
}) {
  if (active && payload && payload.length) {
    const data = payload[0].payload as ChartPoint;
    return (
      <div className="chart-tooltip-box">
        <div className="chart-tooltip-date">
          {data.isProjection ? `Forecast: ${data.date}` : `Ledger Date: ${data.date}`}
        </div>
        {data.balance !== undefined && (
          <div className="chart-tooltip-row">
            <span>Historical Balance:</span>
            <strong className="tabular-num">{money(data.balance.toFixed(2), currency)}</strong>
          </div>
        )}
        {data.projection !== undefined && (
          <div className="chart-tooltip-row forecast">
            <span>Projected Balance:</span>
            <strong className="tabular-num">{money(data.projection.toFixed(2), currency)}</strong>
          </div>
        )}
        {data.inflow !== undefined && data.inflow > 0 && (
          <div className="chart-tooltip-row inflow">
            <span>Day Inflow:</span>
            <strong className="tabular-num">+{money(data.inflow.toFixed(2), currency)}</strong>
          </div>
        )}
        {data.outflow !== undefined && data.outflow > 0 && (
          <div className="chart-tooltip-row outflow">
            <span>Day Outflow:</span>
            <strong className="tabular-num">-{money(data.outflow.toFixed(2), currency)}</strong>
          </div>
        )}
      </div>
    );
  }
  return null;
}

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
  const [filesList, setFilesList] = useState<File[]>([]);
  const [csvText, setCsvText] = useState<string | null>(null);
  const [threshold, setThreshold] = useState('30');
  const [result, setResult] = useState<CashAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [activeTab, setActiveTab] = useState<'pulse' | 'portfolio' | 'flows' | 'working_capital'>('pulse');
  const [selectedAccount, setSelectedAccount] = useState<string>('all');
  const [selectedMonth, setSelectedMonth] = useState<string>('all');
  const [accountAnalysisCache, setAccountAnalysisCache] = useState<Record<string, CashAnalysisResponse>>({});

  const displayResult = useMemo(() => {
    if (!result) return null;
    if (selectedAccount !== 'all' && accountAnalysisCache[selectedAccount]) {
      return accountAnalysisCache[selectedAccount];
    }
    return result;
  }, [result, selectedAccount, accountAnalysisCache]);

  const uniqueAccountClusters = useMemo(() => {
    if (!result?.accounts_breakdown || result.accounts_breakdown.length === 0) return [];
    const map = new Map<string, { accountId: string; fileNames: string[]; latestBalance: string; latestDate: string }>();
    result.accounts_breakdown.forEach((acc) => {
      const existing = map.get(acc.account_id);
      if (!existing) {
        map.set(acc.account_id, {
          accountId: acc.account_id,
          fileNames: [acc.file_name],
          latestBalance: acc.closing_balance,
          latestDate: acc.end_date,
        });
      } else {
        existing.fileNames.push(acc.file_name);
        if (acc.end_date >= existing.latestDate) {
          existing.latestBalance = acc.closing_balance;
          existing.latestDate = acc.end_date;
        }
      }
    });
    return Array.from(map.values());
  }, [result]);

  const isSingleAccountPortfolio = uniqueAccountClusters.length === 1 && (result?.accounts_breakdown?.length || 0) > 1;

  const dynamicAlertDate = computeAlertBoundaryDate(displayResult?.end_date, threshold) || displayResult?.alert_boundary_date;

  const trajectoryData = useMemo(() => {
    return buildCashTrajectorySeries(csvText, displayResult, Number(threshold) || 30);
  }, [csvText, displayResult, threshold]);

  const availableMonths = useMemo(() => {
    const monthsMap = new Map<string, string>();
    trajectoryData.forEach((p) => {
      if (p.date && !p.isProjection) {
        const ym = p.date.slice(0, 7);
        if (!monthsMap.has(ym)) {
          try {
            const [year, month] = ym.split('-');
            const monthName = new Date(Number(year), Number(month) - 1, 1).toLocaleString('en-US', {
              month: 'long',
              year: 'numeric',
            });
            monthsMap.set(ym, monthName);
          } catch {
            monthsMap.set(ym, ym);
          }
        }
      }
    });
    return Array.from(monthsMap.entries()).map(([key, label]) => ({ key, label }));
  }, [trajectoryData]);

  const displayedChartData = useMemo(() => {
    if (selectedMonth === 'all') {
      return trajectoryData;
    }
    const monthPoints = trajectoryData.filter(
      (p) =>
        p.date.startsWith(selectedMonth) ||
        (p.isProjection && selectedMonth === availableMonths[availableMonths.length - 1]?.key)
    );
    return monthPoints.length > 0 ? monthPoints : trajectoryData;
  }, [trajectoryData, selectedMonth, availableMonths]);

  const selectedMonthStats = useMemo(() => {
    if (selectedMonth === 'all') return null;
    const monthPts = trajectoryData.filter((p) => p.date.startsWith(selectedMonth) && !p.isProjection);
    if (monthPts.length === 0) return null;
    const totalInflow = monthPts.reduce((acc, p) => acc + (p.inflow || 0), 0);
    const totalOutflow = monthPts.reduce((acc, p) => acc + (p.outflow || 0), 0);
    const firstPt = monthPts[0];
    const lastPt = monthPts[monthPts.length - 1];
    const startBal: number = firstPt && typeof firstPt.balance === 'number' ? firstPt.balance : 0;
    const endBal: number = lastPt && typeof lastPt.balance === 'number' ? lastPt.balance : 0;
    return {
      inflow: totalInflow,
      outflow: totalOutflow,
      net: totalInflow - totalOutflow,
      startBal,
      endBal,
    };
  }, [trajectoryData, selectedMonth]);

  async function handleSelectAccount(accountKey: string) {
    setSelectedAccount(accountKey);
    if (accountKey === 'all') return;
    if (accountAnalysisCache[accountKey]) return;

    const target = filesList.find((f) => f.name === accountKey);
    if (target) {
      try {
        const data = new FormData();
        data.append('file', target);
        data.append('alert_threshold_days', threshold);
        const res = await fetch(`${API_URL}/api/v1/analyze`, { method: 'POST', body: data });
        if (res.ok) {
          const body: CashAnalysisResponse = await res.json();
          setAccountAnalysisCache((prev) => ({ ...prev, [accountKey]: body }));
        }
      } catch {}
    }
  }

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

  async function executeAnalysis(targetFile: File | File[], thresholdValue?: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    const effectiveDays = thresholdValue && Number(thresholdValue) >= 1
      ? thresholdValue
      : (threshold && Number(threshold) >= 1 ? threshold : '30');
    try {
      const data = new FormData();
      if (Array.isArray(targetFile)) {
        targetFile.forEach((f) => {
          data.append('files', f);
        });
      } else if (targetFile) {
        data.append('files', targetFile);
      }
      data.append('alert_threshold_days', effectiveDays);
      const headers: Record<string, string> = {};
      if (llmConfig) {
        headers['X-LLM-Config'] = JSON.stringify(llmConfig);
      }
      const response = await fetch(`${API_URL}/api/v1/analyze`, { method: 'POST', body: data, headers });
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

  async function loadAllFilesText(files: File[], activeSessionId: string): Promise<string> {
    if (files.length === 0) {
      setCsvText(null);
      return '';
    }
    const texts = await Promise.all(
      files.map((f) =>
        typeof f.text === 'function'
          ? f.text()
          : new Promise<string>((resolve) => {
              const r = new FileReader();
              r.onload = () => resolve((r.result as string) || '');
              r.readAsText(f);
            })
      )
    );
    const combined = texts.join('\n');
    setCsvText(combined);
    try {
      localStorage.setItem(`sme_copilot_csv_${activeSessionId}`, combined);
      localStorage.setItem('sme_copilot_csv_text', combined);
    } catch {
      // LocalStorage fallback
    }
    return combined;
  }

  async function handleAddFiles(newFiles: File[]) {
    if (newFiles.length === 0) return;

    // Deduplicate incoming files against current filesList by name + size
    const existing = [...filesList];
    const map = new Map<string, File>();
    existing.forEach((f) => map.set(`${f.name}_${f.size}`, f));
    newFiles.forEach((f) => map.set(`${f.name}_${f.size}`, f));
    const merged = Array.from(map.values());

    setFilesList(merged);
    setFile(merged[0] || null);

    const activeSession = sessionId || `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    if (!sessionId) {
      setSessionId(activeSession);
    }

    await loadAllFilesText(merged, activeSession);
    executeAnalysis(merged, threshold);

    const fileTitle =
      merged.length > 1
        ? `${merged.length} Statements (${merged[0].name.replace(/\.[^/.]+$/, '')} +${merged.length - 1})`
        : deriveSessionTitle(undefined, merged[0].name);

    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === activeSession);
      if (idx >= 0) {
        const current = prev[idx];
        const isGeneric =
          current.title.startsWith('Session ') ||
          current.title === 'Current Session' ||
          current.title === 'New Session' ||
          current.title === 'New Conversation';
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
  }

  async function handleRemoveSingleFile(indexToRemove: number) {
    const next = filesList.filter((_, idx) => idx !== indexToRemove);
    setFilesList(next);
    if (next.length === 0) {
      handleRemoveCsv();
    } else {
      setFile(next[0]);
      await loadAllFilesText(next, sessionId);
      executeAnalysis(next, threshold);
    }
  }

  function handleFileInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const pickedList = event.target.files ? Array.from(event.target.files) : [];
    if (pickedList.length > 0) {
      handleAddFiles(pickedList);
    }
    if (event.target) {
      event.target.value = '';
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const dropped = Array.from(e.dataTransfer.files).filter(
        (f) => f.name.endsWith('.csv') || f.type === 'text/csv' || f.type.includes('csv')
      );
      if (dropped.length > 0) {
        handleAddFiles(dropped);
      } else {
        setError('Please drop CSV bank statement files.');
      }
    }
  }

  async function handleRemoveCsv() {
    setFile(null);
    setFilesList([]);
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
    if (!file && filesList.length === 0 && !csvText) {
      setError('Choose a CSV file before reviewing cash activity.');
      return;
    }
    if (filesList.length > 1) {
      await executeAnalysis(filesList, threshold);
    } else {
      const targetFile = filesList[0] || file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' });
      await executeAnalysis(targetFile, threshold);
    }
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

        {!result ? (
          <div className="onboarding-container">
            <section className="panel onboarding-panel" aria-labelledby="upload-title">
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
                    <strong>{threshold || '30'} days</strong>
                    {dynamicAlertDate && (
                      <span> (before <time dateTime={dynamicAlertDate}>{dynamicAlertDate}</time>)</span>
                    )}
                    .
                  </div>
                </div>

                {/* Drag & Drop Zone */}
                <div
                  className={`dropzone ${isDragging ? 'dragging' : ''}`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  style={{ cursor: 'pointer' }}
                  role="button"
                  tabIndex={0}
                  aria-label="Upload CSV statements dropzone"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                >
                  <span className="upload-icon" aria-hidden="true">↑</span>
                  <label className="field-label" htmlFor="csv-file" style={{ cursor: 'pointer', margin: '4px 0' }}>
                    {isDragging ? 'Drop CSV statements here' : 'Drop CSV statements here, or click to browse'}
                  </label>
                  <input
                    ref={fileInputRef}
                    id="csv-file"
                    className="file-input"
                    aria-label="Choose bank statement CSV file"
                    type="file"
                    accept=".csv,text/csv"
                    multiple
                    style={{ display: 'none' }}
                    onChange={handleFileInputChange}
                  />
                  <div className="file-name" style={{ marginTop: 4 }}>
                    Universal format · Multi-file & multi-bank supported · Max 1 MB
                  </div>
                </div>

                {/* Multi-Statement Staging Queue */}
                {filesList.length > 0 && (
                  <div className="statement-queue-container">
                    <div className="statement-queue-header">
                      <div className="statement-queue-title">
                        <span>📚 Queued Statements ({filesList.length})</span>
                        <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--muted)' }}>
                          · {(filesList.reduce((acc, f) => acc + f.size, 0) / 1024).toFixed(1)} KB total
                        </span>
                      </div>
                      <button
                        type="button"
                        className="add-more-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          fileInputRef.current?.click();
                        }}
                      >
                        <span>+ Add Another Statement</span>
                      </button>
                    </div>

                    <div className="statement-queue-items">
                      {filesList.map((f, idx) => (
                        <div key={`${f.name}_${idx}`} className="statement-queue-item">
                          <div className="statement-queue-item-info">
                            <span aria-hidden="true">📄</span>
                            <span className="statement-queue-item-name">{f.name}</span>
                            <span className="statement-queue-item-size">{(f.size / 1024).toFixed(1)} KB</span>
                          </div>
                          <button
                            type="button"
                            className="statement-queue-item-remove"
                            onClick={() => handleRemoveSingleFile(idx)}
                            title={`Remove ${f.name}`}
                          >
                            ✕ Remove
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className="statement-queue-actions">
                      <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                        {filesList.length === 1
                          ? '1 statement queued. You can add more statements from other banks or months to consolidate treasury.'
                          : `${filesList.length} statements queued for consolidated multi-account treasury analysis.`}
                      </span>
                      <button
                        type="button"
                        className="remove-csv-btn"
                        onClick={handleRemoveCsv}
                        style={{ fontSize: 11.5, padding: '4px 10px' }}
                      >
                        Clear All
                      </button>
                    </div>
                  </div>
                )}

                <div style={{ marginTop: 12, fontSize: 11, color: 'var(--muted)', lineHeight: 1.5 }}>
                  Universal Ingestion: Compatible with CSV exports from any financial institution, bank, payment gateway, or accounting system worldwide. Automatically resolves column layouts, date formats, currencies, and multi-account portfolios.
                </div>

                <button className="submit" type="submit" disabled={loading || (filesList.length === 0 && !file && !csvText)} style={{ marginTop: 16 }}>
                  {loading
                    ? 'Analyzing statements…'
                    : filesList.length > 1
                    ? `Analyze ${filesList.length} Consolidated Statements`
                    : 'Analyze cash activity'}
                </button>
              </form>
              {loading && <div className="notice loading" role="status" aria-live="polite">Reading statement and calculating cash metrics…</div>}
              {error && <div className="notice error" role="alert">{error}</div>}
            </section>
          </div>
        ) : (
          <div className="executive-workspace">
            {/* Statement Context Bar */}
            <div className="statement-context-bar" role="region" aria-label="Statement Context">
              <div className="statement-context-left">
                <span className="statement-context-icon" aria-hidden="true">
                  {filesList.length > 1 ? '📚' : '📄'}
                </span>
                <div>
                  <div className="statement-context-filename">
                    {filesList.length > 1
                      ? `${filesList.length} Statements (Consolidated Treasury)`
                      : file
                      ? file.name
                      : 'Active_Statement.csv'}
                  </div>
                  <div className="statement-context-meta">
                    {filesList.length > 1
                      ? `${(filesList.reduce((acc, f) => acc + f.size, 0) / 1024).toFixed(1)} KB`
                      : file
                      ? `${(file.size / 1024).toFixed(1)} KB`
                      : csvText
                      ? `${(csvText.length / 1024).toFixed(1)} KB`
                      : ''}
                    {result.start_date && result.end_date && (
                      <> · <time dateTime={result.start_date}>{result.start_date}</time> to <time dateTime={result.end_date}>{result.end_date}</time></>
                    )}
                  </div>
                </div>

                {result.analysis_mode && (
                  <span
                    className={`mode-badge ${result.analysis_mode === 'HISTORICAL_AUDIT' ? 'audit' : 'live'}`}
                    role="status"
                    title={
                      result.analysis_mode === 'HISTORICAL_AUDIT'
                        ? `Statement closed ${result.statement_age_days} days ago. Metrics evaluate historical liquidity.`
                        : `Statement is current (closed ${result.statement_age_days ?? 0} days ago).`
                    }
                  >
                    <span className="mode-dot" aria-hidden="true" />
                    {result.analysis_mode === 'HISTORICAL_AUDIT'
                      ? `Audit · Closed ${result.statement_age_days}d ago`
                      : 'Live Operating'}
                  </span>
                )}

                <span
                  className={`status ${result.cash_status}`}
                  role="status"
                  aria-label={`Liquidity status: ${CASH_STATUS_LABELS[result.cash_status] || result.cash_status}`}
                >
                  <span className="status-dot" aria-hidden="true" />
                  {CASH_STATUS_LABELS[result.cash_status] || result.cash_status.replaceAll('_', ' ')}
                </span>
              </div>

              <div className="statement-context-actions">
                <div className="threshold-quick-select" title="Runway alert horizon">
                  <span className="threshold-quick-label">Horizon:</span>
                  <div className="threshold-quick-pills">
                    {RUNWAY_HORIZON_PRESETS.map((preset) => {
                      const isSelected = threshold === preset.days;
                      return (
                        <button
                          key={preset.days}
                          type="button"
                          className={`threshold-quick-pill ${isSelected ? 'active' : ''}`}
                          onClick={() => {
                            setThreshold(preset.days);
                            if (filesList.length > 0 || file || csvText) {
                              const target = filesList.length > 0 ? filesList : (file || new File([csvText || ''], 'statement.csv', { type: 'text/csv' }));
                              executeAnalysis(target, preset.days);
                            }
                          }}
                        >
                          {preset.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <input
                  ref={fileInputRef}
                  id="csv-file-active"
                  className="file-input"
                  aria-label="Upload CSV statements"
                  type="file"
                  accept=".csv,text/csv"
                  multiple
                  style={{ display: 'none' }}
                  onChange={handleFileInputChange}
                />
                <button
                  type="button"
                  className="context-action-btn"
                  onClick={() => fileInputRef.current?.click()}
                  title="Add another statement to consolidate treasury"
                >
                  <span style={{ fontWeight: 700, color: 'var(--green)' }}>+</span>
                  <span>Add Statement</span>
                </button>
                <button
                  type="button"
                  className="context-action-btn danger"
                  onClick={handleRemoveCsv}
                  title="Reset workspace"
                >
                  <span aria-hidden="true">✕</span> Reset
                </button>
              </div>
            </div>

            {/* Active Statements Tag Bar if multiple statements */}
            {filesList.length > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--muted)' }}>
                  Consolidated ({filesList.length}):
                </span>
                {filesList.map((f, idx) => (
                  <span
                    key={`${f.name}_${idx}`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '3px 8px',
                      background: 'white',
                      border: '1px solid var(--line)',
                      borderRadius: 6,
                      fontSize: 12,
                      color: 'var(--ink)',
                    }}
                  >
                    <span>📄 {f.name}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveSingleFile(idx)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: 11,
                        color: 'var(--muted)',
                        lineHeight: 1,
                      }}
                      title={`Remove ${f.name} from consolidated analysis`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    background: 'none',
                    border: '1px dashed #97aca0',
                    borderRadius: 6,
                    padding: '3px 8px',
                    fontSize: 11.5,
                    color: 'var(--green)',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  + Add Another
                </button>
              </div>
            )}

            {/* Account & Month Filter Bar */}
            <div className="workspace-filter-bar" role="region" aria-label="Account and Period Filters">
              <div className="filter-controls-left">
                {/* Account Combobox / Switcher */}
                <div className="filter-group">
                  <label className="filter-label" htmlFor="account-selector">
                    <span>🏛️</span> Account:
                  </label>
                  <select
                    id="account-selector"
                    className="filter-select"
                    value={selectedAccount}
                    onChange={(e) => handleSelectAccount(e.target.value)}
                    aria-label="Select treasury account view"
                  >
                    <option value="all">
                      {isSingleAccountPortfolio
                        ? `Consolidated Timeline (All ${result.accounts_breakdown?.length} Statements) — ${money(result.current_balance, result.currency)}`
                        : `All Accounts (Consolidated Treasury) — ${money(result.current_balance, result.currency)}`}
                    </option>
                    {result.accounts_breakdown &&
                      result.accounts_breakdown.map((acc, idx) => (
                        <option key={idx} value={acc.file_name}>
                          {isSingleAccountPortfolio
                            ? `Statement: ${acc.file_name} — ${money(acc.closing_balance, result.currency)}`
                            : `${acc.account_id} (${acc.file_name}) — ${money(acc.closing_balance, result.currency)}`}
                        </option>
                      ))}
                  </select>
                </div>

                {/* Period / Month Selector */}
                {availableMonths.length > 1 && (
                  <div className="filter-group">
                    <label className="filter-label" htmlFor="month-selector">
                      <span>📅</span> Period:
                    </label>
                    <select
                      id="month-selector"
                      className="filter-select"
                      value={selectedMonth}
                      onChange={(e) => setSelectedMonth(e.target.value)}
                      aria-label="Select statement calendar month"
                    >
                      <option value="all">
                        Full Timeline ({result.period_days} Days)
                      </option>
                      {availableMonths.map((m) => (
                        <option key={m.key} value={m.key}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                {result.has_overlaps_deduped && (
                  <span className="filter-badge deduped" title="Overlapping statement dates deduplicated automatically">
                    ✓ Overlaps Auto-Merged
                  </span>
                )}
                {result.calendar_gaps && result.calendar_gaps.length > 0 && (
                  <span className="filter-badge continuity" title="Calendar continuity alert detected">
                    ⚠️ {result.calendar_gaps.length} Statement Gap{result.calendar_gaps.length > 1 ? 's' : ''}
                  </span>
                )}
                <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 500 }}>
                  {selectedAccount === 'all'
                    ? isSingleAccountPortfolio
                      ? `1 Account (${result.accounts_breakdown?.length} Statements Merged)`
                      : `${uniqueAccountClusters.length || filesList.length || 1} Accounts Consolidated`
                    : `Viewing: ${selectedAccount}`}
                </span>
              </div>
            </div>

            {/* Calendar Month Focus Banner if a month is selected */}
            {selectedMonthStats && (
              <div style={{ marginTop: 12, padding: '10px 16px', background: 'white', border: '1px solid var(--line)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                <div style={{ fontSize: 13, color: 'var(--ink)' }}>
                  <strong>Calendar Month Focus:</strong> {availableMonths.find((m) => m.key === selectedMonth)?.label}
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                  <span>Inflows: <strong className="tabular-num" style={{ color: '#15803d' }}>+{money(selectedMonthStats.inflow.toFixed(2), result.currency)}</strong></span>
                  <span>Outflows: <strong className="tabular-num" style={{ color: '#b91c1c' }}>-{money(selectedMonthStats.outflow.toFixed(2), result.currency)}</strong></span>
                  <span>Net Change: <strong className="tabular-num" style={{ color: selectedMonthStats.net >= 0 ? '#15803d' : '#b91c1c' }}>{money(selectedMonthStats.net.toFixed(2), result.currency)}</strong></span>
                </div>
              </div>
            )}

            {/* 3-Card Verdict Strip */}
            <div className="verdict-strip">
              <div className="verdict-card hero-liquidity">
                <div className="verdict-card-head">
                  <span className="verdict-card-label">
                    {selectedAccount === 'all'
                      ? 'Total Treasury Liquidity'
                      : `${displayResult?.accounts_breakdown?.[0]?.account_id || selectedAccount} Balance`}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--green)', fontWeight: 600 }}>
                    {selectedAccount === 'all'
                      ? isSingleAccountPortfolio
                        ? `1 Account (${result.accounts_breakdown?.length} Statements)`
                        : uniqueAccountClusters.length > 1
                        ? `${uniqueAccountClusters.length} Accounts`
                        : 'Primary Treasury'
                      : 'Account View'}
                  </span>
                </div>
                <div className="verdict-card-value">
                  {money(displayResult?.current_balance || result.current_balance, displayResult?.currency || result.currency)}
                </div>
                <div className="verdict-card-sub">
                  {(displayResult || result).end_date
                    ? `Closing ledger balance as of ${(displayResult || result).end_date}`
                    : 'Active operational cash balance'}
                </div>
              </div>

              <div
                className={`verdict-card ${
                  (displayResult || result).cash_status === 'LOW_RUNWAY' || (displayResult || result).cash_status === 'CASH_NONPOSITIVE'
                    ? 'critical'
                    : (displayResult || result).cash_status === 'WATCH'
                    ? 'warning'
                    : 'safe'
                }`}
              >
                <div className="verdict-card-head">
                  <span className="verdict-card-label">
                    {(displayResult || result).analysis_mode === 'HISTORICAL_AUDIT' ? 'Historical Runway' : 'Cash Runway Horizon'}
                  </span>
                  <span
                    className={`status ${(displayResult || result).cash_status}`}
                    style={{ padding: '2px 8px', fontSize: 11 }}
                  >
                    <span className="status-dot" aria-hidden="true" />
                    {CASH_STATUS_LABELS[(displayResult || result).cash_status] || (displayResult || result).cash_status.replaceAll('_', ' ')}
                  </span>
                </div>
                <div className="verdict-card-value">
                  {(displayResult || result).runway_days === null ? 'No Burn' : `${(displayResult || result).runway_days} Days`}
                </div>
                <div className="verdict-card-sub">
                  {(displayResult || result).runway_days === null
                    ? 'Net cash-positive · Inflows exceed burn'
                    : (displayResult || result).projected_depletion_date
                    ? `Projected zero-cash: ${(displayResult || result).projected_depletion_date}`
                    : `Cash depletes within ${(displayResult || result).runway_days} days`}
                </div>
              </div>

              <div className={`verdict-card ${Number((displayResult || result).net_period_change) < 0 ? 'warning' : 'safe'}`}>
                <div className="verdict-card-head">
                  <span className="verdict-card-label">Daily Operational Burn</span>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: Number((displayResult || result).net_period_change) >= 0 ? '#146b55' : '#b45309',
                    }}
                  >
                    {Number((displayResult || result).net_period_change) >= 0 ? 'Net Positive' : 'Net Outflow'}
                  </span>
                </div>
                <div className="verdict-card-value">
                  {money((displayResult || result).average_daily_burn, (displayResult || result).currency)}
                  <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--muted)', marginLeft: 4 }}>
                    / day
                  </span>
                </div>
                <div className="verdict-card-sub">
                  Period change: {money((displayResult || result).net_period_change, (displayResult || result).currency)} over {(displayResult || result).period_days}d
                </div>
              </div>
            </div>

            {/* Segmented Workspace Navigation */}
            <div className="workspace-tabs-bar" role="tablist" aria-label="Executive Workspace Deep-Dives">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'pulse'}
                className={`workspace-tab-btn ${activeTab === 'pulse' ? 'active' : ''}`}
                onClick={() => setActiveTab('pulse')}
              >
                <span>📈</span> Treasury Pulse & Trajectory
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'portfolio'}
                className={`workspace-tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`}
                onClick={() => setActiveTab('portfolio')}
              >
                <span>🏛️</span> {isSingleAccountPortfolio
                  ? `Statement History (${result.accounts_breakdown?.length || 0})`
                  : uniqueAccountClusters.length > 1
                  ? `Portfolio Accounts (${uniqueAccountClusters.length})`
                  : 'Portfolio Account'}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'flows'}
                className={`workspace-tab-btn ${activeTab === 'flows' ? 'active' : ''}`}
                onClick={() => setActiveTab('flows')}
              >
                <span>💸</span> Cash Flow Breakdown
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'working_capital'}
                className={`workspace-tab-btn ${activeTab === 'working_capital' ? 'active' : ''}`}
                onClick={() => setActiveTab('working_capital')}
              >
                <span>⏱️</span> Working Capital & Cycles
              </button>
            </div>

            {/* Tab 1: Treasury Pulse & Trajectory */}
            {activeTab === 'pulse' && (
              <div>
                <div className="chart-wrapper-card">
                  <div className="chart-header-row">
                    <div>
                      <h3 className="chart-title">Treasury Pulse & Forward Runway Projection</h3>
                      <p className="chart-subtitle">
                        Historical daily balance ledger corridor with forward burn depletion trajectory
                      </p>
                    </div>
                    <div className="chart-legend-row">
                      <div className="legend-item">
                        <span className="legend-dot historical" />
                        <span>Historical Ledger</span>
                      </div>
                      {(displayResult || result).runway_days !== null && (
                        <div className="legend-item">
                          <span className="legend-dot forecast" />
                          <span>Forward Depletion Corridor</span>
                        </div>
                      )}
                      {dynamicAlertDate && (
                        <div className="legend-item">
                          <span className="legend-dot alert" />
                          <span>Alert Horizon ({threshold}d)</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ width: '100%', height: 320, marginTop: 16 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={displayedChartData} margin={{ top: 12, right: 16, left: 0, bottom: 4 }}>
                        <defs>
                          <linearGradient id="historicalGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#146b55" stopOpacity={0.25} />
                            <stop offset="95%" stopColor="#146b55" stopOpacity={0.0} />
                          </linearGradient>
                          <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#d97706" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#d97706" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e8ede9" vertical={false} />
                        <XAxis
                          dataKey="displayDate"
                          stroke="#718779"
                          fontSize={11}
                          tickLine={false}
                          axisLine={{ stroke: '#dce3de' }}
                        />
                        <YAxis
                          stroke="#718779"
                          fontSize={11}
                          tickLine={false}
                          axisLine={{ stroke: '#dce3de' }}
                          tickFormatter={(val: number) =>
                            `$${Math.abs(val) >= 1000 ? (val / 1000).toFixed(0) + 'k' : val}`
                          }
                        />
                        <Tooltip content={<CustomChartTooltip currency={(displayResult || result).currency} />} />
                        <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
                        <Area
                          type="monotone"
                          dataKey="balance"
                          stroke="#146b55"
                          strokeWidth={2.5}
                          fillOpacity={1}
                          fill="url(#historicalGradient)"
                          name="Historical Balance"
                        />
                        <Area
                          type="monotone"
                          dataKey="projection"
                          stroke="#d97706"
                          strokeWidth={2}
                          strokeDasharray="4 4"
                          fillOpacity={1}
                          fill="url(#forecastGradient)"
                          name="Projected Balance"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Solvency Diagnostic Callout */}
                <div className="solvency-diagnostic-card">
                  <span className="solvency-icon" aria-hidden="true">
                    {(displayResult || result).cash_status === 'NO_BURN'
                      ? '🛡️'
                      : (displayResult || result).cash_status === 'WATCH'
                      ? 'ℹ️'
                      : '⚠️'}
                  </span>
                  <div>
                    <h4 className="solvency-title">
                      {(displayResult || result).cash_status === 'NO_BURN'
                        ? 'Institutional Solvency Assessment: Sustainable Inflow Positive'
                        : (displayResult || result).cash_status === 'WATCH'
                        ? `Treasury Caution: Runway Within ${threshold}-Day Horizon`
                        : 'Critical Liquidity Alert: Action Required'}
                    </h4>
                    <p className="solvency-text">
                      {(displayResult || result).runway_days === null
                        ? `Operating cash flows demonstrate net positive growth. Over the ${(displayResult || result).period_days}-day period reviewed, inflows have comfortably funded disbursements with no net operational burn.`
                        : (displayResult || result).cash_status === 'WATCH'
                        ? `At the current burn rate of ${money((displayResult || result).average_daily_burn, (displayResult || result).currency)} per day, treasury reserves will last approximately ${(displayResult || result).runway_days} days. Review outstanding customer invoices or stage a contingency credit facility to avoid liquidity compression.`
                        : `Daily operational burn of ${money((displayResult || result).average_daily_burn, (displayResult || result).currency)}/day is projected to deplete cash reserves by ${(displayResult || result).projected_depletion_date || 'the near term'}. Immediate action recommended: factor outstanding receivables, draw an approved credit line, or defer discretionary expenses.`}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: Portfolio Accounts */}
            {activeTab === 'portfolio' && (
              <div className="tab-content-panel">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>
                      {isSingleAccountPortfolio
                        ? `Single Account Statement Continuity (${result.accounts_breakdown?.length || 0} Periods)`
                        : uniqueAccountClusters.length > 1
                        ? `Portfolio Accounts Breakdown (${uniqueAccountClusters.length} Accounts)`
                        : 'Portfolio Accounts Breakdown'}
                    </h3>
                    <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--muted)' }}>
                      {isSingleAccountPortfolio
                        ? 'All statements belong to the same bank account and have been merged into a continuous timeline.'
                        : 'Individual balances and multi-account sweep reconciliation'}
                    </p>
                  </div>
                  {result.has_overlaps_deduped && (
                    <span style={{ fontSize: 11, padding: '3px 9px', borderRadius: 6, background: 'rgba(34, 197, 94, 0.12)', color: '#15803d', border: '1px solid rgba(34, 197, 94, 0.25)', fontWeight: 600 }}>
                      ✓ Overlaps Deduplicated
                    </span>
                  )}
                </div>

                {result.accounts_breakdown && result.accounts_breakdown.length > 0 ? (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
                    {result.accounts_breakdown.map((acc, idx) => (
                      <div key={idx} style={{ padding: '14px 16px', background: '#fbfdfc', borderRadius: 10, border: '1px solid var(--line)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--ink)' }}>
                            {isSingleAccountPortfolio ? `Statement Period ${idx + 1}` : acc.account_id}
                          </span>
                          <span className="tabular-num" style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>
                            {money(acc.closing_balance, result.currency)}
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={acc.file_name}>
                          {acc.file_name}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8, borderTop: '1px solid #eef2ef', paddingTop: 6 }}>
                          {acc.start_date} → {acc.end_date} · <strong className="tabular-num">{acc.transaction_count}</strong> transactions
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ padding: '16px 20px', background: '#fbfdfc', borderRadius: 10, border: '1px solid var(--line)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>Primary Operating Account</div>
                        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{file?.name || 'Active Statement'}</div>
                      </div>
                      <div className="tabular-num" style={{ fontWeight: 700, fontSize: 18, color: 'var(--ink)' }}>
                        {money(result.current_balance, result.currency)}
                      </div>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 10, borderTop: '1px solid #eef2ef', paddingTop: 8 }}>
                      {result.start_date} → {result.end_date} · <strong className="tabular-num">{result.accepted_count}</strong> transactions accepted
                    </div>
                  </div>
                )}

                {result.internal_transfers_excluded && (
                  <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: 8, background: 'rgba(59, 130, 246, 0.07)', border: '1px solid rgba(59, 130, 246, 0.22)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <span style={{ fontSize: 18, marginTop: 1 }}>🔄</span>
                    <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>
                      <strong style={{ color: '#1d4ed8' }}>Contra-Transfers Eliminated:</strong>{' '}
                      <span className="tabular-num" style={{ fontWeight: 700 }}>
                        {money(result.internal_transfers_excluded, result.currency)}
                      </span>{' '}
                      in internal bank sweeps/transfers were identified across accounts and excluded to prevent double-counting of revenue and burn.
                      {result.operational_inflows && (
                        <div style={{ color: 'var(--muted)', fontSize: 11.5, marginTop: 4 }}>
                          Operational Inflows: <span className="tabular-num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{money(result.operational_inflows, result.currency)}</span> · Operational Outflows: <span className="tabular-num" style={{ fontWeight: 600, color: 'var(--ink)' }}>{money(result.operational_outflows || '0.00', result.currency)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {result.calendar_gaps && result.calendar_gaps.length > 0 && (
                  <div style={{ marginTop: 14, padding: '12px 16px', borderRadius: 8, background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.25)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                    <span style={{ fontSize: 18 }}>⚠️</span>
                    <div style={{ fontSize: 12.5, lineHeight: 1.5, color: '#b45309' }}>
                      <strong>Statement Continuity Notice:</strong>
                      <ul style={{ margin: '4px 0 0 0', paddingLeft: 18 }}>
                        {result.calendar_gaps.map((gap, gIdx) => (
                          <li key={gIdx}>{gap}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: Cash Flow Breakdown */}
            {activeTab === 'flows' && (
              <div className="tab-content-panel">
                <div style={{ marginBottom: 16 }}>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--ink)' }}>
                    Cash Flow Breakdown & Operational Decomposition
                  </h3>
                  <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--muted)' }}>
                    Gross flow volume reconciled with operational inflows and expenses
                  </p>
                </div>

                <div className="metrics" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                  <Metric
                    label="Gross Period Inflows"
                    value={money((displayResult || result).gross_inflows || (displayResult || result).net_period_change, (displayResult || result).currency)}
                    sub="Total customer deposits & credits"
                  />
                  <Metric
                    label="Gross Period Outflows"
                    value={money((displayResult || result).gross_outflows || (displayResult || result).average_daily_burn, (displayResult || result).currency)}
                    sub="Total debits & operational disbursements"
                  />
                  <Metric
                    label="Net Period Change"
                    value={money((displayResult || result).net_period_change, (displayResult || result).currency)}
                    sub={Number((displayResult || result).net_period_change) >= 0 ? 'Net cash expansion' : 'Net cash contraction'}
                  />
                  <Metric
                    label="Average Daily Burn"
                    value={money((displayResult || result).average_daily_burn, (displayResult || result).currency)}
                    sub={(displayResult || result).runway_days === null ? 'Zero net burn rate' : 'Daily outflow velocity'}
                  />
                  <Metric
                    label="Period Reviewed"
                    value={`${(displayResult || result).period_days} Days`}
                    sub={`${(displayResult || result).start_date || 'Start'} → ${(displayResult || result).end_date || 'End'}`}
                  />
                  <Metric
                    label="Transactions Ingested"
                    value={`${(displayResult || result).accepted_count} Rows`}
                    sub="Deduplicated & validated"
                  />
                </div>

                {selectedMonthStats && (
                  <div style={{ marginTop: 20, padding: '16px 20px', borderRadius: 10, background: '#f8faf9', border: '1px solid #dce5df' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>
                        📅 Calendar Month Reconciliation: {availableMonths.find((m) => m.key === selectedMonth)?.label || selectedMonth}
                      </div>
                      <span className="filter-badge" style={{ background: '#eef2ef', color: '#146b55', fontWeight: 600 }}>
                        Filtered Timeline
                      </span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                      <div style={{ padding: '10px 14px', background: '#ffffff', borderRadius: 8, border: '1px solid #eef2ef' }}>
                        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 600 }}>Month Inflows</div>
                        <div className="tabular-num" style={{ fontSize: 16, fontWeight: 700, color: '#16a34a', marginTop: 4 }}>
                          {money(selectedMonthStats.inflow.toFixed(2), (displayResult || result).currency)}
                        </div>
                      </div>
                      <div style={{ padding: '10px 14px', background: '#ffffff', borderRadius: 8, border: '1px solid #eef2ef' }}>
                        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 600 }}>Month Outflows</div>
                        <div className="tabular-num" style={{ fontSize: 16, fontWeight: 700, color: '#dc2626', marginTop: 4 }}>
                          {money(selectedMonthStats.outflow.toFixed(2), (displayResult || result).currency)}
                        </div>
                      </div>
                      <div style={{ padding: '10px 14px', background: '#ffffff', borderRadius: 8, border: '1px solid #eef2ef' }}>
                        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 600 }}>Net Month Delta</div>
                        <div className="tabular-num" style={{ fontSize: 16, fontWeight: 700, color: selectedMonthStats.net >= 0 ? '#16a34a' : '#dc2626', marginTop: 4 }}>
                          {money(selectedMonthStats.net.toFixed(2), (displayResult || result).currency)}
                        </div>
                      </div>
                      <div style={{ padding: '10px 14px', background: '#ffffff', borderRadius: 8, border: '1px solid #eef2ef' }}>
                        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 600 }}>Period Balance Shift</div>
                        <div className="tabular-num" style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginTop: 4 }}>
                          {money(selectedMonthStats.startBal.toFixed(2), (displayResult || result).currency)} → {money(selectedMonthStats.endBal.toFixed(2), (displayResult || result).currency)}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {(displayResult || result).rejected_rows.length > 0 && (
                  <div className="rejections" style={{ marginTop: 20 }}>
                    <h3>Excluded Rows ({(displayResult || result).rejected_rows.length})</h3>
                    <ul>
                      {(displayResult || result).rejected_rows.map((row) => (
                        <li key={`${row.row_number}-${row.reason_code}`}>
                          Row {row.row_number}: {row.reason_code.replaceAll('_', ' ').toLowerCase()}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Tab 4: Working Capital & Cycles */}
            {activeTab === 'working_capital' && (
              <div className="tab-content-panel">
                <div className="wc-hero-card">
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>
                        Working Capital & Cash Conversion Cycle
                      </h3>
                      {result.working_capital_status && (
                        <span className={`wc-badge ${result.working_capital_status}`}>
                          {result.working_capital_status.replaceAll('_', ' ')}
                        </span>
                      )}
                    </div>
                    <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: 640, lineHeight: 1.5 }}>
                      {result.working_capital_rationale ||
                        'Evaluates the operational velocity at which capital invested in operations is recovered back as liquid treasury cash.'}
                    </p>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '0.05em' }}>
                      Cash Conversion Cycle
                    </div>
                    <div className="tabular-num" style={{ fontSize: 32, fontWeight: 700, color: 'var(--ink)', margin: '4px 0' }}>
                      {result.cash_conversion_cycle_days !== undefined && result.cash_conversion_cycle_days !== null
                        ? `${result.cash_conversion_cycle_days}d`
                        : 'Healthy'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                      {result.cash_conversion_cycle_days !== undefined && result.cash_conversion_cycle_days !== null && result.cash_conversion_cycle_days <= 30
                        ? 'Rapid Cash Recovery'
                        : 'Operating Cycle Benchmark'}
                    </div>
                  </div>
                </div>

                <div className="wc-grid">
                  <div className="wc-pillar-card">
                    <div className="wc-pillar-name">Days Sales Outstanding (DSO)</div>
                    <div className="tabular-num" style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>
                      Receivables Window
                    </div>
                    <div className="wc-pillar-desc">
                      Average time required to collect receivables from client invoices into cash deposits. Lower DSO accelerates runway.
                    </div>
                  </div>

                  <div className="wc-pillar-card">
                    <div className="wc-pillar-name">Days Inventory Outstanding (DIO)</div>
                    <div className="tabular-num" style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>
                      Holding Period
                    </div>
                    <div className="wc-pillar-desc">
                      Time working capital remains tied up in work-in-progress or inventory before generating cash revenue.
                    </div>
                  </div>

                  <div className="wc-pillar-card">
                    <div className="wc-pillar-name">Days Payable Outstanding (DPO)</div>
                    <div className="tabular-num" style={{ fontSize: 22, fontWeight: 700, color: 'var(--ink)' }}>
                      Payables Window
                    </div>
                    <div className="wc-pillar-desc">
                      Average duration before trade vendors and suppliers must be settled. Longer DPO preserves liquidity in treasury.
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: 20, padding: '12px 16px', background: '#f7faf8', borderRadius: 8, border: '1px solid var(--line)', fontSize: 12, color: 'var(--muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <span>
                    📐 <strong>Institutional Formula:</strong> Cash Conversion Cycle (CCC) = DSO + DIO − DPO
                  </span>
                  <span style={{ fontStyle: 'italic' }}>
                    Negative or low CCC indicates self-funding operations.
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
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

function computeAlertBoundaryDate(endDateStr: string | null | undefined, thresholdDaysStr: string): string | null {
  if (!endDateStr) return null;
  const days = parseInt(thresholdDaysStr, 10);
  if (isNaN(days) || days <= 0) return null;
  try {
    const [year, month, day] = endDateStr.split('-').map(Number);
    if (!year || !month || !day) return null;
    const dt = new Date(Date.UTC(year, month - 1, day));
    dt.setUTCDate(dt.getUTCDate() + days);
    return dt.toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {sub && <span className="metric-sub">{sub}</span>}
    </div>
  );
}
