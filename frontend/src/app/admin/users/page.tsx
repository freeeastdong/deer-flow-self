"use client";

import { AlertTriangle, ArrowLeft, Copy, KeyRound, Plus, Shield, Trash2, User as UserIcon, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { fetch } from "@/core/api/fetcher";
import { useAuth } from "@/core/auth/AuthProvider";

interface AdminUser {
  id: string;
  email: string;
  role: string;
  createdAt: string;
  isActive: boolean;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const { user, isLoading: isPending } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState("user");
  const [createError, setCreateError] = useState("");

  const [resetOpen, setResetOpen] = useState(false);
  const [resetUser, setResetUser] = useState<AdminUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [copied, setCopied] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleteConfirmEmail, setDeleteConfirmEmail] = useState("");
  const [deleteError, setDeleteError] = useState("");

  useEffect(() => {
    if (!isPending) {
      if (!user) router.push("/login");
      else if (user.system_role !== "admin") router.push("/workspace");
    }
  }, [isPending, user, router]);

  const loadUsers = async () => {
    if (!user || user.system_role !== "admin") return;
    setIsLoading(true); setError("");
    try {
      const res = await fetch("/api/admin/users");
      if (res.status === 403) { router.push("/workspace"); return; }
      if (!res.ok) throw new Error("请求失败");
      const data: AdminUser[] = await res.json();
      setUsers(data);
    } catch { setError("加载用户列表失败"); }
    finally { setIsLoading(false); }
  };

  useEffect(() => { loadUsers(); }, [user]);

  const toggleStatus = async (u: AdminUser) => {
    try {
      const res = await fetch(`/api/admin/users/${u.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !u.isActive }),
      });
      if (!res.ok) throw new Error("操作失败");
      setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, isActive: !u.isActive } : x)));
    } catch { setError("状态更新失败"); }
  };

  const openReset = (u: AdminUser) => { setResetUser(u); setNewPassword(""); setCopied(false); setResetOpen(true); };

  const doReset = async () => {
    if (!resetUser) return;
    try {
      const res = await fetch(`/api/admin/users/${resetUser.id}/reset-password`, { method: "POST" });
      if (!res.ok) throw new Error("重置失败");
      const data = await res.json();
      setNewPassword(data.password);
    } catch { setError("密码重置失败"); setResetOpen(false); }
  };

  const copyPassword = async () => {
    if (!newPassword) return;
    await navigator.clipboard.writeText(newPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const doCreate = async () => {
    setCreateError("");
    if (!createEmail || !createPassword) { setCreateError("请填写邮箱和密码"); return; }
    if (createPassword.length < 8) { setCreateError("密码至少 8 位"); return; }
    try {
      const res = await fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: createEmail, password: createPassword, system_role: createRole }),
      });
      if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || "创建失败"); }
      setCreateOpen(false); setCreateEmail(""); setCreatePassword(""); setCreateRole("user"); await loadUsers();
    } catch (e: unknown) { setCreateError(e instanceof Error ? e.message : "创建失败"); }
  };

  const updateRole = async (u: AdminUser, role: string) => {
    try {
      const res = await fetch(`/api/admin/users/${u.id}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ system_role: role }),
      });
      if (!res.ok) throw new Error("更新失败");
      setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, role } : x)));
    } catch { setError("角色更新失败"); }
  };

  const openDelete = (u: AdminUser) => { setDeleteTarget(u); setDeleteConfirmEmail(""); setDeleteError(""); setDeleteOpen(true); };

  const doDelete = async () => {
    if (!deleteTarget) return;
    if (deleteConfirmEmail !== deleteTarget.email) { setDeleteError("邮箱输入不正确"); return; }
    try {
      const res = await fetch(`/api/admin/users/${deleteTarget.id}`, { method: "DELETE" });
      if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || "删除失败"); }
      setDeleteOpen(false); await loadUsers();
    } catch (e: unknown) { setDeleteError(e instanceof Error ? e.message : "删除失败"); }
  };

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

  return (
    <div className="flex min-h-screen items-start justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-5xl">
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-primary" />
              <CardTitle className="text-2xl">用户管理</CardTitle>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="mr-1 h-4 w-4" />创建用户</Button>
              <Button variant="ghost" size="sm" onClick={() => router.push("/workspace")}><ArrowLeft className="mr-1 h-4 w-4" />返回</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error && <Alert variant="destructive" className="mb-4"><AlertDescription>{error}</AlertDescription></Alert>}
          {isLoading ? (
            <div className="py-8 text-center text-muted-foreground">加载用户列表...</div>
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">邮箱</th>
                    <th className="px-4 py-3 text-left font-medium">角色</th>
                    <th className="px-4 py-3 text-left font-medium">状态</th>
                    <th className="px-4 py-3 text-left font-medium">注册时间</th>
                    <th className="px-4 py-3 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-muted/50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                            {(u.email?.[0] ?? "?").toUpperCase()}
                          </div>
                          <span className="font-medium">{u.email}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Select value={u.role} onValueChange={(v) => updateRole(u, v)} disabled={u.id === user.id}>
                          <SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="admin"><span className="inline-flex items-center gap-1"><Shield className="h-3 w-3" />管理员</span></SelectItem>
                            <SelectItem value="user"><span className="inline-flex items-center gap-1"><UserIcon className="h-3 w-3" />普通用户</span></SelectItem>
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="px-4 py-3">{u.isActive ? <Badge variant="default">正常</Badge> : <Badge variant="secondary">已禁用</Badge>}</td>
                      <td className="px-4 py-3 text-muted-foreground">{u.createdAt ? new Date(u.createdAt).toLocaleString("zh-CN") : "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <div className="flex items-center gap-1.5">
                            <Switch checked={u.isActive} onCheckedChange={() => toggleStatus(u)} disabled={u.id === user.id} />
                            <span className="text-xs text-muted-foreground">{u.isActive ? "启用" : "禁用"}</span>
                          </div>
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openReset(u)} title="重置密码"><KeyRound className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => openDelete(u)} disabled={u.id === user.id} title="删除用户"><Trash2 className="h-4 w-4" /></Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && !error && <div className="py-8 text-center text-muted-foreground">暂无用户数据</div>}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>创建用户</DialogTitle><DialogDescription>创建一个新用户账号。密码至少 8 位字符。</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2">
            {createError && <Alert variant="destructive"><AlertDescription>{createError}</AlertDescription></Alert>}
            <div className="space-y-2"><label htmlFor="email" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">邮箱</label><Input id="email" type="email" placeholder="user@example.com" value={createEmail} onChange={(e) => setCreateEmail(e.target.value)} /></div>
            <div className="space-y-2"><label htmlFor="password" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">密码</label><Input id="password" type="password" placeholder="至少 8 位" value={createPassword} onChange={(e) => setCreatePassword(e.target.value)} /></div>
            <div className="space-y-2"><label htmlFor="role" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">角色</label><Select value={createRole} onValueChange={setCreateRole}><SelectTrigger id="role"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="user">普通用户</SelectItem><SelectItem value="admin">管理员</SelectItem></SelectContent></Select></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button><Button onClick={doCreate}>创建</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>重置密码</DialogTitle><DialogDescription>{resetUser && `为 ${resetUser.email} 生成新密码`}</DialogDescription></DialogHeader>
          <div className="py-4">
            {!newPassword ? (
              <p className="text-sm text-muted-foreground">点击确认后将生成随机密码，该用户的所有现有登录会话将被登出。</p>
            ) : (
              <div className="space-y-3">
                <Alert><AlertDescription className="font-mono text-lg tracking-wider">{newPassword}</AlertDescription></Alert>
                <Button variant="outline" size="sm" className="w-full" onClick={copyPassword}><Copy className="mr-2 h-4 w-4" />{copied ? "已复制" : "复制密码"}</Button>
                <p className="text-xs text-muted-foreground">请立即复制并妥善保存此密码。关闭弹窗后将无法再次查看。</p>
              </div>
            )}
          </div>
          <DialogFooter>
            {!newPassword ? (<><Button variant="outline" onClick={() => setResetOpen(false)}>取消</Button><Button onClick={doReset}>确认重置</Button></>) : (<Button onClick={() => setResetOpen(false)}>关闭</Button>)}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="flex items-center gap-2 text-destructive"><AlertTriangle className="h-5 w-5" />确认删除用户</DialogTitle><DialogDescription>此操作将永久删除用户 <strong>{deleteTarget?.email}</strong> 及其所有数据（对话线程、运行记录、文件）。此操作无法撤销。</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2">
            {deleteError && <Alert variant="destructive"><AlertDescription>{deleteError}</AlertDescription></Alert>}
            <div className="space-y-2"><label htmlFor="confirm-email" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">请输入用户邮箱以确认删除</label><Input id="confirm-email" placeholder={deleteTarget?.email} value={deleteConfirmEmail} onChange={(e) => setDeleteConfirmEmail(e.target.value)} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setDeleteOpen(false)}>取消</Button><Button variant="destructive" onClick={doDelete}>确认删除</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
