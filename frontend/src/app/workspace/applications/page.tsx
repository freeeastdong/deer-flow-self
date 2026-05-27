"use client";

import Link from "next/link";
import { MapPinned, Music, TrendingUp } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";

export default function ApplicationsPage() {
  const { t } = useI18n();

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="items-start">
        <div className="flex size-full flex-col p-6">
          <h1 className="text-2xl font-semibold tracking-tight mb-2">
            {t.sidebar.applications}
          </h1>
          <p className="text-muted-foreground mb-8">
            探索 DeerFlow 提供的各种交互式应用。
          </p>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <Link href="/workspace/applications/literary-map" className="group">
              <Card className="h-full transition-all hover:shadow-md hover:border-primary/30">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <MapPinned className="size-5" />
                    </div>
                    <CardTitle className="text-base">世界文学地图</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">
                    在 3D 地球上探索世界各地的文学之城，了解著名作家与他们的不朽之作。
                  </CardDescription>
                </CardContent>
              </Card>
            </Link>
            <Link href="/workspace/applications/hedge-fund" className="group">
              <Card className="h-full transition-all hover:shadow-md hover:border-primary/30">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <TrendingUp className="size-5" />
                    </div>
                    <CardTitle className="text-base">AI 对冲基金</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">
                    19 位 AI 投资 Agent 协作分析股票，模拟传奇投资者的投资决策过程。
                  </CardDescription>
                </CardContent>
              </Card>
            </Link>
            <Link href="/workspace/applications/music-station" className="group">
              <Card className="h-full transition-all hover:shadow-md hover:border-primary/30">
                <CardHeader>
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Music className="size-5" />
                    </div>
                    <CardTitle className="text-base">音乐电台</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">
                    AI 语音助手驱动的沉浸式音乐电台，3D 宇宙粒子背景、智能歌曲推荐与语音交互。
                  </CardDescription>
                </CardContent>
              </Card>
            </Link>

          </div>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
