# Pull Request Workflow

## After Creating or Pushing to a Pull Request

Every time you push changes to a branch with an open pull request, you MUST:

1. **Wait for CI to complete** - Check the workflow status after pushing.
2. **Check for CI failures** - Use `github_list_failed_workflow_logs` to inspect any failed jobs.
3. **Fix failures before reporting completion** - If CI fails, fix the issues, verify locally, push again.

## Before Pushing

Always run the full CI pipeline locally before pushing:

```bash
npm run lint
npm run build
npm test
```

If any of these fail, fix them BEFORE pushing. Do not push code that fails locally.

## Common CI Issues

- **Snapshot tests**: If you change CDK infrastructure, update or remove snapshot tests. Run `npm test -- -u` to update snapshots.
- **ESLint**: Run `npm run lint` and fix all errors. Use `npm run lint:fix` for auto-fixable issues.
- **TypeScript compilation**: Run `npm run build` to catch type errors.
- **Cyclic dependencies in CDK**: Avoid creating circular references between CloudFormation resources.

## CI Configuration

The CI workflow (`.github/workflows/ci.yml`) runs:
1. `npm ci`
2. `npm run lint`
3. `npm run build`
4. `npm test`
5. `npx cdk synth` (continue-on-error)
