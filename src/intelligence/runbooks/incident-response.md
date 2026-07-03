# Incident Response Runbook

## 1. Detect
- Monitor alerts from AegisNex dashboard
- Common triggers: CPU > 90%, memory > 85%, disk > 90%, container restart loops

## 2. Triage
- Determine severity: critical (service down), high (degraded), medium (warning), low (info)
- Check if automated remediation is available
- Escalate to on-call engineer if critical

## 3. Investigate
- Check system metrics (CPU, memory, disk, network)
- Review container logs
- Check recent audit logs for configuration changes
- Review monitoring target history

## 4. Remediate
- Restart unhealthy containers
- Clear disk space (remove old logs, pruning Docker)
- Scale up resources if needed
- Roll back recent changes

## 5. Document
- Record incident timeline
- Note root cause
- Update runbook with lessons learned

## 6. Resolve
- Verify service health returns to normal
- Confirm monitoring targets are reachable
- Close incident with resolution notes
