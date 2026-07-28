"use client";

import { useCallback, useEffect, useState } from "react";
import { Settings, Shield, Palette, Globe, Bell, Key, AlertTriangle, Copy, Check, Loader2, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { RouteScaffold } from "@/components/pages/RouteScaffold";
import { getAppSettings, saveAppSettings, API_BASE_URL, type AppSettings } from "@/lib/api";
import { toast } from "sonner";
import { publish } from "@/lib/workflow";
import { SkeletonList } from "@/components/common/Skeleton";

type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
};

type ApiKeysResponse = {
  keys: ApiKey[];
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [showNewKeyDialog, setShowNewKeyDialog] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleteKeyConfirm, setDeleteKeyConfirm] = useState<ApiKey | null>(null);
  const [deleteWorkspaceConfirm, setDeleteWorkspaceConfirm] = useState(false);
  const [deleteWorkspaceText, setDeleteWorkspaceText] = useState("");

  useEffect(() => {
    getAppSettings().then((res) => setSettings(res.settings)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadApiKeys = useCallback(async () => {
    setApiKeysLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/api-keys`, { credentials: "include" });
      if (res.ok) {
        const data: ApiKeysResponse = await res.json();
        setApiKeys(data.keys);
      }
    } catch {} finally {
      setApiKeysLoading(false);
    }
  }, []);

  useEffect(() => { loadApiKeys(); }, [loadApiKeys]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveAppSettings(settings);
      toast.success("Settings saved");
    } catch {
      toast.error("Failed to save settings");
    }
    setSaving(false);
  };

  const update = (key: keyof AppSettings, value: string) => setSettings((prev) => ({ ...prev, [key]: value }));

  const handleGenerateKey = async () => {
    if (!newKeyName.trim()) { toast.error("Please enter a name for the API key"); return; }
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/api-keys`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newKeyName.trim() }),
      });
      if (!res.ok) throw new Error("Failed to generate key");
      const data = await res.json();
      setNewKeyValue(data.key);
      toast.success("API key generated");
      loadApiKeys();
    } catch {
      toast.error("Failed to generate API key");
    }
  };

  const handleRevokeKey = async (key: ApiKey) => {
    const keyId = key.id;
    const keyName = key.name;
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/api-keys/${keyId}`, {
        method: "DELETE", credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to revoke key");
      toast.success("API key revoked", {
        action: {
          label: "Undo",
          onClick: async () => {
            await fetch(`${API_BASE_URL}/api/settings/api-keys`, {
              method: "POST", credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: keyName }),
            });
            publish("ApiKeyCreated", { name: keyName });
            toast.success("API key restored");
            loadApiKeys();
          },
        },
        duration: 10000,
      });
      publish("ApiKeyRevoked", { id: keyId });
      setDeleteKeyConfirm(null);
      loadApiKeys();
    } catch {
      toast.error("Failed to revoke API key");
    }
  };

  const handleDeleteWorkspace = async () => {
    if (deleteWorkspaceText !== "DELETE") { toast.error("Type DELETE to confirm"); return; }
    try {
      const res = await fetch(`${API_BASE_URL}/api/settings/workspace`, {
        method: "DELETE", credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to delete workspace");
      toast.success("Workspace deleted");
      setDeleteWorkspaceConfirm(false);
      setDeleteWorkspaceText("");
    } catch {
      toast.error("Failed to delete workspace");
    }
  };

  const handleCopy = () => {
    if (newKeyValue) {
      navigator.clipboard.writeText(newKeyValue);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    return `${diffDays} days ago`;
  };

  const formatLastUsed = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    const d = new Date(dateStr);
    const now = new Date();
    const diffHours = Math.floor((now.getTime() - d.getTime()) / 3600000);
    if (diffHours < 1) return `${Math.floor((now.getTime() - d.getTime()) / 60000)} minutes ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    return `${Math.floor(diffHours / 24)} days ago`;
  };

  const accentColors = [
    { name: "Cyan", class: "bg-[#00E5FF]" },
    { name: "Purple", class: "bg-[#8B5CF6]" },
    { name: "Green", class: "bg-[#34D399]" },
    { name: "Pink", class: "bg-[#FB7185]" },
    { name: "Amber", class: "bg-[#F59E0B]" },
  ];

  return (
    <RouteScaffold title="Settings" description="Configure workspace settings, security preferences, and system behavior." icon={Settings}>
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingCard icon={Shield} title="Security" description="Authentication and access control settings">
          <div className="space-y-2">
            <label className="text-xs font-medium text-text-primary">Session Timeout</label>
            <Input type="number" value={settings.session_timeout ?? "30"} onChange={(e) => update("session_timeout", e.target.value)} placeholder="30" />
            <p className="text-[11px] text-text-tertiary">Minutes of inactivity before logout</p>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Two-Factor Authentication</span>
            <Badge variant="warning-subtle">Disabled</Badge>
          </div>
          <Button variant="outline" className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : null}
            {saving ? "Saving..." : "Save Security Settings"}
          </Button>
        </SettingCard>

        <SettingCard icon={Palette} title="Appearance" description="Customize the look and feel">
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Current theme</span>
            <Badge variant="secondary">{settings.theme ?? "Dark"}</Badge>
          </div>
          <div>
            <label className="text-xs font-medium text-text-primary">Accent Color</label>
            <div className="mt-1.5 flex gap-2">
              {accentColors.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  onClick={() => update("accent_color", c.name.toLowerCase())}
                  className={`size-7 rounded-md ${c.class} border-2 transition-all ${
                    (settings.accent_color ?? "cyan") === c.name.toLowerCase() ? "border-white shadow-md scale-110" : "border-transparent hover:border-border"
                  }`}
                  title={c.name}
                />
              ))}
            </div>
          </div>
          <Button variant="outline" className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : null}
            {saving ? "Saving..." : "Save Appearance"}
          </Button>
        </SettingCard>

        <SettingCard icon={Bell} title="Notifications" description="Configure notification preferences">
          <div className="space-y-2">
            <label className="text-xs font-medium text-text-primary">Email Notifications</label>
            <Input type="email" value={settings.email_notifications ?? ""} onChange={(e) => update("email_notifications", e.target.value)} placeholder="ops@example.com" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Current setting</span>
            <Badge variant="secondary">{settings.notification_frequency ?? "Immediate"}</Badge>
          </div>
          <Button variant="outline" className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : null}
            {saving ? "Saving..." : "Save Notification Settings"}
          </Button>
        </SettingCard>

        <SettingCard icon={Globe} title="Workspace" description="General workspace configuration">
          <div className="space-y-2">
            <label className="text-xs font-medium text-text-primary">Workspace Name</label>
            <Input value={settings.workspace_name ?? "AegisNex Operations"} onChange={(e) => update("workspace_name", e.target.value)} placeholder="AegisNex Operations" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-text-secondary">Time Zone</span>
            <Badge variant="secondary">{settings.timezone ?? "UTC-7"}</Badge>
          </div>
          <Button variant="outline" className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : null}
            {saving ? "Saving..." : "Save Workspace Settings"}
          </Button>
        </SettingCard>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Key className="size-4 text-primary" />
            <CardTitle>API Keys</CardTitle>
          </div>
          <CardDescription>Manage API keys for external integrations</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border/50">
            {apiKeysLoading ? (
              <div className="py-4"><SkeletonList count={3} /></div>
            ) : apiKeys.length === 0 ? (
              <p className="py-6 text-center text-xs text-text-tertiary">No API keys have been generated yet.</p>
            ) : (
              apiKeys.map((key) => (
                <div key={key.id} className="flex items-center justify-between py-3.5">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{key.name}</p>
                    <p className="text-xs text-text-tertiary">
                      Created {formatDate(key.created_at)} &middot; Last used {formatLastUsed(key.last_used_at)} &middot; {key.prefix}...
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={key.is_active ? "success-subtle" : "secondary"} dot>{key.is_active ? "Active" : "Revoked"}</Badge>
                    {key.is_active && (
                      <Button variant="ghost" size="sm" onClick={() => setDeleteKeyConfirm(key)}>Revoke</Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <Button className="mt-4 w-full" onClick={() => { setNewKeyName(""); setNewKeyValue(null); setShowNewKeyDialog(true); }}>
            <Key className="size-3.5 mr-1" />
            Generate New API Key
          </Button>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between rounded-xl border border-danger/20 bg-danger/5 p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="size-5 text-danger shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-text-primary">Danger Zone</p>
            <p className="text-xs text-text-tertiary">Irreversible actions that affect your workspace</p>
          </div>
        </div>
        <Button variant="destructive" size="sm" onClick={() => { setDeleteWorkspaceConfirm(true); setDeleteWorkspaceText(""); }}>
          <Trash2 className="size-3.5 mr-1" />
          Delete Workspace
        </Button>
      </div>

      <Dialog open={showNewKeyDialog} onOpenChange={(o) => { if (!o) setShowNewKeyDialog(false); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Generate API Key</DialogTitle>
            <DialogDescription>Create a new API key for external integrations.</DialogDescription>
          </DialogHeader>
          {newKeyValue ? (
            <div className="space-y-3">
              <p className="text-xs text-warning">Copy this key now. You will not be able to see it again.</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-lg bg-surface p-2.5 font-mono text-xs break-all">{newKeyValue}</code>
                <Button variant="ghost" size="icon" onClick={handleCopy}>
                  {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
                </Button>
              </div>
              <Button className="w-full" onClick={() => setShowNewKeyDialog(false)}>Done</Button>
            </div>
          ) : (
            <div className="space-y-3">
              <label className="text-xs font-medium text-text-primary">Key Name</label>
              <Input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="e.g. Production Integration"
                autoFocus
              />
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowNewKeyDialog(false)}>Cancel</Button>
                <Button onClick={handleGenerateKey}>Generate</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={deleteKeyConfirm !== null} onOpenChange={(o) => { if (!o) setDeleteKeyConfirm(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Revoke API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke &ldquo;{deleteKeyConfirm?.name}&rdquo;? Any services using this key will lose access immediately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteKeyConfirm(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteKeyConfirm && handleRevokeKey(deleteKeyConfirm)}>Revoke</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteWorkspaceConfirm} onOpenChange={(o) => { if (!o) setDeleteWorkspaceConfirm(false); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete Workspace</DialogTitle>
            <DialogDescription>
              This will permanently delete the entire workspace and all associated data. Type <strong>DELETE</strong> to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={deleteWorkspaceText}
            onChange={(e) => setDeleteWorkspaceText(e.target.value)}
            placeholder='Type "DELETE" to confirm'
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteWorkspaceConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteWorkspace} disabled={deleteWorkspaceText !== "DELETE"}>Delete Workspace</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </RouteScaffold>
  );
}

function SettingCard({ icon: Icon, title, description, children }: { icon: any; title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/40 bg-surface-elevated/40 p-5 transition-all duration-200 hover:border-border/60">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-elevated/80 ring-1 ring-border/50">
          <Icon className="size-3.5 text-text-secondary" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <p className="text-[11px] text-text-tertiary">{description}</p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}
