import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const firebaseDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(firebaseDirectory, "..");

async function readJson(relativePath) {
  return JSON.parse(await readFile(resolve(repositoryRoot, relativePath), "utf8"));
}

const expectedIndexes = {
  indexes: [
    {
      collectionGroup: "tickets",
      queryScope: "COLLECTION",
      fields: [
        { fieldPath: "customerId", order: "ASCENDING" },
        { fieldPath: "createdAt", order: "DESCENDING" },
      ],
    },
    {
      collectionGroup: "notifications",
      queryScope: "COLLECTION",
      fields: [
        { fieldPath: "recipientUid", order: "ASCENDING" },
        { fieldPath: "expiresAt", order: "DESCENDING" },
        { fieldPath: "createdAt", order: "DESCENDING" },
      ],
    },
    {
      collectionGroup: "notifications",
      queryScope: "COLLECTION",
      fields: [
        { fieldPath: "recipientUid", order: "ASCENDING" },
        { fieldPath: "readAt", order: "ASCENDING" },
        { fieldPath: "expiresAt", order: "DESCENDING" },
        { fieldPath: "createdAt", order: "DESCENDING" },
      ],
    },
  ],
  fieldOverrides: [],
};

test("firestore index manifest is valid JSON with the exact required index", async () => {
  const manifest = await readJson("firestore.indexes.json");
  assert.deepEqual(manifest, expectedIndexes);
});

test("firebase.json references the repository rules and index manifests", async () => {
  const config = await readJson("firebase.json");
  assert.deepEqual(config.firestore, {
    rules: "firebase/firestore.rules",
    indexes: "firestore.indexes.json",
  });
});
