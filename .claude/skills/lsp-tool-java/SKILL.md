---
name: lsp-tool-java
description: Accurate code navigation via LSP. Navigate code (definitions, references, implementations), search symbols, preview refactorings, and get file outlines.
---

# LSP Code Exploration for Java Repositories

## Prerequisites

Before using LSP operations, ensure:

1. **jdtls is installed** — Run `which jdtls` to verify. If missing, use the `configure-lsp-server` skill to install.
2. **LSP is configured** — Either `~/.copilot/lsp-config.json` (user-level) or `.github/lsp.json` (repo-level) must exist with the Java server entry.
3. **Java 17+** is available on PATH.

> **First-time startup**: jdtls may take 30–90 seconds to index a project (especially large Maven/Gradle projects). LSP operations may return incomplete results during this window.


## Core Rules

**Use LSP for ALL semantic Java code navigation.** Text search tools (`grep`, `glob`) should only be used for non-semantic tasks.

1. **For semantic navigation** (definitions, references, implementations, call hierarchy, type info) — **always use LSP**.
2. **To find a method in a file** — use `lsp documentSymbol` first, then `view` the relevant line range. Do NOT read the entire file.
3. **To find usages of a class/method** — use `lsp findReferences`, NOT grep.
4. **To find where something is defined** — use `lsp goToDefinition`, NOT grep/find.
5. **To find implementations of an interface** — use `lsp goToImplementation`.

### When text search IS appropriate

- Searching **non-Java files** (XML, YAML, properties, Dockerfiles, etc.)
- Searching for **string literals, comments, or log messages**
- Searching **build config** (pom.xml, build.gradle)
- **Fallback** when LSP is unavailable or not yet indexed


## Tool Selection

Prioritize LSP for semantic code navigation:

| Task | Text Search Tool | LSP Operation |
| --- | --- | --- |
| Find where something is defined | `grep` | `goToDefinition` |
| Search symbols across workspace | `grep -r` | `workspaceSymbol` |
| Find implementations of interface/type | `grep -r` | `goToImplementation` |
| Find what calls a function | `grep -r` | `incomingCalls` |
| Find what a function calls | `grep -r` | `outgoingCalls` |
| Find all usages of a symbol | `grep -r` | `findReferences` |
| List all symbols in a file | `view` whole file | `documentSymbol` |
| Get type info and documentation | `view` | `hover` |
| Rename a symbol across files | `sed` | `rename` |
| Get compiler errors and warnings | build output | `ide-get_diagnostics` |


## LSP Operations Reference

### goToDefinition

Jump to where a symbol (class, method, field, variable) is defined.

```
lsp goToDefinition <file_uri> <line> <character>
```

**Use when**: You see a method call or type reference and need to navigate to its source code.

**Example scenarios**:
- Click-through from `userService.findById(id)` → jumps to `UserService.findById()` implementation
- Navigate from `@Autowired private OrderRepository repo` → jumps to `OrderRepository` interface


### findReferences

Find all locations where a symbol is used across the workspace.

```
lsp findReferences <file_uri> <line> <character>
```

**Use when**: You need to understand the impact of changing a method, assess usage patterns, or find all callers.

**Example scenarios**:
- Before refactoring `UserService.createUser()`, find every call site
- Check if a deprecated method is still in use


### goToImplementation

Find concrete implementations of an interface or abstract method.

```
lsp goToImplementation <file_uri> <line> <character>
```

**Use when**: You have an interface/abstract class and need to find all implementing classes.

**Example scenarios**:
- From `PaymentProcessor` interface → find `StripePaymentProcessor`, `PayPalPaymentProcessor`
- From abstract `BaseRepository.save()` → find all concrete repository implementations


### workspaceSymbol

Search for symbols (classes, methods, fields) by name across the entire workspace.

```
lsp workspaceSymbol <query>
```

**Use when**: You know a symbol name (or partial name) but don't know which file it's in.

**Example scenarios**:
- Find `OrderController` without knowing its package
- Search for all classes containing `Service` in their name


### documentSymbol

List all symbols (classes, methods, fields, inner classes) defined in a single file.

```
lsp documentSymbol <file_uri>
```

**Use when**: You need an overview of a file's structure, or want to locate a specific method's line number before using `view`.

**Example scenarios**:
- Get the outline of a large `UserService.java` to find method line numbers
- Understand the structure of an unfamiliar class


### hover

Get type information, Javadoc, and documentation for a symbol at a specific position.

```
lsp hover <file_uri> <line> <character>
```

