# Database Schema

AegisNex uses a single-repository pattern with `PlatformRepository` (`src/platform_db.py`) that supports both SQLite and PostgreSQL backends. AI memory, telemetry, and scheduler data live in separate databases.

---

## Platform DB Tables

All stored in `aegisnex.db` (SQLite) or via `AEGISNEX_DATABASE_URL` (PostgreSQL).

### users

| Column            | Type       | Description                        | Constraints               |
|-------------------|------------|------------------------------------|---------------------------|
| `id`              | INTEGER    | Primary key                        | PK AUTOINCREMENT          |
| `email`           | TEXT       | User email address                 | NOT NULL UNIQUE           |
| `hashed_password` | TEXT       | bcrypt-hashed password             | NOT NULL                  |
| `is_active`       | INTEGER    | Account active flag                | NOT NULL DEFAULT 1        |
| `is_superuser`    | INTEGER    | Superuser privileges               | NOT NULL DEFAULT 0        |
| `is_verified`     | INTEGER    | Email verified                     | NOT NULL DEFAULT 1        |
| `created_at`      | TEXT       | ISO 8601 timestamp                 | NOT NULL                  |

### incidents

| Column                  | Type       | Description                        | Constraints             |
|-------------------------|------------|------------------------------------|-------------------------|
| `incident_id`           | TEXT       | UUID or formatted ID               | PK                      |
| `timestamp`             | TEXT       | When incident was created           | NOT NULL                |
| `severity`              | TEXT       | info/low/medium/high/critical      | NOT NULL                |
| `service_name`          | TEXT       | Affected service name              | NOT NULL                |
| `incident_type`         | TEXT       | Type classification                | NOT NULL                |
| `description`           | TEXT       | Human-readable description         | NOT NULL                |
| `health_check_results`  | TEXT       | JSON health data                   | NOT NULL                |
| `remediation_attempted` | INTEGER    | Whether remediation was tried      | NOT NULL DEFAULT 0      |
| `remediation_successful`| INTEGER    | Whether remediation succeeded      | NOT NULL DEFAULT 0      |
| `status`                | TEXT       | Legacy status field                | NOT NULL                |
| `incident_status`       | TEXT       | active/acknowledged/resolved       | NOT NULL DEFAULT 'active'|
| `acknowledged_by`       | TEXT       | Actor email                        | NULLABLE                |
| `acknowledged_at`       | TEXT       | ISO timestamp                      | NULLABLE                |
| `resolved_by`           | TEXT       | Actor email                        | NULLABLE                |
| `resolved_at`           | TEXT       | ISO timestamp                      | NULLABLE                |
| `resolved_timestamp`    | TEXT       | Legacy resolved timestamp          | NULLABLE                |
| `resolution_notes`      | TEXT       | Free-text resolution notes         | NULLABLE                |

### monitoring_targets

| Column                    | Type       | Description                        | Constraints             |
|---------------------------|------------|------------------------------------|-------------------------|
| `id`                      | INTEGER    | Primary key                        | PK AUTOINCREMENT        |
| `name`                    | TEXT       | Target name                        | NOT NULL UNIQUE         |
| `target_type`             | TEXT       | http/tcp/ssl                       | NOT NULL                |
| `address`                 | TEXT       | URL or host:port                   | NOT NULL                |
| `expected_status`         | INTEGER    | Expected HTTP status                | NULLABLE                |
| `timeout_seconds`         | INTEGER    | Check timeout                      | NOT NULL DEFAULT 5      |
| `warning_days`            | INTEGER    | SSL warning threshold              | NOT NULL DEFAULT 30     |
| `is_active`               | INTEGER    | Whether target is monitored        | NOT NULL DEFAULT 1      |
| `last_error`              | TEXT       | Last error message                 | NULLABLE                |
| `last_status_code`        | INTEGER    | Last HTTP status code              | NULLABLE                |
| `last_response_time_ms`   | REAL       | Last response time                 | NULLABLE                |
| `last_successful_check_at`| TEXT       | Last successful check timestamp    | NULLABLE                |
| `created_at`              | TEXT       | ISO timestamp                      | NOT NULL                |
| `updated_at`              | TEXT       | ISO timestamp                      | NOT NULL                |

