# Quick start

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\86_install_forecast_factory_v103.ps1
```

Then:

```powershell
python .\scripts\forecast_factory_v103.py status
```

Optional daily test:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\87_run_forecast_evidence_cycle.ps1
```

Only after that succeeds, register the Windows task if desired:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\88_register_forecast_evidence_task.ps1
```
