// Starts the real backend (serving the built frontend) on a throwaway data directory for E2E tests.
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const backend = path.resolve(import.meta.dirname, '..', '..', 'backend')
const candidates = [path.join(backend, '.venv', 'Scripts', 'python.exe'), path.join(backend, '.venv', 'bin', 'python')]
const python = process.env.ZTB_PYTHON ?? candidates.find((p) => existsSync(p))
if (!python) throw new Error('Backend virtualenv not found; run setup first')
const dataDir = mkdtempSync(path.join(tmpdir(), 'ztb-e2e-'))
const child = spawn(python, ['run.py'], {
  cwd: backend,
  stdio: 'inherit',
  env: { ...process.env, ZTB_DATA_DIR: dataDir, ZTB_PORT: process.env.ZTB_E2E_PORT ?? '8765', ZTB_LOG_LEVEL: 'WARNING' },
})
const stop = () => child.kill()
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
child.on('exit', (code) => process.exit(code ?? 0))