### check_results

| Column        | Type       | Description                        | Constraints             |
|---------------|------------|------------------------------------|-------------------------|
| `id`          | INTEGER    | Primary key                        | PK AUTOINCREMENT        |
| `target_id`   | INTEGER    | FK to monitoring_targets           | NULLABLE                |
| `target_name` | TEXT       | Denormalized target name           | NOT NULL                |
| `target_type` | TEXT       | http/tcp/ssl                       | NOT NULL                |
| `timestamp`   | TEXT       | Check timestamp                    | NOT NULL                |
| `status`      | TEXT       | ok/warning/error                   | NOT NULL                |
| `latency_ms`  | REAL       | Response latency                   | NULLABLE                |
| `details`     | TEXT       | JSON result details                | NOT NULL                |

### metrics_snapshots

| Column                     | Type       | Description                        | Constraints             |
|----------------------------|------------|------------------------------------|-------------------------|
| `id`                       | INTEGER    | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`                | TEXT       | Snapshot timestamp                 | NOT NULL                |
| `cpu_percent`              | REAL       | System CPU usage                   | NOT NULL                |
| `memory_percent`           | REAL       | System memory usage                | NOT NULL                |
| `disk_percent`             | REAL       | Disk usage                         | NOT NULL                |
| `network_bytes_sent`       | REAL       | Total bytes sent                   | NOT NULL                |
| `network_bytes_received`   | REAL       | Total bytes received               | NOT NULL                |
| `running_containers`       | REAL       | Count of running containers        | NOT NULL                |
| `stopped_containers`       | REAL       | Count of stopped containers        | NOT NULL                |
| `unhealthy_containers`     | REAL       | Count of unhealthy containers      | NOT NULL                |
| `active_incidents`         | REAL       | Count of active incidents          | NOT NULL                |
| `resolved_incidents`       | REAL       | Count of resolved incidents        | NOT NULL                |
| `total_incidents`          | REAL       | Total incidents                    | NOT NULL                |
| `restart_attempts`         | REAL       | Total restart attempts             | NOT NULL                |
| `successful_restarts`      | REAL       | Successful restarts                | NOT NULL                |
| `failed_restarts`          | REAL       | Failed restarts                    | NOT NULL                |
| `notifications_sent`       | REAL       | Notifications sent                 | NOT NULL                |
| `notifications_failed`     | REAL       | Notifications failed               | NOT NULL                |

### notifications

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`  | TEXT    | Notification time                  | NOT NULL                |
| `event_type` | TEXT    | Type of event                      | NOT NULL                |
| `incident_id`| TEXT    | Related incident                   | NOT NULL                |
| `service_name`| TEXT   | Service name                       | NOT NULL                |
| `provider`   | TEXT    | email/slack/discord                | NOT NULL                |
| `status`     | TEXT    | sent/failed/pending                | NOT NULL                |
| `attempts`   | INTEGER | Delivery attempts                  | NOT NULL                |
| `message`    | TEXT    | Notification body                  | NOT NULL                |

### remediation_actions

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Action timestamp                   | NOT NULL                |
| `service_name`| TEXT    | Service acted upon                 | NOT NULL                |
| `action`      | TEXT    | Action type (restart, etc.)        | NOT NULL                |
| `successful`  | INTEGER | Whether action succeeded           | NOT NULL                |
| `incident_id` | TEXT    | Related incident                   | NULLABLE                |
| `details`     | TEXT    | JSON details                       | NOT NULL                |

### incident_transitions

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `incident_id` | TEXT    | FK to incidents                    | NOT NULL                |
| `timestamp`   | TEXT    | Transition time                    | NOT NULL                |
| `from_status` | TEXT    | Previous status                    | NULLABLE                |
| `to_status`   | TEXT    | New status                         | NOT NULL                |
| `actor`       | TEXT    | Who performed the action           | NOT NULL                |
| `details`     | TEXT    | JSON reason/notes                  | NOT NULL                |

