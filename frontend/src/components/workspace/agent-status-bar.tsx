"use client";

import {
  BotIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  MessageSquareIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { useAgents } from "@/core/agents";
import { useI18n } from "@/core/i18n/hooks";
import type { AgentThread } from "@/core/threads/types";
import { useThreads } from "@/core/threads/hooks";
import { pathOfThread, titleOfThread } from "@/core/threads/utils";
import { formatTimeAgo } from "@/core/utils/datetime";
import { cn } from "@/lib/utils";

interface AgentStatusBarProps {
  currentAgentName?: string;
}

function getAgentNameFromThread(thread: AgentThread): string | undefined {
  return (
    thread.context?.agent_name ??
    (typeof thread.metadata?.agent_name === "string"
      ? thread.metadata.agent_name
      : undefined)
  );
}

export function AgentStatusBar({ currentAgentName }: AgentStatusBarProps) {
  const { t } = useI18n();
  const router = useRouter();
  const { agents, isLoading } = useAgents();
  const { data: threads = [] } = useThreads({ limit: 200 });
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  const agentThreadsMap = useMemo(() => {
    const map = new Map<string, AgentThread[]>();
    for (const thread of threads) {
      const name = getAgentNameFromThread(thread);
      if (!name) continue;
      if (!map.has(name)) map.set(name, []);
      map.get(name)!.push(thread);
    }
    for (const [name, list] of map) {
      map.set(name, list.slice(0, 5));
    }
    return map;
  }, [threads]);

  const handleAgentClick = (agentName: string) => {
    router.push(
      `/workspace/agents/${encodeURIComponent(agentName)}/chats/new`,
    );
  };

  const handleDefaultAgentClick = () => {
    router.push("/workspace/chats/new");
  };

  const handleToggleThreads = (agentName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedAgent((prev) => (prev === agentName ? null : agentName));
  };

  const handleThreadClick = (thread: AgentThread, e: React.MouseEvent) => {
    e.stopPropagation();
    router.push(pathOfThread(thread));
  };

  return (
    <div className="group relative">
      {/* Trigger bar */}
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1.5 rounded-md border px-2 py-1 transition-colors",
          "bg-background/50 hover:bg-background/80",
        )}
      >
        <BotIcon className="text-primary h-3.5 w-3.5 shrink-0" />
        <span className="max-w-[120px] truncate text-xs font-medium">
          {currentAgentName ?? t.sidebar.agents}
        </span>
        <ChevronDownIcon className="h-3 w-3 shrink-0 transition-transform duration-200 group-hover:rotate-180" />
      </div>

      {/* Dropdown panel */}
      <div
        className={cn(
          "absolute top-full left-0 z-50 mt-1 overflow-hidden rounded-lg border shadow-lg",
          "bg-background/95 backdrop-blur-md",
          "max-h-0 opacity-0 transition-all duration-200 ease-out",
          "group-hover:max-h-[min(480px,80vh)] group-hover:opacity-100 group-hover:overflow-y-auto",
        )}
      >
        <div className="min-w-64 max-w-lg p-2">
          {/* Default Agent */}
          <button
            onClick={handleDefaultAgentClick}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
              !currentAgentName && "bg-accent/50 text-accent-foreground",
            )}
          >
            <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
              <MessageSquareIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">
                {t.agents.defaultAgent}
              </div>
            </div>
          </button>

          <div className="bg-border my-1 h-px" />

          {isLoading ? (
            <div className="text-muted-foreground py-4 text-center text-xs">
              {t.common.loading}
            </div>
          ) : agents.length === 0 ? (
            <div className="text-muted-foreground py-4 text-center text-xs">
              {t.agents.emptyTitle}
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {agents.map((agent) => {
                const isActive = agent.name === currentAgentName;
                const isExpanded = expandedAgent === agent.name;
                const recentThreads = agentThreadsMap.get(agent.name) ?? [];

                return (
                  <div key={agent.name} className="flex flex-col">
                    <div className="flex items-center">
                      <button
                        onClick={() => handleAgentClick(agent.name)}
                        className={cn(
                          "flex flex-1 items-center gap-2 px-2 py-2 text-left transition-colors",
                          recentThreads.length > 0 ? "rounded-l-md" : "rounded-md",
                          "hover:bg-accent hover:text-accent-foreground",
                          isActive && "bg-accent/50 text-accent-foreground",
                        )}
                      >
                        <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
                          <BotIcon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">
                            {agent.name}
                          </div>
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            {[
                              ...(agent.skills ?? []),
                              ...(agent.tool_groups ?? []),
                            ]
                              .slice(0, 3)
                              .map((tag) => (
                                <Badge
                                  key={tag}
                                  variant="secondary"
                                  className="text-[10px] px-1 py-0"
                                >
                                  {tag}
                                </Badge>
                              ))}
                          </div>
                        </div>
                      </button>
                      {recentThreads.length > 0 && (
                        <button
                          onClick={(e) =>
                            handleToggleThreads(agent.name, e)
                          }
                          className={cn(
                            "flex h-8 w-8 shrink-0 items-center justify-center rounded-r-md transition-colors",
                            "hover:bg-accent hover:text-accent-foreground",
                            isActive && "text-accent-foreground",
                          )}
                        >
                          <ChevronRightIcon
                            className={cn(
                              "h-4 w-4 transition-transform duration-200",
                              isExpanded && "rotate-90",
                            )}
                          />
                        </button>
                      )}
                    </div>

                    {isExpanded && (
                      <div className="border-border ml-10 mt-1 flex flex-col gap-1 border-l-2 pl-2">
                        {recentThreads.map((thread) => (
                          <button
                            key={thread.thread_id}
                            onClick={(e) =>
                              handleThreadClick(thread, e)
                            }
                            className={cn(
                              "flex flex-col rounded-md px-2 py-1.5 text-left transition-colors",
                              "hover:bg-accent hover:text-accent-foreground",
                            )}
                          >
                            <div className="truncate text-xs font-medium">
                              {titleOfThread(thread)}
                            </div>
                            {thread.updated_at && (
                              <div className="text-muted-foreground text-[10px]">
                                {formatTimeAgo(thread.updated_at)}
                              </div>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
