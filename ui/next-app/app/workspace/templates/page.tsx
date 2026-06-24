import { TemplateSwitchingPage } from "@/components/TemplateSwitchingPage";
import { loadServerBases, loadServerCustomerTaskTemplates, loadServerTemplateBindings, loadServerTemplatePackages } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function TemplatesPage({ searchParams }: PageProps) {
  const [templatePackages, templateBindings, bases, customerTemplates, params] = await Promise.all([
    loadServerTemplatePackages(),
    loadServerTemplateBindings(),
    loadServerBases(),
    loadServerCustomerTaskTemplates(),
    searchParams || Promise.resolve({} as SearchParams),
  ]);

  return (
    <TemplateSwitchingPage
      bases={bases}
      customerTemplates={customerTemplates}
      feedback={{
        previewStatus: one(params.preview_status),
        previewTemplateId: one(params.preview_template_id),
        previewFromBaseId: one(params.preview_from_base_id),
        previewToBaseId: one(params.preview_to_base_id),
        migratableCount: one(params.migratable_count),
        protectedCount: one(params.protected_count),
        error: one(params.error),
      }}
      selectedTemplateId={one(params.template_id)}
      targetBaseId={one(params.target_base_id)}
      templateBindings={templateBindings}
      templatePackages={templatePackages}
    />
  );
}
