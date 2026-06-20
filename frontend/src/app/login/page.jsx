"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { postLogin } from "../../services/api";
import { Lock, User, Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Vui lòng điền đầy đủ tài khoản và mật khẩu.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const data = await postLogin(username.trim(), password.trim());
      if (data.success && data.token) {
        localStorage.setItem("token", data.token);
        localStorage.setItem("username", data.user.username);
        localStorage.setItem("role", data.user.role);
        localStorage.setItem(
          "cameras",
          JSON.stringify(data.user.cameras || []),
        );

        // Redirection based on role
        if (data.user.role === "moderator") {
          router.push("/camera");
        } else {
          router.push("/");
        }
      } else {
        setError("Đăng nhập thất bại.");
      }
    } catch (err) {
      setError(err.message || "Tên tài khoản hoặc mật khẩu không chính xác.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950 px-4 py-12">
      {/* Decorative Blur Spheres */}
      <div className="absolute -left-20 -top-20 h-72 w-72 rounded-full bg-blue-500/10 blur-[100px]" />
      <div className="absolute -right-20 -bottom-20 h-72 w-72 rounded-full bg-indigo-500/10 blur-[100px]" />

      <div className="relative w-full max-w-md">
        {/* Logo Section */}
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 text-xl font-bold text-white shadow-lg shadow-blue-500/30">
            FD
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white sm:text-3xl font-display">
            Front Desk AI
          </h1>
          <p className="mt-1.5 text-sm text-slate-400">
            Đăng nhập để quản trị và theo dõi camera.
          </p>
        </div>

        {/* Card */}
        <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur-md">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Username Input */}
            <div>
              <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Tài khoản
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <User className="h-5 w-5" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nhập tên tài khoản"
                  className="w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-10 pr-4 text-sm text-white outline-none placeholder:text-slate-500 focus:border-blue-500 focus:bg-white/10 transition-colors"
                />
              </div>
            </div>

            {/* Password Input */}
            <div>
              <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Mật khẩu
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
                  <Lock className="h-5 w-5" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu"
                  className="w-full rounded-xl border border-white/10 bg-white/5 py-3 pl-10 pr-10 text-sm text-white outline-none placeholder:text-slate-500 focus:border-blue-500 focus:bg-white/10 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-white transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5" />
                  ) : (
                    <Eye className="h-5 w-5" />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-xl border border-red-500/10 bg-red-500/10 px-4 py-3 text-xs text-red-400">
                {error}
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-500 py-3 text-sm font-semibold text-white hover:from-blue-700 hover:to-indigo-600 disabled:opacity-50 transition-all shadow-lg shadow-blue-500/20 active:scale-[0.98]"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Đang xác thực...
                </>
              ) : (
                "Đăng nhập"
              )}
            </button>
          </form>
        </div>

        {/* Guest Return Link */}
        <div className="mt-6 text-center">
          <button
            onClick={() => {
              localStorage.removeItem("token");
              localStorage.removeItem("username");
              localStorage.removeItem("role");
              localStorage.removeItem("cameras");
              router.push("/");
            }}
            className="text-xs font-semibold text-slate-400 hover:text-white transition-colors"
          >
            ← Quay lại với tư cách khách (Guest)
          </button>
        </div>
      </div>
    </main>
  );
}
