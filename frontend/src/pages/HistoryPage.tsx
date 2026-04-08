import { useEffect } from "react";
import { Archive } from "lucide-react";
import { JobCard } from "@/components/JobCard";
import { useJobStore } from "@/stores/useJobStore";

export function HistoryPage() {
  const { jobs, isLoading, fetchJobs } = useJobStore();

  useEffect(() => {
    void fetchJobs();
  }, [fetchJobs]);

  return (
    <div className="flex-1 p-6 lg:p-10 max-w-4xl mx-auto w-full">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-foreground tracking-tight">Historique</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Tous les jobs d'upscaling soumis
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        </div>
      )}

      {!isLoading && jobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Archive className="w-10 h-10 mb-4 opacity-40" />
          <p className="text-sm">Aucun job pour le moment</p>
        </div>
      )}

      {!isLoading && jobs.length > 0 && (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onDownload={
                job.status === "completed"
                  ? () => window.open(`/api/jobs/${job.id}/download`, "_blank")
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
