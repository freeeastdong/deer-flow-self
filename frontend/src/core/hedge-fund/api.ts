import { getBackendBaseURL } from "@/core/config";

export interface AnalyzeRequest {
  tickers: string[];
  start_date?: string;
  end_date?: string;
  selected_analysts?: string[];
  show_reasoning?: boolean;
  model_name?: string;
  model_provider?: string;
  initial_cash?: number;
  margin_requirement?: number;
}

export interface BacktestRequest {
  tickers: string[];
  start_date?: string;
  end_date?: string;
  selected_analysts?: string[];
  model_name?: string;
  model_provider?: string;
  initial_cash?: number;
  margin_requirement?: number;
}

export interface TaskResponse {
  task_id: string;
  status: string;
  message: string;
}

export interface TaskResult {
  task_id: string;
  status: string;
  result?: Record<string, unknown>;
  error?: string | null;
}

export async function startAnalyze(request: AnalyzeRequest): Promise<TaskResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/hedge-fund/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${response.status}`);
  }
  return response.json();
}

export async function startBacktest(request: BacktestRequest): Promise<TaskResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/hedge-fund/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${response.status}`);
  }
  return response.json();
}

export async function getTaskResult(taskId: string): Promise<TaskResult> {
  const response = await fetch(`${getBackendBaseURL()}/api/hedge-fund/tasks/${taskId}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${response.status}`);
  }
  return response.json();
}
