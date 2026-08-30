# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

## ⚠️ API Contract & Runtime Verification Note

After making any changes to the `/api/reconcile` response dictionary shape in `policy.py` or `main.py`:
1. Run `npm run build` to verify JavaScript compilation.
2. Manually verify in the browser (or run Cypress/E2E test suite) that the **Human Review Queue** table populates with rows matching the **Human Review** summary card count.
3. *Note*: Build compilation succeeds with zero errors even if backend/frontend key names (e.g. `human_review` vs `human_review_queue`) mismatch, causing silent runtime failures if not visually verified.
