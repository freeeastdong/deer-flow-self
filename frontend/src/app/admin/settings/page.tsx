"use client";

import { ArrowLeft, Copy, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetch } from "@/core/api/fetcher";
import { useAuth } from "@/core/auth/AuthProvider";

interface InviteCode {
  code: string;
  createdBy: string;
  createdAt: string;
  maxUses: number;
  usedCount: number;
  isActive: boolean;
}

export default function AdminSettingsPage() {
  const router = useRouter();
  const { user, isLoading: isPending } = useAuth();

  const [allowPublic, setAllowPublic] = useState(true);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [codesLoading, setCodesLoading] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [maxUses, setMaxUses] = useState(1);
  const [newCode, setNewCode] = useState("");

  const [error, setError] = useState("");

  useEffect(() => {
    if (!isPending) {
      if (!user) router.push("/login");
      else if (user.system_role !== "admin") router.push("/workspace");
    }
  }, [isPending, user, router]);

  const loadSettings = async () => {
    try {
      const res = await fetch("/api/admin/settings");
      if (!res.ok) throw new Error("加载失败");
      const data = await res.json();
      setAllowPublic(data.allowPublicRegistration);
    } catch {
      setError("加载设置失败");
    }
  };

  const loadCodes = async () => {
    setCodesLoading(true);
    try {
      const res = await fetch("/api/admin/invite-codes");
      if (!res.ok) throw new Error("加载失败");
      const data: InviteCode[] = await res.json();
      setCodes(data);
    } catch {
      setError("加载邀请码失败");
    } finally {
      setCodesLoading(false);
    }
  };

  useEffect(() => {
    if (user && user.system_role === "admin") {
      loadSettings();
      loadCodes();
    }
  }, [user]);

  const saveSettings = async () => {
    setSettingsLoading(true);
    setSettingsSaved(false);
    try {
      const res = await fetch("/api/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allow_public_registration: allowPublic }),
      });
      if (!res.ok) throw new Error("保存失败");
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 3000);
    } catch {
      setError("保存设置失败");
    } finally {
      setSettingsLoading(false);
    }
  };

  const doCreateCode = async () => {
    try {
      const res = await fetch("/api/admin/invite-codes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_uses: maxUses }),
      });
      if (!res.ok) throw new Error("创建失败");
      const data = await res.json();
      setNewCode(data.code);
      await loadCodes();
    } catch {
      setError("创建邀请码失败");
    }
  };

  const copyCode = async (code: string) => {
    await navigator.clipboard.writeText(code);
  };

  const deactivateCode = async (code: string) => {
    try {
      const res = await fetch(`/api/admin/invite-codes/${code}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("删除失败");
      await loadCodes();
    } catch {
      setError("删除邀请码失败");
    }
  };

  if (isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <Card className="w-full max-w-3xl">
          <CardContent className="py-8 text-center text-muted-foreground">加载中...</CardContent>
        </Card>
      </div>
    );
  }
  if (!user || user.system_role !== "admin") return null;

  return (
    <div className="flex min-h-screen items-start justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-3xl">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>系统设置</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => router.push("/workspace")}>
              <ArrowLeft className="mr-1 h-4 w-4" />
              返回
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <Alert variant="destructive" className="mb-4"><AlertDescription>{error}</AlertDescription></Alert>}
          <Tabs defaultValue="settings">
            <TabsList className="mb-4">
              <TabsTrigger value="settings">注册设置</TabsTrigger>
              <TabsTrigger value="invite">邀请码管理</TabsTrigger>
            </TabsList>

            <TabsContent value="settings" className="space-y-4">
              <div className="flex items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">允许公开注册</p>
                  <p className="text-xs text-muted-foreground">关闭后新用户只能通过邀请码注册</p>
                </div>
                <Switch checked={allowPublic} onCheckedChange={setAllowPublic} />
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={saveSettings} disabled={settingsLoading}>
                  {settingsLoading ? "保存中..." : "保存设置"}
                </Button>
                {settingsSaved && <span className="text-xs text-green-600">已保存</span>}
              </div>
            </TabsContent>

            <TabsContent value="invite" className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">共 {codes.length} 个邀请码</p>
                <Button size="sm" onClick={() => { setCreateOpen(true); setNewCode(""); setMaxUses(1); }}>
                  <Plus className="mr-1 h-4 w-4" />生成邀请码
                </Button>
              </div>
              {codesLoading ? (
                <div className="py-8 text-center text-muted-foreground">加载中...</div>
              ) : (
                <div className="overflow-hidden rounded-lg border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium">邀请码</th>
                        <th className="px-4 py-2 text-left font-medium">最大使用次数</th>
                        <th className="px-4 py-2 text-left font-medium">已使用</th>
                        <th className="px-4 py-2 text-left font-medium">状态</th>
                        <th className="px-4 py-2 text-right font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {codes.map((c) => (
                        <tr key={c.code} className="hover:bg-muted/50">
                          <td className="px-4 py-2 font-mono text-xs">{c.code}</td>
                          <td className="px-4 py-2">{c.maxUses}</td>
                          <td className="px-4 py-2">{c.usedCount}</td>
                          <td className="px-4 py-2">{c.isActive ? <Badge variant="default">有效</Badge> : <Badge variant="secondary">已失效</Badge>}</td>
                          <td className="px-4 py-2">
                            <div className="flex items-center justify-end gap-1">
                              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => copyCode(c.code)} title="复制"><Copy className="h-3.5 w-3.5" /></Button>
                              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => deactivateCode(c.code)} disabled={!c.isActive} title="停用"><Trash2 className="h-3.5 w-3.5" /></Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {codes.length === 0 && <div className="py-8 text-center text-muted-foreground">暂无邀请码</div>}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>生成邀请码</DialogTitle><DialogDescription>创建一个新的注册邀请码。</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2">
            {!newCode ? (
              <div className="space-y-2">
                <label className="text-sm font-medium leading-none">最大使用次数</label>
                <Input type="number" min={1} max={100} value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} />
              </div>
            ) : (
              <div className="space-y-3">
                <Alert><AlertDescription className="font-mono text-lg tracking-wider">{newCode}</AlertDescription></Alert>
                <Button variant="outline" size="sm" className="w-full" onClick={() => copyCode(newCode)}><Copy className="mr-2 h-4 w-4" />复制邀请码</Button>
              </div>
            )}
          </div>
          <DialogFooter>
            {!newCode ? (<><Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button><Button onClick={doCreateCode}>生成</Button></>) : (<Button onClick={() => setCreateOpen(false)}>关闭</Button>)}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
