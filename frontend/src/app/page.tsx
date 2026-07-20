export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 text-slate-950">
      <section className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-10 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-widest text-blue-700">
          Day 2 foundation
        </p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight">
          ComplaintGuard
        </h1>
        <p className="mt-4 max-w-xl text-lg leading-8 text-slate-600">
          The frontend environment is ready. Complaint workflows will be added
          on their scheduled project days.
        </p>
        <p className="mt-8 text-sm text-slate-500">
          English and Myanmar support planned · USD 0 MVP
        </p>
      </section>
    </main>
  );
}
