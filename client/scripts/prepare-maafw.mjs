import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const clientDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(clientDir, "..");
const srcTauriDir = path.resolve(clientDir, "src-tauri");
const generatedDir = path.resolve(srcTauriDir, "gen");
const runtimeDir = path.resolve(generatedDir, "maafw");

const depsBinDir = path.resolve(repoRoot, "deps", "bin");
const sourceResourceDir = path.resolve(repoRoot, "assets", "resource");
const sourceInterfacePath = path.resolve(repoRoot, "assets", "interface.jsonc");
const sourceAgentExePath = path.resolve(repoRoot, "dist", "agent.exe");
const sourceAgentDir = path.resolve(repoRoot, "agent");

await assertSafeGeneratedRuntimeDir(runtimeDir);
await rm(runtimeDir, { recursive: true, force: true });
await mkdir(runtimeDir, { recursive: true });

await copyRequiredDirectory(depsBinDir, runtimeDir);
await copyRequiredDirectory(sourceResourceDir, path.join(runtimeDir, "resource"));

let hasPackagedAgent = false;
try {
  await cp(sourceAgentExePath, path.join(runtimeDir, "agent.exe"));
  hasPackagedAgent = true;
} catch (error) {
  if (error?.code !== "ENOENT") throw error;
  await copyRequiredDirectory(sourceAgentDir, path.join(runtimeDir, "agent"));
}

await writeRuntimeInterface(hasPackagedAgent);

console.log(`Prepared MaaFramework runtime at ${runtimeDir}`);

async function assertSafeGeneratedRuntimeDir(targetDir) {
  const relativePath = path.relative(generatedDir, targetDir);
  if (relativePath === "" || relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error(`Refusing to prepare Maa runtime outside generated directory: ${targetDir}`);
  }
}

async function copyRequiredDirectory(sourceDir, targetDir) {
  await cp(sourceDir, targetDir, {
    recursive: true,
    force: true,
    filter: (source) => path.basename(source) !== "debug"
  });
}

async function writeRuntimeInterface(hasPackagedAgent) {
  const interfaceText = await readFile(sourceInterfacePath, "utf8");
  const interfaceConfig = JSON.parse(stripJsoncComments(interfaceText));

  if (hasPackagedAgent) {
    interfaceConfig.agent = {
      child_exec: "./agent.exe",
      child_args: []
    };
  }

  await writeFile(
    path.join(runtimeDir, "interface.json"),
    `${JSON.stringify(interfaceConfig, null, 3)}\n`,
    "utf8"
  );
}

function stripJsoncComments(text) {
  let result = "";
  let inString = false;
  let quote = "";
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (inString) {
      result += char;
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        inString = false;
      }
      continue;
    }

    if (char === "\"" || char === "'") {
      inString = true;
      quote = char;
      result += char;
      continue;
    }

    if (char === "/" && next === "/") {
      while (index < text.length && text[index] !== "\n") index += 1;
      result += "\n";
      continue;
    }

    if (char === "/" && next === "*") {
      index += 2;
      while (index < text.length && !(text[index] === "*" && text[index + 1] === "/")) index += 1;
      index += 1;
      continue;
    }

    result += char;
  }

  return result;
}
