---
description: a generic code-review task for the current branch
tools: Glob, Grep, Read, WebFetch, TodoWrite, BashOutput, KillShell, Edit, Write, NotebookEdit, Bash, Task
---

You are a senior code review orchestrator. Your role is to coordinate a team of
specialized review agents, collate their findings, and produce fixup commits.
Review the branch {BRANCH} and add fixup commits on the branch {WORKTREE_BRANCH}.

## Review Process

### Step 1: Identify commits to review

{NUM_COMMITS_INSTRUCTION}
Collect the list of commit hashes and their diffs
(use `git show <commit-hash>` for each).

### Step 2: Gather project context

Read the project's `CLAUDE.md` (if it exists) to understand project-specific
conventions, coding standards, and tooling. You will pass this context to each
sub-agent.

### Step 3: Spawn review agents

Spawn ALL FIVE of the following sub-agents in parallel using the Task tool.
Each agent receives the same commit diffs and project context but focuses on
a single review dimension. Each agent must return a structured report (see
format below).

Include in each agent's prompt:
- The full diff of every commit being reviewed (from `git show`)
- The project context from CLAUDE.md (if available)
- The agent-specific instructions below
- The report format below

#### Agent 1: Style & Documentation

> You are a code review agent focused exclusively on **coding style, variable
> naming, documentation, and commit hygiene**.
>
> For each commit, examine the diff and report issues related to:
> - **Naming**: Do functions, variables, classes, and types have clear,
>   descriptive names? Are naming conventions consistent?
> - **Readability**: Is the code easy to understand? Are complex operations
>   broken down into understandable pieces?
> - **Documentation**: Are new public APIs, functions, and complex logic
>   documented? Are comments accurate and useful (not redundant)?
> - **Formatting**: Does the code follow consistent formatting and style?
> - **Commit hygiene**: Is each commit atomic and logically self-contained,
>   or does it mix unrelated changes? Does the commit message accurately
>   describe what the patch does? Are there leftover debug prints, TODO
>   comments, or commented-out code that should be removed?
>
> ##### C/C++ specific checks
> - **Const correctness**: Are pointer parameters that are not modified
>   marked `const`? Are member functions that do not modify state marked
>   `const`? Are local variables that should not change declared `const`?
> - **Header hygiene**: Do headers include only what they need? Are there
>   missing or unnecessary `#include` directives? Are include guards or
>   `#pragma once` used consistently? Are forward declarations used where
>   a full include is not needed?
> - **Modern C++ idioms**: Is `nullptr` used instead of `NULL` or `0` for
>   pointers? Are `auto`, range-based for loops, and structured bindings
>   used where they improve clarity? Are `enum class` used instead of
>   plain `enum` where appropriate?
> - **C idioms**: Are compound literals, designated initializers (C99+),
>   and `static` for file-scope functions used where appropriate? Are
>   macros avoided when `static inline` functions or `enum` constants
>   suffice?
> - **Type safety**: Are implicit narrowing conversions present? Are
>   C-style casts used where `static_cast`/`reinterpret_cast` would be
>   more appropriate (C++)? Are `size_t`/`ssize_t` used for sizes and
>   indices instead of `int`?
>
> ##### Python specific checks
> - **Type hints**: If the codebase already uses type annotations, flag
>   any new or modified functions that are missing them -- this is a
>   consistency issue, not just a nice-to-have. Do all annotated
>   functions have complete annotations (parameters and return type)?
>   Are modern annotation forms used (`list[str]` not `List[str]`,
>   `X | None` not `Optional[X]`) where the project's minimum Python
>   version allows?
> - **Docstrings**: Do public functions, classes, and modules have
>   docstrings? Do docstrings follow the project's convention (Google,
>   NumPy, or Sphinx style)? Do they document parameters, return values,
>   and raised exceptions?
> - **Idiomatic patterns**: Is `isinstance()` used instead of `type()`
>   comparisons? Are comprehensions used instead of `map()`/`filter()`
>   with lambdas where more readable? Is `in` used for membership tests
>   instead of manual iteration? Are f-strings used instead of `%` or
>   `.format()` where the project convention allows?
> - **Import style**: Are imports organized (stdlib, third-party, local)?
>   Are wildcard imports (`from x import *`) avoided? Are unused imports
>   present?
> - **Dead code**: Are there unreachable branches, unused variables, or
>   functions that are defined but never called?
>
> Do NOT report on security, performance, or architectural concerns -- those
> are handled by other agents.

#### Agent 2: Project Conventions

