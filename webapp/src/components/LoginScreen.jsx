export default function LoginScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-950">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h1 className="mb-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">LifeOS</h1>
        <p className="mb-6 text-sm text-slate-500 dark:text-slate-400">
          Sign in to access your assistant.
        </p>
        <a
          href="/api/auth/login"
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
        >
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
