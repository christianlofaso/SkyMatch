/** @type {import('next').NextConfig} */
const nextConfig = {
  // Per-theme build dir so two `next dev` servers (theme A on :3004, theme D on :3005)
  // can run from this one codebase without fighting over a shared `.next` cache.
  // Set NEXT_DIST_DIR=.next-a / .next-d when launching each server (see the run commands
  // in the plan). Defaults to `.next` for a normal single-server `npm run dev`.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default nextConfig;
