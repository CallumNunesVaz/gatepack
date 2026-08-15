// Pull in the `@testing-library/jest-dom` matcher type augmentations for the
// whole renderer test suite. `app/vitest.setup.ts` registers them at runtime
// but lives outside this tsconfig's `include`, so the type side is imported here.
import '@testing-library/jest-dom/vitest';
