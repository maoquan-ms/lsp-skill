# Configuring LSP Servers for Java

### Installing Language Servers

```bash
bash scripts/install-java-lsp.sh
```


### Configuring LSP Servers

LSP servers are configured through a dedicated LSP configuration file. You can configure LSP servers at the user level or repository level:

**User-level configuration** (applies to all projects):
Edit `~/.copilot/lsp-config.json`

**Repository-level configuration** (applies to specific project):
Create `.github/lsp.json` in your repository root
```bash

# configure jdtls in ~/.copilot/lsp-config.json
cat > ".github/lsp.json" << 'LSP_EOF'
{
    "java": {
        "command": "jdtls",
        "args": [],
        "extensionToLanguage": {
            ".java": "java"
        },
        "transport": "stdio",
        "initializationOptions": {},
        "settings": {},
        "startupTimeout": 90000,
        "shutdownTimeout": 15000,
        "maxRestarts": 3
    }
}
LSP_EOF
```