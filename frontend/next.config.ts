import type { NextConfig } from "next";

// URL lama (berbahasa Indonesia) dialihkan permanen agar bookmark tetap berfungsi.
const LEGACY_ROUTES: Record<string, string> = {
  masuk: "login",
  daftar: "register",
  dokumen: "documents",
  soal: "questions",
};

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    agentUpgrade: "security",
  },
  redirects() {
    return Object.entries(LEGACY_ROUTES).flatMap(([from, to]) => [
      { source: `/${from}`, destination: `/${to}`, permanent: true },
      { source: `/${from}/:path*`, destination: `/${to}/:path*`, permanent: true },
    ]);
  },
};

export default nextConfig;
