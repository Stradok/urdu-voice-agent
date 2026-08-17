const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const { spawn } = require('node:child_process');

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const VENV_PYTHON = path.join(PROJECT_ROOT, '.venv', 'bin', 'python');
const isDev = !app.isPackaged;

// Electron's Linux sandbox needs chrome-sandbox owned by root with mode 4755, which a plain
// `npm run app:dev` checkout won't have (no installer ran to set that up) - Electron aborts
// on startup rather than silently running unsandboxed. The fix has to be the --no-sandbox
// flag on the electron CLI invocation itself (see package.json's app:dev script) - the
// native sandbox check happens before any of this file's JS runs, so setting it
// programmatically here via app.commandLine.appendSwitch (tried first) is too late and has
// no effect. Dev-only concern: this window only ever loads our own local Vite server, never
// arbitrary/untrusted content, so running unsandboxed here carries none of the risk it would
// for a browser. A packaged build's installer sets the binary's permissions correctly, so
// production doesn't need this.


let pythonProcess = null;
let mainWindow = null;

function startPythonBackend() {
  pythonProcess = spawn(VENV_PYTHON, ['-m', 'uvicorn', 'src.api:app', '--host', '127.0.0.1', '--port', '8420'], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });

  pythonProcess.on('exit', (code) => {
    console.log(`Python backend exited with code ${code}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#0a0a0f',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    console.log(`[renderer:${level}] ${message} (${sourceId}:${line})`);
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.log('[renderer crashed]', details);
  });
  mainWindow.on('closed', () => {
    console.log('[main] window closed');
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

app.whenReady().then(() => {
  startPythonBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (pythonProcess) pythonProcess.kill();
});
