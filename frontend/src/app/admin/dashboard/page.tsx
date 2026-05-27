"use client";

import { Activity, ArrowLeft, MessageSquare, Play, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetch } from "@/core/api/fetcher";
import { useAuth } from "@/core/auth/AuthProvider";

interface DailyStat {
  date: string;
  count: number;
}

interface StatsData {
  totalUsers: number;
  totalAdmins: number;
  todayNewUsers: number;
  totalThreads: number;
  totalRuns: number;
  dailyNewUsers: DailyStat[];
}

function StatCard({ title, value, icon }: { title: string; value: number; icon: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { user, isLoading: isPending } = useAuth();
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!isPending) {
      if (!user) router.push("/login");
      else if (user.system_role !== "admin") router.push("/workspace");
    }
  }, [isPending, user, router]);

  useEffect(() => {
    if (!user || user.system_role !== "admin") return;
    setIsLoading(true);
    fetch("/api/admin/stats")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("加载失败"))))
      .then((data: StatsData) => setStats(data))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [user]);

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="w-full max-w-5xl">
          <CardContent className="py-8 text-center text-muted-foreground">加载中...</CardContent>
        </Card>
      </div>
    );
  }
  if (!user || user.system_role !== "admin") return null;

  const maxDaily = Math.max(1, ...(stats?.dailyNewUsers.map((d) => d.count) ?? [1]));

  return (
    <div className="flex min-h-screen items-start justify-center bg-background px-4 py-8">
      <div className="w-full max-w-5xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Dashboard 概览</h1>
          <Button variant="ghost" size="sm" onClick={() => router.push("/workspace")}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </div>

        {isLoading || !stats ? (
          <div className="py-12 text-center text-muted-foreground">加载统计数据...</div>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard title="总用户数" value={stats.totalUsers} icon={<Users className="h-4 w-4 text-muted-foreground" />} />
              <StatCard title="今日新增" value={stats.todayNewUsers} icon={<Activity className="h-4 w-4 text-muted-foreground" />} />
              <StatCard title="总线程数" value={stats.totalThreads} icon={<MessageSquare className="h-4 w-4 text-muted-foreground" />} />
              <StatCard title="总运行次数" value={stats.totalRuns} icon={<Play className="h-4 w-4 text-muted-foreground" />} />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">近 30 天用户注册趋势</CardTitle>
              </CardHeader>
              <CardContent>
                {stats.dailyNewUsers.length === 0 ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">暂无数据</div>
                ) : (
                  <div className="flex h-48 items-end gap-1">
                    {stats.dailyNewUsers.map((d) => (
                      <div key={d.date} className="group relative flex flex-1 flex-col items-center justify-end">
                        <div
                          className="w-full rounded-t bg-primary/80 transition-all hover:bg-primary"
                          style={{ height: `${(d.count / maxDaily) * 100}%`, minHeight: 4 }}
                        />
                        <span className="mt-1 text-[10px] text-muted-foreground">{d.date.slice(5)}</span>
                        <div className="pointer-events-none absolute -top-8 rounded bg-black px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                          {d.count}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
