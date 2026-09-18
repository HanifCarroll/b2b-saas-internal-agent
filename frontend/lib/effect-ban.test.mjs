import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

test("effect ban rejects aliases and property access with actionable guidance", () => {
  const directory = mkdtempSync(join(tmpdir(), "effect-ban-"));
  try {
    const examples = [
      'import { useEffect } from "react"; useEffect(() => {}, []);',
      'import { useEffect as sync } from "react"; sync(() => {}, []);',
      'import React from "react"; React.useEffect(() => {}, []);',
      'import R from "react"; R["useEffect"](() => {}, []);',
      'import React from "react"; const { useEffect: sync } = React; sync(() => {}, []);',
    ];
    for (const [index, source] of examples.entries()) {
      const file = join(directory, `case-${index}.tsx`);
      writeFileSync(file, source);
      const result = spawnSync(
        resolve("node_modules/.bin/oxlint"),
        ["-c", resolve(".oxlintrc.json"), file],
        { encoding: "utf8" },
      );
      assert.equal(result.status, 1, source);
      assert.match(result.stdout + result.stderr, /TanStack Query/);
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