### audit_logs

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Log entry time                     | NOT NULL                |
| `actor`       | TEXT    | User email or "system"             | NOT NULL                |
| `action`      | TEXT    | Action performed                   | NOT NULL                |
| `resource_type`| TEXT   | Resource category                  | NOT NULL                |
| `resource_id` | TEXT    | Resource identifier                | NOT NULL                |
| `details`     | TEXT    | JSON payload                       | NOT NULL                |

### app_settings

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `key`        | TEXT    | Setting key                        | PK                      |
| `value`      | TEXT    | Setting value (JSON)               | NOT NULL                |
| `updated_at` | TEXT    | Last update timestamp              | NOT NULL                |

### notification_channels

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`         | TEXT    | Channel name                       | NOT NULL UNIQUE         |
| `channel_type` | TEXT    | email/slack/discord                | NOT NULL                |
| `config`       | TEXT    | JSON config (webhook, SMTP, etc.)  | NOT NULL                |
| `is_active`    | INTEGER | Channel enabled                    | NOT NULL DEFAULT 1      |
| `created_at`   | TEXT    | ISO timestamp                      | NOT NULL                |
| `updated_at`   | TEXT    | ISO timestamp                      | NOT NULL                |

### api_keys

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`         | TEXT    | Key label                          | NOT NULL UNIQUE         |
| `key_hash`     | TEXT    | SHA-256 hash of the full key       | NOT NULL                |
| `key_prefix`   | TEXT    | First 8 chars for identification   | NOT NULL                |
| `role`         | TEXT    | viewer/operator/admin              | NOT NULL DEFAULT 'viewer'|
| `is_active`    | INTEGER | Key enabled                        | NOT NULL DEFAULT 1      |
| `created_at`   | TEXT    | ISO timestamp                      | NOT NULL                |
| `last_used_at` | TEXT    | Last usage timestamp               | NULLABLE                |
| `request_count`| INTEGER | Total requests with this key       | NOT NULL DEFAULT 0      |

### alert_rules

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`        | TEXT    | Rule name                          | NOT NULL UNIQUE         |
| `description` | TEXT    | Rule description                   | NOT NULL DEFAULT ''     |
| `target_type` | TEXT    | http/tcp/ssl                       | NOT NULL DEFAULT ''     |
| `condition`   | TEXT    | above/below                        | NOT NULL DEFAULT 'above'|
| `threshold`   | REAL    | Threshold value                    | NOT NULL DEFAULT 0.0    |
| `severity`    | TEXT    | info/low/medium/high/critical      | NOT NULL DEFAULT 'medium'|
| `enabled`     | INTEGER | Rule active                        | NOT NULL DEFAULT 1      |
| `created_at`  | TEXT    | ISO timestamp                      | NOT NULL                |
| `updated_at`  | TEXT    | ISO timestamp                      | NOT NULL                |

### reports

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`  | TEXT    | Generation time                    | NOT NULL                |
| `report_type`| TEXT    | weekly/monthly                     | NOT NULL                |
| `status`     | TEXT    | generated/failed                   | NOT NULL                |
| `path`       | TEXT    | File path                          | NOT NULL                |
| `summary`    | TEXT    | JSON summary                       | NOT NULL                |

---

## AI Memory Tables

All stored in `ai_memory.db` (configured via `AEGIS_AI_MEMORY_DB`).

### ai_conversations

| Column           | Type    | Description                         | Constraints             |
|------------------|---------|-------------------------------------|-------------------------|
| `id`             | INTEGER | Primary key                         | PK AUTOINCREMENT        |
| `request`        | TEXT    | User request text                   | NOT NULL                |
| `response`       | TEXT    | AI response text                    | NOT NULL                |
| `confidence`     | REAL    | Confidence score (0–1)              | DEFAULT 0.0             |
| `goal_achieved`  | INTEGER | Whether goal was met                | DEFAULT 0               |
| `steps`          | TEXT    | JSON array of step descriptions     | DEFAULT '[]'            |
| `errors`         | TEXT    | JSON array of errors                | DEFAULT '[]'            |
| `corrections`    | TEXT    | JSON array of corrections           | DEFAULT '[]'            |
| `duration_ms`    | REAL    | Execution duration                  | DEFAULT 0.0             |
| `provider`       | TEXT    | AI provider used                    | DEFAULT ''              |
| `model`          | TEXT    | Model name                          | DEFAULT ''              |
| `extra`          | TEXT    | JSON extra data                     | DEFAULT '{}'            |
| `created_at`     | TEXT    | ISO timestamp                       | DEFAULT (datetime('now'))|

