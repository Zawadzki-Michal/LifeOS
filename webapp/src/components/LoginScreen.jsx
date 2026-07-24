export default function LoginScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg p-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-accent text-lg font-semibold text-white">
          L
        </div>
        <h1 className="mb-2 text-2xl font-semibold text-ink">LifeOS</h1>
        <p className="mb-6 text-sm text-muted">Sign in to access your assistant.</p>
        <a
          href="/api/auth/login"
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:bg-accent-strong"
        >
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
