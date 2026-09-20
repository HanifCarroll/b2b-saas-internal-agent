import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

test("application UI never uses native browser dialogs", () => {
  const nativeDialog = /\b(?:window\.)?(?:alert|confirm|prompt)\s*\(/;
  const violations = ["app", "components"].flatMap((directory) =>
    readdirSync(directory, { recursive: true })
      .filter((path) => /\.[jt]sx?$/.test(path.toString()))
      .filter((path) => nativeDialog.test(readFileSync(join(directory, path.toString()), "utf8")))
      .map((path) => join(directory, path.toString())),
  );

  assert.deepEqual(violations, []);
});
