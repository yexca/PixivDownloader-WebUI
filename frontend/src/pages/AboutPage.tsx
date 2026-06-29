import type * as React from "react";
import {
  BookOpen,
  Code2,
  Database,
  ExternalLink,
  HeartHandshake,
  Info,
  LockKeyhole,
  ShieldCheck
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";

const dependencies = [
  {
    label: "Backend",
    items: ["FastAPI", "Uvicorn", "Pydantic", "pixivpy3", "SQLite"]
  },
  {
    label: "Frontend",
    items: ["React", "TypeScript", "Vite", "Tailwind CSS", "TanStack Query", "Radix UI", "lucide-react"]
  },
  {
    label: "Authentication helper",
    items: ["Playwright", "Express", "Docker Compose", "noVNC"]
  },
  {
    label: "Development",
    items: ["pytest", "ruff", "ESLint"]
  }
];

const references = [
  {
    name: "Applio",
    url: "https://github.com/IAHispano/Applio",
    detail: "Referenced for the dependency installation and local startup flow."
  },
  {
    name: "PixivBatchDownloader",
    url: "https://github.com/xuejianxianzun/PixivBatchDownloader",
    detail: "Referenced for Pixiv API pacing ideas, including request sleeps and gentler crawling behavior."
  }
];

export function AboutPage(): JSX.Element {
  return (
    <>
      <PageHeader
        title="About"
        description="Project background, acknowledgements, dependencies, and responsible-use notes."
      />
      <div className="space-y-4 p-4 sm:p-6">
        <section className="surface p-4">
          <div className="flex items-start gap-3">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0">
              <h2 className="text-base font-semibold">Pixiv Downloader WebUI</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                Pixiv Downloader WebUI is a local Pixiv download and library management tool backed by a
                FastAPI backend, a React frontend, and a local SQLite database. It is designed for personal
                archiving workflows, queue inspection, retry handling, and legacy database migration from the
                older PyQt-based downloader data format.
              </p>
            </div>
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.6fr)]">
          <section className="surface p-4">
            <SectionTitle icon={<Code2 className="h-4 w-4" aria-hidden="true" />} title="Development" />
            <div className="mt-3 space-y-3 text-sm leading-6 text-muted-foreground">
              <p>
                This project is developed by yexca with assistance from Codex. Codex helped with implementation,
                documentation, refactoring, and debugging while project direction and maintenance remain under
                yexca's control.
              </p>
              <p>
                The maintained runtime is the WebUI version. Legacy desktop application source code is outside
                this project; compatibility is limited to explicit import paths for old Pixiv SQLite data.
              </p>
            </div>
          </section>

          <section className="surface p-4">
            <SectionTitle icon={<Database className="h-4 w-4" aria-hidden="true" />} title="Version" />
            <dl className="mt-3 grid gap-3 text-sm">
              <InfoRow label="Application" value="0.1.0" />
              <InfoRow label="Runtime" value="Local WebUI" />
              <InfoRow label="Storage" value="SQLite" />
            </dl>
          </section>
        </div>

        <section className="surface p-4">
          <SectionTitle icon={<BookOpen className="h-4 w-4" aria-hidden="true" />} title="References" />
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {references.map((reference) => (
              <div key={reference.name} className="rounded-md border bg-muted/20 p-3">
                <h3 className="text-sm font-semibold">
                  <a
                    className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                    href={reference.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {reference.name}
                    <ExternalLink className="h-3.5 w-3.5" aria-label="opens in a new tab" />
                  </a>
                </h3>
                <p className="mt-1 text-sm leading-5 text-muted-foreground">{reference.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="surface p-4">
          <SectionTitle icon={<HeartHandshake className="h-4 w-4" aria-hidden="true" />} title="Dependencies" />
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {dependencies.map((group) => (
              <div key={group.label} className="rounded-md border bg-muted/20 p-3">
                <h3 className="text-sm font-semibold">{group.label}</h3>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {group.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="surface p-4">
            <SectionTitle icon={<LockKeyhole className="h-4 w-4" aria-hidden="true" />} title="Data And Privacy" />
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              The application runs locally. Settings, refresh tokens, library records, and downloaded files are
              stored on this machine or inside the configured Docker volume mounts. This project does not provide
              a hosted account system and does not intentionally upload local library data.
            </p>
          </section>

          <section className="surface p-4">
            <SectionTitle icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />} title="Responsible Use" />
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              This tool is intended for personal learning, research, and data backup. Follow Pixiv's terms of
              service, respect creator rights, and do not use this project for abusive bulk downloading,
              redistribution, or other unauthorized use.
            </p>
          </section>
        </div>
      </div>
    </>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      {icon}
      <h2 className="text-sm font-semibold">{title}</h2>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border bg-muted/20 px-3 py-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
