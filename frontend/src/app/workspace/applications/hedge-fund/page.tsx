"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TrendingUp, Loader2, Play, RotateCcw, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";
import {
  startAnalyze,
  startBacktest,
  getTaskResult,
} from "@/core/hedge-fund/api";

const POLL_INTERVAL = 3000;

export default function HedgeFundPage() {
  const { t } = useI18n();
  const [tickers, setTickers] = useState("AAPL,MSFT,NVDA");

  useEffect(() => {
    document.title = `${t.pages.hedgeFund} - ${t.pages.appName}`;
  }, [t]);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>("");
  const [taskResult, setTaskResult] = useState<Record<string, unknown> | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => clearPoll();
  }, [clearPoll]);

  const pollTask = useCallback(
    async (id: string) => {
      try {
        const data = await getTaskResult(id);
        setTaskStatus(data.status);
        if (data.status === "completed") {
          setTaskResult(data.result ?? null);
          clearPoll();
          setLoading(false);
        } else if (data.status === "failed") {
          setTaskError(data.error ?? "Task failed");
          clearPoll();
          setLoading(false);
        }
      } catch (e) {
        setTaskError(e instanceof Error ? e.message : "Polling error");
        clearPoll();
        setLoading(false);
      }
    },
    [clearPoll],
  );

  const handleSubmit = async (action: "analyze" | "backtest") => {
    clearPoll();
    setLoading(true);
    setTaskId(null);
    setTaskStatus("queued");
    setTaskResult(null);
    setTaskError(null);

    const tickerList = tickers
      .split(",")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);

    if (tickerList.length === 0) {
      setTaskError("Please enter at least one ticker");
      setLoading(false);
      return;
    }

    try {
      const request = { tickers: tickerList };
      const res =
        action === "analyze"
          ? await startAnalyze(request)
          : await startBacktest(request);

      setTaskId(res.task_id);
      pollRef.current = setInterval(() => pollTask(res.task_id), POLL_INTERVAL);
    } catch (e) {
      setTaskError(e instanceof Error ? e.message : "Failed to start task");
      setLoading(false);
    }
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="items-start">
        <div className="flex size-full flex-col p-6 max-w-5xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <TrendingUp className="size-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">AI 对冲基金</h1>
              <p className="text-sm text-muted-foreground">
                基于多 Agent 协作的投资决策分析系统（仅供教育和研究）
              </p>
            </div>
          </div>

          <Alert variant="destructive" className="mb-6 mt-2">
            <AlertTriangle className="size-4" />
            <AlertDescription>
              本功能仅供教育和研究用途，不构成任何投资建议。使用前应确保已配置
              FINANCIAL_DATASETS_API_KEY 和 LLM API Key。
            </AlertDescription>
          </Alert>

          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base">参数设置</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">股票代码</label>
                <Input
                  placeholder="例如: AAPL, MSFT, NVDA"
                  value={tickers}
                  onChange={(e) => setTickers(e.target.value)}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  多个代码用英文逗号分隔
                </p>
              </div>

              <Tabs defaultValue="analyze" className="w-full">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="analyze">分析</TabsTrigger>
                  <TabsTrigger value="backtest">回测</TabsTrigger>
                </TabsList>
                <TabsContent value="analyze" className="pt-4">
                  <Button
                    onClick={() => handleSubmit("analyze")}
                    disabled={loading}
                    className="w-full"
                  >
                    {loading ? (
                      <Loader2 className="size-4 mr-2 animate-spin" />
                    ) : (
                      <Play className="size-4 mr-2" />
                    )}
                    开始分析
                  </Button>
                </TabsContent>
                <TabsContent value="backtest" className="pt-4">
                  <Button
                    onClick={() => handleSubmit("backtest")}
                    disabled={loading}
                    className="w-full"
                  >
                    {loading ? (
                      <Loader2 className="size-4 mr-2 animate-spin" />
                    ) : (
                      <Play className="size-4 mr-2" />
                    )}
                    开始回测
                  </Button>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          {loading && (
            <Card className="mb-6 border-primary/30">
              <CardContent className="py-8">
                <div className="flex flex-col items-center justify-center gap-3">
                  <Loader2 className="size-8 animate-spin text-primary" />
                  <div className="text-center">
                    <p className="font-medium">任务运行中...</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Task ID: {taskId}
                    </p>
                    <Badge variant="secondary" className="mt-2">
                      {taskStatus}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {taskError && !loading && (
            <Alert variant="destructive" className="mb-6">
              <AlertDescription className="flex items-center justify-between">
                <span>{taskError}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setTaskError(null);
                    setTaskResult(null);
                  }}
                >
                  <RotateCcw className="size-4 mr-1" />
                  重试
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {taskResult && !loading && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">分析结果</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setTaskResult(null);
                    setTaskError(null);
                  }}
                >
                  <RotateCcw className="size-4 mr-1" />
                  新的分析
                </Button>
              </CardHeader>
              <CardContent>
                <ResultView data={taskResult} />
              </CardContent>
            </Card>
          )}
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}

function ResultView({ data }: { data: Record<string, unknown> }) {
  const decisions = data.decisions as Record<string, unknown> | null;
  const signals = data.analyst_signals as Record<string, unknown> | undefined;

  return (
    <div className="space-y-6">
      {decisions && (
        <div>
          <h3 className="text-sm font-semibold mb-3">最终决策</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(decisions).map(([ticker, decision]) => {
              const d = decision as Record<string, unknown>;
              const action = (d.action as string) ?? "hold";
              return (
                <Card key={ticker} className="border-l-4 border-l-primary">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-lg">{ticker}</span>
                      <Badge
                        variant={
                          action === "buy"
                            ? "default"
                            : action === "sell"
                              ? "destructive"
                              : "secondary"
                        }
                      >
                        {action.toUpperCase()}
                      </Badge>
                    </div>
                    {d.quantity != null && (
                      <p className="text-sm text-muted-foreground">
                        数量: {String(d.quantity)}
                      </p>
                    )}
                    {d.confidence != null && (
                      <p className="text-sm text-muted-foreground">
                        置信度: {String(d.confidence)}
                      </p>
                    )}
                    {d.reasoning != null && (
                      <p className="text-sm mt-2 line-clamp-4">
                        {String(d.reasoning)}
                      </p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      <Separator />

      {signals && (
        <div>
          <h3 className="text-sm font-semibold mb-3">分析师信号</h3>
          <div className="space-y-3">
            {Object.entries(signals).map(([agent, signal]) => {
              const s = signal as Record<string, unknown>;
              return (
                <div
                  key={agent}
                  className="flex items-start justify-between rounded-lg border p-3"
                >
                  <div>
                    <p className="font-medium text-sm">{agent}</p>
                    {s.signal != null && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        信号: {String(s.signal)}
                      </p>
                    )}
                  </div>
                  {s.signal != null && (
                    <Badge
                      variant={
                        String(s.signal) === "bullish"
                          ? "default"
                          : String(s.signal) === "bearish"
                            ? "destructive"
                            : "secondary"
                      }
                      className="text-xs"
                    >
                      {String(s.signal)}
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!decisions && !signals && (
        <pre className="text-xs bg-muted p-4 rounded-lg overflow-auto max-h-[60vh]">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
