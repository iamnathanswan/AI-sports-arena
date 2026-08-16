/**
 * Guards the two rules that are painful to retrofit: the simulation must stay
 * headless, and it must never reach for unseeded randomness.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const srcRoot = fileURLToPath(new URL('../src', import.meta.url));

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((entry: string) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? filesUnder(path) : path.endsWith('.ts') ? [path] : [];
  });
}

/** Comments are allowed to mention the things the code may not do. */
const codeOnly = (file: string): string =>
  readFileSync(file, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');

const simFiles = filesUnder(join(srcRoot, 'sim'));
const contentFiles = filesUnder(join(srcRoot, 'content'));
const headlessFiles = [...simFiles, ...contentFiles];

describe('architecture', () => {
  it('finds the headless sources it is meant to guard', () => {
    expect(simFiles.length).toBeGreaterThan(5);
    expect(contentFiles.length).toBeGreaterThan(2);
  });

  it('keeps three.js out of simulation and content code', () => {
    for (const file of headlessFiles) {
      expect(codeOnly(file), file).not.toMatch(/from\s+['"]three/);
    }
  });

  it('keeps the DOM out of simulation and content code', () => {
    for (const file of headlessFiles) {
      const source = codeOnly(file);
      expect(source, file).not.toMatch(/\b(document|window|navigator)\./);
    }
  });

  it('bans Math.random() outside the render and input layers', () => {
    for (const file of headlessFiles) {
      expect(codeOnly(file), file).not.toContain('Math.random');
    }
  });
});
