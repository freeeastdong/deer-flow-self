"use client";

import { useEffect } from "react";

import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";

export default function MusicStationPage() {
  const { t } = useI18n();

  useEffect(() => {
    document.title = `${t.pages.musicStation} - ${t.pages.appName}`;
  }, [t]);

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="p-0 flex flex-col">
        <iframe
          src="/applications/music-station/index.html"
          className="w-full flex-1 border-0 min-h-0"
          title="音乐电台"
          allow="fullscreen"
        />
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
