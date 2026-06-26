"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import {
  Camera,
  KeyRound,
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

const STORAGE_KEY = "frontdesk_permission_mock_users";

const CAMERA_OPTIONS = [
  { id: "default", name: "Camera mặc định", area: "Quầy lễ tân" },
  { id: "DSLR-001", name: "DSLR-001", area: "Sảnh chính" },
  { id: "DSLR-002", name: "DSLR-002", area: "Cổng vào" },
  { id: "DSLR-003", name: "DSLR-003", area: "Khu dịch vụ" },
  { id: "CAM-VIP", name: "CAM-VIP", area: "Khu khách VIP" },
];

const DEFAULT_USERS = [
  {
    id: "mock-moderator-main",
    username: "moderator",
    password: "change_me_immediately",
    role: "moderator",
    cameras: ["DSLR-002", "DSLR-003"],
    updatedAt: "2026-06-26 09:00",
  },
  {
    id: "mock-frontdesk-shift",
    username: "frontdesk_shift",
    password: "frontdesk123",
    role: "moderator",
    cameras: ["default", "DSLR-001"],
    updatedAt: "2026-06-26 09:15",
  },
];

const EMPTY_FORM = {
  username: "",
  password: "",
  cameras: ["default"],
};

function makeId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `mock-${Date.now()}`;
}

