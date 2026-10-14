"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Camera,
  KeyRound,
  Lock,
  Pencil,
  Plus,
  Save,
  Search,
  Shield,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import {
  createModerator,
  deleteModerator,
  fetchCameras,
  fetchUsers,
  updateCameraPermissions,
  updateModerator,
} from "../../services/api";
import { useApp } from "../../context/AppContext";

const EMPTY_FORM = { username: "", password: "", cameraIds: [] };

function StatBox({ Icon, label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
          <p className="text-xl font-semibold text-slate-900 dark:text-white">{value}</p>
        </div>
      </div>
    </div>
  );
}

function CameraCheckbox({ camera, checked, onToggle }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 hover:border-blue-200 dark:hover:border-blue-600 hover:bg-blue-50/40 dark:hover:bg-slate-700/50">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-1 h-4 w-4 rounded border-slate-300 dark:border-slate-600 text-blue-600 focus:ring-blue-500"
      />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-slate-800 dark:text-white">
          {camera.display_name}
        </span>
        <span className="block truncate font-mono text-[10px] text-slate-500 dark:text-slate-400">
          {camera.camera_id}
        </span>
      </span>
    </label>
  );
}

function CameraBadges({ cameraIds, cameraMap }) {
  const { t } = useApp();
  if (!cameraIds.length) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">{t("unassigned")}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {cameraIds.map((cameraId) => (
        <span
          key={cameraId}
          title={cameraId}
          className="rounded-full border border-blue-100 dark:border-blue-900/60 bg-blue-50 dark:bg-blue-950/60 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300"
        >
          {cameraMap.get(cameraId)?.display_name || cameraId}
        </span>
      ))}
    </div>
  );
}

