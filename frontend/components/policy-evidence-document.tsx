import Markdown from "react-markdown";

const metadataLabels: Record<string, string> = {
  version: "Version",
  owner: "Owner",
  access: "Access",
  status: "Status",
  effective_on: "Effective",
  supersedes: "Supersedes",
  superseded_by: "Superseded by",
};

export function PolicyEvidenceDocument({
  content,
  changed,
}: {
  content: string;
  changed: boolean;
}) {
  const policy = parsePolicyDocument(content);

  return (
    <div data-changed={changed} className={changed ? "rounded-lg bg-amber-50 p-4" : undefined}>
      {policy.metadata.length > 0 && (
        <dl className="grid gap-x-8 gap-y-4 border-b pb-6 sm:grid-cols-2">
          {policy.metadata.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {label}
              </dt>
              <dd className="mt-1 text-sm font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="max-w-[65ch]">
        <Markdown
          skipHtml
          disallowedElements={["img"]}
          components={{
            h1: ({ children }) => (
              <h1 className="mt-8 text-2xl font-semibold tracking-tight first:mt-0">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-8 text-lg font-semibold tracking-tight">{children}</h2>
            ),
            h3: ({ children }) => <h3 className="mt-6 font-semibold">{children}</h3>,
            p: ({ children }) => (
              <p className="mt-4 text-[15px] leading-7 text-foreground/90">{children}</p>
            ),
            ul: ({ children }) => (
              <ul className="mt-4 list-disc space-y-2 pl-5 text-[15px] leading-7">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="mt-4 list-decimal space-y-2 pl-5 text-[15px] leading-7">{children}</ol>
            ),
            blockquote: ({ children }) => (
              <blockquote className="mt-5 border-l-2 pl-4 text-muted-foreground">
                {children}
              </blockquote>
            ),
            a: ({ children, href }) => (
              <a className="font-medium text-blue-700 underline underline-offset-4" href={href}>
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.9em]">
                {children}
              </code>
            ),
          }}
        >
          {policy.body}
        </Markdown>
      </div>
    </div>
  );
}

export function parsePolicyDocument(content: string) {
  const lines = content.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return { metadata: [], body: content };

  const metadataEnd = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (metadataEnd === -1) return { metadata: [], body: content };

  const metadata = lines
    .slice(1, metadataEnd)
    .map((line) => {
      const separator = line.indexOf(":");
      if (separator === -1) return null;

      const key = line.slice(0, separator).trim();
      const value = line.slice(separator + 1).trim();
      const label = metadataLabels[key];
      return label && value ? ([label, formatMetadataValue(key, value)] as const) : null;
    })
    .filter((entry): entry is readonly [string, string] => entry !== null);

  return {
    metadata,
    body: lines
      .slice(metadataEnd + 1)
      .join("\n")
      .trim(),
  };
}

function formatMetadataValue(key: string, value: string) {
  if (key !== "access" && key !== "status") return value;

  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
