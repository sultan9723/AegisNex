# Container Troubleshooting Runbook

## Common Issues

### Container Crash Loop
- Check logs: `docker logs <container> --tail 100`
- Verify resource limits (memory, CPU)
- Check for OOM kills in dmesg
- Validate configuration files

### Container Not Starting
- Check image exists: `docker images`
- Verify port availability
- Check volume mounts
- Review network configuration

### High Resource Usage
- Identify top consumers: `docker stats`
- Check for memory leaks
- Review application logs
- Consider scaling horizontally

### Health Check Failures
- Verify application is listening on correct port
- Check health check endpoint configuration
- Review application startup time
- Ensure dependencies are available (database, cache, etc.)