export default function PermissionsPage() {
  const router = useRouter();
  const { t } = useApp();
  const [role, setRole] = useState(null);
  const [users, setUsers] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingUsername, setEditingUsername] = useState(null);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    if (savedRole !== "admin") {
      router.push("/");
      return;
    }
    setRole(savedRole);
  }, [router]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userData, cameraData] = await Promise.all([
        fetchUsers(),
        fetchCameras(),
      ]);
      setUsers(
        (userData.users || []).filter((user) => user.role === "moderator"),
      );
      setCameras(cameraData.cameras || []);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : t("cannot_load_data"),
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (role === "admin") loadData();
  }, [role, loadData]);

  const editingUser = useMemo(
    () => users.find((user) => user.username === editingUsername) || null,
    [editingUsername, users],
  );
  const cameraMap = useMemo(
    () => new Map(cameras.map((camera) => [camera.camera_id, camera])),
    [cameras],
  );
  const filteredUsers = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return users;
    return users.filter((user) =>
      `${user.username} ${(user.camera_ids || []).join(" ")}`
        .toLowerCase()
        .includes(keyword),
    );
  }, [query, users]);
  const assignedCameraCount = useMemo(
    () => new Set(users.flatMap((user) => user.camera_ids || [])).size,
    [users],
  );

  const resetForm = () => {
    setEditingUsername(null);
    setForm(EMPTY_FORM);
    setMessage("");
    setError("");
  };

  const startEdit = (user) => {
    setEditingUsername(user.username);
    setForm({
      username: user.username,
      password: "",
      cameraIds: (user.camera_ids || []).filter((cameraId) =>
        cameraMap.has(cameraId),
      ),
    });
    setMessage("");
    setError("");
  };

  const toggleCamera = (cameraId) => {
    setForm((current) => ({
      ...current,
      cameraIds: current.cameraIds.includes(cameraId)
        ? current.cameraIds.filter((item) => item !== cameraId)
        : [...current.cameraIds, cameraId],
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const username = form.username.trim();
    if (!username) return setError(t("username_required"));
    if (!editingUser && form.password.length < 6) {
      return setError(t("password_min_length"));
    }
    if (!form.cameraIds.length) {
      return setError(t("select_one_camera"));
    }

    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (editingUser) {
        const updatePayload = {};
        if (form.password) {
          updatePayload.password = form.password;
        }
        if (Object.keys(updatePayload).length > 0) {
          await updateModerator(editingUser.username, updatePayload);
        }
        await updateCameraPermissions(editingUser.username, form.cameraIds);
        setMessage(`${t("updated_mod_success")} ${editingUser.username}.`);
      } else {
        await createModerator(username, form.password);
        await updateCameraPermissions(username, form.cameraIds);
        setMessage(`${t("created_mod_success")} ${username}.`);
      }
      await loadData();
      setEditingUsername(null);
      setForm(EMPTY_FORM);
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : t("cannot_save_changes"),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleStatus = async (user) => {
    const nextStatus = user.status === "active" ? "disabled" : "active";
    try {
      await updateModerator(user.username, { status: nextStatus });
      setMessage(
        nextStatus === "active"
          ? `${t("unlocked_mod")} ${user.username}.`
          : `${t("locked_mod")} ${user.username}.`,
      );
      await loadData();
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : t("cannot_change_status"));
    }
  };

  const handleDelete = async (user) => {
    if (!window.confirm(`${t("confirm_delete_mod")} "${user.username}"?`)) return;
    try {
      await deleteModerator(user.username);
      if (editingUsername === user.username) resetForm();
      setMessage(`${t("deleted_mod_success")} ${user.username}.`);
      await loadData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : t("cannot_delete_account"));
    }
  };

  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-950 text-sm text-slate-500 dark:text-slate-400">
        {t("checking_access")}
      </div>
    );
  }

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white dark:bg-slate-950 transition-colors duration-200">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="notifications" />
        <div className="flex min-h-0 min-w-0 flex-col bg-slate-50 dark:bg-slate-950">
          <PageHeader title={t("auth_page_title")} subtitle={t("auth_page_subtitle")} />
          <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5 lg:p-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatBox Icon={Users} label={t("moderators_stat")} value={users.length} />
              <StatBox Icon={Camera} label={t("available_cameras_stat")} value={cameras.length} />
              <StatBox Icon={Shield} label={t("assigned_cameras_stat")} value={assignedCameraCount} />
            </div>

            {error && !editingUser ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-950/60 dark:border-rose-900/60 dark:text-rose-400">{error}</div>
            ) : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
              <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                      {editingUser ? <Pencil className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
                    </div>
                    <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {editingUser ? t("edit_moderator") : t("add_moderator")}
                    </h2>
                  </div>
                  {editingUser ? (
                    <button type="button" onClick={resetForm} className="rounded-md border border-slate-200 dark:border-slate-700 p-1.5 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800">
                      <X className="h-4 w-4" />
                    </button>
                  ) : null}
                </div>

                <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">{t("username")}</label>
                    <div className="relative">
                      <Users className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={form.username}
                        disabled={Boolean(editingUser)}
                        onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                        className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2.5 pl-9 pr-3 text-sm text-slate-800 dark:text-white outline-none disabled:bg-slate-50 dark:disabled:bg-slate-850"
                        placeholder={t("username_placeholder")}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">{t("password")}</label>
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        type="password"
                        value={form.password}
                        onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                        className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2.5 pl-9 pr-3 text-sm text-slate-800 dark:text-white outline-none"
                        placeholder={editingUser ? t("password_placeholder_edit") : t("password_placeholder_new")}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <label className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">{t("authorized_cameras")}</label>
                      <span className="text-xs text-slate-400">{form.cameraIds.length}/{cameras.length}</span>
                    </div>
                    <div className="grid max-h-72 gap-2 overflow-auto">
                      {cameras.map((camera) => (
                        <CameraCheckbox
                          key={camera.camera_id}
                          camera={camera}
                          checked={form.cameraIds.includes(camera.camera_id)}
                          onToggle={() => toggleCamera(camera.camera_id)}
                        />
                      ))}
                    </div>
                  </div>

                  {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
                  {message ? <p className="text-sm text-blue-700 dark:text-blue-400">{message}</p> : null}
                  <button
                    type="submit"
                    disabled={saving || loading}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                  >
                    {editingUser ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                    {saving ? "..." : editingUser ? t("save_changes") : t("add_moderator")}
                  </button>
                </form>
              </section>

              <section className="min-w-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
                <div className="flex flex-col gap-3 border-b border-slate-100 dark:border-slate-800 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{t("user_management")}</h2>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{t("user_management_desc")}</p>
                  </div>
                  <div className="relative w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={t("search_users_placeholder")}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 py-2 pl-9 pr-3 text-sm text-slate-800 dark:text-white outline-none"
                    />
                  </div>
                </div>

                <div className="overflow-auto">
                  <table className="w-full min-w-[760px] text-left">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-800 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                        <th className="px-4 py-3">{t("username_col")}</th>
                        <th className="px-4 py-3">{t("col_status")}</th>
                        <th className="px-4 py-3">{t("nav_camera")}</th>
                        <th className="px-4 py-3">{t("col_updated")}</th>
                        <th className="px-4 py-3 text-right">{t("col_actions")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {loading ? (
                        <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-slate-400 animate-pulse">{t("connecting")}</td></tr>
                      ) : filteredUsers.length === 0 ? (
                        <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-slate-400">{t("no_moderators")}</td></tr>
                      ) : filteredUsers.map((user) => (
                        <tr key={user.id} className={editingUsername === user.username ? "bg-blue-50/50 dark:bg-blue-950/30" : "hover:bg-slate-50/60 dark:hover:bg-slate-800/40"}>
                          <td className="px-4 py-4">
                            <p className="text-sm font-semibold text-slate-900 dark:text-white">{user.username}</p>
                            <p className="text-xs text-slate-400">{t("role")}: Moderator</p>
                          </td>
                          <td className="px-4 py-4">
                            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${user.status === "active" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`}>
                              {user.status === "active" ? t("status_active") : t("status_disabled")}
                            </span>
                          </td>
                          <td className="px-4 py-4"><CameraBadges cameraIds={user.camera_ids || []} cameraMap={cameraMap} /></td>
                          <td className="px-4 py-4 text-xs text-slate-500 dark:text-slate-400">{user.updated_at || "-"}</td>
                          <td className="px-4 py-4">
                            <div className="flex justify-end gap-2">
                              <button type="button" onClick={() => startEdit(user)} title={t("rename")} className="rounded-md border border-slate-200 dark:border-slate-700 p-1.5 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"><Pencil className="h-4 w-4" /></button>
                              <button type="button" onClick={() => handleStatus(user)} title={user.status === "active" ? t("lock") : t("unlock")} className="rounded-md border border-amber-100 dark:border-amber-900/60 p-1.5 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/40"><Lock className="h-4 w-4" /></button>
                              <button type="button" onClick={() => handleDelete(user)} title={t("delete")} className="rounded-md border border-rose-100 dark:border-rose-900/60 p-1.5 text-rose-500 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40"><Trash2 className="h-4 w-4" /></button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
