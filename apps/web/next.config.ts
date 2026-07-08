import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 前端开发配置 */
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
