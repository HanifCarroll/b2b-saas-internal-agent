# Switchboard web demo

Next.js and shadcn interface for scenario selection, investigation, saved history, policy evaluation, and access-controlled proposal approval. FastAPI calls the existing Python workflow and business functions.

See the root README for starting the API and UI. From this directory:

```sh
npm ci
npm run dev -- --hostname 127.0.0.1
```

```sh
npm run lint
npm run build
```

Employee selection is a local identity simulation, not authentication. Investigation and optional policy evaluation make model calls. Approval does not execute a configuration change.
