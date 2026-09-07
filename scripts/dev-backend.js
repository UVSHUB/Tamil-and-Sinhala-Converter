const { spawnSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const isWindows = process.platform === 'win32';

// 1. Determine paths
const venvPath = path.join(rootDir, '.venv');
const pythonExec = isWindows 
  ? path.join(venvPath, 'Scripts', 'python.exe')
  : path.join(venvPath, 'bin', 'python');
const uvicornExec = isWindows
  ? path.join(venvPath, 'Scripts', 'uvicorn.exe')
  : path.join(venvPath, 'bin', 'uvicorn');

// 2. Create venv if not exists
if (!fs.existsSync(venvPath)) {
  console.log('Creating virtual environment...');
  let created = false;
  // Try different python commands
  for (const cmd of ['python', 'python3', 'py']) {
    console.log(`Trying ${cmd} -m venv .venv...`);
    const res = spawnSync(cmd, ['-m', 'venv', '.venv'], { cwd: rootDir, stdio: 'inherit' });
    if (res.status === 0) {
      created = true;
      break;
    }
  }
  if (!created) {
    console.error('Failed to create virtual environment. Please make sure Python is installed and in your PATH.');
    process.exit(1);
  }
}

// 3. Install requirements
console.log('Installing/updating requirements...');
const pipRes = spawnSync(pythonExec, ['-m', 'pip', 'install', '-r', 'requirements.txt'], {
  cwd: rootDir,
  stdio: 'inherit'
});

if (pipRes.status !== 0) {
  console.error('Failed to install requirements.');
  process.exit(pipRes.status || 1);
}

// 4. Start uvicorn via python module
console.log('Starting FastAPI backend...');
const uvicornProcess = spawn(pythonExec, ['-m', 'uvicorn', 'backend.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'], {
  cwd: rootDir,
  stdio: 'inherit'
});

uvicornProcess.on('close', (code) => {
  process.exit(code || 0);
});

// Handle termination signals
process.on('SIGINT', () => {
  uvicornProcess.kill('SIGINT');
});
process.on('SIGTERM', () => {
  uvicornProcess.kill('SIGTERM');
});
