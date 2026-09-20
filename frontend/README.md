# Switchboard web demo

Next.js and shadcn interface for prepared demo cases, fictional persona switching, investigation, saved history, policy evaluation, approval, execution, and delivery verification. FastAPI calls the existing Python workflow and business functions.

See the root README for the hybrid local launcher. From the repository root:

```sh
./scripts/dev
```

The default local launcher uses immediate fixture investigations. Run `SWITCHBOARD_INVESTIGATION_MODE=live ./scripts/dev` when testing the real model-backed workflow.

```sh
npm run lint
npm run format:check
npm run build
```

Demo mode requires no Microsoft account. Each visitor receives isolated synthetic storage and can switch among clearly labeled fictional personas. Hybrid mode adds a local choice between that demo and the configured Microsoft account. Investigations automatically validate policy claims before presenting their results. Approval, execution, and delivery verification remain separate explicit actions. Use demo mode by itself for the hosted portfolio.

Use `npm run format` to apply Oxfmt formatting. Oxlint checks TypeScript, React, Next.js, and accessibility rules. Generated shadcn label/field primitives have two narrow lint exceptions because their accessibility attributes are supplied through props and composition. Python continues to use Ruff.
