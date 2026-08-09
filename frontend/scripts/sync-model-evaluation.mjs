import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = resolve(
  frontendRoot,
  "..",
  "evaluation",
  "day18",
  "model_evaluation_v1.json",
);
const generatedPath = resolve(
  frontendRoot,
  "src",
  "generated",
  "model_evaluation_v1.json",
);

const source = await readFile(sourcePath, "utf8");
const parsed = JSON.parse(source);

if (parsed.schema_version !== 1 || parsed.status !== "completed") {
  throw new Error(
    "Day 18 evaluation source must have schema_version 1 and completed status.",
  );
}

await mkdir(dirname(generatedPath), { recursive: true });

let generated = null;
try {
  generated = await readFile(generatedPath, "utf8");
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
}

if (generated !== source) {
  await writeFile(generatedPath, source, "utf8");
}

const written = await readFile(generatedPath, "utf8");
if (written !== source) {
  throw new Error("Generated evaluation evidence does not match its Day 18 source.");
}

const digest = createHash("sha256").update(source).digest("hex").slice(0, 12);
process.stdout.write(`Evaluation evidence synchronized (${digest}).\n`);
