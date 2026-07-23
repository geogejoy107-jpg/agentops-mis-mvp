/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: "/api/agent-gateway/:path*",
        destination: "/api/mis/agent-gateway/:path*",
      },
      {
        source: "/api/operator/loop-supervision",
        destination: "/api/mis/operator/loop-supervision",
      },
    ];
  },
};

export default nextConfig;
