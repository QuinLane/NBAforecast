export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-4xl font-bold tracking-tight">NBAforecast</h1>
      <p className="text-muted-foreground text-center max-w-md">
        Explainable NBA predictions — calibrated win probability, player props,
        and RAPM with SHAP-driven breakdowns.
      </p>
      <p className="text-sm text-muted-foreground">
        Under construction — M1 data pipeline in progress.
      </p>
    </main>
  );
}
