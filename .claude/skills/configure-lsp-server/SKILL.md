---
name: configure-lsp-server
description: Install and configure LSP servers for Java projects. Use when setting up jdtls, configuring lsp.json, or troubleshooting LSP connectivity.
---

# Configuring LSP Servers for Java

## Installing jdtls

```bash
bash scripts/install-java-lsp.sh
```

To reinstall non-interactively:
```bash
FORCE_REINSTALL=1 bash scripts/install-java-lsp.sh
```

## Configuring LSP Servers

LSP servers are configured via JSON config files. Copilot CLI loads configs in this priority order (highest first):

1. **Repository-level**: `.github/lsp.json` in your repository root
2. **User-level**: `~/.copilot/lsp-config.json` (applies to all projects)

### Config Schema

```json
{
  "lspServers": {
    "<server-key>": {
      "command": "<binary>",
      "args": ["--stdio"],
      "fileExtensions": {
        ".<ext>": "<languageId>"
      }
    }
  }
}
```

### Supported Fields

| Field | Required | Description |
| --- | --- | --- |
| `command` | **Yes** | Binary name (must be on `$PATH`) or absolute path |
| `args` | No | Command arguments (usually `[]` for jdtls) |
| `fileExtensions` | **Yes** | Map of file extension → LSP language ID |
| `env` | No | Environment variables; supports `${VAR}` and `${VAR:-default}` |
| `rootUri` | No | LSP root dir relative to git root (default: `"."`); useful for monorepos |
| `initializationOptions` | No | Custom options sent to server during initialization |
| `requestTimeoutMs` | No | Request timeout in ms (default: 90000) |

### Java (jdtls) — Repository Config

```bash
mkdir -p .github
cat > ".github/lsp.json" << 'LSP_EOF'
{
  "lspServers": {
    "java": {
      "command": "jdtls",
      "args": [],
      "fileExtensions": {
        ".java": "java"
      },
      "initializationTimeoutMs": 180000,
      "requestTimeoutMs": 120000
    }
  }
}
LSP_EOF
```

### Java (jdtls) — User Config

```bash
cat > ~/.copilot/lsp-config.json << 'LSP_EOF'
{
  "lspServers": {
    "java": {
      "command": "jdtls",
      "args": [],
      "fileExtensions": {
        ".java": "java"
      }
    }
  }
}
LSP_EOF
```

### Monorepo Example

For a monorepo where Java code lives in a subdirectory:

```json
{
  "lspServers": {
    "java": {
      "command": "jdtls",
      "args": [],
      "fileExtensions": { ".java": "java" },
      "rootUri": "backend/java-service"
    }
  }
}
```

## Waiting for LSP Indexing (Large Projects)

jdtls can take 60–300+ seconds to index large Java/Maven/Gradle projects on first load. During indexing, LSP queries return incomplete or empty results. **Always run the readiness check before using LSP tools on large projects.**

### Readiness Check Script

```bash
python3 scripts/wait-for-lsp-ready.py --project-dir /path/to/java/project
```

Options:
| Flag | Default | Description |
| --- | --- | --- |
| `--project-dir`, `-p` | `.` | Path to the Java project root |
| `--timeout`, `-t` | `300` | Max seconds to wait for indexing |
| `--jdtls-cmd` | auto-detect | jdtls command (reads from lsp.json if available) |

The script:
1. Starts jdtls and sends LSP initialize/initialized
2. Monitors `language/status` and `$/progress` notifications for indexing progress
3. Reports progress to stdout (building, importing, indexing)
4. Exits with **0** when indexing is complete, **1** on timeout or error
5. Warms the jdtls workspace cache (`~/.cache/jdtls-workspace`), making subsequent LSP starts faster

### When to Run

- **First time** opening a large Java project (500+ source files, multi-module Maven/Gradle)
- **After** cleaning the jdtls workspace cache (`rm -rf ~/.cache/jdtls-workspace`)
- **After** major dependency changes (new modules, large POM changes)


> **Note**: The script auto-detects the jdtls command from `.github/lsp.json` or `~/.copilot/lsp-config.json`. If neither exists, it falls back to `jdtls` on PATH.

## Verifying LSP Setup

After configuration, verify the LSP server is working:

1. **Check status**: Use `/lsp` or `/lsp show` in Copilot CLI interactive mode
2. **Test server**: Use `/lsp test java` to verify the server starts correctly
3. **Reload config**: Use `/lsp reload` after editing config files
4. **Check environment**: Use `/env` to see LSP in the loaded environment summary

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `jdtls` not found | Run `which jdtls` — if missing, run the install script |
| Java version too low | jdtls requires JDK 17+; check with `java -version` |
| LSP not indexing | Large Maven/Gradle projects may take 60–90s on first load |
| Cross-module resolution fails | Run `mvn install` or `gradle build` to resolve dependencies |
| Config not picked up | Run `/lsp reload` or restart Copilot CLI |
| Plugins directory missing | See [Plugins Directory Missing](#plugins-directory-missing) below |
| Server initialize timed out + exit code 1 | Usually means jdtls installation is corrupted; reinstall with `FORCE_REINSTALL=1` |

### Plugins Directory Missing

The jdtls binary (`~/.local/bin/jdtls`) exists but its plugins directory (`~/.local/share/jdtls/plugins`) is missing or corrupted. This can happen after partial installs, interrupted downloads, or manual cleanup.

**Diagnosis**:
```bash
# Check if jdtls binary exists
which jdtls

# Check if plugins directory exists
ls ~/.local/share/jdtls/plugins/
```

**Fix**: Force reinstall jdtls to restore the plugins directory:
```bash
FORCE_REINSTALL=1 bash scripts/install-java-lsp.sh
```

This removes `~/.local/share/jdtls` entirely and re-downloads + extracts the full jdtls distribution, restoring the plugins directory.