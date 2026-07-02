import { DatabaseBackup } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SettingsSection } from "@/pages/settings/shared";

export type MaintenanceSettingsTabProps = {
  importLegacyDatabaseData?: { workflow_run_id?: string | null; import_job_id?: string | null };
  isImporting: boolean;
  legacyDatabaseInputId: string;
  onImportLegacyDatabase: (file: File) => void;
  onRequestLegacyImport: () => void;
};

export function MaintenanceSettingsTab({
  importLegacyDatabaseData,
  isImporting,
  legacyDatabaseInputId,
  onImportLegacyDatabase,
  onRequestLegacyImport
}: MaintenanceSettingsTabProps): JSX.Element {
  return (
    <div className="mt-5 divide-y">
      <SettingsSection title="Data maintenance" description="Run one-off maintenance tasks for local library data.">
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              id={legacyDatabaseInputId}
              className="hidden"
              type="file"
              accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3,application/octet-stream"
              disabled={isImporting}
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) {
                  onImportLegacyDatabase(file);
                }
              }}
            />
            <Button
              type="button"
              variant="outline"
              title="Import artists and artwork metadata from an old PyQt pixiv.db or SQLite database."
              disabled={isImporting}
              onClick={onRequestLegacyImport}
            >
              <DatabaseBackup className="h-4 w-4" aria-hidden="true" />
              Import Legacy Database
            </Button>
            {importLegacyDatabaseData ? (
              <span className="text-xs text-muted-foreground">
                Legacy import workflow started
                {importLegacyDatabaseData.workflow_run_id ? `: ${importLegacyDatabaseData.workflow_run_id}` : "."}
              </span>
            ) : null}
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
