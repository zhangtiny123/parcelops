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
        description="Track source files, mapping readiness, and normalization progress before data lands in the modeled tables. For the seeded walkthrough, the sample CSVs live in data/generated/."
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

      <div className="inline-notice inline-notice--good" role="status">
        Manual demo tip: normalize <code>orders.csv</code> and <code>shipments.csv</code>
        before invoice files so issue linkage is complete. <code>./scripts/demo-up.sh</code>
        does this automatically.
      </div>

      <UploadWorkflow
        initialUploads={uploadsResult.data ?? []}
        initialUploadsError={uploadsResult.error}
      />
    </div>
  );
}