### ai_incidents

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `incident_id` | TEXT    | External incident ID               | NOT NULL                |
| `summary`     | TEXT    | Incident summary                   | NOT NULL                |
| `severity`    | TEXT    | Severity level                     | DEFAULT 'info'          |
| `service`     | TEXT    | Service name                       | DEFAULT ''              |
| `status`      | TEXT    | open/resolved                      | DEFAULT 'open'          |
| `resolved`    | INTEGER | Resolved flag                      | DEFAULT 0               |
| `extra`       | TEXT    | JSON extra data                    | DEFAULT '{}'            |
| `created_at`  | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_recommendations

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `request`      | TEXT    | Original request text              | NOT NULL                |
| `recommendation`| TEXT   | Generated recommendation           | NOT NULL                |
| `confidence`   | REAL    | Recommendation confidence          | DEFAULT 0.0             |
| `was_accepted` | INTEGER | Whether recommendation was accepted| NULLABLE                |
| `extra`        | TEXT    | JSON extra data                    | DEFAULT '{}'            |
| `created_at`   | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_remediations

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `action`       | TEXT    | Remediation action                 | NOT NULL                |
| `target`       | TEXT    | Target of remediation              | NOT NULL                |
| `successful`   | INTEGER | Whether action succeeded           | DEFAULT 0               |
| `triggered_by` | TEXT    | What triggered the remediation     | DEFAULT ''              |
| `duration_ms`  | REAL    | Execution duration                 | DEFAULT 0.0             |
| `extra`        | TEXT    | JSON extra data                    | DEFAULT '{}'            |
| `created_at`   | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_tool_executions

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `tool_name`    | TEXT    | Tool name                          | NOT NULL                |
| `parameters`   | TEXT    | JSON parameters                    | DEFAULT '{}'            |
| `result_status`| TEXT    | ok/error                           | DEFAULT ''              |
| `duration_ms`  | REAL    | Execution time                     | DEFAULT 0.0             |
| `error`        | TEXT    | Error message if failed            | DEFAULT ''              |
| `extra`        | TEXT    | JSON extra data                    | DEFAULT '{}'            |
| `created_at`   | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_learnings

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `root_cause` | TEXT    | Root cause description             | NOT NULL                |
| `resolution` | TEXT    | Resolution applied                 | NOT NULL                |
| `service`    | TEXT    | Affected service                   | DEFAULT ''              |
| `severity`   | TEXT    | Severity level                     | DEFAULT 'info'          |
| `category`   | TEXT    | Categorization (tool_failure, etc.)| DEFAULT ''              |
| `outcome`    | TEXT    | corrected/unresolved/achieved      | DEFAULT ''              |
| `confidence` | REAL    | Confidence in learning             | DEFAULT 0.0             |
| `tags`       | TEXT    | JSON array of tags                 | DEFAULT '[]'            |
| `extra`      | TEXT    | JSON extra data                    | DEFAULT '{}'            |
| `created_at` | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_integrations

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`        | TEXT    | Integration name                   | NOT NULL UNIQUE         |
| `enabled`     | INTEGER | Whether enabled                    | DEFAULT 1               |
| `credentials` | TEXT    | JSON credentials                   | DEFAULT '{}'            |
| `settings`    | TEXT    | JSON settings                      | DEFAULT '{}'            |
| `created_at`  | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### ai_knowledge_docs

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `source`     | TEXT    | File path or URL                   | NOT NULL UNIQUE         |
| `title`      | TEXT    | Document title                     | DEFAULT ''              |
| `doc_type`   | TEXT    | Document type                      | DEFAULT ''              |
| `page_count` | INTEGER | Page count                         | DEFAULT 0               |
| `chunk_count`| INTEGER | Number of chunks                   | DEFAULT 0               |
| `indexed_at` | TEXT    | Index timestamp                    | DEFAULT (datetime('now'))|

### ai_knowledge_chunks

| Column       | Type    | Description                        | Constraints              |
|--------------|---------|------------------------------------|--------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT         |
| `doc_id`     | INTEGER | FK to ai_knowledge_docs            | NOT NULL FK CASCADE      |
| `chunk_index`| INTEGER | Chunk position                     | DEFAULT 0                |
| `content`    | TEXT    | Chunk text content                 | NOT NULL                 |
| `headings`   | TEXT    | JSON array of headings             | DEFAULT '[]'             |
| `metadata`   | TEXT    | JSON metadata                      | DEFAULT '{}'             |
| `created_at` | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

---

## Telemetry Tables

All stored in `telemetry.db`.

### telemetry_api (api_latency)

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Request timestamp                  | NOT NULL                |
| `method`      | TEXT    | HTTP method                        | NOT NULL                |
| `path`        | TEXT    | Request path                       | NOT NULL                |
| `status_code` | INTEGER | Response status code               | NOT NULL                |
| `duration_ms` | REAL    | Request duration                   | NOT NULL                |

### telemetry_workflows (workflow_executions)

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`    | TEXT    | Execution timestamp                | NOT NULL                |
| `workflow_name`| TEXT    | Workflow identifier                | NOT NULL                |
| `duration_ms`  | REAL    | Execution time                     | NOT NULL                |
| `success`      | INTEGER | Whether succeeded                  | NOT NULL                |
| `steps`        | INTEGER | Number of steps executed           | NOT NULL                |