**Use when**: You need to understand a symbol's type, generic parameters, or read its documentation without navigating away.

**Example scenarios**:
- Check the return type of `repository.findAll()`
- Read Javadoc for a third-party library method


### incomingCalls / outgoingCalls

Trace the call hierarchy — find what calls a function (incoming) or what a function calls (outgoing).

```
lsp incomingCalls <file_uri> <line> <character>
lsp outgoingCalls <file_uri> <line> <character>
```

**Use when**: Tracing execution flow, understanding dependencies between methods, or debugging.

**Example scenarios**:
- Trace `OrderService.processOrder()` → find all controllers/services that invoke it
- Understand what external services `processOrder()` depends on


### rename

Semantically rename a symbol across the entire workspace (safe refactoring).

```
lsp rename <file_uri> <line> <character> <new_name>
```

**Use when**: Renaming a class, method, field, or variable — LSP handles all references, imports, and Javadoc.

> **Important**: Preview the changes before applying. Use `rename` instead of manual `sed`/find-replace to avoid breaking references.


## Workflow Patterns

### Pattern 1: Explore an unfamiliar class

```
1. lsp workspaceSymbol "UserService"          → find the file
2. lsp documentSymbol <file_uri>              → get method outline
3. view <file> <start_line>-<end_line>        → read specific methods
4. lsp goToDefinition on dependencies         → trace into called services
```

### Pattern 2: Trace a Spring MVC request flow

```
1. lsp workspaceSymbol "OrderController"      → find the controller
2. lsp documentSymbol <controller_uri>        → find endpoint methods
3. lsp goToDefinition on service calls        → navigate Controller → Service
4. lsp goToDefinition on repository calls     → navigate Service → Repository
5. lsp goToImplementation on Repository       → find JPA/custom implementation
```

### Pattern 3: Assess refactoring impact

```
1. lsp findReferences on the target method    → find all callers
2. lsp incomingCalls for call hierarchy        → understand call depth
3. For each caller: lsp hover to check types  → verify compatibility
4. lsp rename to safely rename                → or manual edit with full awareness
```

### Pattern 4: Debug a compilation error

```
1. ide-get_diagnostics <file_uri>             → get compiler errors/warnings
2. lsp hover on error location                → understand expected types
3. lsp goToDefinition on involved symbols     → check source definitions
4. Fix the issue, then re-check diagnostics
```

### Parallel Calls

When you need multiple independent pieces of information, batch LSP calls in a single turn:

```
# These can all be called in parallel:
lsp documentSymbol <file_a>
lsp documentSymbol <file_b>
lsp findReferences <file_c> <line> <char>
```


## Java-Specific Considerations

### Project Structure
- **Maven**: sources in `src/main/java`, tests in `src/test/java`, config in `src/main/resources`
- **Gradle**: same layout, but check `build.gradle` for custom source sets
- **Multi-module**: each module has its own `src/` — LSP handles cross-module navigation

### Common Gotchas
- **Lombok**: `@Data`, `@Builder`, etc. generate methods at compile time. LSP may not resolve generated getters/setters until the project is fully indexed. If `goToDefinition` fails on a Lombok-generated method, check the class annotations.
- **Generated sources**: Code generated by annotation processors (MapStruct, Dagger, etc.) lives in `target/generated-sources/`. LSP should index these, but they may lag behind source changes.
- **Spring proxies**: `@Transactional`, `@Async` methods are proxied at runtime. `goToImplementation` shows the source class, not the proxy.
- **Multi-module dependency**: If LSP cannot resolve cross-module references, the project may need a `mvn install` or `gradle build` first.

### Import Resolution
When LSP reports unresolved imports, check:
1. Is the dependency declared in `pom.xml` / `build.gradle`?
2. Has `mvn dependency:resolve` / `gradle dependencies` been run?
3. Is the JDK version compatible?


## Fallback Strategy

If LSP is not available or returns errors:

1. **Check LSP status**: Use `/lsp` command in interactive mode
2. **Check configuration**: Verify `~/.copilot/lsp-config.json` or `.github/lsp.json` exists
3. **Check jdtls**: Run `which jdtls` and `java -version`
4. **Wait for indexing**: Large projects may take 60–90s on first load
5. **Fall back to text search**: Use `grep` with Java-aware patterns as a last resort:
   - `grep -rn "class ClassName"` for class definitions
   - `grep -rn "void methodName"` for method definitions
   - Always use `--include="*.java"` or glob filter to limit scope
