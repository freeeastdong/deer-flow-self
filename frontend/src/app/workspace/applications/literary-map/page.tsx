"use client";

import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";

export default function LiteraryMapPage() {
  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="p-0 flex flex-col">
        <iframe
          src="/applications/world-literary-map/index.html"
          className="size-full border-0 flex-1"
          title="世界文学地图"
          allow="fullscreen"
        />
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
