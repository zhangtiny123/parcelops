import { PageHeader } from "../../_components/page-header";
import { listUploads, makeApiUrl } from "../../_lib/api";
import { UploadWorkflow } from "./upload-workflow";

export default async function UploadsPage() {
  const uploadsResult = await listUploads();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Uploads"
        title="Ingestion lane"
        description="Track source files, mapping readiness, and normalization progress before data lands in the modeled tables."
      >
        <div className="page-action-row">
          <a
            className="button button-primary"
            href={makeApiUrl("/uploads")}
            rel="noreferrer"
            target="_blank"
          >
            Uploads API
          </a>
        </div>
      </PageHeader>

      <UploadWorkflow
        initialUploads={uploadsResult.data ?? []}
        initialUploadsError={uploadsResult.error}
      />
    </div>
  );
}