### telemetry_agents (agent_executions)

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Execution timestamp                | NOT NULL                |
| `agent_id`    | TEXT    | Agent identifier                   | NOT NULL                |
| `task`        | TEXT    | Task description                   | NOT NULL                |
| `duration_ms` | REAL    | Execution time                     | NOT NULL                |
| `success`     | INTEGER | Whether succeeded                  | NOT NULL                |

### telemetry_tools (tool_failures)

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Failure timestamp                  | NOT NULL                |
| `tool_name`   | TEXT    | Tool that failed                   | NOT NULL                |
| `error`       | TEXT    | Error message                      | NOT NULL                |
| `duration_ms` | REAL    | Time before failure                 | NOT NULL                |

### telemetry_approvals (approval_times)

| Column        | Type    | Description                        | Constraints             |
|---------------|---------|------------------------------------|-------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `timestamp`   | TEXT    | Timestamp                          | NOT NULL                |
| `approval_id` | TEXT    | Approval identifier                | NOT NULL                |
| `action`      | TEXT    | Action requiring approval          | NOT NULL                |
| `decision`    | TEXT    | approve/reject                     | NOT NULL                |
| `duration_ms` | REAL    | Time to decision                   | NOT NULL                |

---

## Multi-Tenant Tables

All stored in the platform database alongside core tables.

### organizations

