const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: true,
  },
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        path: false,
        crypto: false,
      };
      config.resolve.alias = {
        ...config.resolve.alias,
        'onnxruntime-web$': path.resolve(__dirname, 'node_modules/onnxruntime-web/dist/ort.min.js'),
      };
    } else {
      config.externals = [...(config.externals || []), 'onnxruntime-web'];
    }
    return config;
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'https://api.checkinface.me/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
