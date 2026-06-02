# Use a highly secure, minimal alpine Linux base image
FROM alpine:3.19

# Install core runtime network utilities
RUN apk add --no-cache bash curl tar

# Download and install the stable production release of the Nuclei engine directly
RUN curl -L -s https://github.com/projectdiscovery/nuclei/releases/download/v3.3.0/nuclei_3.3.0_linux_amd64.zip -o nuclei.zip \
    && apk add --no-cache unzip \
    && unzip nuclei.zip -d /usr/local/bin/ \
    && rm nuclei.zip \
    && chmod +x /usr/local/bin/nuclei

# Set the internal working directory environment
WORKDIR /app

# Copy your verified application auditing asset from the host machine
COPY audit_engine.sh .

# Pre-populate and initialize the core vulnerability signature definitions during build time
RUN nuclei -update-templates

# Configure the service to execute the app-audit engine automatically upon startup
ENTRYPOINT ["/bin/bash", "./audit_engine.sh"]