function getNowLabel() {
  return new Date().toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function StatBox({ Icon, label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-slate-500">{label}</p>
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
          {camera.name}
        </span>
        <span className="block truncate text-xs text-slate-500">
          {camera.area}
        </span>
      </span>
    </label>
  );
}

function CameraBadges({ cameraIds }) {
  if (!cameraIds.length) {
    return <span className="text-xs text-slate-400">Chưa phân quyền</span>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {cameraIds.map((cameraId) => (
        <span
          key={cameraId}
          className="rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700"
        >
          {cameraId}
        </span>
      ))}
    </div>
  );
}

export default function PermissionsPage() {
  const router = useRouter();
  const [role, setRole] = useState(null);
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const savedRole = localStorage.getItem("role") || "guest";
    if (savedRole !== "admin") {
      router.push("/");
      return;
    }

    setRole(savedRole);
    try {
      const savedUsers = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      setUsers(Array.isArray(savedUsers) ? savedUsers : DEFAULT_USERS);
    } catch {
      setUsers(DEFAULT_USERS);
    }
  }, [router]);

  useEffect(() => {
    if (role === "admin") {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(users));
    }
  }, [role, users]);

  const editingUser = useMemo(
    () => users.find((user) => user.id === editingId) || null,
    [editingId, users],
  );

  const filteredUsers = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return users;

    return users.filter((user) => {
      const cameras = user.cameras.join(" ").toLowerCase();
      return (
        user.username.toLowerCase().includes(keyword) ||
        cameras.includes(keyword)
      );
    });
  }, [query, users]);

  const assignedCameraCount = useMemo(() => {
    const unique = new Set();
    users.forEach((user) => user.cameras.forEach((camera) => unique.add(camera)));
    return unique.size;
  }, [users]);

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setMessage("");
  };

  const toggleCamera = (cameraId) => {
    setForm((current) => {
      const exists = current.cameras.includes(cameraId);
      return {
        ...current,
        cameras: exists
          ? current.cameras.filter((item) => item !== cameraId)
          : [...current.cameras, cameraId],
      };
    });
  };

  const startEdit = (user) => {
    setEditingId(user.id);
    setForm({
      username: user.username,
      password: "",
      cameras: user.cameras,
    });
    setMessage("");
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    const username = form.username.trim();
    const password = form.password.trim();

    if (!username) {
      setMessage("Vui lòng nhập tên tài khoản moderator.");
      return;
    }
    if (!editingUser && !password) {
      setMessage("Vui lòng nhập mật khẩu cho tài khoản mới.");
      return;
    }
    if (!editingUser && password.length < 6) {
      setMessage("Mật khẩu nên có ít nhất 6 ký tự.");
      return;
    }
    if (form.cameras.length === 0) {
      setMessage("Vui lòng chọn ít nhất một camera.");
      return;
    }

    const duplicate = users.some(
      (user) =>
        user.username.toLowerCase() === username.toLowerCase() &&
        user.id !== editingId,
    );
    if (duplicate) {
      setMessage("Tên tài khoản này đã tồn tại.");
      return;
    }

    if (editingUser) {
      setUsers((current) =>
        current.map((user) =>
          user.id === editingUser.id
            ? {
                ...user,
                username,
                password: password || user.password,
                cameras: form.cameras,
                updatedAt: getNowLabel(),
              }
            : user,
        ),
      );
      setMessage(`Đã cập nhật phân quyền cho ${username}.`);
      setForm({ username, password: "", cameras: form.cameras });
      return;
    }

    const nextUser = {
      id: makeId(),
      username,
      password,
      role: "moderator",
      cameras: form.cameras,
      updatedAt: getNowLabel(),
    };

    setUsers((current) => [nextUser, ...current]);
    setMessage(`Đã thêm moderator ${username}.`);
    setForm(EMPTY_FORM);
  };

  const handleDelete = (user) => {
    const ok = window.confirm(`Xóa moderator "${user.username}"?`);
    if (!ok) return;

    setUsers((current) => current.filter((item) => item.id !== user.id));
    if (editingId === user.id) resetForm();
    setMessage(`Đã xóa moderator ${user.username}.`);
  };

  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">
          Đang kiểm tra quyền truy cập...
        </p>
      </div>
    );
  }

  return (
    <main className="h-dvh w-screen overflow-hidden bg-white">
      <div className="grid h-full w-full overflow-hidden lg:grid-cols-[64px_minmax(0,1fr)]">
        <Sidebar active="notifications" />

        <div className="flex min-w-0 min-h-0 flex-col border-x border-slate-100 bg-slate-50">
          <PageHeader
            title="Phân quyền"
            subtitle="Quản lý moderator và camera được phép theo dõi."
          />

          <div className="flex-1 min-h-0 overflow-auto p-4 sm:p-5 lg:p-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <StatBox Icon={Users} label="Moderator" value={users.length} />
              <StatBox
                Icon={Camera}
                label="Camera khả dụng"
                value={CAMERA_OPTIONS.length}
              />
              <StatBox
                Icon={Shield}
                label="Camera đã gán"
                value={assignedCameraCount}
              />
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
              <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                      {editingUser ? (
                        <Pencil className="h-4 w-4" />
                      ) : (
                        <UserPlus className="h-4 w-4" />
                      )}
                    </div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      {editingUser ? "Sửa moderator" : "Thêm moderator"}
                    </h2>
                  </div>
                  {editingUser ? (
                    <button
                      type="button"
                      onClick={resetForm}
                      title="Hủy sửa"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  ) : null}
                </div>

                <form onSubmit={handleSubmit} className="mt-4 space-y-4">
                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500">
                      Tên tài khoản
                    </label>
                    <div className="relative">
                      <Users className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        value={form.username}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            username: event.target.value,
                          }))
                        }
                        placeholder="VD: moderator_sanh"
                        className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1.5 block text-xs font-semibold uppercase text-slate-500">
                      Mật khẩu
                    </label>
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        type="password"
                        value={form.password}
                        onChange={(event) =>
                          setForm((current) => ({
                            ...current,
                            password: event.target.value,
                          }))
                        }
                        placeholder={
                          editingUser ? "Để trống nếu không đổi" : "Nhập mật khẩu"
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-blue-400"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <label className="text-xs font-semibold uppercase text-slate-500">
                        Camera được phép xem
                      </label>
                      <span className="text-xs text-slate-400">
                        {form.cameras.length}/{CAMERA_OPTIONS.length}
                      </span>
                    </div>
                    <div className="grid gap-2">
                      {CAMERA_OPTIONS.map((camera) => (
                        <CameraCheckbox
                          key={camera.id}
                          camera={camera}
                          checked={form.cameras.includes(camera.id)}
                          onToggle={() => toggleCamera(camera.id)}
                        />
                      ))}
                    </div>
                  </div>

                  {message ? (
                    <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-700">
                      {message}
                    </div>
                  ) : null}

                  <button
                    type="submit"
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
                  >
                    {editingUser ? (
                      <Save className="h-4 w-4" />
                    ) : (
                      <Plus className="h-4 w-4" />
                    )}
                    {editingUser ? "Lưu thay đổi" : "Thêm moderator"}
                  </button>
                </form>
              </section>

              <section className="min-w-0 rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      Quản lý user
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      Danh sách tài khoản moderator và phạm vi camera.
                    </p>
                  </div>
                  <div className="relative w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Tìm user hoặc camera..."
                      className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none placeholder:text-slate-400 focus:border-blue-400"
                    />
                  </div>
                </div>

                <div className="overflow-auto">
                  <table className="w-full min-w-[720px] text-left">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs font-medium text-slate-400">
                        <th className="px-4 py-3">Tài khoản</th>
                        <th className="px-4 py-3">Vai trò</th>
                        <th className="px-4 py-3">Camera</th>
                        <th className="px-4 py-3">Cập nhật</th>
                        <th className="px-4 py-3 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {filteredUsers.length === 0 ? (
                        <tr>
                          <td
                            colSpan={5}
                            className="px-4 py-8 text-center text-sm text-slate-400"
                          >
                            Không tìm thấy moderator phù hợp.
                          </td>
                        </tr>
                      ) : (
                        filteredUsers.map((user) => (
                          <tr
                            key={user.id}
                            className={
                              editingId === user.id ? "bg-blue-50/50" : "bg-white"
                            }
                          >
                            <td className="px-4 py-4">
                              <div className="flex items-center gap-3">
                                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">
                                  {user.username.charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold text-slate-900">
                                    {user.username}
                                  </p>
                                  <p className="truncate text-xs text-slate-400">
                                    Tài khoản moderator
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-4">
                              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                                <Shield className="h-3.5 w-3.5" />
                                Moderator
                              </span>
                            </td>
                            <td className="px-4 py-4">
                              <CameraBadges cameraIds={user.cameras} />
                            </td>
                            <td className="px-4 py-4 text-sm text-slate-500">
                              {user.updatedAt}
                            </td>
                            <td className="px-4 py-4">
                              <div className="flex justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => startEdit(user)}
                                  title="Sửa user"
                                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDelete(user)}
                                  title="Xóa user"
                                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-rose-100 text-rose-500 hover:bg-rose-50"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
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
