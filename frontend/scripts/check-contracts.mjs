import { execFileSync } from 'node:child_process'
import { readFileSync, unlinkSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const generated = join(project, 'src/contracts/generated.ts')
const temporary = join(tmpdir(), `atlas-contract-${randomUUID()}.ts`)
try {
  execFileSync(
    process.execPath,
    [
      join(project, 'node_modules/openapi-typescript/bin/cli.js'),
      join(project, '../backend/openapi.yaml'),
      '--output',
      temporary,
    ],
    { cwd: project, stdio: 'inherit' },
  )
  const normalize = (text) => text.replaceAll('\r\n', '\n')
  if (normalize(readFileSync(generated, 'utf8')) !== normalize(readFileSync(temporary, 'utf8'))) {
    console.error('API types differ from the canonical Django schema. Run npm run generate:api.')
    process.exitCode = 1
  }
} finally {
  try {
    unlinkSync(temporary)
  } catch (error) {
    if (error.code !== 'ENOENT') {
      console.error('Could not remove the temporary contract-check file.')
      process.exitCode = 1
    }
  }
}
