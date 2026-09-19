# Switchboard web demo

Next.js and shadcn interface for prepared demo cases, fictional persona switching, investigation, saved history, policy evaluation, approval, and execution. FastAPI calls the existing Python workflow and business functions.

See the root README for starting the API and UI. From this directory:

```sh
npm ci
npm run dev -- --hostname 127.0.0.1
```

```sh
npm run lint
npm run format:check
npm run build
```

Demo mode requires no Microsoft account. Each visitor receives isolated synthetic storage and can switch among clearly labeled fictional personas. Investigation and optional policy evaluation make model calls. Approval and execution remain separate explicit actions. Entra mode remains available for authenticated internal use.

Use `npm run format` to apply Oxfmt formatting. Oxlint checks TypeScript, React, Next.js, and accessibility rules. Generated shadcn label/field primitives have two narrow lint exceptions because their accessibility attributes are supplied through props and composition. Python continues to use Ruff.
