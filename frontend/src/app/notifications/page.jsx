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

const EMPTY_FORM = { username: "", password: "", cameraIds: [], sendBbox: true };

function StatBox({ Icon, label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500">{label}</p>
          <p className="text-xl font-semibold text-slate-900">{value}</p>
        </div>
      </div>
    </div>
  );
}

function CameraCheckbox({ camera, checked, onToggle }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 hover:border-blue-200 hover:bg-blue-50/40">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
      />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-slate-800">
          {camera.display_name}
        </span>
        <span className="block truncate font-mono text-[10px] text-slate-500">
          {camera.camera_id}
        </span>
      </span>
    </label>
  );
}

function CameraBadges({ cameraIds, cameraMap }) {
  if (!cameraIds.length) {
    return <span className="text-xs text-slate-400">Chưa phân quyền</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {cameraIds.map((cameraId) => (
        <span
          key={cameraId}
          title={cameraId}
          className="rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700"
        >
          {cameraMap.get(cameraId)?.display_name || cameraId}
        </span>
      ))}
    </div>
  );
}

export default function PermissionsPage() {
  const router = useRouter();
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
        loadError instanceof Error ? loadError.message : "Không thể tải dữ liệu",
      );
    } finally {
      setLoading(false);
    }
  }, []);

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
      sendBbox: user.send_bbox !== undefined ? Boolean(user.send_bbox) : true,
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
    if (!username) return setError("Vui lòng nhập tên tài khoản moderator.");
    if (!editingUser && form.password.length < 6) {
      return setError("Mật khẩu phải có ít nhất 6 ký tự.");
    }
    if (!form.cameraIds.length) {
      return setError("Vui lòng chọn ít nhất một camera.");
    }

    setSaving(true);
    setError("");
    setMessage("");
    try {
      if (editingUser) {
        const updatePayload = { send_bbox: form.sendBbox };
        if (form.password) {
          updatePayload.password = form.password;
        }
        await updateModerator(editingUser.username, updatePayload);
        await updateCameraPermissions(editingUser.username, form.cameraIds);
        setMessage(`Đã cập nhật moderator ${editingUser.username}.`);
      } else {
        await createModerator(username, form.password, form.sendBbox);
        await updateCameraPermissions(username, form.cameraIds);
        setMessage(`Đã tạo moderator ${username}.`);
      }
      await loadData();
      setEditingUsername(null);
      setForm(EMPTY_FORM);
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Không thể lưu thay đổi",
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
          ? `Đã mở khóa ${user.username}.`
          : `Đã khóa ${user.username}.`,
      );
      await loadData();
    } catch (statusError) {
      setError(statusError instanceof Error ? statusError.message : "Không thể đổi trạng thái");
    }
  };

  const handleDelete = async (user) => {
    if (!window.confirm(`Xóa moderator "${user.username}"?`)) return;
    try {
      await deleteModerator(user.username);
      if (editingUsername === user.username) resetForm();
      setMessage(`Đã xóa moderator ${user.username}.`);
      await loadData();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Không thể xóa tài khoản");
    }
  };

  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">
        Đang kiểm tra quyền truy cập...
      </div>
    );
  }

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="notifications" />
        <div className="flex min-h-0 min-w-0 flex-col bg-slate-50">
          <PageHeader title="Phân quyền" subtitle="Quản lý moderator và camera được phép theo dõi." />
          <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5 lg:p-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatBox Icon={Users} label="Moderator" value={users.length} />
              <StatBox Icon={Camera} label="Camera khả dụng" value={cameras.length} />
              <StatBox Icon={Shield} label="Camera đã gán" value={assignedCameraCount} />
            </div>

            {error && !editingUser ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
            ) : null}

            <div className="mt-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
              <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                      {editingUser ? <Pencil className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
                    </div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      {editingUser ? "Sửa moderator" : "Thêm moderator"}
                    </h2>
                  </div>
                  {editingUser ? (
                    <button type="button" onClick={resetForm} className="rounded-md border border-slate-200 p-1.5 text-slate-500">
                      <X className="h-4 w-4" />
                    </button>
                  ) : null}
                </div>

                <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500">Tên tài khoản</label>
                    <div className="relative">
                      <Users className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={form.username}
                        disabled={Boolean(editingUser)}
                        onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                        className="w-full rounded-lg border border-slate-200 py-2.5 pl-9 pr-3 text-sm outline-none disabled:bg-slate-50"
                        placeholder="VD: moderator_sanh"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500">Mật khẩu</label>
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        type="password"
                        value={form.password}
                        onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                        className="w-full rounded-lg border border-slate-200 py-2.5 pl-9 pr-3 text-sm outline-none"
                        placeholder={editingUser ? "Để trống nếu không đổi" : "Ít nhất 6 ký tự"}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <label className="text-xs font-semibold uppercase text-slate-500">Camera được phép xem</label>
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
                  <div>
                    <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 hover:border-blue-200 hover:bg-blue-50/40">
                      <input
                        type="checkbox"
                        checked={form.sendBbox}
                        onChange={(e) => setForm((curr) => ({ ...curr, sendBbox: e.target.checked }))}
                        className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-slate-800">
                          Hiển thị Bounding Box
                        </span>
                        <span className="block truncate text-[10px] text-slate-500">
                          Bật tùy chọn này để moderator nhận được bounding box
                        </span>
                      </span>
                    </label>
                  </div>
                  {error ? <p className="text-sm text-rose-600">{error}</p> : null}
                  {message ? <p className="text-sm text-blue-700">{message}</p> : null}
                  <button
                    type="submit"
                    disabled={saving || loading}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {editingUser ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                    {saving ? "Đang lưu..." : editingUser ? "Lưu thay đổi" : "Thêm moderator"}
                  </button>
                </form>
              </section>

              <section className="min-w-0 rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Quản lý user</h2>
                    <p className="mt-1 text-xs text-slate-500">Dữ liệu thật từ database và permission theo Camera ID.</p>
                  </div>
                  <div className="relative w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm user hoặc camera..." className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none" />
                  </div>
                </div>

                <div className="overflow-auto">
                  <table className="w-full min-w-[760px] text-left">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs font-medium text-slate-400">
                        <th className="px-4 py-3">Tài khoản</th>
                        <th className="px-4 py-3">Trạng thái</th>
                        <th className="px-4 py-3">Camera</th>
                        <th className="px-4 py-3">Cập nhật</th>
                        <th className="px-4 py-3 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {loading ? (
                        <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-slate-400">Đang tải dữ liệu...</td></tr>
                      ) : filteredUsers.length === 0 ? (
                        <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-slate-400">Chưa có moderator.</td></tr>
                      ) : filteredUsers.map((user) => (
                        <tr key={user.id} className={editingUsername === user.username ? "bg-blue-50/50" : "bg-white"}>
                          <td className="px-4 py-4">
                            <p className="text-sm font-semibold text-slate-900">{user.username}</p>
                            <p className="text-xs text-slate-400">Moderator</p>
                          </td>
                          <td className="px-4 py-4">
                            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${user.status === "active" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                              {user.status === "active" ? "Hoạt động" : "Đã khóa"}
                            </span>
                          </td>
                          <td className="px-4 py-4"><CameraBadges cameraIds={user.camera_ids || []} cameraMap={cameraMap} /></td>
                          <td className="px-4 py-4 text-xs text-slate-500">{user.updated_at || "-"}</td>
                          <td className="px-4 py-4">
                            <div className="flex justify-end gap-2">
                              <button type="button" onClick={() => startEdit(user)} title="Sửa" className="rounded-md border border-slate-200 p-1.5 text-slate-500"><Pencil className="h-4 w-4" /></button>
                              <button type="button" onClick={() => handleStatus(user)} title={user.status === "active" ? "Khóa" : "Mở khóa"} className="rounded-md border border-amber-100 p-1.5 text-amber-600"><Lock className="h-4 w-4" /></button>
                              <button type="button" onClick={() => handleDelete(user)} title="Xóa" className="rounded-md border border-rose-100 p-1.5 text-rose-500"><Trash2 className="h-4 w-4" /></button>
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
