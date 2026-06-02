# Use a secure, minimal alpine Linux base image
FROM alpine:3.19

# Install standard runtime parameters along with nmap scripting templates
RUN apk add --no-cache bash nmap nmap-scripts grep

# Set the operational context directory inside the container
WORKDIR /app

# Copy the custom modular asset from the host machine context
COPY scan_engine.sh .

# Automatically invoke the custom shell framework upon runtime initiation
ENTRYPOINT ["/bin/bash", "./scan_engine.sh"]
