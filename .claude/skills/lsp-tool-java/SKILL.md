---
name: lsp-tool-java
description: Accurate code navigation via LSP. Navigate code (definitions, references, implementations), search symbols, preview refactorings, and get file outlines.
---

# LSP Code Exploration for Java Repositories


## Overview RULES
**You MUST use the lsp tool for ALL Java code navigation.**

1. **NEVER use `grep`, `find`, or `glob` to search Java code.** Use `lsp` with `workspaceSymbol` or `findReferences` instead.
2. **NEVER read an entire Java file to find a method.** Use `lsp documentSymbol` first, then `view` the relevant section.
3. **To find where a method/class is used**, use `lsp findReferences` — NOT grep.
4. **To find where something is defined**, use `lsp goToDefinition` — NOT grep/find.
5. **To find implementations of an interface**, use `lsp goToImplementation`.

 
### Tool Selection

You SHOULD prioritize LSP commands for code navigation and analysis:

| Task | Basic Tool | Recommended LSP operation  |
| --- |  --- |  --- |
| To find where something is defined | `grep`, `read` | goToDefinition |
| To search symbols across workspace | `grep -r` | workspaceSymbol |
| To find implementations of an interface/type | `grep -r` | goToImplementation |
| To find what calls a function | `grep -r` | incomingCalls |
| To find what a function calls | `grep -r` | outgoingCalls |
| To find all usages of a symbol     | `grep -r` | findReferences |
| To list all symbols in a file | `read` | documentSymbol |
| To get type info and documentation | `read` | hover |
| To semantically rename a symbol across files | `sed` | rename |