| Column       | Type    | Description                        | Constraints             |
|--------------|---------|------------------------------------|-------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`       | TEXT    | Organization name                  | NOT NULL                |
| `slug`       | TEXT    | URL-safe slug                      | NOT NULL UNIQUE         |
| `domain`     | TEXT    | Associated domain                  | NOT NULL DEFAULT ''     |
| `settings`   | TEXT    | JSON settings                      | NOT NULL DEFAULT '{}'   |
| `is_active`  | INTEGER | Active flag                        | NOT NULL DEFAULT 1      |
| `created_at` | TEXT    | ISO timestamp                      | NOT NULL                |

### teams

| Column        | Type    | Description                        | Constraints              |
|---------------|---------|------------------------------------|--------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT         |
| `org_id`      | INTEGER | FK to organizations                | NOT NULL REFERENCES      |
| `name`        | TEXT    | Team name                          | NOT NULL                 |
| `slug`        | TEXT    | URL-safe slug                      | NOT NULL                 |
| `description` | TEXT    | Team description                   | NOT NULL DEFAULT ''      |
| `settings`    | TEXT    | JSON settings                      | NOT NULL DEFAULT '{}'    |
| `created_at`  | TEXT    | ISO timestamp                      | NOT NULL                 |
| UNIQUE        |         |                                    | `(org_id, slug)`         |

### projects

| Column        | Type    | Description                        | Constraints              |
|---------------|---------|------------------------------------|--------------------------|
| `id`          | INTEGER | Primary key                        | PK AUTOINCREMENT         |
| `org_id`      | INTEGER | FK to organizations                | NOT NULL REFERENCES      |
| `team_id`     | INTEGER | FK to teams                        | NOT NULL REFERENCES      |
| `name`        | TEXT    | Project name                       | NOT NULL                 |
| `slug`        | TEXT    | URL-safe slug                      | NOT NULL                 |
| `description` | TEXT    | Project description                | NOT NULL DEFAULT ''      |
| `created_at`  | TEXT    | ISO timestamp                      | NOT NULL                 |
| UNIQUE        |         |                                    | `(org_id, team_id, slug)`|

### tenant_users

| Column       | Type    | Description                        | Constraints              |
|--------------|---------|------------------------------------|--------------------------|
| `id`         | INTEGER | Primary key                        | PK AUTOINCREMENT         |
| `user_id`    | INTEGER | FK to users                        | NOT NULL                 |
| `org_id`     | INTEGER | FK to organizations                | NOT NULL REFERENCES      |
| `role`       | TEXT    | viewer/operator/admin              | NOT NULL DEFAULT 'viewer'|
| `permissions`| TEXT    | JSON permissions                   | NOT NULL DEFAULT '{}'    |
| UNIQUE       |         |                                    | `(user_id, org_id)`      |

### tenant_user_teams

| Column    | Type    | Description                        | Constraints              |
|-----------|---------|------------------------------------|--------------------------|
| `user_id` | INTEGER | FK to users                        | NOT NULL                 |
| `org_id`  | INTEGER | FK to organizations                | NOT NULL                 |
| `team_id` | INTEGER | FK to teams                        | NOT NULL                 |
| PRIMARY   |         |                                    | `(user_id, org_id, team_id)`|

---

## Scheduler Tables

All stored in `ai_scheduler.db` (configured via `AEGIS_AI_SCHEDULER_DB`).

### scheduled_tasks

| Column           | Type    | Description                        | Constraints             |
|------------------|---------|------------------------------------|-------------------------|
| `id`             | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `name`           | TEXT    | Task name                          | NOT NULL                |
| `cron_expression`| TEXT    | Cron schedule                      | NOT NULL                |
| `task_type`      | TEXT    | Type of task                       | NOT NULL                |
| `params`         | TEXT    | JSON parameters                    | DEFAULT '{}'            |
| `enabled`        | INTEGER | Task enabled                       | DEFAULT 1               |
| `last_run`       | TEXT    | Last execution timestamp           | NULLABLE                |
| `next_run`       | TEXT    | Next scheduled timestamp           | NULLABLE                |
| `created_at`     | TEXT    | ISO timestamp                      | DEFAULT (datetime('now'))|

### scheduled_task_log

| Column         | Type    | Description                        | Constraints             |
|----------------|---------|------------------------------------|-------------------------|
| `id`           | INTEGER | Primary key                        | PK AUTOINCREMENT        |
| `task_name`    | TEXT    | Task name                          | NOT NULL                |
| `status`       | TEXT    | completed/failed                   | NOT NULL                |
| `result`       | TEXT    | JSON result                        | NULLABLE                |
| `started_at`   | TEXT    | Start timestamp                    | NULLABLE                |
| `completed_at` | TEXT    | Completion timestamp               | NULLABLE                |
| `duration_ms`  | REAL    | Execution duration                 | DEFAULT 0.0             |
