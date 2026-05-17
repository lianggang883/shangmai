module.exports = {
  apps: [{
    name: 'shangmai',
    script: '/opt/shangmai/backend/venv/bin/uvicorn',
    args: 'app.main:app --host 0.0.0.0 --port 8000',
    interpreter: 'none',
    cwd: '/opt/shangmai/backend',
    env: {
      PYTHONPATH: '/opt/shangmai/backend'
    }
  }]
}
