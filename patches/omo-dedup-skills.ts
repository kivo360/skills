#!/usr/bin/env bun
import { readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const MARKER = "/* OMO_DEDUP_PATCH_v1 */"
const CACHE = `${process.env.HOME}/.bun/install/cache`

const DEDUP_LINE = `${MARKER} skills2 = Array.from(new Map(skills2.map((__s) => [__s.name, __s])).values());`
const DEDUP_LINE_AVAIL = `${MARKER} availableSkills = Array.from(new Map(availableSkills.map((__s) => [__s.name, __s])).values());`

const SECTION_BEFORE = `function buildSkillsSection(skills2) {
  const builtinSkills = skills2.filter((skill2) => skill2.location === "plugin");`
const SECTION_AFTER = `function buildSkillsSection(skills2) {
  ${DEDUP_LINE}
  const builtinSkills = skills2.filter((skill2) => skill2.location === "plugin");`

const REMINDER_BEFORE = `function buildReminderMessage(availableSkills) {
  const builtinSkills = availableSkills.filter((s) => s.location === "plugin");`
const REMINDER_AFTER = `function buildReminderMessage(availableSkills) {
  ${DEDUP_LINE_AVAIL}
  const builtinSkills = availableSkills.filter((s) => s.location === "plugin");`

interface Result {
  path: string
  status: "patched" | "already-patched" | "skipped" | "error"
  detail?: string
}

const findBundles = (): string[] => {
  const out: string[] = []
  let entries: string[]
  try {
    entries = readdirSync(CACHE)
  } catch {
    return out
  }
  for (const name of entries) {
    if (!name.startsWith("oh-my-openagent@")) continue
    const p = join(CACHE, name, "dist", "index.js")
    try {
      if (statSync(p).isFile()) out.push(p)
    } catch {}
  }
  return out
}

const patchOne = async (path: string): Promise<Result> => {
  const text = await Bun.file(path).text()

  if (text.includes(MARKER)) {
    return { path, status: "already-patched" }
  }

  let next = text
  let touched = 0

  if (next.includes(SECTION_BEFORE)) {
    next = next.replace(SECTION_BEFORE, SECTION_AFTER)
    touched++
  }
  if (next.includes(REMINDER_BEFORE)) {
    next = next.replace(REMINDER_BEFORE, REMINDER_AFTER)
    touched++
  }

  if (touched === 0) {
    return { path, status: "skipped", detail: "no patch sites matched (different OMO version?)" }
  }

  await Bun.write(path, next)
  return { path, status: "patched", detail: `${touched} site(s)` }
}

const bundles = findBundles()
if (bundles.length === 0) {
  console.error("No oh-my-openagent bundles found in", CACHE)
  process.exit(1)
}

const results: Result[] = []
for (const b of bundles) {
  try {
    results.push(await patchOne(b))
  } catch (e: any) {
    results.push({ path: b, status: "error", detail: e?.message ?? String(e) })
  }
}

for (const r of results) {
  const ver = r.path.match(/oh-my-openagent@([\d.]+)/)?.[1] ?? "?"
  const tag =
    r.status === "patched"
      ? "✓ patched"
      : r.status === "already-patched"
        ? "= idempotent (already patched)"
        : r.status === "skipped"
          ? "- skipped"
          : "✗ error"
  console.log(`  ${tag.padEnd(32)}  v${ver}  ${r.detail ?? ""}`)
}

process.exit(results.some((r) => r.status === "error") ? 1 : 0)