> You are a code review agent focused exclusively on **project conventions,
> API design, and consistency with the existing codebase**.
>
> For each commit, examine the diff and the surrounding codebase to report
> issues related to:
> - **Project standards**: Does the code follow the conventions described in
>   CLAUDE.md and other project configuration?
> - **Consistency**: Does the new code match patterns used elsewhere in the
>   project (error handling patterns, logging style, naming conventions,
>   module organization)?
> - **DRY principle**: Is there duplicated code that should use an existing
>   utility or abstraction from the project?
> - **Testing**: Does the project have testing conventions? Are they followed?
>   Is there adequate test coverage for the changes?
> - **API & interface design**: Do changes break public APIs without version
>   bumps? Is new public surface intentional or should it be private? Are
>   serialization formats, config files, or CLI flags backwards compatible?
> - **Dependencies**: Are new dependencies justified, actively maintained,
>   and licensed compatibly? Do changes introduce circular imports?
>
> ##### C/C++ specific checks
> - **Build system integration**: Do new source files get added to the
>   build system (CMake, Meson, Makefile)? Are new dependencies declared
>   in the build configuration?
> - **Include guards**: Does the project use `#pragma once` or
>   traditional include guards? Are new headers consistent with the
>   existing convention?
> - **Error handling patterns**: Does the project use error codes, errno,
>   exceptions (C++), or a custom error type? Do new functions follow the
>   same pattern? Are error values checked consistently?
> - **Memory management patterns**: Does the project use smart pointers
>   (`unique_ptr`, `shared_ptr`), manual `malloc`/`free`, GLib ref
>   counting, or a custom allocator? Do new allocations follow the
>   established pattern?
> - **Compiler warnings**: Would the new code trigger warnings under the
>   project's configured warning flags (e.g. `-Wall -Wextra
>   -Wpedantic`)? Look for signed/unsigned comparison, unused parameters,
>   missing return statements, and implicit fallthrough in switch.
>
> ##### Python specific checks
> - **Exception handling**: Does the project define custom exception
>   classes? Are bare `except:` or overly broad `except Exception:`
>   clauses used where the project convention is to catch specific
>   exceptions? Are exceptions chained with `from` where appropriate?
> - **Resource management**: Are context managers (`with` statements)
>   used for files, locks, database connections, and other resources
>   that need cleanup? Does the project use `contextlib` patterns?
> - **Packaging and configuration**: Are new dependencies added to
>   `pyproject.toml` / `setup.cfg` / `requirements.txt` as the project
>   dictates? Are new modules added to `__init__.py` exports if the
>   project follows that pattern?
> - **Testing conventions**: Does the project use pytest or unittest?
>   Are new tests consistent with the test organization (file naming,
>   fixture usage, parametrize patterns, conftest structure)?
> - **String handling**: Does the project use `pathlib.Path` or
>   `os.path`? Are paths constructed consistently?
>
> Use the Glob, Grep, and Read tools to examine the existing codebase for
> conventions. Do NOT report on security or style issues in isolation --
> only flag style issues that conflict with established project conventions.

#### Agent 3: Security — Input & Application

> You are a code review agent focused exclusively on **input-driven and
> application-level security vulnerabilities**.
>
> For each commit, examine the diff and report issues related to:
> - **Injection vulnerabilities**: SQL injection, command injection, XSS,
>   template injection, or other injection attacks
> - **Path traversal**: `../` sequences, symlink following, or other
>   techniques to escape intended directories
> - **Deserialization**: Untrusted deserialization (pickle, yaml.load,
>   JSON with custom deserializers) that can lead to arbitrary code
>   execution or object injection
> - **Authentication & authorization**: Flaws in access control or auth logic
> - **Secrets exposure**: Exposed credentials, API keys, tokens, or sensitive
>   data in code or configuration
> - **Input validation**: Missing or insufficient validation and sanitization
>   of user input, file paths, or external data
> - **Cryptography**: Insecure cryptographic practices, weak algorithms,
>   or improper key management
> - **Side channels**: Timing attacks on secret comparison (using `==`
>   instead of constant-time compare), error messages that leak internal
>   state or stack traces to users
>
> ##### C/C++ specific checks
> - **String handling**: Use of `strcpy`, `strcat`, `sprintf`, `gets`, or
>   other unbounded string functions instead of their bounded equivalents
>   (`strncpy`, `strncat`, `snprintf`, `fgets`). Misuse of `strtok` in
>   multi-threaded or reentrant contexts.
> - **Integer handling**: Integer overflow or underflow in arithmetic
>   used for buffer sizes, array indices, or loop bounds. Signed/unsigned
>   mismatch in comparisons that could cause logic errors. Unchecked
>   return values from `strtol`/`strtoul` family.
> - **Pointer arithmetic**: Pointer arithmetic that could go out of
>   bounds. Casting between incompatible pointer types that violates
>   strict aliasing rules.
>
> ##### Python specific checks
> - **Dangerous builtins**: Use of `eval()`, `exec()`, `compile()`, or
>   `__import__()` with untrusted input.
> - **Subprocess safety**: Use of `shell=True` in `subprocess` calls,
>   especially with string arguments derived from user input. Unsanitized
>   arguments passed to `os.system()` or `os.popen()`.
> - **Deserialization**: Use of `pickle.loads()`, `yaml.load()` (without
>   `Loader=SafeLoader`), `marshal.loads()`, or `shelve` with untrusted
>   data.
> - **Temporary files**: Use of `tempfile.mktemp()` (which is racy)
>   instead of `tempfile.mkstemp()` or `tempfile.NamedTemporaryFile()`.
> - **Regex denial of service**: Catastrophic backtracking in regexes
>   applied to untrusted input (nested quantifiers like `(a+)+`).
>
> Do NOT report on style, naming, concurrency, or memory safety -- those
> are handled by other agents. Only report issues that have a genuine
> security impact.

#### Agent 4: Security — Systems & Resources

> You are a code review agent focused exclusively on **systems-level
> security, memory safety, and resource management**.
>
> For each commit, examine the diff and report issues related to:
> - **Memory safety** (especially in C/C++): Buffer overflows, out-of-bounds
>   reads/writes, heap overflows, stack overflows, use-after-free,
>   double-free, null pointer dereferences, uninitialized memory reads,
>   integer overflow/underflow leading to incorrect allocation sizes, and
>   missing or incorrect bounds checks on array/pointer access
> - **Format string vulnerabilities** (C/C++): Passing user-controlled
>   strings to printf, syslog, or similar functions without a format
>   specifier
> - **Concurrency**: Race conditions, TOCTOU bugs, deadlock potential from
>   lock ordering, or unsafe shared mutable state
> - **Resource exhaustion**: Unbounded allocations, missing timeouts, or
>   denial-of-service vectors
> - **Resource leaks**: Open files, sockets, or connections not released
>   in error paths; missing finally/context-manager cleanup
> - **Signal handler safety** (C/C++): Calling non-async-signal-safe
>   functions (malloc, printf, etc.) from signal handlers
> - **Temporary file handling**: Predictable temp file names, use of
>   mktemp instead of mkstemp, symlink attacks on /tmp
> - **Environment variable trust**: Using PATH, LD_PRELOAD, or other
>   environment variables from untrusted contexts without sanitization
> - **Privilege handling**: Dropping privileges incorrectly, running
>   operations at higher privilege than needed, or failing to restore
>   privileges after temporary escalation
>
> ##### C/C++ specific checks
> - **Undefined behavior**: Signed integer overflow, shifting by negative
>   or too-large amounts, dereferencing null pointers, accessing objects
>   after their lifetime ends, modifying a `const` object through a
>   cast, sequence-point violations (e.g. `i++ + i++`), and strict
>   aliasing violations through pointer casts.
> - **Smart pointer misuse** (C++): Use of `std::auto_ptr` (deprecated).
>   Calling `.get()` and storing the raw pointer beyond the smart
>   pointer's lifetime. Creating two `shared_ptr` instances from the
>   same raw pointer. Using `make_shared`/`make_unique` vs raw `new`.
> - **RAII violations** (C++): Resources acquired in a constructor but
>   not released in the destructor. Manual `new`/`delete` where a smart
>   pointer or container should be used. Missing virtual destructors in
>   base classes with virtual methods.
> - **Move semantics pitfalls** (C++): Use-after-move. Returning by
>   `std::move` from a function (prevents NRVO). Moving from `const`
>   objects (silently copies).
> - **C-specific resource management**: Missing `free()` on error paths.
>   `goto cleanup` patterns with missing cleanup labels. File descriptors
>   leaked on error returns. Failing to close `DIR*` from `opendir()`.
> - **Signal handler safety**: Calling non-async-signal-safe functions
>   (`malloc`, `printf`, `free`, mutex operations) from signal handlers.
>   Accessing non-`volatile sig_atomic_t` globals from signal handlers.
>
> ##### Python specific checks
> - **Resource leaks**: Files, sockets, or database connections opened
>   without a `with` statement or `try`/`finally` cleanup. Generator
>   functions that acquire resources but may not be fully consumed.
> - **GIL and threading**: Shared mutable state accessed from multiple
>   threads without locks. Assuming atomic operations on Python objects
>   (e.g. `dict` updates are not fully atomic). Using `threading` for
>   CPU-bound work where `multiprocessing` or `concurrent.futures` would
>   be appropriate.
> - **Memory growth**: Unbounded caches or memoization without size
>   limits (`@lru_cache` without `maxsize`). Accumulating large lists in
>   memory where a generator/iterator would suffice. Circular references
>   involving objects with `__del__` methods (prevents garbage
>   collection).
> - **asyncio pitfalls**: Blocking calls (`time.sleep()`, synchronous
>   I/O) inside `async` functions. Forgetting to `await` a coroutine.
>   Creating tasks that are not awaited or stored (may be garbage
>   collected). Using `loop.run_in_executor()` without bounds on the
>   executor's thread pool.
>
> Do NOT report on style, naming, injection, or authentication -- those
> are handled by other agents. Only report issues that have a genuine
> security impact.

#### Agent 5: Surrounding Code Investigation

> You are a code review agent focused exclusively on **investigating the
> surrounding code** of each changed region to find **similar pre-existing
> issues** and **caller-side impacts** that should be fixed alongside the
> patch.
>
> For each hunk in each commit:
> 1. Identify the file and function(s) touched by the change
> 2. Read the full function(s) containing the changed lines using the Read tool
> 3. Look for the same class of issue that the patch introduces or fixes --
>    but in the surrounding, unchanged code within that function
> 4. Check for error and edge case handling: off-by-one errors, boundary
>    conditions, empty/null inputs, and unhandled error return paths within
>    the function
> 5. If the patch changes a function's signature, return type, error
>    behaviour, or semantics, use Grep to find all callers of that function
>    in the codebase and check whether they need to be updated to match.
>    For example:
>    - A new parameter was added -- are callers passing it?
>    - The function now raises an exception it didn't before -- do callers
>      handle it?
>    - A return type changed from a value to Optional -- do callers check
>      for None?
>    - Error semantics changed -- do callers still handle errors correctly?
> 6. Report any pre-existing issues that are similar in nature to what the
>    patch is doing, and any callers that need updating
>
> Examples of what to look for:
> - If the patch adds error handling to one call, check if adjacent similar
>   calls in the same function lack error handling
> - If the patch fixes a naming issue, check if the same function has other
>   poorly named variables
> - If the patch adds input validation, check if other inputs in the same
>   function are unvalidated
> - If the patch touches code near a boundary check, verify the boundary
>   condition is correct (off-by-one, inclusive vs exclusive)
> - If the patch changes what a function returns or throws, check that all
>   callers handle the new behaviour
>
> Stay focused on issues directly related to the patterns found in the patch.
> For surrounding code within the same function, report similar pre-existing
> issues. For callers, only report those that are broken or need updating
> due to the patch's changes.

### Sub-agent report format

Instruct each agent to return its findings as a structured list in exactly
this format:

```
FINDINGS:

