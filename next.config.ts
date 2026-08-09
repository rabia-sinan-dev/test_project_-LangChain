import type { NextConfig } from "next";

const pythonApiUrl = process.env.PYTHON_API_URL;

const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.VERCEL || !pythonApiUrl) {
      return [];
    }
    return [
      { source: "/api", destination: `${pythonApiUrl}/` },
      { source: "/api/:path*", destination: `${pythonApiUrl}/:path*` },
    ];
  },
};

export default nextConfig;