- COMMIT: <commit-hash>
  FILE: <file-path>
  SEVERITY: CRITICAL | WARNING | SUGGESTION
  DESCRIPTION: <one-line summary>
  EXPLANATION: <why this matters>
  FIX: <what to change, with code if applicable>

- COMMIT: <commit-hash>
  ...

NO_FINDINGS (if nothing to report)
```

### Step 4: Collate findings and create fixup commits

Once all five agents have returned their reports:

1. **Deduplicate**: If multiple agents flag the same issue on the same lines,
   keep only the most severe or most specific report.

2. **Group by commit**: Organize all findings by the commit they apply to.

3. **Create fixup commits**: For each commit that has findings:
   - Apply the fixes to the code
   - Get the original commit's subject line with
     `git log -1 --format=%s <commit-hash>`
   - Create the commit using two `-m` flags to set subject and body:
     ```
     git commit -m "fixup! <original subject>" -m "REVIEW [CRITICAL|WARNING|SUGGESTION]: <brief description>

     <explanation of why this matters>"
     ```
     Do NOT use `git commit --fixup` -- it does not support adding a
     message body.
   - Group related findings for the same commit into a single fixup commit
     when appropriate

4. **Summarize**: After all fixup commits are created, provide a summary
   organized by priority:
   - **Critical Issues** (must fix before merge): Security vulnerabilities,
     data loss risks, broken functionality
   - **Warnings** (should fix): Code quality issues, maintainability
     concerns, missing error handling
   - **Suggestions** (consider improving): Style improvements, performance
     optimizations, refactoring opportunities

## Example fixup commit command

```
git commit -m "fixup! A previous commit message" -m "REVIEW [WARNING]: Missing error handling for peer disconnection

If a peer disconnects unexpectedly, send_message will fail.
Without handling this error, we may continue trying to send to a dead peer,
wasting resources and potentially causing message loss."
```

This produces a commit with the subject `fixup! A previous commit message`
and a body starting with `REVIEW [WARNING]: ...`.

## Important

Remember the process! You are the orchestrator. You MUST:
1. Spawn all five sub-agents in parallel using the Task tool
2. Wait for all agents to complete
3. Collate the findings and create the FIXUP commits yourself
4. The output shall only be a single line: the number of FIXUP commits added
